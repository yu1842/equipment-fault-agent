"""案例知识库质量校验：结构、粒度、规范、可检索性与索引同步。

与 kbcheck.py 的分工：
  * kbcheck.py   校验项目知识库（冻结维护，仅内部）
  * casecheck.py 校验案例知识库（业务资产，对外可见）

任一 E 级问题都会让 `python tools/verify_cases.py` 非 0 退出，测试套件同样会失败。
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .knowledge import bigrams, dice

REQUIRED_FIELDS = ("id", "equipment", "model", "symptom", "causes", "steps", "keywords", "risk", "source")
ID_PATTERN = re.compile(r"^EFA-\d{3}$")
SPEC_PATTERN = re.compile(r"\d+(\.\d+)?\s*(℃|°C|mm|MPa|bar|V|A|Hz|rpm|kW|%|小时|分钟|秒|s\b)")
VAGUE_WORDS = ("视情况", "检查一下", "等等", "可能有问题", "具体问题具体分析", "看情况", "酌情")
SAFETY_WORDS = ("停机", "断电", "隔离", "挂牌", "泄压", "急停", "停止", "上锁", "确认安全")


@dataclass
class Issue:
    level: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


def verify(project_root: str | Path) -> tuple[list[Issue], dict]:
    root = Path(project_root).resolve()
    cases_path = root / "data" / "fault_cases.json"
    index_path = root / "data" / "case_index.json"
    issues: list[Issue] = []

    try:
        raw = json.loads(cases_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Issue("E", "CASE_LOAD", f"无法读取案例库：{exc}")], {}

    cases = raw.get("cases", []) if isinstance(raw, dict) else raw
    ids: set[str] = set()

    for item in cases:
        cid = str(item.get("id", "?"))

        for field in REQUIRED_FIELDS:
            if field not in item or item.get(field) in (None, "", []):
                issues.append(Issue("E", "MISSING_FIELD", f"{cid} 缺少字段 {field}"))

        if not ID_PATTERN.match(cid):
            issues.append(Issue("E", "BAD_ID", f"{cid} 编号格式应为 EFA-三位数字"))
        if cid in ids:
            issues.append(Issue("E", "DUP_ID", f"{cid} 编号重复"))
        ids.add(cid)

        if item.get("risk") not in ("高", "中", "低"):
            issues.append(Issue("E", "BAD_RISK", f"{cid} 风险等级应为 高/中/低，实际 {item.get('risk')!r}"))

        causes = item.get("causes") or []
        steps = item.get("steps") or []
        keywords = item.get("keywords") or []
        if len(causes) < 2:
            issues.append(Issue("W", "FEW_CAUSES", f"{cid} 可能原因仅 {len(causes)} 条，建议至少 2 条"))
        if len(steps) < 4:
            issues.append(Issue("E", "FEW_STEPS", f"{cid} 处理步骤仅 {len(steps)} 条，建议至少 4 条"))
        if len(keywords) < 4:
            issues.append(Issue("E", "FEW_KEYWORDS", f"{cid} 关键词仅 {len(keywords)} 个，影响召回"))
        if len(set(keywords)) != len(keywords):
            issues.append(Issue("W", "DUP_KEYWORD", f"{cid} 关键词存在重复"))
        if len(str(item.get("symptom", ""))) < 12:
            issues.append(Issue("W", "SHORT_SYMPTOM", f"{cid} 故障现象过短，检索区分度不足"))
        if len(str(item.get("equipment", ""))) > 20:
            issues.append(Issue("W", "LONG_EQUIPMENT", f"{cid} 设备名过长，不利于分类统计"))

        step_text = " ".join(steps)
        if not SPEC_PATTERN.search(step_text):
            issues.append(Issue("W", "NO_SPEC", f"{cid} 步骤中没有可量化的技术参数（阈值/数值）"))

        if item.get("risk") in ("高", "中") and steps:
            if not any(word in str(steps[0]) for word in SAFETY_WORDS):
                issues.append(Issue("W", "NO_SAFETY_FIRST", f"{cid} 首条步骤未包含安全隔离动作"))

        text = step_text + " ".join(causes)
        for word in VAGUE_WORDS:
            if word in text:
                issues.append(Issue("E", "VAGUE", f"{cid} 含模糊表述「{word}」，请给出可执行动作"))

    # 重复：同设备且现象高度相似
    for a, b in itertools.combinations(cases, 2):
        if a.get("equipment") != b.get("equipment"):
            continue
        score = dice(bigrams(str(a.get("symptom", ""))), bigrams(str(b.get("symptom", ""))))
        if score > 0.55:
            issues.append(
                Issue("E", "DUPLICATE", f"{a.get('id')} 与 {b.get('id')} 现象相似度 {score:.2f}，疑似重复")
            )

    # 可检索性：用现象检索，Top1 必须是自己
    try:
        from .knowledge import KnowledgeBase

        kb = KnowledgeBase(cases_path)
        for case in kb.cases:
            hits = kb.search(case.symptom, top_k=1)
            if not hits or hits[0].case.id != case.id:
                got = hits[0].case.id if hits else "无命中"
                issues.append(Issue("E", "NOT_SEARCHABLE", f"{case.id} 用自身现象检索不到自己（Top1={got}）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue("W", "SEARCH_CHECK_FAIL", f"可检索性检查未执行：{exc}"))

    # 索引同步
    try:
        from . import kb_index

        data = kb_index.load_index(index_path)
        if data is None:
            issues.append(Issue("W", "INDEX_MISSING", "缺少 data/case_index.json，请执行 python tools/rebuild_index.py"))
        elif data.get("kb_hash") != kb_index.file_hash(cases_path):
            issues.append(Issue("W", "INDEX_STALE", "案例索引与数据不同版本，请执行 python tools/rebuild_index.py"))
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue("W", "INDEX_CHECK_FAIL", f"索引检查未执行：{exc}"))

    equipment = {str(c.get("equipment", "")) for c in cases}
    summary = {
        "cases": len(cases),
        "equipment": len(equipment),
        "errors": sum(1 for i in issues if i.level == "E"),
        "warnings": sum(1 for i in issues if i.level == "W"),
    }
    return issues, summary
