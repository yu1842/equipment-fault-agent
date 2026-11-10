"""测试包：导入时把 src 目录加入 sys.path，保证免安装即可运行测试。"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
