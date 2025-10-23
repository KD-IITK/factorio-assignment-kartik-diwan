import json
import sys
import subprocess
import os

COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_RESET = "\033[0m"

script_dir = os.path.dirname(os.path.abspath(__file__))

TEMP_INPUT = os.path.join(script_dir, "temp_factory_input.json")
TEMP_EXPECTED = os.path.join(script_dir, "temp_factory_expected.json")
TEMP_ACTUAL = os.path.join(script_dir, "temp_factory_actual.json")

def main():
    print("Starting factory test runner (Python)...")
    
    test_cases_file = os.path.join(script_dir, "factory_test_cases.json")
    script_to_test = os.path.join(script_dir, "..", "factory", "main.py")
    compare_script = os.path.join(script_dir, "compare_json.py")
    
    for f in [test_cases_file, script_to_test, compare_script]:
        if not os.path.exists(f):
            print(f"{COLOR_RED}FATAL: Required file '{f}' not found.{COLOR_RESET}")
            print("Please make sure all files are in the correct locations.")
            sys.exit(1)
            
    try:
        with open(test_cases_file, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{COLOR_RED}FATAL: Could not parse {test_cases_file}: {e}{COLOR_RESET}")
        sys.exit(1)
        
    total_tests = len(test_cases)
    passed_count = 0
    failed_count = 0

    for test in test_cases:
        test_id = test.get("id", "Unnamed Test")
        print(f"Running test: {test_id} ... ", end="", flush=True)

        try:
            with open(TEMP_INPUT, 'w', encoding='utf-8') as f:
                json.dump(test["input"], f, indent=2)

            with open(TEMP_EXPECTED, 'w', encoding='utf-8') as f:
                json.dump(test["expected_output"], f, indent=2)

            with open(TEMP_INPUT, 'r', encoding='utf-8') as stdin_file:
                with open(TEMP_ACTUAL, 'w', encoding='utf-8') as stdout_file:
                    run_result = subprocess.run(
                        [sys.executable, script_to_test],
                        stdin=stdin_file,
                        stdout=stdout_file,
                        stderr=subprocess.PIPE,
                        timeout=5, 
                        text=True,
                        encoding='utf-8'
                    )
            
            if run_result.returncode != 0:
                print(f"{COLOR_RED}FAIL (Script Error){COLOR_RESET}")
                print(f"  '{script_to_test}' exited with code {run_result.returncode}")
                print(f"  STDERR:\n{run_result.stderr}")
                failed_count += 1
                continue 

            compare_result = subprocess.run(
                [sys.executable, compare_script, TEMP_EXPECTED, TEMP_ACTUAL],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )

            if compare_result.returncode == 0:
                print(f"{COLOR_GREEN}PASS{COLOR_RESET}")
                passed_count += 1
            else:
                print(f"{COLOR_RED}FAIL (Output Mismatch){COLOR_RESET}")
                print(compare_result.stdout.strip())
                failed_count += 1
        
        except subprocess.TimeoutExpired:
            print(f"{COLOR_RED}FAIL (Timeout){COLOR_RESET}")
            print("  Test case took longer than 5 seconds.")
            failed_count += 1
        except Exception as e:
            print(f"{COLOR_RED}FAIL (Runner Error){COLOR_RESET}")
            print(f"  An unexpected error occurred: {e}")
            failed_count += 1

    print("----------------------------------------")
    print("Factory Test Summary:")
    print(f"{COLOR_GREEN}Passed: {passed_count}{COLOR_RESET}")
    print(f"{COLOR_RED}Failed: {failed_count}{COLOR_RESET}")
    print(f"Total: {total_tests}")

    for f in [TEMP_INPUT, TEMP_EXPECTED, TEMP_ACTUAL]:
        if os.path.exists(f):
            os.remove(f)

    if failed_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()