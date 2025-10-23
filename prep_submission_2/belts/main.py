"""
This tool solves the problem by transforming it into a standard
max-flow problem on a modified graph and running one max-flow
calculation.
"""

import sys
import json
import collections
try:
    import networkx as nx
except ImportError:
    sys.stderr.write("Error: The 'networkx' library is required. Please install it with 'pip install networkx'\n")
    print(json.dumps({"status": "error", "message": "Missing required library: networkx"}, indent=2))
    sys.exit(1)

TOLERANCE = 1e-9

def solve_belts(data):
    # solves the flow network problem
    try:
        G, build_data = build_transformed_graph(data)
    except Exception as e:
        return {"status": "error", "message": f"Failed to build graph: {e}"}

    total_expected_flow = build_data['total_expected_flow']
    
    if total_expected_flow < TOLERANCE:
        return format_success(
            {}, 
            data, 
            build_data['original_edges'], 
            0.0 # total_supply
        )

    try:
        max_flow, flow_dict = nx.maximum_flow(
            G, 's_super', 't_super', capacity='capacity'
        )
    except nx.NetworkXUnbounded:
        return {"status": "error", "message": "Flow problem is unbounded. Check for missing capacities."}
    except nx.NetworkXError as e:
         return {"status": "error", "message": f"Max-flow algorithm failed: {e}"}


    if max_flow < total_expected_flow - TOLERANCE:
        return format_infeasible(
            G, 
            max_flow, 
            total_expected_flow, 
            build_data
        )
    else:
        return format_success(
            flow_dict, 
            data, 
            build_data['original_edges'], 
            build_data['total_supply']
        )


def build_transformed_graph(data):
    """
    Builds a new graph (G) that represents the flow-with-demands
    problem as a standard max-flow problem.
    """
    G = nx.DiGraph()
    
    sources = data.get('sources', {})
    sink = data.get('sink')
    edges = data.get('edges', [])
    node_caps = data.get('node_caps', {})

    if not sink:
        raise ValueError("A 'sink' node must be specified.")

    lo_demands = collections.defaultdict(float)
    
    mapped_in = {}  # v -> v_in or v
    mapped_out = {} # v -> v_out or v
    split_nodes = {} # v -> (v_in, v_out)
    original_edges = [] # ( (u,v), (u_map, v_map), lo )
    
    all_nodes = set(sources.keys()) | {sink}
    for edge in edges:
        all_nodes.add(edge['from'])
        all_nodes.add(edge['to'])
    all_nodes.update(node_caps.keys())

    for n in all_nodes:
        mapped_in[n] = n
        mapped_out[n] = n

    for node, cap in node_caps.items():
        if node == sink or node in sources:
            continue
        
        v_in = f"{node}_in"
        v_out = f"{node}_out"
        
        G.add_edge(v_in, v_out, capacity=cap)
        
        mapped_in[node] = v_in
        mapped_out[node] = v_out
        split_nodes[node] = (v_in, v_out)
        
    for edge in edges:
        u, v = edge['from'], edge['to']
        lo, hi = edge.get('lower', 0.0), edge.get('upper', float('inf'))
        
        if hi < lo - TOLERANCE:
            raise ValueError(f"Edge ({u}->{v}) has upper bound {hi} < lower bound {lo}")

        u_mapped = mapped_out[u]
        v_mapped = mapped_in[v]
        
        cap = hi - lo
        if cap < TOLERANCE:
            cap = 0.0 # Avoid negative capacity if hi == lo
        
        G.add_edge(u_mapped, v_mapped, capacity=cap)
        
        original_edges.append(((u, v), (u_mapped, v_mapped), lo))
        
        lo_demands[u] -= lo
        lo_demands[v] += lo

    G.add_nodes_from(['s_super', 't_super'])
    total_lo_demand = 0.0
    total_supply = 0.0
    
    for v, d in lo_demands.items():
        if d > TOLERANCE:
            G.add_edge('s_super', mapped_in[v], capacity=d)
            total_lo_demand += d
        elif d < -TOLERANCE:
            G.add_edge(mapped_out[v], 't_super', capacity=-d)
            
    for s, supply in sources.items():
        G.add_edge('s_super', mapped_out[s], capacity=supply)
        total_supply += supply
        
    sink_cap = total_supply if total_supply > TOLERANCE else float('inf')
    G.add_edge(mapped_in[sink], 't_super', capacity=sink_cap)

    total_expected_flow = total_lo_demand + total_supply
            
    build_data = {
        'total_expected_flow': total_expected_flow,
        'total_supply': total_supply,
        'original_edges': original_edges,
        'split_nodes': split_nodes,
        'node_map': {n: n for n in all_nodes}
    }
    
    # Create reverse map for infeasibility report
    build_data['node_map']['s_super'] = 's_super'
    build_data['node_map']['t_super'] = 't_super'
    for v, (v_in, v_out) in split_nodes.items():
        build_data['node_map'][v_in] = v
        build_data['node_map'][v_out] = v

    return G, build_data

def format_success(flow_dict, data, original_edges, total_supply):
    # Reconstructs the original flows from the transformed flow solution
    final_flows = []
    
    def get_flow(u, v):
        if u in flow_dict and v in flow_dict[u]:
            return flow_dict[u][v]
        return 0.0

    for (u, v), (u_mapped, v_mapped), lo in original_edges:
        flow = get_flow(u_mapped, v_mapped) + lo
        
        if flow > TOLERANCE:
            final_flows.append({
                "from": u,
                "to": v,
                "flow": flow
            })

    return {
        "status": "ok",
        "max_flow_per_min": total_supply,
        "flows": final_flows
    }

def format_infeasible(G, max_flow, total_expected_flow, build_data):
    # Generates the infeasibility certificate using the min cut
    deficit_val = total_expected_flow - max_flow
    
    try:
        cut_value, (reachable, unreachable) = nx.minimum_cut(
            G, 's_super', 't_super', capacity='capacity'
        )
    except nx.NetworkXError:
        reachable = {'s_super'}
        unreachable = set(G.nodes()) - reachable
    
    node_map = build_data['node_map']
    
    cut_reachable_original = set()
    
    for n in reachable:
        if n in node_map and n != 's_super' and n != 't_super':
            cut_reachable_original.add(node_map[n])

    tight_nodes = []
    tight_edges = []
    
    for v, (v_in, v_out) in build_data['split_nodes'].items():
        if v_in in reachable and v_out in unreachable:
            tight_nodes.append(v)
            
    for (u, v), (u_mapped, v_mapped), lo in build_data['original_edges']:
        if u_mapped in reachable and v_mapped in unreachable:
            tight_edges.append({
                "from": u,
                "to": v
            })

    return {
        "status": "infeasible",
        "cut_reachable": sorted(list(cut_reachable_original)),
        "deficit": {
            "demand_balance": deficit_val,
            "tight_nodes": sorted(list(set(tight_nodes))),
            "tight_edges": tight_edges 
        }
    }


def main():
    """
    Main entry point. Reads from stdin, solves, prints to stdout.
    """
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        output = {"status": "error", "message": f"Invalid JSON input: {e}"}
        print(json.dumps(output, indent=2))
        sys.exit(1)
        
    output = solve_belts(data)
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()