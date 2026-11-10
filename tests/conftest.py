"""测试引导：把 src 加入导入路径，使测试可在未安装包的情况下直接运行。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
