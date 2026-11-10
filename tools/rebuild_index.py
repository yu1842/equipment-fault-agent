"""重建知识库倒排索引。

    python tools/rebuild_index.py           # 重建并写入 data/kb_index.json
    python tools/rebuild_index.py --check   # 只检查索引是否与数据同步

数据改动后必须执行一次，否则 ProjectKB 会标记 stale 并退回线性扫描
（检索结果不变，但失去加速，且 verify_kb 会给出提示）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from efa import kb_index  # noqa: E402
from efa.config import DATA_DIR  # noqa: E402

KB_PATH = DATA_DIR / "project_kb.json"
INDEX_PATH = DATA_DIR / "kb_index.json"


def main() -> int:
    check_only = "--check" in sys.argv
    current = kb_index.file_hash(KB_PATH)
    data = kb_index.load_index(INDEX_PATH)

    if check_only:
        if data is None:
            print("索引不存在，请执行 python tools/rebuild_index.py")
            return 1
        if data.get("kb_hash") != current:
            print("索引已过期（数据哈希不一致），请重建")
            return 1
        print(f"索引同步：{data['entries']} 条、{data['terms']} 个索引词，建于 {data['built_at']}")
        return 0

    index = kb_index.build_index(KB_PATH)
    kb_index.save_index(index, INDEX_PATH)
    print(f"索引已重建：{index['entries']} 条、{index['terms']} 个索引词 -> {INDEX_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
