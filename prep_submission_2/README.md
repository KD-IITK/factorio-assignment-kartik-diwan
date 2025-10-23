This document details the modeling choices and implementation strategies for the `factory` and `belts` solvers.

## Factory Steady State

The factory problem is modeled as a standard Linear Programming problem and solved using `scipy.optimize.linprog(method='highs')`. The variables in the LP are the `crafts_per_min` for each recipe.

### 1. Modeling Choices

* **Item Balances (Conservation):**
    * An equality constraint matrix (`A_eq`) is constructed where each row represents a non-raw item (intermediate or target).
    * Each column `j` in a row `i` represents the *net production* of item `i` by recipe `j`.
    * `net = (output * (1 + prod_mod)) - input`
    * The right-hand side (`b_eq`) is `0` for all intermediates (enforcing steady-state balance) and `target_rate` for the target item.

* **Raw Consumption:**
    * Raw item constraints are handled in the inequality matrix (`A_ub`).
    * For each raw item, two constraints are added:
        1.  `net_flow <= 0`: Ensures raw items are only consumed (or balanced at zero), never produced.
        2.  `-net_flow <= raw_cap`: Ensures the total consumption (`-net_flow`) does not exceed the available supply.

* **Machine Capacity:**
    * Machine caps are also added to the inequality matrix (`A_ub`).
    * First, the *machine cost* (machines per craft/min) is calculated for each recipe `r`:
        * `eff_crafts_per_min(r) = base_speed * (1 + speed_mod) * 60 / time_s(r)`
        * `machine_cost(r) = 1.0 / eff_crafts_per_min(r)`
    * For each machine type `m`, a constraint is added:
        * `SUM(x_r * machine_cost(r) FOR all r using m) <= max_machines[m]`

* **Module Application:**
    * Modules are applied *per-machine-type* during the `prepare_problem` phase.
    * `speed` modifiers are used to calculate the `eff_crafts_per_min` for all recipes using that machine.
    * `prod` modifiers are applied directly to the `output` values when building the item balance (conservation) matrix.

* **Cycles & Byproducts:**
    * These are handled naturally by the LP formulation. A cycle (e.g., A -> B -> A) or a byproduct is just another set of intermediate items. By setting their corresponding rows in `b_eq` to `0`, the solver is forced to find a steady state where their production and consumption are perfectly balanced.

* **Objective Function (Tie-breaking):**
    * The primary objective is feasibility. The secondary objective is to minimize total machines.
    * This is implemented in the `c_objective` vector, which is set to `machine_cost(r)` for each recipe `r`.
    * `minimize: SUM(x_r * machine_cost(r))`
    * When `linprog` solves Phase 1, it finds a solution that *both* meets the `target_rate` and minimizes the total machine cost. This correctly implements the tie-breaking as a single-phase optimization.

* **Infeasibility Detection:**
    * The solver follows a two-phase approach:
    * **Phase 1:** Attempts to solve the problem as described above. If `res_p1.success` is `False`, the requested `target_rate` is infeasible.
    * **Phase 2:** If Phase 1 fails, a new LP is formulated to *maximize* the target rate. This is done by:
        1.  Adding a new variable `y_target_rate` to the problem.
        2.  Changing the objective to `minimize: -y_target_rate`.
        3.  Modifying the target item's balance constraint to `net_flow(target) - y_target_rate = 0`.
    * The result of this LP is the `max_feasible_target_per_min`.
    * **Bottleneck Hint:** After a successful Phase 2, the solution vector `x` is checked against the original inequality constraints (`A_ub`). Any machine cap or raw supply cap that is met (within `TOLERANCE`) is reported as a bottleneck.

---

## Belts with Bounds and Node Caps

The belts problem is modeled as a maximum flow problem with demands (due to lower bounds) and node capacities. It is solved by transforming the graph into a standard max-flow problem and using `networkx.maximum_flow`.

### 1. Modeling Choices

* **Transformation Strategy:**
    * The problem is transformed into a single max-flow problem on a graph `G` with a super-source `s_super` and a super-sink `t_super`.
    * Feasibility is determined by checking if the resulting `max_flow` from `s_super` to `t_super` is equal to the total *expected* flow.
    * `total_expected_flow = total_supply + total_lower_bound_demands`

