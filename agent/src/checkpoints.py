"""Conversation memory for the two agent graphs, bounded in the number of threads.

`MemorySaver` keeps every thread for the life of the process, and each thread
holds its whole history, attached document included. Left alone the agent's
memory only grows. `BoundedMemorySaver` keeps the `MAX_THREADS` most recently
written threads and drops the others.

Only the number of threads is bounded: a single thread keeps growing for as
long as the conversation goes on. A thread that was dropped and is resumed
starts again from an empty state.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, ChannelVersions
from langgraph.checkpoint.memory import MemorySaver

MAX_THREADS = 32


class BoundedMemorySaver(MemorySaver):
    """`MemorySaver` that evicts the least recently written thread past a cap."""

    def __init__(self, *, max_threads: int = MAX_THREADS, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_threads = max_threads
        # Thread ids from least to most recently written.
        self._recency: OrderedDict[str, None] = OrderedDict()

    # `aput` delegates to `put`, so this covers both.
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        saved = super().put(config, checkpoint, metadata, new_versions)
        thread_id = config.get("configurable", {})["thread_id"]
        self._recency[thread_id] = None
        self._recency.move_to_end(thread_id)
        while len(self._recency) > self.max_threads:
            oldest, _ = self._recency.popitem(last=False)
            self.delete_thread(oldest)
        return saved
