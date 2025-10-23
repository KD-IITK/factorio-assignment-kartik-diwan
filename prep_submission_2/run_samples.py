import subprocess
import sys
import os

# ANSI escape codes for colors
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_RESET = "\033[0m"

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    test_scripts = [
        os.path.join(root_dir, "tests", "test_factory.py"),
        os.path.join(root_dir, "tests", "test_belts.py")
    ]
    
    print(f"{COLOR_YELLOW}Starting all test suites...{COLOR_RESET}\n")
    
    failed_suites = []

    for script_path in test_scripts:
        if not os.path.exists(script_path):
            print(f"{COLOR_RED}ERROR: Test script not found: {script_path}{COLOR_RESET}")
            failed_suites.append(script_path)
            continue
        
        print(f"--- Running {os.path.basename(script_path)} ---")
        
        try:
            # Run the test script using the same Python executable
            result = subprocess.run(
                [sys.executable, script_path],
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"{COLOR_RED}--- {os.path.basename(script_path)} FAILED ---{COLOR_RESET}\n")
                failed_suites.append(os.path.basename(script_path))
            else:
                print(f"{COLOR_GREEN}--- {os.path.basename(script_path)} PASSED ---{COLOR_RESET}\n")
                
        except Exception as e:
            print(f"{COLOR_RED}FATAL: An error occurred while running {script_path}: {e}{COLOR_RESET}\n")
            failed_suites.append(os.path.basename(script_path))

    print("========================================")
    print("Overall Test Summary:")
    
    if not failed_suites:
        print(f"{COLOR_GREEN}All test suites passed!{COLOR_RESET}")
        sys.exit(0)
    else:
        print(f"{COLOR_RED}One or more test suites failed:{COLOR_RESET}")
        for suite in failed_suites:
            print(f"  - {suite}")
        sys.exit(1)

if __name__ == "__main__":
    main()