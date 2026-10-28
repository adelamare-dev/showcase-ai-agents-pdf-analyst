"""Replay sample PDFs through the real agent graphs and measure each LLM call.

Usage, from `agent/`:

    uv run python scripts/measure.py --dry-run
    uv run python scripts/measure.py > report.md

Every live turn calls Mistral and consumes tokens: a run is limited to
`MAX_TURNS` turns. Progress goes to stderr, the Markdown report to stdout.

The PDF text is extracted with pypdf and cut at the cap read from
`src/lib/pdf.ts`, with the same rule as the browser, so the agent receives the
input it gets in production. pypdf and pdf.js do not extract identical text:
the character counts are close, not equal.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from pypdf import PdfReader

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = AGENT_DIR.parent
PDF_TS = REPO_DIR / "src" / "lib" / "pdf.ts"
SAMPLES_DIR = REPO_DIR / "public" / "samples"

MAX_TURNS = 12

# Route, sample file under `public/samples/`, question. These mirror the
# one-click samples of `src/lib/samples.ts`.
SCENARIOS: list[tuple[str, str, str]] = [
    (
        "fixed",
        "insee-comptes-nationaux-t2-2026.pdf",
        "Génère le tableau de bord de ce document.",
    ),
    (
        "dynamic",
        "insee-comptes-nationaux-t2-2026.pdf",
        "Montre l'évolution trimestrielle du PIB.",
    ),
    (
        "dynamic",
        "arxiv-2610.07204-spear.pdf",
        "Résume ce document en cinq points.",
    ),
]

ROUTES = ("fixed", "dynamic")
MAIN_ROLE = "agent"


# --- Text preparation (pure helpers) ------------------------------------------


def read_text_cap(pdf_ts: Path = PDF_TS) -> int:
    """Read `PDF_TEXT_MAX_CHARS` from the front-end source: one constant only."""
    source = pdf_ts.read_text(encoding="utf-8")
    match = re.search(r"PDF_TEXT_MAX_CHARS\s*=\s*([\d_]+)\s*;", source)
    if match is None:
        raise RuntimeError(f"PDF_TEXT_MAX_CHARS not found in {pdf_ts}")
    return int(match.group(1).replace("_", ""))


def cap_pages(pages: list[str], max_chars: int) -> tuple[str, int, bool]:
    """Keep whole pages joined by newlines while the total fits `max_chars`.

    Same rule as `capPages` in `src/lib/pdf.ts`. If page 1 alone is too long it
    is cut at `max_chars`. Returns (text, kept pages, truncated).
    """
    text = ""
    kept = 0
    for page in pages:
        candidate = page if kept == 0 else f"{text}\n{page}"
        if len(candidate) > max_chars:
            break
        text = candidate
        kept += 1
    if kept == 0 and pages:
        return pages[0][:max_chars], 1, True
    return text, kept, kept < len(pages)


def prepare_text(pages: list[str], max_chars: int) -> str:
    """Cap the pages and prefix the truncation note, as `preparePdf` does."""
    text, kept, truncated = cap_pages(pages, max_chars)
    if truncated:
        return f"[Document tronqué : pages 1 à {kept} sur {len(pages)}]\n{text}"
    return text


def extract_pages(path: Path) -> list[str]:
    return [(page.extract_text() or "") for page in PdfReader(path).pages]


def build_message(question: str, filename: str, text: str) -> HumanMessage:
    """The user message as the agent receives it after the multimodal patch.

    The question comes first, then the document inlined as a text block under
    a `[Document: <filename>]` header (see `src/multimodal_middleware.py`).
    """
    return HumanMessage(
        content=[
            {"type": "text", "text": question},
            {"type": "text", "text": f"[Document: {filename}]\n{text}"},
        ]
    )


# --- Callback instrumentation --------------------------------------------------


ERROR_TEXT_CHARS = 200


def describe_error(exc: BaseException) -> str:
    """Name an error without leaking anything from a request.

    An HTTP error is reported as class and status only. Any other exception
    adds its message, cut short and on one line, so a failure is diagnosable.
    """
    name = type(exc).__name__
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status:
        return f"{name} {status}"
    text = " ".join(str(exc).split())[:ERROR_TEXT_CHARS]
    return f"{name}: {text}" if text else name


@dataclass
class LlmCall:
    start: float
    model: str
    role: str
    duration: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


@dataclass
class ToolCall:
    start: float
    name: str
    input_chars: int
    top_level: bool
    duration: float = 0.0


class CallTimer(BaseCallbackHandler):
    """Record every LLM call and tool call of a turn, keyed by run id.

    An LLM call is attributed to the nearest tool run among its ancestors, or
    to the main agent when it has none. Parents are tracked for every run kind
    because chains sit between a tool run and the model call it makes.
    """

    def __init__(self) -> None:
        # A plain class: a dataclass would drop `__hash__`, which LangChain
        # needs to register a handler.
        self.parents: dict[Any, Any] = {}
        self.llm_calls: dict[Any, LlmCall] = {}
        self.tool_calls: dict[Any, ToolCall] = {}

    def _tool_ancestor(self, run_id: Any) -> Any | None:
        current = self.parents.get(run_id)
        while current is not None:
            if current in self.tool_calls:
                return current
            current = self.parents.get(current)
        return None

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kw):
        self.parents[run_id] = parent_run_id

    def on_chat_model_start(
        self, serialized, messages, *, run_id, parent_run_id=None, **kwargs
    ):
        self.parents[run_id] = parent_run_id
        params = kwargs.get("invocation_params") or {}
        metadata = kwargs.get("metadata") or {}
        model = metadata.get("ls_model_name") or params.get("model") or "?"
        tool_run = self._tool_ancestor(run_id)
        role = self.tool_calls[tool_run].name if tool_run else MAIN_ROLE
        self.llm_calls[run_id] = LlmCall(time.perf_counter(), str(model), role)

    def on_llm_end(self, response, *, run_id, **kwargs):
        call = self.llm_calls.get(run_id)
        if call is None:
            return
        call.duration = time.perf_counter() - call.start
        usage = None
        generations = response.generations
        if generations and generations[0]:
            message = getattr(generations[0][0], "message", None)
            usage = getattr(message, "usage_metadata", None)
        if usage:
            call.input_tokens = usage.get("input_tokens")
            call.output_tokens = usage.get("output_tokens")
        else:
            token_usage = (response.llm_output or {}).get("token_usage") or {}
            call.input_tokens = token_usage.get("prompt_tokens")
            call.output_tokens = token_usage.get("completion_tokens")

    def on_llm_error(self, error, *, run_id, **kwargs):
        call = self.llm_calls.get(run_id)
        if call is not None:
            call.duration = time.perf_counter() - call.start
            call.error = describe_error(error)

    def on_tool_start(
        self, serialized, input_str, *, run_id, parent_run_id=None, inputs=None, **kw
    ):
        self.parents[run_id] = parent_run_id
        if isinstance(inputs, dict):
            chars = sum(len(str(value)) for value in inputs.values())
        else:
            chars = len(input_str)
        name = (serialized or {}).get("name") or kw.get("name") or "tool"
        top_level = self._tool_ancestor(run_id) is None
        self.tool_calls[run_id] = ToolCall(time.perf_counter(), name, chars, top_level)

    def on_tool_end(self, output, *, run_id, **kwargs):
        call = self.tool_calls.get(run_id)
        if call is not None:
            call.duration = time.perf_counter() - call.start

    def on_tool_error(self, error, *, run_id, **kwargs):
        self.on_tool_end(None, run_id=run_id)

    def errors(self) -> list[str]:
        return [c.error for c in self.llm_calls.values() if c.error]


# --- Turns ----------------------------------------------------------------------


@dataclass
class Turn:
    route: str
    label: str
    wall: float
    timer: CallTimer
    error: str | None = None


def effective_models(args: argparse.Namespace) -> dict[str, str]:
    from src import models

    return {
        "agent": args.agent_model or models.AGENT_MODEL,
        "extractor": args.extractor_model or models.EXTRACTOR_MODEL,
        "render": args.render_model or models.RENDER_MODEL,
    }


def build_graphs(models: dict[str, str]) -> dict[str, Any]:
    """Build both graphs with the effective models; production code is untouched."""
    from src import dynamic_agent, fixed_agent, pdf_tools
    from src.models import chat_model

    fixed_agent.AGENT_MODEL = models["agent"]
    dynamic_agent.AGENT_MODEL = models["agent"]
    pdf_tools._EXTRACTOR = chat_model(models["extractor"])
    dynamic_agent._RENDER_MODEL = chat_model(models["render"])
    return {
        "fixed": fixed_agent.build_fixed_agent(),
        "dynamic": dynamic_agent.build_dynamic_agent(),
    }


async def run_turn(graph: Any, message: HumanMessage, timer: CallTimer) -> Any:
    # Outside AG-UI nobody fills the `copilotkit` state key that the CopilotKit
    # middleware reads, so it is supplied empty.
    return await graph.ainvoke(
        {"messages": [message], "copilotkit": {"actions": [], "context": []}},
        config={
            "callbacks": [timer],
            "configurable": {"thread_id": str(uuid.uuid4())},
            "recursion_limit": 50,
        },
    )


def tool_error(result: Any) -> str | None:
    """The text of a provider failure that a tool turned into a tool message."""
    from src.errors import TOOL_ERROR_PREFIX

    for message in (result or {}).get("messages", []):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.startswith(TOOL_ERROR_PREFIX):
            return content[:ERROR_TEXT_CHARS]
    return None


async def play(graph: Any, route: str, label: str, message: HumanMessage) -> Turn:
    """Play one turn. All turns of a run must share one event loop: the model
    clients keep connections bound to the loop that first used them."""
    timer = CallTimer()
    start = time.perf_counter()
    error = None
    result = None
    try:
        result = await run_turn(graph, message, timer)
    except Exception as exc:
        error = describe_error(exc)
    wall = time.perf_counter() - start
    # The agent middleware turns provider failures into a chat reply, so they
    # do not raise: they are read from the failed LLM calls, or from the tool
    # message that carries them, instead.
    error = error or next(iter(timer.errors()), None) or tool_error(result)
    return Turn(route, label, wall, timer, error)


async def play_all(
    graphs: dict[str, Any], plan: list[tuple[str, Path, str, str]]
) -> list[Turn]:
    """Play the turns in order on one event loop; stop at the first failure."""
    turns: list[Turn] = []
    for index, (route, path, question, text) in enumerate(plan, start=1):
        print(f"[{index}/{len(plan)}] {route} {path.name}", file=sys.stderr)
        label = f"{path.stem}: {question[:40]}".replace("|", "/")
        message = build_message(question, path.name, text)
        turn = await play(graphs[route], route, label, message)
        turns.append(turn)
        if turn.error:
            break
    return turns


# --- Report ----------------------------------------------------------------------


def _n(value: int | None) -> str:
    return "" if value is None else str(value)


def render_turn(turn: Turn) -> list[str]:
    timer = turn.timer
    events: list[tuple[float, list[str]]] = []
    for call in timer.llm_calls.values():
        if call.error:
            tokens = [f"ERROR {call.error}", ""]
        else:
            tokens = [_n(call.input_tokens), _n(call.output_tokens)]
        events.append(
            (
                call.start,
                [call.role, call.model, f"{call.duration:.1f}", *tokens, ""],
            )
        )
    for tool in timer.tool_calls.values():
        if tool.top_level:
            events.append(
                (
                    tool.start,
                    [
                        f"tool {tool.name}",
                        "-",
                        f"{tool.duration:.1f}",
                        "",
                        "",
                        str(tool.input_chars),
                    ],
                )
            )
    prefix = [turn.route, turn.label]
    rows = [prefix + cells for _, cells in sorted(events, key=lambda e: e[0])]
    ok = [c for c in timer.llm_calls.values() if not c.error]
    total_in = sum(c.input_tokens or 0 for c in ok)
    total_out = sum(c.output_tokens or 0 for c in ok)
    total = prefix + [
        "TOTAL",
        "",
        f"{turn.wall:.1f}",
        str(total_in),
        str(total_out),
        "",
    ]
    return ["| " + " | ".join(row) + " |" for row in [*rows, total]]


def render_report(
    turns: list[Turn], models: dict[str, str], cap: int, timeout: float
) -> str:
    lines = [
        "# Agent latency and token measurement",
        "",
        f"- Date: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- Models: agent={models['agent']}, extractor={models['extractor']}, "
        f"render={models['render']}",
        f"- Text cap: {cap} chars",
        f"- Request timeout: {timeout} s",
        "",
        "| route | scenario | call | model | duration (s) | input tokens "
        "| output tokens | tool input chars |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for turn in turns:
        lines.extend(render_turn(turn))
        if turn.error:
            cells = [turn.route, turn.label, f"ERROR {turn.error}", "", "", "", "", ""]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# --- Entry point -------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--repeat", type=int, default=1, help="plays per scenario")
    parser.add_argument(
        "--extra",
        nargs=3,
        action="append",
        default=[],
        metavar=("ROUTE", "PDF_PATH", "QUESTION"),
        help="add a scenario on any local PDF (repeatable)",
    )
    parser.add_argument("--cap", type=int, help="override the text cap (chars)")
    parser.add_argument("--agent-model", help="model id of the main agent")
    parser.add_argument("--extractor-model", help="model id of query_pdf")
    parser.add_argument("--render-model", help="model id of generate_a2ui")
    parser.add_argument("--dry-run", action="store_true", help="no network call")
    return parser.parse_args(argv)


def collect_scenarios(args: argparse.Namespace) -> list[tuple[str, Path, str]]:
    scenarios = [(r, SAMPLES_DIR / f, q) for r, f, q in SCENARIOS]
    for route, path, question in args.extra:
        scenarios.append((route, Path(path), question))
    for route, path, _ in scenarios:
        if route not in ROUTES:
            raise SystemExit(f"Unknown route {route!r}, expected one of {ROUTES}.")
        if not path.is_file():
            raise SystemExit(f"PDF not found: {path}")
    return scenarios


def main(argv: list[str] | None = None) -> int:
    # The questions carry accents: keep the report readable on any console.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = parse_args(argv)
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1.")
    scenarios = collect_scenarios(args)
    planned = len(scenarios) * args.repeat
    if planned > MAX_TURNS:
        print(
            f"Refusing to play {planned} turns: the limit is {MAX_TURNS} per run "
            "(each turn consumes Mistral tokens).",
            file=sys.stderr,
        )
        return 2

    sys.path.insert(0, str(AGENT_DIR))
    cap = read_text_cap() if args.cap is None else args.cap
    models = effective_models(args)

    prepared = []
    for route, path, question in scenarios:
        pages = extract_pages(path)
        prepared.append((route, path, question, prepare_text(pages, cap)))

    if args.dry_run:
        print(f"Models: {models}")
        print(f"Text cap: {cap} chars")
        for route, path, question, text in prepared:
            print(f"- {route} | {path.name} | {len(text)} chars | {question}")
        print(f"Planned turns: {planned} (limit {MAX_TURNS}), repeat {args.repeat}")
        return 0

    from dotenv import load_dotenv

    load_dotenv(AGENT_DIR / ".env")
    if not os.environ.get("MISTRAL_API_KEY"):
        print("MISTRAL_API_KEY is not set (agent/.env).", file=sys.stderr)
        return 2
    from src.models import REQUEST_TIMEOUT_S

    graphs = build_graphs(models)
    plan = [prepared[index % len(prepared)] for index in range(planned)]
    turns = asyncio.run(play_all(graphs, plan))
    print(render_report(turns, models, cap, REQUEST_TIMEOUT_S))
    return 1 if turns[-1].error else 0


if __name__ == "__main__":
    sys.exit(main())
