# Test Selection Strategy - Technical Documentation

## Overview

This document explains the intelligent test selection strategy implemented in the PR validation system. The strategy ensures **test integrity** while supporting **new tests in PRs**.

## Problem Statement

### Original Approach (Simple Copy)
The original implementation copied ALL test files from the base branch, which had limitations:
- ❌ New tests in PRs couldn't be added
- ❌ Developers couldn't contribute test improvements
- ❌ Test coverage couldn't grow through PRs

### New Approach (Intelligent Selection)
The new implementation uses set theory to select tests intelligently:
- ✅ Base tests are always the source of truth
- ✅ New tests from PRs are allowed and executed
- ✅ Modified/deleted base tests are ignored (base version runs)
- ✅ Test integrity is maintained

## Mathematical Model

### Definitions

Let:
- **A** = set of test cases from base branch
- **B** = set of test cases from PR (head branch)
- **N** = B − A (new tests introduced in PR)

### Test Selection Logic

```
IF N is empty:
    final_tests = A
ELSE:
    final_tests = A ∪ N
```

### Test Identifier

A test is uniquely identified by:
```python
TestIdentifier(file_path, test_name)
```

Where:
- `file_path`: Relative path from repo root (e.g., "tests/test_calc.py")
- `test_name`: Function or method name (e.g., "test_add" or "TestCalculator::test_add")

Two tests are considered **the same** if both file_path AND test_name match.

## Implementation Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    TestSelector                              │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  1. get_base_tests(base_ref) → Set[TestIdentifier]│    │
│  │     - Checkout base branch                          │    │
│  │     - Discover all tests                            │    │
│  │     - Return to original state                      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  2. get_pr_tests() → Set[TestIdentifier]           │    │
│  │     - Discover tests in current PR branch           │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  3. compute_new_tests(A, B) → Set[TestIdentifier]  │    │
│  │     - Return N = B - A                              │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  4. build_final_test_set(A, N) → Set[TestIdentifier]│   │
│  │     - If N empty: return A                          │    │
│  │     - Else: return A ∪ N                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  5. prepare_test_environment(base_ref, final_tests) │    │
│  │     - Create temp directory                         │    │
│  │     - Copy base test files for tests in A           │    │
│  │     - Copy PR test files for tests in N             │    │
│  │     - Return temp directory path                    │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Test Discovery

Uses Python AST parsing to extract test identifiers:

```python
class TestDiscovery:
    def extract_test_functions(file_path: Path) -> list[str]:
        # Parse Python file
        # Find functions starting with "test_"
        # Find test methods in classes starting with "Test"
        # Return list of test names
```

## Execution Flow

### Step-by-Step Process

```
1. PR Created/Updated
   ↓
2. Checkout PR branch (HEAD)
   ↓
3. Discover Base Tests (A)
   - Temporarily checkout base branch
   - Parse all test files
   - Extract test identifiers
   - Return to PR branch
   ↓
4. Discover PR Tests (B)
   - Parse all test files in PR
   - Extract test identifiers
   ↓
5. Compute New Tests (N = B - A)
   - Set difference operation
   ↓
6. Build Final Test Set
   - If N empty: final = A
   - Else: final = A ∪ N
   ↓
7. Prepare Test Environment
   - Create temp directory
   - For each test in final set:
     * If test in A: copy from base branch
     * If test in N: copy from PR branch
   ↓
8. Run Tests
   - Execute pytest on temp directory
   - All base tests run (integrity maintained)
   - All new tests run (innovation allowed)
   ↓
9. Report Results
   - Success: All tests passed
   - Failure: Show which tests failed
```

## Edge Cases Handled

### 1. Modified Test in PR

**Scenario:**
```
Base: test_add(2, 3) expects 5
PR:   test_add(2, 3) expects 6  (modified)
```

**Behavior:**
- Test is in both A and B
- N = B - A = {} (empty, not considered new)
- Final set uses base version
- PR modification is ignored

**Result:** ✅ Base test runs, catches bug if PR code is wrong

### 2. Deleted Test in PR

**Scenario:**
```
Base: test_add, test_subtract
PR:   test_add (deleted test_subtract)
```

**Behavior:**
- A = {test_add, test_subtract}
- B = {test_add}
- N = B - A = {} (empty)
- Final = A = {test_add, test_subtract}

**Result:** ✅ Both tests run, deletion is ignored

### 3. New Test in PR

**Scenario:**
```
Base: test_add, test_subtract
PR:   test_add, test_subtract, test_multiply (new)
```

**Behavior:**
- A = {test_add, test_subtract}
- B = {test_add, test_subtract, test_multiply}
- N = B - A = {test_multiply}
- Final = A ∪ N = {test_add, test_subtract, test_multiply}

**Result:** ✅ All three tests run (base + new)

### 4. Renamed Test

**Scenario:**
```
Base: test_addition
PR:   test_add (renamed from test_addition)
```

