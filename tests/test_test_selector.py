"""Tests for the test selection logic."""

from pathlib import Path
from pr_validation_agent.test_selector import TestIdentifier, TestSelector


def test_test_identifier_equality():
    """Test that TestIdentifier equality works correctly."""
    test1 = TestIdentifier("tests/test_calc.py", "test_add")
    test2 = TestIdentifier("tests/test_calc.py", "test_add")
    test3 = TestIdentifier("tests/test_calc.py", "test_subtract")
    
    assert test1 == test2
    assert test1 != test3
    assert hash(test1) == hash(test2)
    assert hash(test1) != hash(test3)


def test_compute_new_tests():
    """Test computing new tests (N = B - A)."""
    base_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
        TestIdentifier("tests/test_calc.py", "test_subtract"),
    }
    
    pr_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
        TestIdentifier("tests/test_calc.py", "test_subtract"),
        TestIdentifier("tests/test_calc.py", "test_multiply"),  # New test
    }
    
    selector = TestSelector(Path("."), ["tests/"])
    new_tests = selector.compute_new_tests(base_tests, pr_tests)
    
    assert len(new_tests) == 1
    assert TestIdentifier("tests/test_calc.py", "test_multiply") in new_tests


def test_build_final_test_set_no_new_tests():
    """Test final test set when no new tests (should return only base tests)."""
    base_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
        TestIdentifier("tests/test_calc.py", "test_subtract"),
    }
    
    new_tests = set()
    
    selector = TestSelector(Path("."), ["tests/"])
    final_tests = selector.build_final_test_set(base_tests, new_tests)
    
    assert final_tests == base_tests
    assert len(final_tests) == 2


def test_build_final_test_set_with_new_tests():
    """Test final test set with new tests (should return A ∪ N)."""
    base_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
        TestIdentifier("tests/test_calc.py", "test_subtract"),
    }
    
    new_tests = {
        TestIdentifier("tests/test_calc.py", "test_multiply"),
    }
    
    selector = TestSelector(Path("."), ["tests/"])
    final_tests = selector.build_final_test_set(base_tests, new_tests)
    
    assert len(final_tests) == 3
    assert TestIdentifier("tests/test_calc.py", "test_add") in final_tests
    assert TestIdentifier("tests/test_calc.py", "test_subtract") in final_tests
    assert TestIdentifier("tests/test_calc.py", "test_multiply") in final_tests


def test_modified_test_ignored():
    """Test that modified tests in PR are ignored (base version used)."""
    base_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
    }
    
    # PR has same test (possibly modified)
    pr_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
    }
    
    selector = TestSelector(Path("."), ["tests/"])
    new_tests = selector.compute_new_tests(base_tests, pr_tests)
    
    # No new tests - modified test is not considered "new"
    assert len(new_tests) == 0
    
    final_tests = selector.build_final_test_set(base_tests, new_tests)
    
    # Final set contains only base test
    assert len(final_tests) == 1
    assert TestIdentifier("tests/test_calc.py", "test_add") in final_tests


def test_deleted_test_still_runs():
    """Test that deleted tests in PR still run (from base)."""
    base_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
        TestIdentifier("tests/test_calc.py", "test_subtract"),
    }
    
    # PR deleted test_subtract
    pr_tests = {
        TestIdentifier("tests/test_calc.py", "test_add"),
    }
    
    selector = TestSelector(Path("."), ["tests/"])
    new_tests = selector.compute_new_tests(base_tests, pr_tests)
    
    # No new tests
    assert len(new_tests) == 0
    
    final_tests = selector.build_final_test_set(base_tests, new_tests)
    
    # Final set still contains both base tests (deletion ignored)
    assert len(final_tests) == 2
    assert TestIdentifier("tests/test_calc.py", "test_add") in final_tests
    assert TestIdentifier("tests/test_calc.py", "test_subtract") in final_tests

# Made with Bob
