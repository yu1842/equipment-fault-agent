"""构建《AI 代码生成自检记录》Word 版：正文 + 两张真实界面截图。

流程：复用 docx_build 的排版能力，正文插入完成后按占位符定位插图，
再把占位符替换为空，保证图片独占一段、图题紧随其下。

用法：
    python tools/build_selfcheck_doc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx_build as db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "AI代码生成自检记录.md"
COVER = ROOT / "docs" / "_cover_selfcheck.md"
EVID = ROOT / "docs" / "evidence"
OUT = ROOT.parent / "AI代码生成自检记录.docx"

FIGURES = [
    # (占位符, 图片, 宽, 高)：按截图实际比例 1180×760 传 w/h，否则默认比例会拉伸
    ("[[FIG1]]", EVID / "shot-02-kb.png", 560, 361),
    ("[[FIG2]]", EVID / "shot-01-app.png", 560, 361),
]


def insert_figures(file_id: str) -> None:
    for marker, image, width, height in FIGURES:
        found = db.call("doc_find", file_id=file_id, text=marker)
        locations = found.get("locations") or []
        if not locations:
            print(f"  未找到占位符 {marker}，跳过")
            continue
        begin = int(locations[0]["begin"])
        db.call(
            "doc_insert_image",
            file_id=file_id,
            idx=begin,
            image_path=str(image).replace("\\", "/"),
            w=width,
            h=height,
        )
        again = db.call("doc_find", file_id=file_id, text=marker).get("locations") or []
        if again:
            db.call(
                "doc_replace_text",
                file_id=file_id,
                ranges=[{"begin": int(again[0]["begin"]), "end": int(again[0]["end"])}],
                text="",
            )
        print(f"  {marker} -> {image.name}")


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    last_error: Exception | None = None
    for limit in db.CHUNK_LIMITS:
        try:
            file_id, content_start = db.build_document(COVER, source, limit)
        except RuntimeError as exc:
            last_error = exc
            print(f"块大小 {limit} 构建失败，缩小分块后整份重建：{exc}")
            continue

        db.apply_styles(file_id)
        db.insert_toc(file_id, content_start)
        print("插入插图…")
        insert_figures(file_id)

        OUT.parent.mkdir(parents=True, exist_ok=True)
        print(f"保存到 {OUT}")
        db.call("save_file", file_id=file_id, file_path=str(OUT).replace("\\", "/"))
        try:
            db.enable_field_update(OUT)
        except OSError as exc:
            print(f"  跳过 updateFields 写入（文件被占用）：{exc}")
        print("完成")
        return 0

    print(f"构建失败：{last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
