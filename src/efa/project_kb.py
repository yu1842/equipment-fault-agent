"""项目自述知识库：把项目自身的模块、接口、数据、配置、异常、依赖与约定结构化。

与 knowledge.py 的区别：
  * knowledge.py 面向"设备怎么修"（业务领域知识）；
  * project_kb.py 面向"项目怎么用/怎么改"（工程知识），供 Agent 在后续开发中检索。

两者检索算法同源（关键词 + 中文二元组 Dice + 指数压缩），但字段与权重不同：
工程问题的关键词更集中（模块名、函数名、配置名），因此符号命中的权重更高。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .knowledge import bigrams, dice, normalize

CATEGORY_ORDER = (
    "architecture",
    "module",
    "api",
    "tool",
    "data",
    "config",
    "error",
    "dependency",
    "convention",
    "boundary",
)


@dataclass
class KBEntry:
    id: str
    category: str
    title: str
    summary: str
    details: str = ""
    when_to_use: list[str] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    outputs: str = ""
    scenarios: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    scope: str = ""
    version: str = ""
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    symbol: str = ""
    signature: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "KBEntry":
        return cls(
            id=str(raw.get("id", "")).strip(),
            category=str(raw.get("category", "")).strip(),
            title=str(raw.get("title", "")).strip(),
            summary=str(raw.get("summary", "")).strip(),
            details=str(raw.get("details", "")).strip(),
            when_to_use=[str(x) for x in raw.get("when_to_use", []) if str(x).strip()],
            inputs=[x for x in raw.get("inputs", []) if isinstance(x, dict)],
            outputs=str(raw.get("outputs", "")).strip(),
            scenarios=[str(x) for x in raw.get("scenarios", []) if str(x).strip()],
            cautions=[str(x) for x in raw.get("cautions", []) if str(x).strip()],
            scope=str(raw.get("scope", "")).strip(),
            version=str(raw.get("version", "")).strip(),
            tags=[str(x) for x in raw.get("tags", []) if str(x).strip()],
            refs=[str(x) for x in raw.get("refs", []) if str(x).strip()],
            symbol=str(raw.get("symbol", "")).strip(),
            signature=str(raw.get("signature", "")).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "when_to_use": self.when_to_use,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "scenarios": self.scenarios,
            "cautions": self.cautions,
            "scope": self.scope,
            "version": self.version,
            "tags": self.tags,
            "refs": self.refs,
            "symbol": self.symbol,
            "signature": self.signature,
        }

    def to_brief(self, rank: int, score: float, matched: list[str]) -> dict:
        return {
            "rank": rank,
            "entry_id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "scope": self.scope,
            "score": round(score, 3),
            "matched": matched[:6],
        }


@dataclass
class KBHit:
    entry: KBEntry
    score: float
    matched: list[str] = field(default_factory=list)


class ProjectKB:
    """项目知识库。加载失败时保持可用（空库 + load_error），不抛异常。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: list[KBEntry] = []
        self.categories: list[dict] = []
        self.version: str = ""
        self.load_error: str = ""
        self.load()

    # ---------- 加载 ----------

    def load(self) -> None:
        self.entries = []
        self.categories = []
        self.load_error = ""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.load_error = f"项目知识库文件不存在：{self.path}"
            return
        except (OSError, ValueError) as exc:
            self.load_error = f"项目知识库读取失败：{exc}"
            return

        if not isinstance(raw, dict):
            self.load_error = "项目知识库格式错误：顶层应为对象"
            return

        self.version = str(raw.get("version", ""))
        self.categories = [c for c in raw.get("categories", []) if isinstance(c, dict)]
        for item in raw.get("entries", []):
            if isinstance(item, dict) and item.get("id"):
                self.entries.append(KBEntry.from_dict(item))
        if not self.entries:
            self.load_error = "项目知识库为空，请检查 data/project_kb.json"

    # ---------- 查询 ----------

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, entry_id: str) -> KBEntry | None:
        target = (entry_id or "").strip().upper()
        for entry in self.entries:
            if entry.id.upper() == target:
                return entry
        return None

    def category_id(self, entry: KBEntry) -> str:
        return entry.category

    def category_stats(self) -> list[dict]:
        """按 CATEGORY_ORDER 输出分类与其条目数，未在常量中的分类排在后面。"""
        buckets: dict[str, int] = {}
        for entry in self.entries:
            buckets[entry.category] = buckets.get(entry.category, 0) + 1
        stats: list[dict] = []
        seen: set[str] = set()
        for meta in self.categories:
            cid = str(meta.get("id", ""))
            seen.add(cid)
            stats.append(
                {
                    "id": cid,
                    "name": str(meta.get("name", cid)),
                    "desc": str(meta.get("desc", "")),
                    "entries": buckets.get(cid, 0),
                }
            )
        for cid, count in buckets.items():
            if cid not in seen:
                stats.append({"id": cid, "name": cid, "desc": "", "entries": count})
        order = {cid: i for i, cid in enumerate(CATEGORY_ORDER)}
        stats.sort(key=lambda item: (order.get(item["id"], 99), item["id"]))
        return stats

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 3,
        min_score: float = 0.18,
    ) -> list[KBHit]:
        text = normalize(query)
        if not text:
            return []
        target_category = (category or "").strip().lower()
        q_grams = bigrams(query)
        hits: list[KBHit] = []

        for entry in self.entries:
            if target_category and entry.category.lower() != target_category:
                continue

            score = 0.0
            matched: list[str] = []

            # 1) 符号命中：查询里直接出现类名/方法名，信号最强
            if entry.symbol and normalize(entry.symbol) in text:
                score += 0.50
                matched.append(entry.symbol)

            # 2) 标签命中
            tag_hits = 0
            for tag in entry.tags:
                key = normalize(tag)
                if len(key) >= 2 and key in text and tag_hits < 4:
                    score += 0.18
                    matched.append(tag)
                    tag_hits += 1

            # 3) 标题与正文的字符级相似度
            score += dice(q_grams, bigrams(entry.title)) * 0.45
            score += dice(q_grams, bigrams(entry.summary + entry.details)) * 0.25

            if score <= 0:
                continue
            normalized = 1 - math.exp(-1.1 * score)
            if normalized >= min_score:
                hits.append(KBHit(entry=entry, score=normalized, matched=matched))

        hits.sort(key=lambda h: (-h.score, h.entry.id))
        return hits[: max(1, min(5, top_k))]
