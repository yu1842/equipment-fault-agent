"""把 Markdown 构建为排版规范的 Word 文档。

三条踩坑后固化的经验：
1. 单次插入过长内容会整段失败（InsertMarkdown: HTML segment insertion failed），
   因此按标题边界切块；
2. 插入失败时编辑器**可能已写入半截内容**，同一文档内重试会造成重复，
   所以失败必须整份重建，并逐级减小块大小（2200 → 1200 → 700）；
3. 每次插入前用 doc_get_last_operable_pos 取真实末尾位置，避免 position 回包不准导致乱序。

用法：
    python tools/docx_build.py
    python tools/docx_build.py --source docs/知识库更新报告.md \
        --cover docs/_cover_report.md --output "../知识库更新报告_v2.0.docx"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path(
    r"D:/workbuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/workbuddy-local-office-edit"
)
EDSDK = SKILL_DIR / "edsdk.py"
SOURCE_MD = ROOT / "docs" / "项目交付文档.md"
COVER_MD = ROOT / "docs" / "_cover.md"
DEFAULT_OUT = ROOT.parent / "设备故障咨询Agent_项目交付文档.docx"

CHUNK_LIMITS = (900, 600, 400)


# ---------------------------------------------------------------- 调用封装


def call(tool: str, **args) -> dict:
    cmd = [sys.executable, str(EDSDK), "call", tool, "--json", json.dumps(args, ensure_ascii=False)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(f"{tool} 返回失败：{payload.get('error')}")
        return payload
    # create_doc / save_file 返回的是人类可读文本
    match = re.search(r"file_id=(\S+?)[,\s]", proc.stdout or "")
    if match:
        return {"file_id": match.group(1)}
    if "File saved to" in (proc.stdout or ""):
        return {"ok": True}
    raise RuntimeError(f"{tool} 调用失败：{proc.stdout}\n{proc.stderr}")


def position_of(result: dict, file_id: str, fallback: int = 0) -> int:
    pos = result.get("position")
    if pos is None:
        pos = result.get("last_edit_index")
    if pos is None:
        pos = call("doc_get_last_operable_pos", file_id=file_id).get("position", fallback)
    return int(pos)


# ---------------------------------------------------------------- 切块与排版


def split_markdown(text: str, limit: int = 600) -> list[str]:
    """按空行切段落块，并合并到不超过 limit；代码块内部不切分。

    实测：单次插入上千字（或含长表格）容易整段失败，
    而按段落块插入稳定，因此块大小宁小勿大。
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for block in blocks:
        text_block = "".join(block)
        if buf and size + len(text_block) > limit:
            chunks.append("".join(buf).rstrip() + "\n\n")
            buf, size = [], 0
        buf.append(text_block)
        size += len(text_block)
    if buf:
        chunks.append("".join(buf).rstrip() + "\n\n")
    return chunks


def style_cover(file_id: str) -> None:
    """封面：前两个标题居中放大；坐标从文档结构取，换文案也不会错位。"""
    print("封面排版…")
    try:
        structure = call("doc_resolve_document_structure", file_id=file_id, mode="compact", limit=4)
        headings = [
            node
            for node in structure.get("nodes", [])
            if node.get("type") in ("Heading", "Title", "Subtitle")
        ][:2]
        if len(headings) < 2:
            print("  未找到两个封面标题，跳过")
            return
        title = {"begin": int(headings[0]["start_index"]), "end": int(headings[0]["end_index"])}
        subtitle = {"begin": int(headings[1]["start_index"]), "end": int(headings[1]["end_index"])}
        call("doc_modify_paragraph", file_id=file_id, ranges=[title], jc="center",
             spacing_before=120, spacing_after=10)
        call("doc_update_text_property", file_id=file_id, ranges=[title],
             font_size=24, bold=True, color="1F3864")
        call("doc_modify_paragraph", file_id=file_id, ranges=[subtitle], jc="center",
             spacing_before=4, spacing_after=28)
        call("doc_update_text_property", file_id=file_id, ranges=[subtitle],
             font_size=13, color="6B7280")
    except RuntimeError as exc:
        print(f"  封面排版跳过：{exc}")


def enable_field_update(path: Path) -> None:
    """打开 updateFields，Word 打开时刷新目录域。"""
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/settings.xml":
                text = data.decode("utf-8")
                if "updateFields" not in text:
                    text = text.replace("</w:settings>", '<w:updateFields w:val="true"/></w:settings>')
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(str(tmp), str(path))


