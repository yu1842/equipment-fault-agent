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
    "when_to_use",
    "inputs",
    "outputs",
    "scenarios",
    "cautions",
    "scope",
    "version",
    "tags",
    "refs",
)


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

    summary = {
        "entries": len(entries),
        "categories": len(categories),
        "errors": sum(1 for i in issues if i.level == "E"),
        "warnings": sum(1 for i in issues if i.level == "W"),
    }
    return issues, summary
