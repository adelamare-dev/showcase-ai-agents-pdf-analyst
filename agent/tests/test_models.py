from langchain_mistralai import ChatMistralAI

from src import dynamic_agent, pdf_tools
from src.models import (
    AGENT_MODEL,
    EXTRACTOR_MODEL,
    REQUEST_TIMEOUT_S,
    RENDER_MODEL,
    chat_model,
)


def test_chat_model_pins_mistral_params():
    m = chat_model(RENDER_MODEL)
    assert isinstance(m, ChatMistralAI)
    assert m.model == "ministral-8b-2512"
    assert m.temperature == 0
    assert m.max_retries == 1
    assert REQUEST_TIMEOUT_S == 30
    assert m.timeout == REQUEST_TIMEOUT_S


def test_agent_model_is_ministral_3b():
    assert AGENT_MODEL == "ministral-3b-2512"


def test_call_sites_use_expected_models():
    assert dynamic_agent._RENDER_MODEL.model == "ministral-8b-2512"
    assert pdf_tools._EXTRACTOR.model == "ministral-3b-2512"


def test_no_latest_alias():
    for model_id in (AGENT_MODEL, EXTRACTOR_MODEL, RENDER_MODEL):
        assert "latest" not in model_id
