"""构建《代码审查与调试记录》Word 版（正文 + 6 张证据截图）。

用法：python tools/build_review_doc.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx_build as db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "代码审查与调试记录.md"
COVER = ROOT / "docs" / "_cover_review.md"
EVID = ROOT / "docs" / "evidence"
OUT = ROOT.parent / "代码审查与调试记录.docx"

# (占位符, 图片, 目标宽度像素)
FIGURES = [
    ("[[FIG1]]", EVID / "shot-07-vscode.png", 560),
    ("[[FIG2]]", EVID / "shot-03-pdb.png", 430),
    ("[[FIG3]]", EVID / "shot-04-tests.png", 400),
    ("[[FIG4]]", EVID / "shot-01-app.png", 560),
    ("[[FIG5]]", EVID / "shot-05-unknown.png", 560),
    ("[[FIG6]]", EVID / "shot-06-empty.png", 560),
]


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    return struct.unpack(">II", head[16:24])


def insert_figures(file_id: str) -> None:
    for marker, image, width in FIGURES:
        found = db.call("doc_find", file_id=file_id, text=marker)
        locations = found.get("locations") or []
        if not locations:
            print(f"  未找到 {marker}，跳过")
            continue
        raw_w, raw_h = png_size(image)
        height = max(1, round(width * raw_h / raw_w))  # 按原图比例给 h，避免拉伸
        db.call(
            "doc_insert_image",
            file_id=file_id,
            idx=int(locations[0]["begin"]),
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
        print(f"  {marker} -> {image.name} {width}x{height}")


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
        print("插入截图…")
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
