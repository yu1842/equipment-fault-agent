"""Agent 主循环。

两种运行模式，共用同一套工具与同一份知识库：
  * 在线模式：LLM 通过 function calling 自主决定是否检索、检索什么，再由模型组织回答；
  * 离线模式：模型不可用（无密钥 / 网络异常 / 强制离线）时的规则化兜底，
    直接调用检索工具并按固定模板组织回答，保证演示流程不中断。

两种模式的每次工具调用都会被记录，界面上可逐条查看，用于证明"真实工具调用"。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .config import Settings
from .knowledge import KnowledgeBase
from .llm import LLMClient, LLMError
from .tools import ToolCallRecord, ToolRegistry

SYSTEM_PROMPT = """你是"制造企业设备故障咨询助手"，服务于工厂设备运维场景。

工作规则：
1. 用户描述设备故障时，必须先调用 search_fault_cases 检索本地案例库，不得凭记忆直接作答。
2. 检索到候选案例后，如需要更多原因与处理步骤，调用 get_case_detail 读取完整案例。
3. 回答必须严格依据检索结果，按以下结构输出：
   【判断】一句话概括最可能的故障方向；
   【可能原因】分点列出，注明来自哪个案例编号；
   【处理步骤】分点列出，安全措施优先（断电挂牌、泄压、降温、通风等）；
   【参考案例】列出用到的案例编号与设备名称。
4. 检索结果为空或相关度不足时，必须明确写出"本地知识库暂无该故障的案例依据"，
   并说明无法给出有依据的判断，禁止编造案例编号、故障现象或处理步骤。
