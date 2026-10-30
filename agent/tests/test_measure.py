import pytest

from scripts.measure import PDF_TS, cap_pages, prepare_text, read_text_cap


def test_pages_within_the_cap_are_all_kept():
    assert cap_pages(["aaa", "bbb"], 100) == ("aaa\nbbb", 2, False)


def test_whole_pages_are_dropped_past_the_cap():
    text, kept, truncated = cap_pages(["a" * 40] * 3, 90)
    assert (len(text), kept, truncated) == (81, 2, True)


def test_a_single_oversized_page_is_cut_at_the_cap():
    text, kept, truncated = cap_pages(["a" * 150], 100)
    assert (len(text), kept, truncated) == (100, 1, True)


def test_truncation_is_announced_in_front_of_the_text():
    assert prepare_text(["a" * 40] * 3, 90).startswith(
        "[Document tronqué : pages 1 à 2 sur 3]\n"
    )
    assert prepare_text(["aaa", "bbb"], 100) == "aaa\nbbb"


def test_cap_is_read_from_the_front_end_source():
    assert read_text_cap() > 0


def test_missing_cap_constant_fails_loudly(tmp_path):
    source = tmp_path / "pdf.ts"
    source.write_text("export const OTHER = 1;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PDF_TEXT_MAX_CHARS"):
        read_text_cap(source)


def test_underscore_separators_are_understood(tmp_path):
    source = tmp_path / "pdf.ts"
    source.write_text("export const PDF_TEXT_MAX_CHARS = 60_000;", encoding="utf-8")
    assert read_text_cap(source) == 60000
    assert PDF_TS.is_file()


def test_describe_error_keeps_http_errors_terse_and_explains_others():
    import httpx

    from scripts.measure import describe_error

    request = httpx.Request("POST", "https://example.invalid/secret")
    http_error = httpx.HTTPStatusError(
        "secret url", request=request, response=httpx.Response(429, request=request)
    )
    assert describe_error(http_error) == "HTTPStatusError 429"
    assert describe_error(RuntimeError("Event loop\nis closed")) == (
        "RuntimeError: Event loop is closed"
    )
    assert len(describe_error(RuntimeError("x" * 500))) < 230


def test_agent_model_option_reaches_both_graphs(monkeypatch):
    from scripts.measure import build_graphs
    from src import dynamic_agent, fixed_agent, models, pdf_tools

    seen = []

    def recording(model: str = models.AGENT_MODEL):
        seen.append(model)
        return models.agent_chat_model(model)

    monkeypatch.setattr(fixed_agent, "agent_chat_model", recording)
    monkeypatch.setattr(dynamic_agent, "agent_chat_model", recording)
    # build_graphs assigns these two globals: registered so they get restored.
    monkeypatch.setattr(pdf_tools, "_EXTRACTOR", pdf_tools._EXTRACTOR)
    monkeypatch.setattr(dynamic_agent, "_RENDER_MODEL", dynamic_agent._RENDER_MODEL)

    build_graphs({"agent": "agent-x", "extractor": "extractor-x", "render": "render-x"})

    assert seen == ["agent-x", "agent-x"]


def test_turns_on_one_event_loop_reuse_the_same_model_client():
    """A real ChatMistralAI keeps pooled connections bound to the loop that
    first used them: one `asyncio.run` per turn breaks the second turn with
    "Event loop is closed". A local keep-alive server makes the pool real."""
    import asyncio
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from langchain.agents import create_agent
    from langchain_mistralai import ChatMistralAI

    from scripts.measure import build_message, play

    body = json.dumps(
        {
            "id": "c",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "pong"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        model = ChatMistralAI(
            model_name="m",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            max_retries=0,
        )
        graph = create_agent(model=model, tools=[])
        message = build_message("q", "a.pdf", "text")

        async def three_turns():
            return [await play(graph, "dynamic", "t", message) for _ in range(3)]

        turns = asyncio.run(three_turns())
    finally:
        server.shutdown()
        server.server_close()

    assert [turn.error for turn in turns] == [None, None, None]
