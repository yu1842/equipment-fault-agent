"""Agent 可调用工具集。

所有工具都只读本地模拟知识库，不触及任何真实设备与网络控制接口，
符合"仅允许查询模拟知识库"的安全边界。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .knowledge import KnowledgeBase


@dataclass
class ToolCallRecord:
    """一次工具调用的可展示记录（用于界面与日志）。"""

    name: str
    arguments: dict
    ok: bool
    elapsed_ms: int
    summary: str
    ts: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    round: int = 0

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "round": self.round,
            "tool": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "elapsed_ms": self.elapsed_ms,
            "summary": self.summary,
        }


class ToolError(Exception):
    """工具执行失败（参数错误、目标不存在等）。"""


class ToolRegistry:
    def __init__(self, kb: KnowledgeBase, default_top_k: int = 3, min_score: float = 0.22):
        self.kb = kb
        self.default_top_k = default_top_k
        self.min_score = min_score
        self._impl: dict[str, Callable[..., dict]] = {
            "search_fault_cases": self._search_fault_cases,
            "get_case_detail": self._get_case_detail,
            "list_equipment": self._list_equipment,
        }

    # ---------- 对外 ----------

    def specs(self) -> list[dict]:
        """OpenAI function calling 格式的工具声明。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_fault_cases",
                    "description": (
                        "在本地设备故障案例知识库中检索与用户描述最相近的案例。"
                        "返回案例编号、设备、故障现象、风险等级与匹配度。"
                        "任何设备故障问题都必须先调用本工具。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "检索用的故障描述，可提炼设备名 + 故障现象，例如：液压站 压力上不去",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "返回条数，1~5，默认 3",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_case_detail",
                    "description": "按案例编号读取某条故障案例的完整内容，包括可能原因与建议处理步骤。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "case_id": {
                                "type": "string",
                                "description": "案例编号，例如 EFA-001",
                            }
                        },
                        "required": ["case_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_equipment",
                    "description": "列出知识库当前收录的全部设备类型，用于判断问题是否在覆盖范围内。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def execute(self, name: str, arguments: dict | str) -> tuple[dict, ToolCallRecord]:
        """执行工具并返回（结果, 记录）。异常统一转为结构化错误结果。"""
        started = time.perf_counter()
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except ValueError:
                arguments = {"_raw": arguments}
        if not isinstance(arguments, dict):
            arguments = {}

        fn = self._impl.get(name)
        if fn is None:
            payload = {"ok": False, "error": f"未定义的工具：{name}"}
            elapsed = int((time.perf_counter() - started) * 1000)
            return payload, ToolCallRecord(name, arguments, False, elapsed, payload["error"])

        try:
            result = fn(**arguments)
            ok = True
            summary = self._summarize(name, result)
        except ToolError as exc:
            result = {"ok": False, "error": str(exc)}
            ok = False
            summary = f"失败：{exc}"
        except TypeError as exc:
            result = {"ok": False, "error": f"参数不合法：{exc}"}
            ok = False
            summary = "参数不合法"
        except Exception as exc:  # noqa: BLE001 - 兜底，保证 Agent 不因工具异常中断
            result = {"ok": False, "error": f"工具内部错误：{exc}"}
            ok = False
            summary = "工具内部错误"

        elapsed = int((time.perf_counter() - started) * 1000)
        record = ToolCallRecord(name, arguments, ok, elapsed, summary)
        return result, record

    # ---------- 具体实现 ----------

    def _search_fault_cases(self, query: str = "", top_k: int | None = None) -> dict:
        query = (query or "").strip()
        if not query:
            raise ToolError("检索关键词为空，无法查询案例库")
        try:
            k = int(top_k) if top_k is not None else self.default_top_k
        except (TypeError, ValueError):
            k = self.default_top_k
        k = max(1, min(5, k))

        hits = self.kb.search(query, top_k=k, min_score=self.min_score)
        return {
            "ok": True,
            "query": query,
            "total_in_kb": len(self.kb),
            "hit_count": len(hits),
            "coverage": "有依据" if hits else "无依据",
            "hits": [h.brief(i + 1) for i, h in enumerate(hits)],
            "notice": "" if hits else "知识库中未检索到相关案例，回答时必须说明缺乏依据，不得编造。",
        }

    def _get_case_detail(self, case_id: str = "") -> dict:
        case = self.kb.get(case_id)
        if case is None:
            raise ToolError(f"案例编号不存在：{case_id or '(空)'}")
        return {"ok": True, "case": case.to_dict()}

    def _list_equipment(self) -> dict:
        names = self.kb.equipment_names()
        return {"ok": True, "count": len(names), "equipment": names}

    # ---------- 摘要 ----------

    @staticmethod
    def _summarize(name: str, result: dict) -> str:
        if name == "search_fault_cases":
            if not result.get("hit_count"):
                return "命中 0 条（知识库未覆盖）"
            top = result["hits"][0]
            return f"命中 {result['hit_count']} 条，Top1={top['case_id']} score={top['score']}"
        if name == "get_case_detail":
            case = result.get("case", {})
            return f"读取 {case.get('id', '?')} {case.get('equipment', '')}"
        if name == "list_equipment":
            return f"设备类型 {result.get('count', 0)} 种"
        return "完成"
