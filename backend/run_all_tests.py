#!/usr/bin/env python3
"""Run all offline tests. Usage: cd backend && source venv/bin/activate && python run_all_tests.py"""

import subprocess
import sys


def main() -> int:
    scripts = [
        "tests/test_assignment_bills.py",
        "tests/test_edge_cases.py",
        "tests/test_scenario_bills.py",
    ]
    for script in scripts:
        print(f"\n=== {script} ===")
        result = subprocess.run([sys.executable, script], check=False)
        if result.returncode != 0:
            return result.returncode
    print("\n=== ALL OFFLINE TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
