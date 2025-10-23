"""
Two-phase optimization:
1.  Phase 1: Try to solve for the requested target_rate while minimizing
    total machines used.
2.  Phase 2: If Phase 1 is infeasible, solve for the *maximum feasible*
    target_rate and report bottlenecks.
"""

import sys
import json

try:
    import numpy as np
    from scipy.optimize import linprog
except ImportError:
    sys.stderr.write("Error: 'numpy' and 'scipy' libraries are required. Please install them (e.g., 'pip install numpy scipy')\n")
    print(json.dumps({"status": "error", "message": "Missing required libraries: numpy, scipy"}, indent=2))
    sys.exit(1)


TOLERANCE = 1e-9

def solve_factory(data):
    # Prepares and solves the factory production linear program.
    try:
        prepared_data = prepare_problem(data)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to prepare problem: {e}"
        }

    # Phase 1: try to solve for the requested target rate
    res_p1 = linprog(
        c=prepared_data['c_objective'],
        A_ub=prepared_data['A_ub'],
        b_ub=prepared_data['b_ub'],
        A_eq=prepared_data['A_eq'],
        b_eq=prepared_data['b_eq'],
        bounds=prepared_data['bounds'],
        method='highs'
    )

    if res_p1.success:
        # Phase 1 succeeded
        output = format_success_output(res_p1.x, prepared_data)
        return output
    else:
        # Phase 1 failed (infeasible), proceed to phase 2
        try:
            res_p2, bottlenecks = solve_phase2_max_rate(prepared_data)
            
            if res_p2.success:
                max_rate = res_p2.x[-1]
                # Handle near-zero negative rates from solver noise
                if max_rate < TOLERANCE:
                    max_rate = 0.0
                
                output = {
                    "status": "infeasible",
                    "max_feasible_target_per_min": max_rate,
                    "bottleneck_hint": bottlenecks
                }
                return output
            else:
                # Phase 2 also failed
                return {
                    "status": "infeasible",
                    "max_feasible_target_per_min": 0.0,
                    "bottleneck_hint": ["Problem is fundamentally infeasible"]
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed during Phase 2 optimization: {e}"
            }

