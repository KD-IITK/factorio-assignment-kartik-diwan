import json
import sys
import math

TOLERANCE = 1e-8

def deep_compare(a, b, path="root"):
    if type(a) != type(b):
        print(f"\nFAIL: Type mismatch at {path}")
        print(f"  Expected: {type(a)}")
        print(f"  Got: {type(b)}")
        return False

    if isinstance(a, dict):
        a_keys = sorted(list(a.keys()))
        b_keys = sorted(list(b.keys()))
        if a_keys != b_keys:
            print(f"\nFAIL: Key mismatch at {path}")
            print(f"  Expected keys: {a_keys}")
            print(f"  Got keys: {b_keys}")
            return False
        for key in a_keys:
            if not deep_compare(a[key], b[key], path=f"{path}.{key}"):
                return False
    
    elif isinstance(a, list):
        if len(a) != len(b):
            print(f"\nFAIL: List length mismatch at {path}: {len(a)} vs {len(b)}")
            return False
        
        a_sorted = a
        b_sorted = b

        try:
            if len(a) > 0 and isinstance(a[0], dict):
                if 'from' in a[0] and 'to' in a[0]:
                     a_sorted = sorted(a, key=lambda x: (x.get('from', ''), x.get('to', '')))
                     b_sorted = sorted(b, key=lambda x: (x.get('from', ''), x.get('to', '')))
                else:
                    a_sorted = sorted(a, key=lambda x: json.dumps(x, sort_keys=True))
                    b_sorted = sorted(b, key=lambda x: json.dumps(x, sort_keys=True))
            elif len(a) == 0 or isinstance(a[0], (str, int, float, bool)) or a[0] is None:
                a_sorted = sorted(a)
                b_sorted = sorted(b)
        except (TypeError, AttributeError):
            a_sorted = a
            b_sorted = b

        for i in range(len(a_sorted)):
            if not deep_compare(a_sorted[i], b_sorted[i], path=f"{path}[{i}]"):
                print(f"  (Mismatch occurred in list comparison at index {i})")
                return False
    
    elif isinstance(a, float):
        if not math.isclose(a, b, abs_tol=TOLERANCE):
            print(f"\nFAIL: Float mismatch at {path}")
            print(f"  Expected: {a}")
            print(f"  Got: {b}")
            return False

    else: 
        if a != b:
            print(f"\nFAIL: Value mismatch at {path}")
            print(f"  Expected: {a}")
            print(f"  Got: {b}")
            return False
            
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_json.py <expected.json> <actual.json>")
        sys.exit(1)

    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            expected_data = json.load(f)
    except Exception as e:
        print(f"Error loading expected file {sys.argv[1]}: {e}")
        sys.exit(1)

    try:
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            actual_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing actual file {sys.argv[2]}: {e}")
        print("--- File Content ---")
        try:
            with open(sys.argv[2], 'r', encoding='utf-8') as f_read:
                print(f_read.read())
        except Exception:
            print("[Could not read actual file content]")
        print("--------------------")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading actual file {sys.argv[2]}: {e}")
        sys.exit(1)


    if deep_compare(expected_data, actual_data):
        sys.exit(0)
    else:
        sys.exit(1)
        