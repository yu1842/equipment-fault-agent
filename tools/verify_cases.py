"""案例知识库校验命令行入口。

    python tools/verify_cases.py            # 校验并打印报告
    python tools/verify_cases.py --quiet    # 只输出结论
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from efa.casecheck import verify  # noqa: E402


def main() -> int:
    quiet = "--quiet" in sys.argv
    issues, summary = verify(ROOT)
    if not summary:
        for issue in issues:
            print(issue)
        return 1

    errors = [i for i in issues if i.level == "E"]
    warnings = [i for i in issues if i.level == "W"]

    if not quiet:
        print("案例知识库质量校验")
        print("=" * 56)
        print(f"案例数：{summary['cases']}　设备类型：{summary['equipment']} 类")
        print(f"错误：{summary['errors']}　警告：{summary['warnings']}")
        print("-" * 56)
        for issue in errors + warnings:
            print(issue)
        print("-" * 56)

    if errors:
        print(f"校验未通过：{len(errors)} 个错误，{len(warnings)} 个警告")
        return 1
    print(f"校验通过：{summary['cases']} 条案例、{summary['equipment']} 类设备，{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
