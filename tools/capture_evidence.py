"""采集自检证据：把真实运行的输出写入 docs/evidence/。

用法：python tools/capture_evidence.py
本脚本只读取项目数据、不修改任何业务文件，输出用于交付文档中的“日志证据”。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "evidence"
sys.path.insert(0, str(ROOT / "src"))

from efa.config import DATA_DIR  # noqa: E402
from efa.knowledge import KnowledgeBase  # noqa: E402


def case_negative() -> str:
    kb = KnowledgeBase(DATA_DIR / "fault_cases.json")
    lines = [
        "复现命令：python tools/capture_evidence.py --case negative",
        f"案例库：{len(kb)} 条 / {len(kb.equipment_names())} 类设备",
        "",
        "【旧负例】注塑机模具冷却水路堵塞，模温降不下来",
        "（v2.1 时知识库无注塑机案例，该问题必为空命中；v2.2 新增 EFA-013 后不再成立）",
    ]
    hits = kb.search("注塑机模具冷却水路堵塞，模温降不下来", top_k=3)
    for i, h in enumerate(hits, 1):
        lines.append(f"  Top{i}  {h.case.id}  {h.case.equipment}  score={h.score:.3f}")
    lines.append(f"  结论：命中 {len(hits)} 条 → 该负例已失效，测试断言 '期望空命中' 必然失败")
    lines.append("")
    lines.append("【新负例】数控冲床送料机构卡料，送不到位")
    lines.append("（库外设备，知识库无任何冲床案例）")
    hits2 = kb.search("数控冲床送料机构卡料，送不到位", top_k=3)
    for i, h in enumerate(hits2, 1):
        lines.append(f"  Top{i}  {h.case.id}  {h.case.equipment}  score={h.score:.3f}")
    lines.append(f"  结论：命中 {len(hits2)} 条 → 仍是有效负例")
    return "\n".join(lines)


def case_layout() -> str:
    """Tkinter 布局读数：update_idletasks() 与 update() 的差异。"""
    from efa.ui import FaultAgentApp

    lines = ["复现命令：python tools/capture_evidence.py --case layout", ""]
    app = FaultAgentApp()
    app.update_idletasks()
    lines.append("只调用 update_idletasks()：")
    lines.append(f"  winfo_width  = {app.winfo_width()}")
    lines.append(f"  winfo_height = {app.winfo_height()}")
    lines.append(f"  chat 宽度     = {app.chat.winfo_width()}   <- 子控件仍为 1，断言 'chat 宽度 > 100' 必失败")
    app.update()
    lines.append("")
    lines.append("补充调用 update() 后：")
    lines.append(f"  winfo_width  = {app.winfo_width()}")
    lines.append(f"  winfo_height = {app.winfo_height()}")
    lines.append(f"  chat 尺寸     = {app.chat.winfo_width()} x {app.chat.winfo_height()}")
    lines.append(f"  input 高度    = {app.input.winfo_height()}")
    lines.append("  结论：update() 触发窗口映射与几何计算后，控件才拿到真实尺寸")
    app.destroy()
    return "\n".join(lines)


def case_quotes() -> str:
    """中文文案里用 ASCII 双引号，会提前结束字符串字面量。"""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="efa-quote-"))
    bad = tmp / "bad.py"
    bad.write_text(
        'TEXT = "检索结果为空时必须写"未收录"，不要臆造实现细节。"\n',
        encoding="utf-8",
    )
    good = tmp / "good.py"
    good.write_text(
        'TEXT = "检索结果为空时必须写「未收录」，不要臆造实现细节。"\n',
        encoding="utf-8",
    )

    lines = ["复现命令：python tools/capture_evidence.py --case quotes"]

    def compile_check(path: Path) -> tuple[bool, str]:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode == 0, (proc.stderr or "").strip()

    ok1, err1 = compile_check(bad)
    lines.append(f"写法 A（中文句子内用 ASCII 引号）：通过={ok1}")
    for line in err1.splitlines()[-3:]:
        lines.append("  " + line)

    ok2, err2 = compile_check(good)
    lines.append(f"写法 B（改用「」）：通过={ok2}  stderr={err2 or '（空）'}")
    lines.append("结论：中文正文里嵌 ASCII 双引号会提前闭合字符串；统一改用「」即可")
    return "\n".join(lines)



def run(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    EVID.mkdir(parents=True, exist_ok=True)
    which = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--case" else "all"
    if which in ("negative", "all"):
        text = case_negative()
        (EVID / "log-01-negative-case.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
    if which in ("layout", "all"):
        text = case_layout()
        (EVID / "log-02-tkinter-layout.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
    if which in ("quotes", "all"):
        text = case_quotes()
        (EVID / "log-03-quote-truncation.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
