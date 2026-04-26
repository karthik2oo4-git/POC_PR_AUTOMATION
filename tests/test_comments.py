from pr_validation_agent.comments import render_success_comment
from pr_validation_agent.models import AnalysisResponse, SummaryAnalysis


def test_success_comment_contains_marker_and_summary():
    body = render_success_comment(
        marker="<!-- marker -->",
        files_changed=["src/app.py"],
        new_functions=[],
        modified_functions=[],
        analysis=AnalysisResponse(
            summary=SummaryAnalysis(high_level_summary="Adds validation.", risk_insights=[], notes=[])
        ),
    )
    assert "<!-- marker -->" in body
    assert "Adds validation." in body
    assert "src/app.py" in body
