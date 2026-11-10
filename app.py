"""程序入口。

用法：
    python app.py                       # 启动 Windows 桌面客户端（默认）
    python app.py --cli "问题"           # 命令行单次问答，便于脚本化验证
    python app.py --cli "问题" --json    # 以 JSON 输出回答与工具调用记录
    python app.py --selftest            # 界面自检：构建窗口后立即退出（CI/快速验证）
    python app.py --list                # 列出知识库中的设备类型
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from efa import __version__  # noqa: E402
from efa.agent import Agent  # noqa: E402
from efa.config import Settings  # noqa: E402


def run_cli(question: str, as_json: bool) -> int:
    settings = Settings.load()
    agent = Agent(settings)
    answer = agent.ask(question)

    if as_json:
        payload = {
            "question": question,
            "mode": answer.mode,
            "elapsed_ms": answer.elapsed_ms,
            "error": answer.error,
            "citations": answer.citations,
            "answer": answer.text,
            "tool_calls": [record.to_dict() for record in answer.tool_records],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[模式] {'在线模型' if answer.mode == 'llm' else '离线规则'}  "
              f"({settings.model if answer.mode == 'llm' else '本地检索'})")
        print(f"[耗时] {answer.elapsed_ms} ms")
        print("-" * 60)
        print(answer.text)
        print("-" * 60)
        print(f"[工具调用] {len(answer.tool_records)} 次")
        for record in answer.tool_records:
            flag = "OK " if record.ok else "ERR"
            print(f"  {flag} {record.ts} {record.name}({record.arguments}) "
                  f"-> {record.summary} [{record.elapsed_ms}ms]")
        if answer.error:
            print(f"[异常] {answer.error}")
    return 0 if answer.ok or answer.error == "llm_failed" else 1


def run_selftest() -> int:
    """不进入事件循环，验证界面可正常构建、控件与数据均已就绪。"""
    from efa.ui import FaultAgentApp

    app = FaultAgentApp()
    app.update_idletasks()
    checks = {
        "窗口标题": bool(app.title()),
        "知识库条目": len(app.agent.kb),
        "知识库列表行数": len(app.kb_tree.get_children()),
        "项目知识条目": len(app.agent.project_kb),
        "项目知识列表行数": len(app.pkb_tree.get_children()),
        "工具声明数": len(app.agent.tools.specs()),
        "对话控件": isinstance(app.chat, object),
        "输入控件": isinstance(app.input, object),
        "工具表": isinstance(app.tool_tree, object),
    }
    print("界面自检结果：")
    for key, value in checks.items():
        print(f"  - {key}: {value}")
    app.destroy()
    ok = all(bool(v) for v in checks.values())
    print("自检" + ("通过" if ok else "未通过"))
    return 0 if ok else 1


def run_list() -> int:
    settings = Settings.load()
    agent = Agent(settings)
    print(f"知识库：{agent.kb.path}")
    print(f"版本：{agent.kb.version}  条数：{len(agent.kb)}")
    for name in agent.kb.equipment_names():
        print(f"  - {name}")
    if agent.kb.load_error:
        print(f"[错误] {agent.kb.load_error}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"设备故障咨询 Agent v{__version__}", add_help=True
    )
    parser.add_argument("--cli", metavar="问题", help="以命令行方式询问一个问题")
    parser.add_argument("--json", action="store_true", help="配合 --cli 输出 JSON")
    parser.add_argument("--selftest", action="store_true", help="界面自检后退出")
    parser.add_argument("--list", action="store_true", help="列出知识库设备类型")
    parser.add_argument("--version", action="store_true", help="显示版本号")
    args = parser.parse_args(argv)

    if args.version:
        print(f"设备故障咨询 Agent v{__version__}")
        return 0
    if args.list:
        return run_list()
    if args.selftest:
        return run_selftest()
    if args.cli is not None:
        return run_cli(args.cli, args.json)

    try:
        from efa.ui import FaultAgentApp
    except ImportError as exc:
        print("无法加载图形界面（Tkinter 不可用）。")
        print(f"原因：{exc}")
        print("可改用命令行模式：python app.py --cli \"你的问题\"")
        return 2
    FaultAgentApp().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