5. 涉及高压、高温、旋转部件、带电作业时，先提示安全隔离措施。
6. 你只提供咨询建议：不连接真实设备，不下发任何设备控制指令，不承诺检修结果。
7. 使用简体中文，分点简洁作答，总长度控制在 400 字以内。"""


@dataclass
class Answer:
    text: str
    mode: str = "offline"  # llm | offline
    tool_records: list[ToolCallRecord] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str = ""
    citations: list[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def ok(self) -> bool:
        return not self.error


class Agent:
    MAX_HISTORY_MESSAGES = 12

    def __init__(
        self,
        settings: Settings | None = None,
        kb: KnowledgeBase | None = None,
    ):
        self.settings = settings or Settings.load()
        self.kb = kb or KnowledgeBase(self.settings.kb_path)
        self.tools = ToolRegistry(self.kb, self.settings.top_k, self.settings.min_score)
        self.llm = LLMClient(self.settings)
        self.history: list[dict] = []
        self._last_records: list[ToolCallRecord] = []

    # ---------- 公共 API ----------

    def reset(self) -> None:
        self.history.clear()

    @property
    def mode_label(self) -> str:
        return self.settings.mode_label

    def ask(self, question: str) -> Answer:
        started = time.perf_counter()
        question = (question or "").strip()
        if not question:
            return Answer(
                text="请输入需要咨询的设备故障描述，例如：液压站压力上不去，执行油缸动作很慢。",
                mode="offline",
                error="empty_input",
                elapsed_ms=0,
            )

        if self.kb.load_error:
            return Answer(
                text=(
                    "知识库未能加载，无法进行检索。\n"
                    f"原因：{self.kb.load_error}\n"
                    "请检查 data/fault_cases.json 是否存在且为合法 JSON 后重试。"
                ),
                mode="offline",
                error="kb_unavailable",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )

        records: list[ToolCallRecord] = []
        self._last_records = records

        if self.settings.online_ready:
            try:
                text, tokens = self._ask_llm(question, records)
            except LLMError as exc:
                text, extra = self._ask_offline(question, records, prefix_reason=str(exc))
                self._push_history(question, text)
                return Answer(
                    text=text,
                    mode="offline",
                    tool_records=records + extra,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    error=f"llm_failed: {exc}",
                )
            self._push_history(question, text)
            return Answer(
                text=text,
                mode="llm",
                tool_records=records,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                citations=self._collect_citations(records),
                tokens=tokens,
            )

        text, _ = self._ask_offline(question, records)
        self._push_history(question, text)
        return Answer(
            text=text,
            mode="offline",
            tool_records=records,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            citations=self._collect_citations(records),
        )

    # ---------- 在线模式 ----------

    def _ask_llm(self, question: str, records: list[ToolCallRecord]) -> tuple[str, int]:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.history[-self.MAX_HISTORY_MESSAGES :])
        messages.append({"role": "user", "content": question})

        tools = self.tools.specs()
        total_tokens = 0

        for round_index in range(1, self.settings.max_rounds + 1):
            response = self.llm.chat(messages, tools)
            total_tokens += response.prompt_tokens + response.completion_tokens
            message = response.message
            tool_calls = message.get("tool_calls") or []

            if tool_calls:
                # 保留模型的工具调用意图，再按顺序回填每个工具的结果
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )
                for call in tool_calls:
                    fn = call.get("function") or {}
                    name = fn.get("name") or ""
                    result, record = self.tools.execute(name, fn.get("arguments") or "{}")
                    record.round = round_index
                    records.append(record)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or f"call_{round_index}",
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                continue

            content = (message.get("content") or "").strip()
            if content:
                return content, total_tokens
            raise LLMError("模型返回了空回答")

        raise LLMError(f"工具调用轮次超过上限（{self.settings.max_rounds} 轮），已中止")

    # ---------- 离线兜底 ----------

    def _ask_offline(
        self,
        question: str,
        records: list[ToolCallRecord],
        prefix_reason: str = "",
    ) -> tuple[str, list[ToolCallRecord]]:
        result, record = self.tools.execute("search_fault_cases", {"query": question})
        records.append(record)

        lines: list[str] = []
        if prefix_reason:
            lines.append(f"（在线模型不可用：{prefix_reason}。已自动切换为本地规则模式作答。）")
        lines.append("【离线规则模式】未调用大模型，以下结论由本地检索引擎生成。")
        lines.append("")

        if not result.get("ok") or not result.get("hit_count"):
            lines.append("【判断】本地知识库暂无该故障的案例依据，无法给出有依据的判断。")
            lines.append("")
            lines.append(
                f"已检索 {len(self.kb)} 条案例，相关度均低于阈值 {self.settings.min_score:.2f}。"
            )
            names = "、".join(self.kb.equipment_names())
            if names:
                lines.append(f"当前覆盖的设备类型：{names}。")
            lines.append("")
            lines.append("建议补充：设备类型、型号、故障现象、报警代码、发生时机（启动/满载/换向）。")
            lines.append("如需接入模型生成自然语言分析，请配置 API Key 后重试。")
            return "\n".join(lines), records

        top = result["hits"][0]
        detail, detail_record = self.tools.execute("get_case_detail", {"case_id": top["case_id"]})
        records.append(detail_record)
        case = detail.get("case", {})

        lines.append(f"【判断】最接近的案例是 {case.get('id')}（{case.get('equipment')}），"
                     f"匹配度 {top.get('score')}。")
        if len(result["hits"]) > 1:
            others = "、".join(h["case_id"] for h in result["hits"][1:])
            lines.append(f"次要候选：{others}。")
        lines.append("")
        lines.append("【可能原因】")
        for i, cause in enumerate(case.get("causes", [])[:4], 1):
            lines.append(f"{i}. {cause}")
        lines.append("")
        lines.append("【处理步骤】")
        for i, step in enumerate(case.get("steps", [])[:6], 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        lines.append(f"【参考案例】{case.get('id')}《{case.get('equipment')}》，风险等级：{case.get('risk')}")
        if self.kb.disclaimer:
            lines.append(f"提示：{self.kb.disclaimer}")
        return "\n".join(lines), records

    # ---------- 辅助 ----------

    def _push_history(self, question: str, answer: str) -> None:
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        if len(self.history) > self.MAX_HISTORY_MESSAGES:
            self.history = self.history[-self.MAX_HISTORY_MESSAGES :]

    @staticmethod
    def _collect_citations(records: list[ToolCallRecord]) -> list[str]:
        ids: list[str] = []
        for record in records:
            if record.name == "search_fault_cases":
                for token in record.summary.split():
                    if token.startswith("EFA-") and token not in ids:
                        ids.append(token)
            if record.name == "get_case_detail":
                arg = record.arguments.get("case_id")
                if arg and arg not in ids:
                    ids.append(str(arg))
        return ids