def prepare_problem(data):
    """
    Parses the input JSON and builds the numpy matrices for the LP solver.
    """
    recipes = data.get('recipes', {})
    machines = data.get('machines', {})
    modules = data.get('modules', {})
    limits = data.get('limits', {})
    target = data.get('target', {})

    target_item = target.get('item')
    target_rate = target.get('rate_per_min', 0)
    if not target_item:
        raise ValueError("Missing 'target.item' in input")

    raw_supply = limits.get('raw_supply_per_min', {})
    machine_caps = limits.get('max_machines', {})

    # Create deterministic orderings
    recipe_list = sorted(recipes.keys())
    machine_list = sorted(machines.keys())
    
    all_items = set()
    for r_data in recipes.values():
        all_items.update(r_data.get('in', {}).keys())
        all_items.update(r_data.get('out', {}).keys())
    
    if target_item not in all_items:
        all_items.add(target_item)
        
    raw_items = set(raw_supply.keys())
    intermediate_items = all_items - raw_items - {target_item}

    item_list = sorted(list(all_items))
    item_idx = {item: i for i, item in enumerate(item_list)}
    raw_list_sorted = sorted(list(raw_items))
    eq_items_sorted = sorted(list(intermediate_items))

    N_recipes = len(recipe_list)
    N_items = len(item_list)
    N_machines = len(machine_list)
    N_raw = len(raw_list_sorted)
    N_intermediates = len(eq_items_sorted)
    
    c_objective = np.zeros(N_recipes)
    
    bounds = [(0, None)] * N_recipes

    eq_constraint_items = eq_items_sorted + [target_item]
    N_eq = N_intermediates + 1
    A_eq = np.zeros((N_eq, N_recipes))
    b_eq = np.zeros(N_eq)
    
    N_ub = N_machines + 2 * N_raw
    A_ub = np.zeros((N_ub, N_recipes))
    b_ub = np.zeros(N_ub)

    
    recipe_calcs = {} # Cache for formatting output
    machine_idx = {name: i for i, name in enumerate(machine_list)}

    for j, r_name in enumerate(recipe_list):
        r = recipes[r_name]
        m_type = r.get('machine')
        if m_type not in machines:
            raise ValueError(f"Recipe '{r_name}' uses unknown machine '{m_type}'")

        m_data = machines[m_type]
        mod_data = modules.get(m_type, {})

        base_speed = m_data.get('crafts_per_min', 0)
        speed_mod = mod_data.get('speed', 0)
        prod_mod = mod_data.get('prod', 0)
        time_s = r.get('time_s', 1.0)
        
        if time_s <= 0:
            raise ValueError(f"Recipe '{r_name}' time_s must be positive")

        eff_crafts = base_speed * (1 + speed_mod) * 60.0 / time_s

        m_cost = 1.0 / eff_crafts if eff_crafts > 0 else np.inf
        
        # Add to objective function
        c_objective[j] = m_cost
        
        # Add to machine cap constraints (A_ub)
        m_idx = machine_idx[m_type]
        A_ub[m_idx, j] = m_cost
        
        # Calculate net item flow for this recipe
        net_flow_vector = np.zeros(N_items)
        for item, amt in r.get('in', {}).items():
            if item in item_idx:
                net_flow_vector[item_idx[item]] -= amt
        
        for item, amt in r.get('out', {}).items():
            if item in item_idx:
                net_flow_vector[item_idx[item]] += amt * (1.0 + prod_mod)
        
        recipe_calcs[r_name] = {
            'm_cost': m_cost,
            'm_type': m_type,
            'net_flow': net_flow_vector
        }

    for i, m_name in enumerate(machine_list):
        b_ub[i] = machine_caps.get(m_name, np.inf)

    for i, item in enumerate(eq_constraint_items):
        item_i = item_idx[item]
        for j, r_name in enumerate(recipe_list):
            A_eq[i, j] = recipe_calcs[r_name]['net_flow'][item_i]
        
        if item == target_item:
            b_eq[i] = target_rate

    raw_ub_row_offset = N_machines
    for i, item in enumerate(raw_list_sorted):
        item_i = item_idx[item]
        row1 = raw_ub_row_offset + i       # net_flow <= 0
        row2 = raw_ub_row_offset + N_raw + i # -net_flow <= cap
        
        b_ub[row1] = 0
        b_ub[row2] = raw_supply.get(item, np.inf)
        
        for j, r_name in enumerate(recipe_list):
            net = recipe_calcs[r_name]['net_flow'][item_i]
            A_ub[row1, j] = net
            A_ub[row2, j] = -net

    # Store matrices for phase 2 and output formatting
    return {
        'data': data,
        'recipe_list': recipe_list,
        'machine_list': machine_list,
        'raw_list_sorted': raw_list_sorted,
        'item_idx': item_idx,
        'recipe_calcs': recipe_calcs,
        'eq_constraint_items': eq_constraint_items,
        'target_item': target_item,
        'c_objective': c_objective,
        'A_ub': A_ub,
        'b_ub': b_ub,
        'A_eq': A_eq,
        'b_eq': b_eq,
        'bounds': bounds,
        # Store components of A_ub/b_ub for bottleneck analysid
        'ub_machines_rows': (0, N_machines),
        'b_machines': b_ub[0:N_machines],
        'ub_raw_neg_flow_rows': (N_machines + N_raw, N_machines + 2 * N_raw),
        'b_raw_caps': b_ub[N_machines + N_raw : N_machines + 2 * N_raw]
    }

