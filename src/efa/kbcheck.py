"""项目知识库一致性校验：把 data/project_kb.json 与真实源码逐项比对。

校验维度：
  1. 结构：字段齐全、ID 唯一、分类存在且无孤儿分类
  2. 引用：refs 中的文件/目录必须真实存在
  3. 符号：条目声明的类/方法/字段必须在源码 AST 中存在
  4. 签名：文档括号内的参数名必须与真实函数参数一致
  5. 契约：工具条目与 ToolRegistry.specs() 的工具集合必须一致
  6. 配置：KB-CFG-001 列出的字段必须与 Settings 数据类字段一致
  7. 数字：正文中"当前 N 个工具 / 当前 N 类设备"等断言必须与运行时一致

任一错误（E）都会让 `python tools/verify_kb.py` 以非 0 退出，测试套件也会失败。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = (
    "id",
    "category",
    "title",
    "summary",
    "details",
    "aliases",
    "background",
    "when_to_use",
    "inputs",
    "outputs",
    "steps",
    "scenarios",
    "cautions",
    "troubleshooting",
    "best_practices",
    "related",
    "scope",
    "version",
    "tags",
    "refs",
)

# 条目编号前缀与分类必须一致，避免检索过滤时对不上
ID_PREFIX = {
    "KB-GUIDE": "guide",
    "KB-ARCH": "architecture",
    "KB-MOD": "module",
    "KB-API": "api",
    "KB-TOOL": "tool",
    "KB-DATA": "data",
    "KB-CFG": "config",
    "KB-ERR": "error",
    "KB-DEP": "dependency",
    "KB-CONV": "convention",
    "KB-BND": "boundary",
}

PLACEHOLDER_WORDS = ("TODO:", "待补充", "待完善", "示例文本", "暂无内容", "占位符", "TBD")
VERSION_PATTERN = re.compile(r"^>=\d+\.\d+\.\d+$")


@dataclass
class Issue:
    level: str  # E = 错误，W = 警告
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


# ---------------------------------------------------------------- 符号索引


def build_symbol_index(paths) -> dict[str, dict]:
    """扫描源码，建立 “类名 / 类名.方法 / 模块级函数” → 参数与字段 的索引。"""
    index: dict[str, dict] = {}
    for path in paths:
        try:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        path = Path(path)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                index.setdefault(node.name, {"params": _params(node), "kind": "func", "file": path})
            elif isinstance(node, ast.ClassDef):
                fields = {
                    stmt.target.id
                    for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                }
                index.setdefault(node.name, {"params": [], "kind": "class", "file": path, "fields": fields})
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        key = f"{node.name}.{sub.name}"
                        index[key] = {"params": _params(sub), "kind": "method", "file": path}
                for name in fields:
                    index[f"{node.name}.{name}"] = {"params": [], "kind": "field", "file": path}
    return index


def _params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names = [a.arg for a in func.args.args]
    return [n for n in names if n not in ("self", "cls")]


def _documented_params(signature: str, symbol: str) -> list[str] | None:
    """从 "ask(self, question: str) -> Answer" 里提取参数名；无法解析返回 None。"""
    match = re.match(r"\s*([A-Za-z_][\w.]*)\s*\(([^)]*)\)", signature or "")
    if not match:
        return None
    name, raw = match.group(1), match.group(2)
    if symbol and name.split(".")[-1] != symbol.split(".")[-1]:
        return None
    params: list[str] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        token = re.split(r"[:=]", token, maxsplit=1)[0].strip()
        if token in ("self", "cls"):
            continue
        if token.startswith("*") or token.isidentifier():
            params.append(token.lstrip("*"))
    return params


# ---------------------------------------------------------------- 主校验


def verify(project_root: str | Path) -> tuple[list[Issue], dict]:
    root = Path(project_root).resolve()
    issues: list[Issue] = []
    kb_path = root / "data" / "project_kb.json"
    src_root = root / "src" / "efa"

    try:
        raw = json.loads(kb_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Issue("E", "KB_LOAD", f"无法读取 {kb_path}：{exc}")], {}

    entries: list[dict] = raw.get("entries", [])
    categories = {str(c.get("id")): str(c.get("name", "")) for c in raw.get("categories", [])}

    # 1. 结构
    seen_ids: set[str] = set()
    for entry in entries:
        eid = str(entry.get("id", "?"))
        if eid in seen_ids:
            issues.append(Issue("E", "DUP_ID", f"{eid} 编号重复"))
        seen_ids.add(eid)
        for field in REQUIRED_FIELDS:
            if field not in entry:
                issues.append(Issue("E", "MISSING_FIELD", f"{eid} 缺少字段 {field}"))
        if entry.get("category") not in categories:
            issues.append(
                Issue("E", "BAD_CATEGORY", f"{eid} 的分类 {entry.get('category')!r} 未在 categories 中定义")
            )
        for list_field in ("when_to_use", "cautions", "tags"):
            if not entry.get(list_field):
                issues.append(Issue("W", "EMPTY_LIST", f"{eid} 的 {list_field} 为空，信息完整度不足"))

    used = {str(e.get("category")) for e in entries}
    for cid in categories:
        if cid not in used:
            issues.append(Issue("W", "ORPHAN_CATEGORY", f"分类 {cid} 没有任何条目"))

    # 2. 引用文件
    for entry in entries:
        for ref in entry.get("refs", []):
            path_text = re.split(r"[#\s]", str(ref))[0].strip()
            if not path_text:
                continue
            target = root / path_text
            if not target.exists():
                issues.append(Issue("E", "BAD_REF", f"{entry.get('id')} 引用了不存在的路径 {path_text}"))

    # 3/4. 符号与签名
    source_paths = sorted(src_root.rglob("*.py")) + [root / "app.py"]
    symbols = build_symbol_index(source_paths)
    for entry in entries:
        symbol = str(entry.get("symbol", "")).strip()
        if not symbol:
            continue
        # 工具名是注册表键而非 Python 符号，交由第 5 步的工具契约校验
        if entry.get("category") == "tool":
            continue
        if symbol not in symbols:
            issues.append(Issue("E", "BAD_SYMBOL", f"{entry.get('id')} 声明的符号 {symbol} 在源码中不存在"))
            continue
        documented = _documented_params(str(entry.get("signature", "")), symbol)
        if documented is None:
            continue
        info = symbols[symbol]
        if info.get("kind") == "class":
            # 类条目里的括号写的是数据类字段，按集合比对（顺序无关）
            actual_fields = set(info.get("fields") or ())
            if actual_fields and set(documented) != actual_fields:
                issues.append(
                    Issue(
                        "E",
                        "BAD_FIELDS",
                        f"{entry.get('id')} 文档字段 {sorted(documented)} 与实际 "
                        f"{sorted(actual_fields)} 不一致（{symbol}）",
                    )
                )
            continue
        actual = info.get("params") or []
        if documented and actual[: len(documented)] != documented:
            issues.append(
                Issue(
                    "E",
                    "BAD_SIGNATURE",
                    f"{entry.get('id')} 文档参数 {documented} 与实际 {actual} 不一致（{symbol}）",
                )
            )

    # 4.5 倒排索引同步
    try:
        from efa import kb_index

        index_path = root / "data" / "kb_index.json"
        data = kb_index.load_index(index_path)
        if data is None:
            issues.append(
                Issue("W", "INDEX_MISSING", "缺少 data/kb_index.json，请执行 python tools/rebuild_index.py")
            )
        elif data.get("kb_hash") != kb_index.file_hash(kb_path):
            issues.append(
                Issue("W", "INDEX_STALE", "索引与数据不同版本，请执行 python tools/rebuild_index.py")
            )
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue("W", "INDEX_CHECK_FAIL", f"索引检查未执行：{exc}"))

    # 4.6 可检索性：用条目自己的标题检索，必须排第一
    try:
        from efa.project_kb import ProjectKB

        probe = ProjectKB(kb_path)
        for entry in probe.entries:
            hits = probe.search(entry.title, top_k=1)
            if not hits or hits[0].entry.id != entry.id:
                got = hits[0].entry.id if hits else "无命中"
                issues.append(
                    Issue("E", "NOT_SEARCHABLE", f"{entry.id} 用自己的标题检索不到自己（Top1={got}），请补 aliases 或调整标题")
                )
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue("W", "SEARCH_CHECK_FAIL", f"可检索性检查未执行：{exc}"))

    # 5. 工具契约
    try:
        from efa.knowledge import KnowledgeBase
        from efa.project_kb import ProjectKB
        from efa.tools import ToolRegistry

        kb = KnowledgeBase(root / "data" / "fault_cases.json")
        pkb = ProjectKB(kb_path)
        registry = ToolRegistry(kb, project_kb=pkb)
        spec_names = {item["function"]["name"] for item in registry.specs()}
        doc_tool_names = {
            str(e.get("symbol", ""))
            for e in entries
            if e.get("category") == "tool" and e.get("symbol")
        }
        for name in sorted(doc_tool_names - spec_names):
            issues.append(Issue("E", "TOOL_NOT_EXPOSED", f"知识库写了工具 {name}，但 specs() 未暴露"))
        for name in sorted(spec_names - doc_tool_names):
            issues.append(Issue("E", "TOOL_UNDOCUMENTED", f"specs() 暴露了工具 {name}，但知识库没有对应条目"))
    except Exception as exc:  # noqa: BLE001 - 校验脚本本身不能因为导入失败而崩
        kb, registry = None, None
        issues.append(Issue("E", "IMPORT_FAIL", f"无法导入项目模块完成契约校验：{exc}"))

    # 6. 配置字段
    try:
        from efa.config import Settings

        settings_fields = set(Settings.__dataclass_fields__)
        cfg_entry = next((e for e in entries if e.get("id") == "KB-CFG-001"), None)
        if cfg_entry:
            documented_fields = {
                token.strip()
                for token in str(cfg_entry.get("signature", "")).split("/")
                if token.strip()
            }
            if documented_fields != settings_fields:
                issues.append(
                    Issue(
                        "E",
                        "CFG_DRIFT",
                        f"KB-CFG-001 字段 {sorted(documented_fields)} 与 Settings {sorted(settings_fields)} 不一致",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        issues.append(Issue("E", "IMPORT_FAIL", f"无法导入 Settings 校验配置字段：{exc}"))

    # 7. 正文中的数字断言
    for entry in entries:
        details = str(entry.get("details", ""))
        tool_claim = re.search(r"当前暴露\s*(\d+)\s*个工具", details)
        if tool_claim and registry is not None:
            actual = len(registry.specs())
            if int(tool_claim.group(1)) != actual:
                issues.append(
                    Issue("E", "STALE_NUMBER", f"{entry.get('id')} 写“{tool_claim.group(0)}”，实际 {actual} 个")
                )
        equip_claim = re.search(r"当前\s*(\d+)\s*类", details)
        if equip_claim and kb is not None:
            actual = len(kb.equipment_names())
            if int(equip_claim.group(1)) != actual:
                issues.append(
                    Issue("E", "STALE_NUMBER", f"{entry.get('id')} 写“{equip_claim.group(0)}”，实际 {actual} 类")
                )

    # 8. 标准化与信息粒度
    ids = {str(e.get("id")) for e in entries}
    titles: dict[str, str] = {}
    for entry in entries:
        eid = str(entry.get("id", "?"))

        prefix = eid.rsplit("-", 1)[0]
        expected = ID_PREFIX.get(prefix)
        if expected is None:
            issues.append(Issue("E", "BAD_ID_PREFIX", f"{eid} 的编号前缀不在约定表内"))
        elif expected != entry.get("category"):
            issues.append(
                Issue("E", "ID_CATEGORY_MISMATCH", f"{eid} 前缀应为 {expected}，实际分类 {entry.get('category')}")
            )

        title = str(entry.get("title", ""))
        key = title.strip()
        if key in titles:
            issues.append(Issue("E", "DUP_TITLE", f"{eid} 与 {titles[key]} 标题重复：{key}"))
        titles[key] = eid
        if not (6 <= len(title) <= 40):
            issues.append(Issue("W", "TITLE_LENGTH", f"{eid} 标题长度 {len(title)}，建议 6~40 字"))

        summary = str(entry.get("summary", ""))
        if not (12 <= len(summary) <= 90):
            issues.append(Issue("W", "SUMMARY_LENGTH", f"{eid} 摘要长度 {len(summary)}，建议 12~90 字"))

        if len(str(entry.get("background", ""))) < 12:
            issues.append(Issue("W", "BACKGROUND_THIN", f"{eid} 背景说明过短，缺少设计动机"))

        if not VERSION_PATTERN.match(str(entry.get("version", ""))):
            issues.append(Issue("E", "BAD_VERSION", f"{eid} 版本约束 {entry.get('version')!r} 应为 >=x.y.z"))

        for name, low, high in (
            ("aliases", 2, 6),
            ("steps", 2, 6),
            ("cautions", 1, 6),
            ("best_practices", 2, 5),
            ("tags", 3, 8),
            ("related", 2, 12),
        ):
            count = len(entry.get(name) or [])
            if count < low:
                issues.append(Issue("W", "TOO_FEW", f"{eid} 的 {name} 只有 {count} 条，建议至少 {low} 条"))
            elif count > high:
                issues.append(Issue("W", "TOO_MANY", f"{eid} 的 {name} 有 {count} 条，建议不超过 {high} 条"))

        for item in entry.get("troubleshooting") or []:
            if not isinstance(item, dict):
                issues.append(Issue("E", "BAD_TROUBLESHOOTING", f"{eid} 排障项应为对象"))
                continue
            for key_name in ("symptom", "check", "fix"):
                if not str(item.get(key_name, "")).strip():
                    issues.append(
                        Issue("E", "BAD_TROUBLESHOOTING", f"{eid} 排障项缺少 {key_name}")
                    )

        for rid in entry.get("related") or []:
            if rid == eid:
                issues.append(Issue("E", "SELF_REFERENCE", f"{eid} 的 related 引用了自己"))
            elif rid not in ids:
                issues.append(Issue("E", "DANGLING_RELATED", f"{eid} 的 related 指向不存在的 {rid}"))
            else:
                target = next(e for e in entries if e.get("id") == rid)
                if eid not in (target.get("related") or []):
                    issues.append(
                        Issue("W", "ASYMMETRIC_RELATED", f"{eid} 引用了 {rid}，但 {rid} 未回引")
                    )

        blob = " ".join(
            [
                title,
                summary,
                str(entry.get("background", "")),
                str(entry.get("details", "")),
                " ".join(str(x) for x in entry.get("steps", [])),
            ]
        )
        for word in PLACEHOLDER_WORDS:
            if word in blob:
                issues.append(Issue("E", "PLACEHOLDER", f"{eid} 含占位词 {word}"))

    summary_info = {
        "entries": len(entries),
        "categories": len(categories),
        "errors": sum(1 for i in issues if i.level == "E"),
        "warnings": sum(1 for i in issues if i.level == "W"),
    }
    return issues, summary_info
