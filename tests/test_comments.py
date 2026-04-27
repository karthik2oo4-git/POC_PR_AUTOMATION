from pr_validation_agent.comments import render_success_comment


def test_success_comment_contains_marker_and_ready_to_merge_message():
    body = render_success_comment(marker="<!-- marker -->")
    assert "<!-- marker -->" in body
    assert "All configured setup and unit-test checks passed." in body
    assert "required status check" in body
