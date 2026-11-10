"""重建知识库倒排索引（案例库 + 项目知识库）。

    python tools/rebuild_index.py           # 重建两个索引（已最新的会跳过）
    python tools/rebuild_index.py --force   # 强制重建
    python tools/rebuild_index.py --check   # 只检查索引是否与数据同步

数据改动后必须执行一次，否则加载方会标记 stale 并退回线性扫描
（检索结果不变，但失去加速）。
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

TARGETS = [
    ("案例库", DATA_DIR / "fault_cases.json", DATA_DIR / "case_index.json", kb_index.build_case_index),
    ("项目知识库", DATA_DIR / "project_kb.json", DATA_DIR / "kb_index.json", kb_index.build_index),
]


def main() -> int:
    check_only = "--check" in sys.argv
    failed = 0
    for name, data_path, index_path, builder in TARGETS:
        current = kb_index.file_hash(data_path)
        data = kb_index.load_index(index_path)

        if check_only:
            if data is None:
                print(f"{name}：索引不存在，请执行 python tools/rebuild_index.py")
                failed += 1
            elif data.get("kb_hash") != current:
                print(f"{name}：索引已过期（数据哈希不一致），请重建")
                failed += 1
            else:
                print(f"{name}：索引同步（{data['entries']} 条 / {data['terms']} 个索引词，建于 {data['built_at']}）")
            continue

        if data is not None and data.get("kb_hash") == current and "--force" not in sys.argv:
            print(f"{name}：已是最新，跳过（{data['entries']} 条 / {data['terms']} 个索引词）")
            continue

        index = builder(data_path)
        kb_index.save_index(index, index_path)
        print(f"{name}：已重建 {index['entries']} 条 / {index['terms']} 个索引词 -> {index_path.name}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
