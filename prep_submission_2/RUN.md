# How to Run
This project requires **Python 3** and the following libraries:

- `numpy`
- `scipy`
- `networkx`

You can install them using pip:

```sh
pip install numpy scipy networkx
```


## Running the Solvers

Both **factory** and **belts** are command-line tools that read a single JSON object from **stdin** and write a single JSON object to **stdout**.

### Factory

```bash
# Run the factory solver
Get-Content [path to input] | python3 factory/main.py | Set-Content [path to output]

# Example
Get-Content input.json | python3 factory/main.py | Set-Content output.json
```

---

### Belts

```bash
# Run the belts solver
Get-Content [path to input] | python3 belts/main.py | Set-Content [path to output]

# Example 
Get-Content input.json | python3 belts/main.py | Set-Content output.json
```


## Running the Test Suites

A **master test runner script** is provided to execute all test cases.  
You must pass it the exact commands to run your **factory** and **belts** executables.

The commands must be wrapped in quotes.

```bash
# Run all test suites (factory and belts)
python3 run_samples.py "python3 factory/main.py" "python3 belts/main.py"
```

This script will execute `tests/test_factory.py` and `tests/test_belts.py` passing the respective command to each. It will provide a final summary.

You can also rin the test suites individually by passing the command directly:
```bash
# Run only the factory tests
python3 tests/test_factory.py "python3 factory/main.py"

# Run only the belts test
python3 tests/test_belts.py "python3 belts/main.py"
```