**Behavior:**
- A = {test_addition}
- B = {test_add}
- N = B - A = {test_add} (treated as new)
- Final = A ∪ N = {test_addition, test_add}

**Result:** ✅ Both tests run (old name from base, new name from PR)

### 5. New Test File

**Scenario:**
```
Base: tests/test_calc.py
PR:   tests/test_calc.py, tests/test_advanced.py (new file)
```

**Behavior:**
- All tests in test_advanced.py are in N
- Final set includes base tests + new file tests
- New file is copied from PR branch

**Result:** ✅ All tests run

### 6. No Tests in PR

**Scenario:**
```
Base: test_add, test_subtract
PR:   (no test directory)
```

**Behavior:**
- A = {test_add, test_subtract}
- B = {} (empty)
- N = B - A = {} (empty)
- Final = A

**Result:** ✅ Base tests still run

## Code Examples

### Example 1: Basic Usage

```python
from pathlib import Path
from pr_validation_agent.test_selector import TestSelector

# Initialize
selector = TestSelector(
    repo_root=Path("/path/to/repo"),
    test_paths=["tests/"]
)

# Get base tests
base_tests = selector.get_base_tests("main")
print(f"Base tests: {len(base_tests)}")

# Get PR tests
pr_tests = selector.get_pr_tests()
print(f"PR tests: {len(pr_tests)}")

# Compute new tests
new_tests = selector.compute_new_tests(base_tests, pr_tests)
print(f"New tests: {len(new_tests)}")

# Build final set
final_tests = selector.build_final_test_set(base_tests, new_tests)
print(f"Final tests: {len(final_tests)}")

# Prepare environment
test_dir = selector.prepare_test_environment("main", final_tests)
print(f"Test directory: {test_dir}")
```

### Example 2: Test Identifier

```python
from pr_validation_agent.test_selector import TestIdentifier

# Create identifiers
test1 = TestIdentifier("tests/test_calc.py", "test_add")
test2 = TestIdentifier("tests/test_calc.py", "test_add")
test3 = TestIdentifier("tests/test_calc.py", "test_subtract")

# Equality
assert test1 == test2  # Same file, same function
assert test1 != test3  # Same file, different function

# Use in sets
tests = {test1, test2, test3}
assert len(tests) == 2  # test1 and test2 are duplicates
```

## Benefits

### 1. Test Integrity
- ✅ Base tests cannot be modified in PRs
- ✅ Base tests cannot be deleted in PRs
- ✅ Test coverage is maintained

### 2. Innovation Support
- ✅ New tests can be added in PRs
- ✅ Test coverage can grow
- ✅ Developers can contribute tests

### 3. Security
- ✅ Prevents test tampering
- ✅ Prevents hiding bugs by modifying tests
- ✅ Ensures consistent validation

### 4. Flexibility
- ✅ Supports multiple test directories
- ✅ Works with any pytest-compatible tests
- ✅ Handles edge cases gracefully

## Configuration

### Test Path Detection

The system automatically detects test paths from the test command:

```yaml
tests:
  command: "pytest tests/"  # Detects "tests/" as test path
```

Multiple paths:
```yaml
tests:
  command: "pytest tests/ integration/"  # Detects both paths
```

Default fallback:
```
If no paths detected: ["tests/", "test/"]
```

## Logging and Debugging

The system provides detailed logging:

```
Discovering tests from base branch...
Found 15 tests in base branch

Discovering tests from PR branch...
Found 17 tests in PR branch

Detected 2 new tests in PR

New tests in PR:
  + tests/test_calc.py::test_multiply
  + tests/test_advanced.py::test_complex

Final test set: 17 tests

Preparing test environment...
Test directory prepared: /tmp/pr_validation_tests_abc123

Running 17 tests...
```

## Performance Considerations

### Optimization Strategies

1. **AST Parsing**: Fast, no test execution needed
2. **Set Operations**: O(n) complexity for test comparison
3. **Selective File Copy**: Only copies needed test files
4. **Temporary Directory**: Isolated, no workspace pollution

### Typical Performance

- Test discovery: < 1 second for 100 tests
- Set operations: < 0.1 seconds
- File preparation: < 2 seconds for 50 test files
- Total overhead: < 5 seconds

## Troubleshooting

### Issue: Tests not discovered

**Cause**: Test files don't match pytest patterns

**Solution**: Ensure files are named `test_*.py` or `*_test.py`

### Issue: New tests not running

**Cause**: Test identifiers don't match

**Solution**: Check test function names start with `test_`

### Issue: Base tests not found

**Cause**: Base branch doesn't have test directory

**Solution**: Ensure base branch has tests in configured paths

## Summary

The intelligent test selection strategy provides:

- **Security**: Base tests cannot be tampered with
- **Flexibility**: New tests can be added
- **Correctness**: All relevant tests run
- **Performance**: Minimal overhead
- **Maintainability**: Clean, modular code

**Key Rule**: Merge is allowed ONLY IF all base tests pass AND all new PR tests pass (if any).