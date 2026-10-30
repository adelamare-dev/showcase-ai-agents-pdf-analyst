import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.graph import END, START, MessagesState, StateGraph

from src import dynamic_agent, fixed_agent
from src.checkpoints import MAX_THREADS, BoundedMemorySaver


def _write(saver: BoundedMemorySaver, thread_id: str) -> None:
    """Store one checkpoint, its channel blob and a pending write for a thread."""
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
    }
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": ["hello"]}
    saved = saver.put(config, checkpoint, {}, {"messages": "1"})
    saver.put_writes(saved, [("messages", "more")], "task")


def _holds(saver: BoundedMemorySaver, thread_id: str) -> tuple[bool, bool, bool]:
    return (
        thread_id in saver.storage,
        any(key[0] == thread_id for key in saver.writes),
        any(key[0] == thread_id for key in saver.blobs),
    )


def test_oldest_thread_is_evicted_everywhere_past_the_cap():
    saver = BoundedMemorySaver(max_threads=2)
    for thread_id in ("a", "b", "c"):
        _write(saver, thread_id)

    assert _holds(saver, "a") == (False, False, False)
    assert _holds(saver, "b") == (True, True, True)
    assert _holds(saver, "c") == (True, True, True)


def test_writing_again_to_a_thread_makes_it_recent():
    saver = BoundedMemorySaver(max_threads=2)
    for thread_id in ("a", "b", "a", "c"):
        _write(saver, thread_id)

    assert _holds(saver, "b") == (False, False, False)
    assert _holds(saver, "a") == (True, True, True)
    assert _holds(saver, "c") == (True, True, True)


def test_put_keeps_returning_the_saved_config():
    saver = BoundedMemorySaver(max_threads=1)
    config: RunnableConfig = {"configurable": {"thread_id": "a", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    saved = saver.put(config, checkpoint, {}, {})
    assert saved.get("configurable", {})["checkpoint_id"] == checkpoint["id"]


def test_default_cap_is_the_module_constant():
    assert BoundedMemorySaver().max_threads == MAX_THREADS == 32


def _echo_graph(saver: BoundedMemorySaver):
    def reply(state: MessagesState) -> dict:
        return {"messages": [AIMessage(content="ok")]}

    builder = StateGraph(MessagesState)
    builder.add_node("reply", reply)
    builder.add_edge(START, "reply")
    builder.add_edge("reply", END)
    return builder.compile(checkpointer=saver)


def _say(graph, thread_id: str, text: str) -> list:
    result = asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content=text)]},
            {"configurable": {"thread_id": thread_id}},
        )
    )
    return result["messages"]


def test_compiled_graph_keeps_the_history_of_a_thread_that_was_not_evicted():
    graph = _echo_graph(BoundedMemorySaver(max_threads=2))

    _say(graph, "t1", "first")
    _say(graph, "t2", "other")
    messages = _say(graph, "t1", "second")

    assert [m.content for m in messages] == ["first", "ok", "second", "ok"]


def test_resuming_an_evicted_thread_starts_from_an_empty_state():
    graph = _echo_graph(BoundedMemorySaver(max_threads=2))

    _say(graph, "t1", "first")
    _say(graph, "t2", "other")
    _say(graph, "t3", "third")  # evicts t1, the least recently written
    messages = _say(graph, "t1", "again")

    assert [m.content for m in messages] == ["again", "ok"]


def test_both_agent_graphs_use_the_bounded_saver():
    assert isinstance(dynamic_agent.graph.checkpointer, BoundedMemorySaver)
    assert isinstance(fixed_agent.graph.checkpointer, BoundedMemorySaver)
