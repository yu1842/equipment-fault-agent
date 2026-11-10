"""项目知识库校验命令行入口。

    python tools/verify_kb.py           # 校验并打印报告，有错误时退出码为 1
    python tools/verify_kb.py --quiet   # 只输出结论

校验规则实现见 src/efa/kbcheck.py，测试套件会对同一函数做断言，
因此“文档与代码不一致”会在提交前被拦下。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from efa.kbcheck import verify  # noqa: E402


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
        print("项目知识库一致性校验")
        print("=" * 56)
        print(f"条目数：{summary['entries']}　分类数：{summary['categories']}")
        print(f"错误：{summary['errors']}　警告：{summary['warnings']}")
        print("-" * 56)
        for issue in errors + warnings:
            print(issue)
        print("-" * 56)

    if errors:
        print(f"校验未通过：{len(errors)} 个错误，{len(warnings)} 个警告")
        return 1
    print(f"校验通过：{summary['entries']} 条知识、{summary['categories']} 个分类，"
          f"{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
