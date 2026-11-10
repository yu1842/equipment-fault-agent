"""测试入口（免安装运行）：

    python run_tests.py            # 运行全部测试
    python run_tests.py -v         # 详细输出
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    verbosity = 2 if "-v" in sys.argv else 1
    suite = unittest.TestLoader().discover(
        start_dir=str(ROOT / "tests"), top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
