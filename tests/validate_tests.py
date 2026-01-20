#!/usr/bin/env python3
"""
Validate test structure and count tests without running them.

This script analyzes the test files to verify:
- Test file structure is correct
- Test classes and methods are properly defined
- Expected number of tests are present
- Fixtures are properly defined in conftest.py
"""

import ast
import sys
from pathlib import Path


def count_tests_in_file(filepath):
    """Count test functions and classes in a Python file."""
    with open(filepath, 'r') as f:
        tree = ast.parse(f.read())

    test_count = 0
    test_classes = []
    test_functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
            test_classes.append(node.name)
            # Count test methods in class
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                    test_count += 1
                    test_functions.append(f"{node.name}::{item.name}")
        elif isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            # Top-level test function
            test_count += 1
            test_functions.append(node.name)

    return test_count, test_classes, test_functions


def count_fixtures_in_file(filepath):
    """Count pytest fixtures in conftest.py."""
    with open(filepath, 'r') as f:
        content = f.read()
        tree = ast.parse(content)

    fixtures = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check if function has @pytest.fixture decorator
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == 'fixture':
                    fixtures.append(node.name)
                elif isinstance(decorator, ast.Attribute) and decorator.attr == 'fixture':
                    fixtures.append(node.name)

    return fixtures


def main():
    """Validate test structure."""
    tests_dir = Path(__file__).parent

    print("=" * 70)
    print("WarDragon Analytics API Test Validation")
    print("=" * 70)
    print()

    # Validate test_api.py
    test_api_path = tests_dir / 'test_api.py'
    if not test_api_path.exists():
        print("ERROR: test_api.py not found!")
        sys.exit(1)

    print(f"Analyzing {test_api_path}...")
    test_count, test_classes, test_functions = count_tests_in_file(test_api_path)

    print(f"\nTest Classes: {len(test_classes)}")
    for cls in test_classes:
        print(f"  - {cls}")

    print(f"\nTotal Test Methods/Functions: {test_count}")
    print(f"\nExpected: ~49 tests")
    print(f"Found: {test_count} tests")

    if test_count >= 45:
        print("✅ Test count looks good!")
    else:
        print("⚠️  Expected more tests")

    # Validate conftest.py
    conftest_path = tests_dir / 'conftest.py'
    if not conftest_path.exists():
        print("\nERROR: conftest.py not found!")
        sys.exit(1)

    print(f"\n\nAnalyzing {conftest_path}...")
    fixtures = count_fixtures_in_file(conftest_path)

    print(f"\nPytest Fixtures: {len(fixtures)}")
    api_fixtures = [f for f in fixtures if 'api' in f.lower() or 'asyncpg' in f.lower() or 'client' in f.lower()]
    print(f"API-related Fixtures: {len(api_fixtures)}")
    for fixture in api_fixtures:
        print(f"  - {fixture}")

    # Check for key fixtures
    expected_fixtures = [
        'mock_asyncpg_connection',
        'mock_asyncpg_pool',
        'client_with_mocked_db',
        'api_sample_kits',
        'api_sample_drones',
        'api_sample_signals'
    ]

    print(f"\n\nChecking for expected API fixtures:")
    all_found = True
    for expected in expected_fixtures:
        if expected in fixtures:
            print(f"  ✅ {expected}")
        else:
            print(f"  ❌ {expected} - NOT FOUND")
            all_found = False

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Test file: {'✅ FOUND' if test_api_path.exists() else '❌ MISSING'}")
    print(f"Conftest file: {'✅ FOUND' if conftest_path.exists() else '❌ MISSING'}")
    print(f"Test count: {test_count} ({'✅ GOOD' if test_count >= 45 else '⚠️ LOW'})")
    print(f"Fixtures: {len(fixtures)} total, {len(api_fixtures)} API-related")
    print(f"Required fixtures: {'✅ ALL FOUND' if all_found else '❌ SOME MISSING'}")

    print("\n" + "=" * 70)
    print("Test Structure Validation: ", end="")

    if test_api_path.exists() and conftest_path.exists() and test_count >= 45 and all_found:
        print("✅ PASSED")
        print("=" * 70)
        print("\nTo run the tests, you'll need to install dependencies:")
        print("  pip install -r tests/requirements-test.txt")
        print("  # or use Docker to run tests in an isolated environment")
        print("\nThen run:")
        print("  pytest tests/test_api.py -v")
        return 0
    else:
        print("❌ FAILED")
        print("=" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(main())