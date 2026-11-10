"""本地故障案例知识库与检索。

检索策略（无第三方分词库，纯标准库）：
  1. 结构化加权：设备名命中 + 关键词命中 + 现象文本相似度；
  2. 字面相似：查询与案例文本的中文二元组 Dice 系数，兜底口语化描述；
  3. 归一化到 0~1，低于阈值判定为"知识库未覆盖"，由上层明确告知用户。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?\"'（）()\[\]{}<>《》\-—_/\\|~`@#$%^&*+=]+")
_LATIN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.\-]*")

STOP_TERMS = {
    "设备", "故障", "问题", "怎么办", "怎么", "如何", "什么", "一下", "我们",
    "厂里", "车间", "请问", "现在", "出现", "发生", "帮忙", "看看", "这个",
}


def normalize(text: str) -> str:
    return _PUNCT.sub("", (text or "").lower())


def bigrams(text: str) -> set[str]:
    text = normalize(text)
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


@dataclass
class FaultCase:
    id: str
    equipment: str
    model: str
    symptom: str
    causes: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    risk: str = "低"
    source: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "FaultCase":
        return cls(
            id=str(raw.get("id", "")).strip() or "UNKNOWN",
            equipment=str(raw.get("equipment", "")).strip(),
            model=str(raw.get("model", "")).strip(),
            symptom=str(raw.get("symptom", "")).strip(),
            causes=[str(x) for x in raw.get("causes", []) if str(x).strip()],
            steps=[str(x) for x in raw.get("steps", []) if str(x).strip()],
            keywords=[str(x) for x in raw.get("keywords", []) if str(x).strip()],
            risk=str(raw.get("risk", "低")).strip() or "低",
            source=str(raw.get("source", "")).strip(),
        )

    def searchable_text(self) -> str:
        parts: Iterable[str] = [
            self.equipment,
            self.model,
            self.symptom,
            " ".join(self.keywords),
            " ".join(self.causes),
        ]
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "equipment": self.equipment,
            "model": self.model,
            "symptom": self.symptom,
            "causes": self.causes,
            "steps": self.steps,
            "keywords": self.keywords,
            "risk": self.risk,
            "source": self.source,
        }


@dataclass
class SearchHit:
    case: FaultCase
    score: float
    matched: list[str] = field(default_factory=list)

    def brief(self, rank: int) -> dict:
        return {
            "rank": rank,
            "case_id": self.case.id,
            "equipment": self.case.equipment,
            "symptom": self.case.symptom,
            "risk": self.case.risk,
            "score": round(self.score, 3),
            "matched_terms": self.matched[:6],
        }


class KnowledgeBase:
    """故障案例知识库。加载失败时保持可用（空库 + 错误信息）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.cases: list[FaultCase] = []
        self.load_error: str = ""
        self.version: str = ""
        self.disclaimer: str = ""
        self.load()

    # ---------- 加载 ----------

    def load(self) -> None:
        self.cases = []
        self.load_error = ""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.load_error = f"知识库文件不存在：{self.path}"
            return
        except (OSError, ValueError) as exc:
            self.load_error = f"知识库读取失败：{exc}"
            return

        items = raw.get("cases", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            self.load_error = "知识库格式错误：cases 字段应为数组"
            return

        for item in items:
            if isinstance(item, dict) and item.get("id"):
                self.cases.append(FaultCase.from_dict(item))

        if isinstance(raw, dict):
            self.version = str(raw.get("version", ""))
            self.disclaimer = str(raw.get("disclaimer", ""))
        if not self.cases:
            self.load_error = "知识库为空，请检查 data/fault_cases.json"

    # ---------- 查询 ----------

    def __len__(self) -> int:
        return len(self.cases)

    def get(self, case_id: str) -> FaultCase | None:
        target = (case_id or "").strip().upper()
        for case in self.cases:
            if case.id.upper() == target:
                return case
        return None

    def equipment_names(self) -> list[str]:
        seen: list[str] = []
        for case in self.cases:
            if case.equipment and case.equipment not in seen:
                seen.append(case.equipment)
        return seen

    def search(self, query: str, top_k: int = 3, min_score: float = 0.22) -> list[SearchHit]:
        text = normalize(query)
        if not text:
            return []
        q_grams = bigrams(query)
        hits: list[SearchHit] = []

        for case in self.cases:
            score = 0.0
            matched: list[str] = []

            # 1) 设备名命中，权重最高
            if case.equipment and normalize(case.equipment) in text:
                score += 0.42
                matched.append(case.equipment)

            # 2) 关键词命中，逐个累加，最多取 4 个，避免长词表刷分
            kw_hits = 0
            for kw in case.keywords:
                key = normalize(kw)
                if len(key) >= 2 and key in text:
                    if kw_hits < 4:
                        score += 0.20
                        matched.append(kw)
                    kw_hits += 1

            # 3) 现象文本字面相似度
            sim = dice(q_grams, bigrams(case.symptom))
            score += sim * 0.55

            # 4) 全案例文本补充相似度（权重较低）
            score += dice(q_grams, bigrams(case.searchable_text())) * 0.20

            if score <= 0:
                continue
            # 压缩到 0~1，避免多个关键词线性叠加超过 1
            normalized = 1 - math.exp(-1.15 * score)
            if normalized >= min_score:
                hits.append(SearchHit(case=case, score=normalized, matched=matched))

        hits.sort(key=lambda h: (-h.score, h.case.id))
        return hits[: max(1, top_k)]