* **Node Capacity (Splitting):**
    * Handled first in `build_transformed_graph`.
    * Any capped node `v` (that is not a source or sink) is split into `v_in` and `v_out`.
    * An edge `(v_in, v_out)` is added to `G` with `capacity = cap(v)`.
    * All original edges `(u, v)` are remapped to `(u_mapped, v_in)`.
    * All original edges `(v, w)` are remapped to `(v_out, w_mapped)`.
    * Sources, the sink, and uncapped nodes are not split (`v_in = v_out = v`).

* **Lower Bounds Transformation:**
    * For each original edge `(u, v)` with bounds `[lo, hi]`:
        1.  An edge `(u_mapped, v_mapped)` is added to `G` with `capacity = hi - lo`.
        2.  A "demand" is accumulated at each node: `lo_demands[v] += lo` and `lo_demands[u] -= lo`.

* **Feasibility Check (Connecting Super-Nodes):**
    * The `lo_demands` and original `sources` are connected to the super-nodes:
    1.  **Original Sources:** For each source `s` with `supply`, an edge `(s_super, s_mapped)` is added with `capacity = supply`.
    2.  **Lower Bound Demands:** For each node `v` with a net positive demand (`d = lo_demands[v] > 0`), an edge `(s_super, v_mapped_in)` is added with `capacity = d`.
    3.  **Lower Bound Supplies:** For each node `v` with a net negative demand (`s = -lo_demands[v] > 0`), an edge `(v_mapped_out, t_super)` is added with `capacity = s`.
    4.  **Final Sink:** The original `sink` is connected via `(sink_mapped_in, t_super)` with `capacity = total_supply` (or infinity if `total_supply` is 0, to allow satisfying lower bounds).
    * The `nx.maximum_flow(G, 's_super', 't_super')` is computed.
    * The flow is **feasible** if and only if `max_flow >= total_expected_flow - TOLERANCE`.

* **Infeasibility Certificate (Min-Cut):**
    * If the flow is infeasible, `format_infeasible` is called.
    * It computes the `nx.minimum_cut(G, 's_super', 't_super')`. This partitions the nodes into `reachable` (R, from `s_super`) and `unreachable` (U).
    * `cut_reachable`: The set of *original* node names corresponding to nodes in the `reachable` set (excluding super-nodes).
    * `deficit`: The exact amount of flow that could not be sent: `total_expected_flow - max_flow`.
    * `tight_nodes`: Original nodes `v` that were split, where `v_in` is in `R` and `v_out` is in `U`.
    * `tight_edges`: Original edges `(u, v)` whose *transformed* edge `(u_mapped, v_mapped)` crosses the cut (from `R` to `U`).

### 2. Numeric Approach & Determinism

* **Tolerances:** A global `TOLERANCE = 1e-9` is used for all floating-point comparisons, including feasibility checks and rounding near-zero flows in the output.
* **Solver:** `factory` uses `scipy.optimize.linprog(method='highs')`. `belts` uses `networkx.maximum_flow`, which typically defaults to a preflow-push algorithm (like `nx.algorithms.flow.preflow_push`).
* **Determinism:**
    * The `highs` solver is deterministic.
    * The `networkx` max-flow algorithm is deterministic.
    * To ensure deterministic JSON output, sorted lists are used when building matrices (`factory`) and when reporting infeasibility results (`belts`, e.g., `sorted(list(cut_reachable_original))`).
    * The JSON output is written with `indent=2` for consistent formatting.

### 3. Failure Modes & Edge Cases

* **Invalid JSON:** Both `main()` functions wrap `json.load(sys.stdin)` in a `try...except` block and will output a valid error JSON.
* **Missing Libraries:** Both scripts check for their required non-standard libraries (`numpy`/`scipy` for factory, `networkx` for belts) on import. If missing, they write an error to `stderr` and print a valid error JSON to `stdout`.
* **Infeasible Inputs:**
    * *Factory:* Handled by the Phase 1 / Phase 2 LP approach. A fundamentally infeasible problem (e.g., target item cannot be produced) will result in `max_feasible_target_per_min: 0.0`.
    * *Belts:* Handled by the `max_flow < total_expected_flow` check, which generates a min-cut certificate.
* **Trivial Inputs (Belts):** If `total_expected_flow` is 0, the problem is trivially feasible and returns an empty flow list.
* **Unbounded (Belts):** If an edge has `upper: inf` (default) and `lower: 0`, and is part of a path with no other caps, `networkx` may raise `NetworkXUnbounded`. This is caught and reported as a solver error.