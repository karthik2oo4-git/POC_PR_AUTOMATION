from pr_validation_agent.detection.base import SourceSnapshot
from pr_validation_agent.detection.python import PythonFunctionDetector


def test_python_detector_extracts_functions_and_methods():
    source = """
def top_level(a):
    return a

class Widget:
    def render(self):
        return "ok"
"""
    symbols = PythonFunctionDetector().extract(SourceSnapshot("app.py", source))
    assert [symbol.qualified_name for symbol in symbols] == ["top_level", "Widget.render"]
