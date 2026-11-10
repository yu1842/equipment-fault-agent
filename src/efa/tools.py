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
from .project_kb import ProjectKB


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
    def __init__(
        self,
        kb: KnowledgeBase,
        default_top_k: int = 3,
        min_score: float = 0.22,
        project_kb: ProjectKB | None = None,
    ):
        self.kb = kb
        self.project_kb = project_kb
        self.default_top_k = default_top_k
        self.min_score = min_score
        self._impl: dict[str, Callable[..., dict]] = {
            "search_fault_cases": self._search_fault_cases,
            "get_case_detail": self._get_case_detail,
            "list_equipment": self._list_equipment,
        }
        # 项目知识库可选：未注入时不注册相关工具，specs() 也不会暴露
        if project_kb is not None:
            self._impl.update(
                {
                    "search_project_kb": self._search_project_kb,
                    "get_kb_entry": self._get_kb_entry,
                    "list_kb_categories": self._list_kb_categories,
                }
            )

    # ---------- 对外 ----------

    def specs(self) -> list[dict]:
        """OpenAI function calling 格式的工具声明。"""
        tools = [
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
        if self.project_kb is not None:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "search_project_kb",
                            "description": (
                                "检索本项目自身的工程知识库（架构分层、模块职责、接口签名、数据结构、"
                                "配置项、异常处理、依赖约束、开发约定、版本边界）。"
                                "当问题涉及本项目代码怎么实现、某个接口怎么调用、有哪些配置项、"
                                "能不能引入依赖时使用；不要用它查设备故障维修。"
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "检索词，例如：ToolRegistry 扩展、配置优先级、异常降级",
                                    },
                                    "category": {
                                        "type": "string",
                                        "description": (
                                            "可选分类过滤：architecture/module/api/tool/data/"
                                            "config/error/dependency/convention/boundary"
                                        ),
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
                            "name": "get_kb_entry",
                            "description": (
                                "按条目编号读取项目知识库的完整内容，包含调用条件、参数规范、"
                                "输出格式、使用场景、注意事项、适用范围与版本约束。"
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "entry_id": {
                                        "type": "string",
                                        "description": "条目编号，例如 KB-API-001",
                                    }
                                },
                                "required": ["entry_id"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "list_kb_categories",
                            "description": "列出项目知识库的全部分类及条目数，用于在检索前缩小范围。",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    },
                ]
            )
        return tools

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

    # ---------- 项目知识库工具 ----------

    def _search_project_kb(
        self, query: str = "", category: str | None = None, top_k: int | None = None
    ) -> dict:
        if self.project_kb is None:
            raise ToolError("项目知识库未加载，无法检索工程知识")
        query = (query or "").strip()
        if not query:
            raise ToolError("检索关键词为空，无法查询项目知识库")
        try:
            k = int(top_k) if top_k is not None else self.default_top_k
        except (TypeError, ValueError):
            k = self.default_top_k
        k = max(1, min(5, k))

        category = (category or "").strip().lower() or None
        if category and category not in {c["id"] for c in self.project_kb.category_stats()}:
            raise ToolError(
                f"分类不存在：{category}，可选值："
                + "/".join(c["id"] for c in self.project_kb.category_stats())
            )

        hits = self.project_kb.search(query, category=category, top_k=k)
        return {
            "ok": True,
            "query": query,
            "category": category or "全部",
            "total_in_kb": len(self.project_kb),
            "hit_count": len(hits),
            "hits": [h.entry.to_brief(i + 1, h.score, h.matched) for i, h in enumerate(hits)],
            "notice": ""
            if hits
            else "项目知识库未收录该问题，回答时应说明未收录，不要臆造实现细节。",
        }

    def _get_kb_entry(self, entry_id: str = "") -> dict:
        if self.project_kb is None:
            raise ToolError("项目知识库未加载，无法读取条目")
        entry = self.project_kb.get(entry_id)
        if entry is None:
            raise ToolError(f"知识条目不存在：{entry_id or '(空)'}")
        related = [
            {"entry_id": item.id, "title": item.title, "category": item.category}
            for item in self.project_kb.related_entries(entry)
        ]
        return {"ok": True, "entry": entry.to_dict(), "related": related}

    def _list_kb_categories(self) -> dict:
        if self.project_kb is None:
            raise ToolError("项目知识库未加载，无法列出分类")
        stats = self.project_kb.category_stats()
        return {"ok": True, "count": len(stats), "categories": stats}

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
        if name == "search_project_kb":
            if not result.get("hit_count"):
                return "命中 0 条（未收录）"
            top = result["hits"][0]
            return f"命中 {result['hit_count']} 条，Top1={top['entry_id']} score={top['score']}"
        if name == "get_kb_entry":
            entry = result.get("entry", {})
            return f"读取 {entry.get('id', '?')} {entry.get('title', '')}"
        if name == "list_kb_categories":
            return f"分类 {result.get('count', 0)} 个"
        return "完成"
