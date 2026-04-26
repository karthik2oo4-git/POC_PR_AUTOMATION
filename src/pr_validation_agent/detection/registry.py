from __future__ import annotations

from pr_validation_agent.config import AppConfig
from pr_validation_agent.detection.base import FunctionDetector
from pr_validation_agent.detection.js_ts import JavaScriptTypeScriptFunctionDetector
from pr_validation_agent.detection.python import PythonFunctionDetector


def build_detectors(config: AppConfig) -> list[FunctionDetector]:
    detectors: list[FunctionDetector] = []
    python_config = config.languages.get("python")
    if python_config is None or python_config.enabled:
        detectors.append(PythonFunctionDetector())
    js_config = config.languages.get("javascript")
    if js_config is not None and js_config.enabled:
        detectors.append(JavaScriptTypeScriptFunctionDetector())
    return detectors