def solve_phase2_max_rate(prep_data):
    # Phase 2, maximize the target_rate
    N_recipes = len(prep_data['recipe_list'])
    
    N_vars_p2 = N_recipes + 1
    
    c_p2 = np.zeros(N_vars_p2)
    c_p2[-1] = -1.0
    
    bounds_p2 = prep_data['bounds'] + [(0, None)]
    
    N_eq, N_r = prep_data['A_eq'].shape
    
    # Add a new column of zeros for the y_target_rate variable
    A_eq_p2 = np.hstack([prep_data['A_eq'], np.zeros((N_eq, 1))])
    
    # Find the target item's row
    target_row_idx = prep_data['eq_constraint_items'].index(prep_data['target_item'])
    
    # Set the y_target_rate coefficient to -1
    A_eq_p2[target_row_idx, -1] = -1.0
    
    # Set all b_eq to 0
    b_eq_p2 = np.zeros(N_eq)
    
    N_ub, N_r = prep_data['A_ub'].shape
    A_ub_p2 = np.hstack([prep_data['A_ub'], np.zeros((N_ub, 1))])
    b_ub_p2 = prep_data['b_ub']
    
    # Solve the maximization problem
    res_p2 = linprog(
        c=c_p2,
        A_ub=A_ub_p2,
        b_ub=b_ub_p2,
        A_eq=A_eq_p2,
        b_eq=b_eq_p2,
        bounds=bounds_p2,
        method='highs'
    )
    
    bottlenecks = []
    if res_p2.success:
        x_sol_p2 = res_p2.x[:-1] # Recipe crafts
        
        # Check machine caps
        m_start, m_end = prep_data['ub_machines_rows']
        machine_usage = prep_data['A_ub'][m_start:m_end, :] @ x_sol_p2
        machine_caps = prep_data['b_machines']
        for i, m_name in enumerate(prep_data['machine_list']):
            if machine_caps[i] < np.inf and machine_usage[i] >= machine_caps[i] - TOLERANCE:
                bottlenecks.append(f"{m_name} cap")
                
        # Check raw supply caps
        r_start, r_end = prep_data['ub_raw_neg_flow_rows']

        raw_consumption = prep_data['A_ub'][r_start:r_end, :] @ x_sol_p2
        raw_caps = prep_data['b_raw_caps']
        for i, r_name in enumerate(prep_data['raw_list_sorted']):
            if raw_caps[i] < np.inf and raw_consumption[i] >= raw_caps[i] - TOLERANCE:
                bottlenecks.append(f"{r_name} supply")

    # If max rate is 0 and no other bottlenecks, it's fundamental
    if res_p2.success and res_p2.x[-1] < TOLERANCE and not bottlenecks:
        bottlenecks = ["Problem is fundamentally infeasible"]

    return res_p2, sorted(list(set(bottlenecks)))

def format_success_output(x, prep_data):
    per_recipe_crafts_per_min = {}
    per_machine_counts = {m_name: 0.0 for m_name in prep_data['machine_list']}
    raw_consumption_per_min = {r_name: 0.0 for r_name in prep_data['raw_list_sorted']}

    # Calculate recipe crafts and machine usage
    for i, r_name in enumerate(prep_data['recipe_list']):
        crafts = x[i]
        # Handle solver noise near zero
        if crafts < TOLERANCE:
            crafts = 0.0
        
        per_recipe_crafts_per_min[r_name] = crafts
        
        if crafts > 0:
            calc = prep_data['recipe_calcs'][r_name]
            per_machine_counts[calc['m_type']] += calc['m_cost'] * crafts
            
    # Calculate raw consumption
    for i, r_name in enumerate(prep_data['raw_list_sorted']):
        consumption = 0.0
        raw_idx = prep_data['item_idx'][r_name]
        for j, r_recipe_name in enumerate(prep_data['recipe_list']):
            if x[j] > 0:
                net_flow = prep_data['recipe_calcs'][r_recipe_name]['net_flow'][raw_idx]
                consumption -= net_flow * x[j] # Consumption is -net_flow
        
        if consumption < TOLERANCE:
            consumption = 0.0
        raw_consumption_per_min[r_name] = consumption
        
    return {
        "status": "ok",
        "per_recipe_crafts_per_min": per_recipe_crafts_per_min,
        "per_machine_counts": per_machine_counts,
        "raw_consumption_per_min": raw_consumption_per_min
    }

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        output = {"status": "error", "message": f"Invalid JSON input: {e}"}
        print(json.dumps(output, indent=2))
        sys.exit(1)
        
    output = solve_factory(data)
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()