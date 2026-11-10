"""知识库倒排索引：加速检索，并保证"数据改了索引跟着变"。

索引文件 data/kb_index.json 记录源数据哈希，加载时比对：
  * 哈希一致 → 用倒排表缩小候选集（terms → entry_ids）
  * 哈希不一致 / 缺失 → 退回线性扫描，并把状态标记为 stale/missing，
    由 tools/verify_kb.py 与测试提示重建，避免"改了数据但检索还走旧索引"。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .knowledge import bigrams, normalize

INDEX_SCHEMA = 1


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def entry_terms(entry: dict) -> set[str]:
    """一条条目参与索引的词项：ASCII 标识符 + 中文二元组。"""
    terms: set[str] = set()
    for field in ("symbol", "signature", "title", "summary"):
        text = normalize(str(entry.get(field, "")))
        for token in text.replace("/", " ").replace(".", " ").split():
            if len(token) >= 2 and token.isascii():
                terms.add(token)
    for field in ("title", "summary"):
        terms.update(bigrams(str(entry.get(field, ""))))
    for field in ("aliases", "tags"):
        for value in entry.get(field, []) or []:
            terms.update(bigrams(str(value)))
            token = normalize(str(value))
            if len(token) >= 2 and token.isascii():
                terms.add(token)
    return {t for t in terms if t}


def case_terms(entry: dict) -> set[str]:
    """案例参与索引的词项：设备名、现象与关键词的二元组，外加 ASCII 型号。"""
    terms: set[str] = set()
    for field in ("equipment", "symptom", "model"):
        terms.update(bigrams(str(entry.get(field, ""))))
    for kw in entry.get("keywords", []) or []:
        terms.update(bigrams(str(kw)))
        token = normalize(str(kw))
        if len(token) >= 2 and token.isascii():
            terms.add(token)
    return {t for t in terms if t}


def build_case_index(cases_path: str | Path) -> dict:
    path = Path(cases_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases", []) if isinstance(raw, dict) else raw
    postings: dict[str, list[str]] = {}
    for item in cases:
        cid = str(item.get("id", ""))
        for term in case_terms(item):
            postings.setdefault(term, []).append(cid)
    return {
        "schema": INDEX_SCHEMA,
        "kb_file": path.name,
        "kb_hash": file_hash(path),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "entries": len(cases),
        "terms": len(postings),
        "postings": {k: sorted(set(v)) for k, v in postings.items()},
    }


def build_index(kb_path: str | Path) -> dict:
    path = Path(kb_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    postings: dict[str, list[str]] = {}
    for entry in raw.get("entries", []):
        eid = str(entry.get("id", ""))
        for term in entry_terms(entry):
            postings.setdefault(term, []).append(eid)
    return {
        "schema": INDEX_SCHEMA,
        "kb_file": path.name,
        "kb_hash": file_hash(path),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "entries": len(raw.get("entries", [])),
        "terms": len(postings),
        "postings": {k: sorted(set(v)) for k, v in postings.items()},
    }


def save_index(index: dict, index_path: str | Path) -> Path:
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_index(index_path: str | Path) -> dict | None:
    path = Path(index_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA:
        return None
    return data


def query_terms(question: str) -> set[str]:
    text = normalize(question)
    terms = bigrams(question)
    for token in text.replace("/", " ").replace(".", " ").split():
        if len(token) >= 2 and token.isascii():
            terms.add(token)
    return {t for t in terms if t}
