"""知识库 v1.1 → v2.0 迁移脚本。

做四件事：
  1. 为 52 条既有条目补入 background / steps / troubleshooting / best_practices / related / aliases
  2. 追加 13 条新条目（校验模块、路由、导航/FAQ/术语/排障、打包、审查、容量边界）
  3. 标准化：统一字段顺序、去空白、去重、related 双向闭合、按分类排序
  4. 写入 schema 元信息并输出统计

执行后 data/project_kb.json 为唯一数据源，本脚本保留作为内容来源留痕。
运行：python tools/kb_enrich_v2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "project_kb.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_v2_data1 import ENRICH_1
from kb_v2_data2 import ENRICH_2
from kb_v2_data3 import ENRICH_3
from kb_v2_data4 import NEW_ENTRIES

CATEGORY_ORDER = [
    "guide", "architecture", "module", "api", "tool",
    "data", "config", "error", "dependency", "convention", "boundary",
]

FIELD_ORDER = [
    "id", "category", "title", "summary", "symbol", "signature", "aliases",
    "background", "when_to_use", "inputs", "outputs", "steps", "scenarios",
    "cautions", "troubleshooting", "best_practices", "related", "scope",
    "version", "tags", "refs", "details",
]

NEW_CATEGORIES = [
    {"id": "guide", "name": "导航与速查", "desc": "上手路线、术语表、排障索引、FAQ、维护流程、版本策略"},
]


def clean_str(value) -> str:
    return str(value or "").strip()


def clean_list(values) -> list:
    out: list = []
    seen: set = set()
    for item in values or []:
        if isinstance(item, dict):
            out.append(item)
            continue
        text = clean_str(item)
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out


def normalize_entry(entry: dict) -> dict:
    fixed = {key: entry.get(key) for key in FIELD_ORDER}
    fixed["id"] = clean_str(fixed["id"])
    fixed["category"] = clean_str(fixed["category"])
    fixed["title"] = clean_str(fixed["title"]).rstrip("。.")
    fixed["summary"] = clean_str(fixed["summary"])
    fixed["symbol"] = clean_str(fixed["symbol"])
    fixed["signature"] = clean_str(fixed["signature"])
    fixed["aliases"] = clean_list(fixed["aliases"])
    fixed["background"] = clean_str(fixed["background"])
    fixed["when_to_use"] = clean_list(fixed["when_to_use"])
    fixed["inputs"] = [i for i in (fixed["inputs"] or []) if isinstance(i, dict)]
    fixed["outputs"] = clean_str(fixed["outputs"])
    fixed["steps"] = clean_list(fixed["steps"])
    fixed["scenarios"] = clean_list(fixed["scenarios"])
    fixed["cautions"] = clean_list(fixed["cautions"])
    fixed["troubleshooting"] = [
        {"symptom": clean_str(i.get("symptom")), "check": clean_str(i.get("check")), "fix": clean_str(i.get("fix"))}
        for i in (fixed["troubleshooting"] or [])
        if isinstance(i, dict)
    ]
    fixed["best_practices"] = clean_list(fixed["best_practices"])
    fixed["related"] = clean_list(fixed["related"])
    fixed["scope"] = clean_str(fixed["scope"])
    fixed["version"] = clean_str(fixed["version"])
    fixed["tags"] = clean_list(fixed["tags"])
    fixed["refs"] = clean_list(fixed["refs"])
    fixed["details"] = clean_str(fixed["details"])
    return fixed


def main() -> int:
    raw = json.loads(KB_PATH.read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in raw["entries"]}
    print(f"读入 {len(entries)} 条既有条目")

    enrich = {**ENRICH_1, **ENRICH_2, **ENRICH_3}
    duplicated = set(ENRICH_1) & set(ENRICH_2) | set(ENRICH_1) & set(ENRICH_3) | set(ENRICH_2) & set(ENRICH_3)
    if duplicated:
        print(f"富化数据存在重复编号：{sorted(duplicated)}")
        return 1
    print(f"富化数据 {len(enrich)} 条，新增条目 {len(NEW_ENTRIES)} 条")

    missing = sorted(set(entries) - set(enrich))
    extra = sorted(set(enrich) - set(entries))
    if missing:
        print(f"以下既有条目缺少富化内容：{missing}")
        return 1
    if extra:
        print(f"富化数据中存在未知条目：{extra}")
        return 1

    merged: dict[str, dict] = {}
    for eid, entry in entries.items():
        entry.update(enrich[eid])
        merged[eid] = entry

    for entry in NEW_ENTRIES:
        if entry["id"] in merged:
            print(f"新增条目编号冲突：{entry['id']}")
            return 1
        merged[entry["id"]] = entry

    # related 双向闭合
    for eid, entry in merged.items():
        for target in list(entry.get("related", [])):
            if target == eid:
                entry["related"].remove(target)
            elif target not in merged:
                raise SystemExit(f"{eid} 的 related 指向不存在的条目 {target}")
            elif eid not in merged[target].get("related", []):
                merged[target].setdefault("related", []).append(eid)

    normalized = [normalize_entry(e) for e in merged.values()]
    for entry in normalized:
        if entry["id"] in entry["related"]:
            entry["related"].remove(entry["id"])

    order = {cid: i for i, cid in enumerate(CATEGORY_ORDER)}
    normalized.sort(key=lambda e: (order.get(e["category"], 99), e["id"]))

    categories = NEW_CATEGORIES + [c for c in raw["categories"] if c["id"] != "guide"]
    output = {
        "schema_version": "2.0",
        "version": "2.0.0",
        "project_version": "2.0.0",
        "updated_at": "2026-11-10",
        "description": raw.get("description", ""),
        "field_spec": {
            "id": "KB-<分类缩写>-<三位序号>，全局唯一",
            "summary": "一句话结论，12~90 字，不含换行",
            "aliases": "同义说法 2~6 个，供检索扩召回",
            "background": "为什么需要它，解决什么问题",
            "when_to_use": "调用条件，2~4 条",
            "inputs": "参数规范，非 API 类可为空数组",
            "outputs": "输出格式或副作用，非 API 类可为空",
            "steps": "实操步骤 2~5 条，按执行顺序",
            "scenarios": "使用场景 2~4 条",
            "cautions": "注意事项 1~5 条，写禁止做法",
            "troubleshooting": "排障项，每项含 symptom/check/fix",
            "best_practices": "最佳实践 2~4 条",
            "related": "交叉引用条目编号，双向闭合",
            "scope": "适用范围，指向具体文件或子系统",
            "version": "起始适用版本，形如 >=2.0.0",
            "tags": "检索标签 3~6 个",
            "refs": "源码或文档出处，必须真实存在",
        },
        "categories": categories,
        "entries": normalized,
    }
    KB_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    avg_related = sum(len(e["related"]) for e in normalized) / len(normalized)
    print(f"写入 {KB_PATH.name}：{len(normalized)} 条，{len(categories)} 个分类")
    print(f"交叉引用平均 {avg_related:.1f} 条/节点")
    for cat in categories:
        count = sum(1 for e in normalized if e["category"] == cat["id"])
        print(f"  {cat['id']:<13}{count:>3} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
