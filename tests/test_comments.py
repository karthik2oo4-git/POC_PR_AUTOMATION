from pr_validation_agent.comments import render_success_comment
from pr_validation_agent.test_selector import TestIdentifier


def test_success_comment_contains_marker_and_ready_to_merge_message():
    body = render_success_comment(marker="<!-- marker -->")
    assert "<!-- marker -->" in body
    assert "All configured setup and unit-test checks passed." in body
    assert "required status check" in body


def test_success_comment_with_new_tests():
    new_tests = {
        TestIdentifier("tests/test_calc.py", "test_multiply"),
        TestIdentifier("tests/test_advanced.py", "test_complex"),
    }
    body = render_success_comment(
        marker="<!-- marker -->",
        base_test_count=10,
        new_tests=new_tests
    )
    assert "<!-- marker -->" in body
    assert "Base branch tests: 10" in body
    assert "New tests in PR: 2" in body
    assert "Total tests executed: 12" in body
    assert "test_multiply" in body
    assert "test_complex" in body


def test_success_comment_without_new_tests():
    body = render_success_comment(
        marker="<!-- marker -->",
        base_test_count=10,
        new_tests=set()
    )
    assert "<!-- marker -->" in body
    assert "Base branch tests: 10" in body
    assert "Total tests executed: 10" in body
    assert "No new tests added in this PR" in body