# ---------------------------------------------------------------- 构建流程


def build_document(cover_path: Path, source: str, limit: int) -> tuple[str, int]:
    """在新建文档里插入封面与正文，返回 (file_id, 正文起始位置)。失败直接抛出。"""
    chunks = split_markdown(source, limit)
    print(f"正文 {len(source)} 字，按 {limit} 字切块，共 {len(chunks)} 块")

    file_id = call("create_doc")["file_id"]
    cover = call("doc_insert_markdown", file_id=file_id, idx=0,
                 markdown=f"file://{cover_path.as_posix()}")
    style_cover(file_id)
    pos = position_of(cover, file_id)
    brk = call("doc_insert_page_break", file_id=file_id, idx=pos)
    content_start = position_of(brk, file_id, pos)

    tmp_dir = Path(tempfile.mkdtemp(prefix="efa-doc-"))
    for index, chunk in enumerate(chunks, 1):
        chunk_file = tmp_dir / f"chunk-{index:03d}.md"
        chunk_file.write_text(chunk, encoding="utf-8")
        tail = call("doc_get_last_operable_pos", file_id=file_id)
        pos = int(tail.get("position", 0))
        try:
            result = call("doc_insert_markdown", file_id=file_id, idx=pos,
                          markdown=f"file://{chunk_file.as_posix()}")
        except RuntimeError as exc:
            head = chunk.strip().splitlines()[0][:40] if chunk.strip() else ""
            raise RuntimeError(f"第 {index} 块失败（{len(chunk)} 字，起始：{head}）：{exc}") from exc
        print(f"  [{index:02d}/{len(chunks)}] {len(chunk):>5} 字 -> {pos} -> {result.get('position')}")

    return file_id, content_start


def apply_styles(file_id: str) -> None:
    print("设置文档样式…")
    call("doc_set_document_style", file_id=file_id,
         default_text_style={"font_family": "宋体", "font_size": 10.5, "color": "1F2430"},
         default_paragraph_style={"line_spacing": 1.45, "line_spacing_rule": 1, "spacing_after": 4},
         page_style={"top_margin": 72, "bottom_margin": 72, "left_margin": 78, "right_margin": 78})
    for name, size, color, before, after in (
        ("HEADING_1", 17, "1F3864", 18, 10),
        ("HEADING_2", 14, "1F3864", 14, 8),
        ("HEADING_3", 12, "2A6EF5", 10, 6),
    ):
        try:
            call("doc_update_named_style", file_id=file_id, named_style_type=name,
                 paragraph_style={"spacing_before": before, "spacing_after": after},
                 text_style={"font_family": "微软雅黑", "font_size": size, "color": color, "bold": True})
        except RuntimeError as exc:
            print(f"  {name} 样式设置跳过：{exc}")


def insert_toc(file_id: str, content_start: int) -> None:
    print("插入目录…")
    try:
        toc = call("doc_insert_toc", file_id=file_id, idx=content_start, max_level=3, hide_page_number=True)
        toc_pos = position_of(toc, file_id, content_start)
        call("doc_insert_page_break", file_id=file_id, idx=toc_pos)
        print("  目录已插入")
    except RuntimeError as exc:
        print(f"  目录插入失败，跳过：{exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="把 Markdown 构建为 Word 文档")
    parser.add_argument("--source", default=str(SOURCE_MD))
    parser.add_argument("--cover", default=str(COVER_MD))
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    out_path = Path(args.output).resolve()
    source = Path(args.source).resolve().read_text(encoding="utf-8")
    cover_path = Path(args.cover).resolve()

    last_error: Exception | None = None
    for limit in CHUNK_LIMITS:
        try:
            file_id, content_start = build_document(cover_path, source, limit)
        except RuntimeError as exc:
            last_error = exc
            print(f"块大小 {limit} 构建失败，缩小分块后整份重建：{exc}")
            continue

        apply_styles(file_id)
        insert_toc(file_id, content_start)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"保存到 {out_path}")
        call("save_file", file_id=file_id, file_path=str(out_path).replace("\\", "/"))
        try:
            enable_field_update(out_path)
        except OSError as exc:
            print(f"  跳过 updateFields 写入（文件被占用）：{exc}")
        print("完成")
        return 0

    print(f"构建失败：{last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
