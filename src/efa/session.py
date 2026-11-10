"""会话记录：把每轮问答与工具调用写入 logs/session_*.jsonl。

用途：
1. 作为"真实工具调用"的可追溯证据（作业要求的执行记录）；
2. 现场演示出问题时，可直接查看历史日志定位。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import LOG_DIR
from .tools import ToolCallRecord


class SessionLog:
    def __init__(self, log_dir: Path | None = None):
        self.dir = Path(log_dir or LOG_DIR)
        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self.path = self.dir / f"session-{self.session_id}.jsonl"
        self._ready = False
        self._ensure()

    def _ensure(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._ready = True
        except OSError:
            self._ready = False

    def _write(self, kind: str, payload: dict) -> None:
        if not self._ready:
            return
        line = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "session": self.session_id,
            "kind": kind,
            **payload,
        }
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            self._ready = False

    def question(self, text: str, mode: str) -> None:
        self._write("question", {"text": text, "mode": mode})

    def answer(self, text: str, mode: str, elapsed_ms: int, error: str = "") -> None:
        self._write(
            "answer",
            {"text": text, "mode": mode, "elapsed_ms": elapsed_ms, "error": error},
        )

    def tool_calls(self, records: list[ToolCallRecord]) -> None:
        for record in records:
            self._write("tool_call", record.to_dict())

    def event(self, name: str, **extra) -> None:
        self._write("event", {"name": name, **extra})
