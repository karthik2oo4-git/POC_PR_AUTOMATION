from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model


load_dotenv()


def build_chat_model():
    model = os.getenv("PR_VALIDATION_MODEL", "openai:gpt-4.1-mini")
    temperature = float(os.getenv("PR_VALIDATION_TEMPERATURE", "0"))

    return init_chat_model(model, temperature=temperature)
