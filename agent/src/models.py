"""Single home for model identifiers and client parameters.

Every Mistral client in the agent is built here so IDs and limits are changed
in one place instead of being scattered across the call sites.

Model IDs are dated snapshots, never a `-latest` alias: an alias can move to a
new model under our feet and change tool-calling behaviour without any code
change on our side.

Retries and timeout are deliberately tight (one retry, 45 s): a rendering call
that is going to fail should fail fast so the user is told, instead of
watching a spinner for minutes behind several silent retries.
"""

from __future__ import annotations

from langchain_mistralai import ChatMistralAI

AGENT_MODEL = "mistral-small-2603"
EXTRACTOR_MODEL = "mistral-small-2603"
RENDER_MODEL = "mistral-large-2512"

REQUEST_TIMEOUT_S = 45
MAX_RETRIES = 1


def chat_model(model: str) -> ChatMistralAI:
    """Build a deterministic Mistral chat client with the shared limits."""
    return ChatMistralAI(
        model=model,
        temperature=0,
        max_retries=MAX_RETRIES,
        timeout=REQUEST_TIMEOUT_S,
    )
