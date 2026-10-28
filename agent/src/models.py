"""Single home for model identifiers and client parameters.

Every Mistral client in the agent is built here so IDs and limits are changed
in one place instead of being scattered across the call sites.

Model IDs are dated snapshots, never a `-latest` alias: an alias can move to a
new model under our feet and change tool-calling behaviour without any code
change on our side.

The demo runs on Mistral's free tier, so each role uses the cheapest dated
model that supports function calling: Ministral 3 3B (`ministral-3b-2512`,
$0.10/M tokens in and out, 1.3M tokens/min on the free tier). If a role proves
unreliable in a live run, escalate only that role one step: `ministral-8b-2512`
($0.15/M), then `ministral-14b-2512` ($0.20/M). `mistral-small-2603` and
`mistral-large-2512` are not usable on this account (0 requests/min, respectively
not in the plan).

The render role has been escalated once: on 3B, follow-up questions came back
as nested component trees that failed validation twice in a row, so the user
only got the text fallback. 8B returns the flat component list.

Retries and timeout are deliberately tight (one retry, 45 s): a rendering call
that is going to fail should fail fast so the user is told, instead of
watching a spinner for minutes behind several silent retries.
"""

from __future__ import annotations

from langchain_mistralai import ChatMistralAI

AGENT_MODEL = "ministral-3b-2512"
EXTRACTOR_MODEL = "ministral-3b-2512"
RENDER_MODEL = "ministral-8b-2512"

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
