"""设备故障咨询 Agent —— Windows 桌面客户端主界面。

技术选择：Tkinter（Python 自带，零安装、零依赖），配合标准库 threading + queue
实现"后台推理、前台不卡界面"。整体为单窗口三区布局：
    顶部：标题、运行模式、设置/导出/关于
    左区：对话记录 + 示例问题 + 输入框
    右区：工具调用记录 / 知识库浏览 / 使用说明
    底部：知识库状态、模式、日志路径、运行状态
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..agent import Agent, Answer
from ..config import EXPORT_DIR, Settings
from ..session import SessionLog

# ---------- 视觉规范 ----------
BG = "#F4F6F9"
CARD = "#FFFFFF"
BORDER = "#E2E7EF"
TEXT = "#1F2430"
MUTED = "#6B7280"
PRIMARY = "#2A6EF5"
PRIMARY_DARK = "#1F57C7"
USER_TAG = "#2A6EF5"
AGENT_TAG = "#12805C"
SYS_TAG = "#B26A00"
OK = "#12805C"
WARN = "#C2410C"

FONT = "Microsoft YaHei UI"
PLACEHOLDER = "描述设备故障现象，例如：液压站压力上不去，油缸动作很慢"

SAMPLES = [
    "液压站压力上不去，油缸动作无力",
    "空压机排气温度过高报警停机了",
    "加工中心加工尺寸超差，反向间隙变大",
]


class FaultAgentApp(tk.Tk):
    def __init__(self, agent: Agent | None = None):
        super().__init__()
        self.settings = Settings.load()
        self.agent = agent or Agent(self.settings)
        self.session = SessionLog()
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.busy = False
        self.transcript: list[tuple[str, str, str]] = []
        self._tool_rows = 0
        self._tool_args: dict[str, str] = {}

        self.title("设备故障咨询 Agent · 本地知识库版")
        self.geometry("1180x760")
        self.minsize(980, 620)
        self.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_body()
        self._build_statusbar()
        self._greet()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._alive = True
        self._poll_id = self.after(120, self._drain_queue)

    # ================= 样式 =================

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Header.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        style.configure("Title.TLabel", background=CARD, foreground=TEXT, font=(FONT, 15, "bold"))
        style.configure("Sub.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
        style.configure("Status.TLabel", background="#EDF1F7", foreground=MUTED, font=(FONT, 9))
        style.configure(
            "Primary.TButton",
            font=(FONT, 10, "bold"),
            background=PRIMARY,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
            padding=(18, 8),
        )
        style.map(
            "Primary.TButton",
            background=[("active", PRIMARY_DARK), ("disabled", "#9CB7EE")],
            foreground=[("disabled", "#F0F4FF")],
        )
        style.configure(
            "Ghost.TButton",
            font=(FONT, 9),
            background=CARD,
            foreground=TEXT,
            borderwidth=1,
            relief="solid",
            padding=(10, 5),
        )
        style.map("Ghost.TButton", background=[("active", "#F0F4FA")])
        style.configure("Chip.TButton", font=(FONT, 9), padding=(10, 4))
        style.configure(
            "TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0)
        )
        style.configure(
            "TNotebook.Tab",
            font=(FONT, 9),
            padding=(14, 7),
            background="#E9EDF4",
            foreground=MUTED,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", PRIMARY)],
        )
        style.configure(
            "Treeview",
            font=(FONT, 9),
            rowheight=26,
            background=CARD,
            fieldbackground=CARD,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading", font=(FONT, 9, "bold"), background="#F2F5FA", foreground=MUTED
        )
        style.map("Treeview", background=[("selected", "#DCE8FE")], foreground=[("selected", TEXT)])

    # ================= 顶栏 =================

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=CARD, height=74)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=CARD)
        left.pack(side="left", padx=(20, 0), pady=12)
        tk.Label(
            left, text="设备故障咨询 Agent", bg=CARD, fg=TEXT, font=(FONT, 15, "bold")
        ).pack(anchor="w")
        tk.Label(
            left,
            text="本地知识库检索 · 工具调用可追溯 · 无密钥亦可离线运行",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=CARD)
        right.pack(side="right", padx=20)
        self.mode_var = tk.StringVar(value=self._mode_text())
        self.mode_label = tk.Label(
            right,
            textvariable=self.mode_var,
            bg="#E8F0FE",
            fg=PRIMARY,
            font=(FONT, 9, "bold"),
            padx=10,
            pady=4,
        )
        self.mode_label.pack(side="left", padx=(0, 10))
        ttk.Button(right, text="设置", style="Ghost.TButton", command=self.open_settings).pack(
            side="left", padx=4
        )
        ttk.Button(right, text="导出会话", style="Ghost.TButton", command=self.export_session).pack(
            side="left", padx=4
        )
        ttk.Button(right, text="关于", style="Ghost.TButton", command=self.show_about).pack(
            side="left", padx=4
        )

        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")

    # ================= 主体 =================

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True, padx=14, pady=12)

        paned = ttk.Panedwindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=BG)
        right = tk.Frame(paned, bg=BG)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        self._build_chat(left)
        self._build_side(right)

    def _card(self, parent) -> tk.Frame:
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    # ---------- 左：对话 ----------

    def _build_chat(self, parent) -> None:
        card = self._card(parent)
        card.pack(fill="both", expand=True, padx=(0, 10))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self.chat = tk.Text(
            card,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 10),
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=12,
            spacing1=2,
            spacing3=2,
            cursor="arrow",
        )
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card, orient="vertical", command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.tag_configure("user_label", foreground=USER_TAG, font=(FONT, 9, "bold"), spacing1=10)
        self.chat.tag_configure("agent_label", foreground=AGENT_TAG, font=(FONT, 9, "bold"), spacing1=10)
        self.chat.tag_configure("sys_label", foreground=SYS_TAG, font=(FONT, 9, "bold"), spacing1=10)
        self.chat.tag_configure("body", foreground=TEXT, font=(FONT, 10), lmargin1=2, lmargin2=2)
        self.chat.tag_configure("meta", foreground=MUTED, font=(FONT, 8))
        self.chat.tag_configure("divider", foreground=BORDER)
        self.chat.configure(state="disabled")

        # 示例问题
        chip_row = tk.Frame(card, bg=CARD)
        chip_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 6))
        tk.Label(chip_row, text="示例：", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left")
        for sample in SAMPLES:
            ttk.Button(
                chip_row,
                text=sample,
                style="Chip.TButton",
                command=lambda s=sample: self._use_sample(s),
            ).pack(side="left", padx=(4, 0))

        # 输入区
        input_wrap = tk.Frame(card, bg=CARD)
        input_wrap.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))
        box = tk.Frame(
            input_wrap, bg="#FBFCFE", highlightbackground=BORDER, highlightthickness=1
        )
        box.pack(fill="x")
        self.input = tk.Text(
            box,
            height=3,
            wrap="word",
            bg="#FBFCFE",
            fg=TEXT,
            font=(FONT, 10),
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
            insertbackground=TEXT,
        )
        self.input.pack(fill="x")
        self.input.bind("<Control-Return>", self.on_send)
        self.input.bind("<FocusIn>", self._clear_placeholder)
        self.input.bind("<FocusOut>", self._restore_placeholder)
        self._restore_placeholder()

        btn_row = tk.Frame(input_wrap, bg=CARD)
        btn_row.pack(fill="x", pady=(8, 0))
        tk.Label(
            btn_row, text="Ctrl + Enter 发送", bg=CARD, fg=MUTED, font=(FONT, 8)
        ).pack(side="left")
        self.send_btn = ttk.Button(
            btn_row, text="发送咨询", style="Primary.TButton", command=self.on_send
        )
        self.send_btn.pack(side="right")
        ttk.Button(
            btn_row, text="清空对话", style="Ghost.TButton", command=self.clear_chat
        ).pack(side="right", padx=(0, 8))

    # ---------- 右：信息面板 ----------

    def _build_side(self, parent) -> None:
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        notebook = ttk.Notebook(card)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # 1. 工具调用
        tab_tools = tk.Frame(notebook, bg=CARD)
        notebook.add(tab_tools, text="工具调用")
        tk.Label(
            tab_tools,
            text="每次检索都会在此留下记录，双击查看完整参数与返回值。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 4))
        cols = ("time", "tool", "result", "ms")
        self.tool_tree = ttk.Treeview(tab_tools, columns=cols, show="headings", height=14)
        for col, text, width, anchor in (
            ("time", "时间", 62, "center"),
            ("tool", "工具", 128, "w"),
            ("result", "结果摘要", 190, "w"),
            ("ms", "耗时", 52, "center"),
        ):
            self.tool_tree.heading(col, text=text)
            self.tool_tree.column(col, width=width, anchor=anchor, stretch=(col == "result"))
        self.tool_tree.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.tool_tree.bind("<Double-1>", self._show_tool_detail)

        # 2. 知识库
        tab_kb = tk.Frame(notebook, bg=CARD)
        notebook.add(tab_kb, text="知识库")
        tk.Label(
            tab_kb,
            text=f"共 {len(self.agent.kb)} 条模拟案例，双击查看原因与处理步骤。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 4))
        kb_cols = ("id", "equipment", "risk")
        self.kb_tree = ttk.Treeview(tab_kb, columns=kb_cols, show="headings", height=14)
        for col, text, width, anchor in (
            ("id", "编号", 72, "center"),
            ("equipment", "设备", 118, "w"),
            ("risk", "风险", 50, "center"),
        ):
            self.kb_tree.heading(col, text=text)
            self.kb_tree.column(col, width=width, anchor=anchor, stretch=(col == "equipment"))
        self.kb_tree.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.kb_tree.bind("<Double-1>", self._show_case_detail)
        self._load_kb_tree()

        # 3. 项目知识库
        tab_pkb = tk.Frame(notebook, bg=CARD)
        notebook.add(tab_pkb, text="项目知识库")
        pkb = getattr(self.agent, "project_kb", None)
        pkb_count = len(pkb) if pkb is not None else 0
        self.pkb_hint = tk.Label(
            tab_pkb,
            text=("共 %d 条工程知识（模块/接口/数据/配置/异常/依赖），双击查看完整条目。"
                  % pkb_count)
            if pkb_count
            else "项目知识库未加载，检查 data/project_kb.json。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        )
        self.pkb_hint.pack(fill="x", padx=8, pady=(6, 4))
        pkb_cols = ("id", "category", "title")
        self.pkb_tree = ttk.Treeview(tab_pkb, columns=pkb_cols, show="headings", height=14)
        for col, text, width, anchor in (
            ("id", "编号", 86, "center"),
            ("category", "分类", 74, "center"),
            ("title", "标题", 220, "w"),
        ):
            self.pkb_tree.heading(col, text=text)
            self.pkb_tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        self.pkb_tree.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.pkb_tree.bind("<Double-1>", self._show_entry_detail)
        self._load_pkb_tree()

        # 4. 说明
        tab_help = tk.Frame(notebook, bg=CARD)
        notebook.add(tab_help, text="使用说明")
        help_text = tk.Text(
            tab_help,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 9),
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        help_text.pack(fill="both", expand=True)
        help_text.insert(
            "1.0",
            "一、运行方式\n"
            "1. 离线模式（默认）：无需 API Key，检索与回答全部本地完成，可直接演示。\n"
            "2. 在线模式：在「设置」中填入 OpenAI 兼容接口地址、模型名与 API Key，\n"
            "   模型会通过 function calling 自主决定检索什么、检索几次。\n\n"
            "二、推荐演示路径\n"
            "① 输入「液压站压力上不去」→ 观察右侧工具调用记录 → 回答问题引用 EFA-001；\n"
            "② 输入知识库未覆盖的问题（如「注塑机模具冷却水路堵塞」）→ 观察是否明确说明缺乏依据；\n"
            "③ 输入空内容或断开网络 → 观察异常提示与自动降级；\n"
            "④ 输入「新增一个工具要改哪些地方」「Settings 配置优先级」等工程问题\n"
            "   → 自动转向项目知识库，回答引用 KB-xxx 条目编号；\n"
            "⑤ 右栏「项目知识库」页签可按编号/分类浏览 52 条工程知识，双击看完整契约。\n\n"
            "三、安全边界\n"
            "本程序只查询本地模拟案例库，不连接任何真实工业设备，\n"
            "不执行设备控制动作，所有建议仅供教学演示。\n\n"
            "四、日志位置\n"
            f"{self.session.path}\n"
            "每次问答与工具调用都会写入该 JSONL 文件，可作为调试证据。",
        )
        help_text.configure(state="disabled")

    # ================= 状态栏 =================

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg="#EDF1F7", height=28)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(
            bar,
            textvariable=self.status_var,
            bg="#EDF1F7",
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).pack(side="left", padx=14)
        self.kb_var = tk.StringVar(
            value=f"案例 {len(self.agent.kb)} 条 · 工程知识 {len(getattr(self.agent, 'project_kb', []) or [])} 条"
            + (f" · {self.agent.kb.load_error}" if self.agent.kb.load_error else "")
        )
        tk.Label(
            bar, textvariable=self.kb_var, bg="#EDF1F7", fg=MUTED, font=(FONT, 9)
        ).pack(side="right", padx=14)

    # ================= 交互 =================

    def _mode_text(self) -> str:
        if self.agent.settings.online_ready:
            return f"在线 · {self.agent.settings.model}"
        return "离线规则模式"

    def _greet(self) -> None:
        self._append(
            "agent",
            "你好，我是设备故障咨询助手。请描述设备类型与故障现象，"
            "我会先检索本地案例库，再给出可能原因与处理步骤。\n"
            "当前为"
            + ("在线模型模式。" if self.agent.settings.online_ready else "离线规则模式，未配置 API Key 也能正常演示检索流程。"),
            meta=f"知识库已加载 {len(self.agent.kb)} 条案例"
            + (f"｜{self.agent.kb.load_error}" if self.agent.kb.load_error else ""),
        )

    def _use_sample(self, text: str) -> None:
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        self.input.focus_set()

    def _clear_placeholder(self, _event=None) -> None:
        if self.input.get("1.0", "end").strip() == PLACEHOLDER:
            self.input.delete("1.0", "end")
            self.input.configure(fg=TEXT)

    def _restore_placeholder(self, _event=None) -> None:
        if not self.input.get("1.0", "end").strip():
            self.input.delete("1.0", "end")
            self.input.insert("1.0", PLACEHOLDER)
            self.input.configure(fg="#9AA3B2")

    def on_send(self, _event=None) -> str | None:
        if self.busy:
            return "break"
        text = self.input.get("1.0", "end").strip()
        if not text or text == PLACEHOLDER:
            self._append("sys", "请先输入设备故障描述再发送。")
            return "break"

        self._append("user", text)
        self.input.delete("1.0", "end")
        self.busy = True
        self.send_btn.configure(state="disabled")
        self.status_var.set("正在检索知识库并组织回答…")
        self.session.question(text, self.agent.mode_label)

        threading.Thread(target=self._worker, args=(text,), daemon=True).start()
        return "break"

    def _worker(self, text: str) -> None:
        try:
            answer = self.agent.ask(text)
            self.queue.put(("answer", answer))
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程异常导致界面卡死
            self.queue.put(("crash", f"{type(exc).__name__}: {exc}"))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "answer":
                    self._render_answer(payload)  # type: ignore[arg-type]
                elif kind == "crash":
                    self._append(
                        "sys",
                        f"程序内部出现未预期错误：{payload}\n可点击「清空对话」后重试，或查看日志定位。",
                    )
                    self._finish_run("运行异常")
        except queue.Empty:
            pass
        if self._alive:
            self._poll_id = self.after(120, self._drain_queue)

    def _render_answer(self, answer: Answer) -> None:
        mode_text = "在线模型" if answer.mode == "llm" else "离线规则"
        tools = len(answer.tool_records)
        meta = f"{mode_text}｜工具调用 {tools} 次｜{answer.elapsed_ms} ms"
        if answer.citations:
            meta += "｜引用 " + "、".join(answer.citations)
        if answer.tokens:
            meta += f"｜tokens {answer.tokens}"
        if answer.error and answer.error.startswith("llm_failed"):
            meta += "｜已自动降级"
        self._append("agent", answer.text, meta=meta)

        for record in answer.tool_records:
            self._add_tool_row(record)

        self.session.answer(answer.text, answer.mode, answer.elapsed_ms, answer.error)
        self.session.tool_calls(answer.tool_records)
        self._finish_run(f"本次回答完成：{mode_text}，{answer.elapsed_ms} ms")

    def _finish_run(self, status: str) -> None:
        self.busy = False
        self.send_btn.configure(state="normal")
        self.status_var.set(status)

    # ================= 记录与展示 =================

    def _append(self, role: str, text: str, meta: str = "") -> None:
        label_map = {"user": ("你", "user_label"), "agent": ("故障助手", "agent_label"), "sys": ("系统", "sys_label")}
        label, tag = label_map.get(role, ("系统", "sys_label"))
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{label}\n", tag)
        self.chat.insert("end", (text or "").strip() + "\n", "body")
        if meta:
            self.chat.insert("end", meta + "\n", "meta")
        self.chat.insert("end", "\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")
        self.transcript.append((time.strftime("%H:%M:%S"), label, (text or "").strip()))

    def _add_tool_row(self, record) -> None:
        args = ", ".join(f"{k}={v}" for k, v in (record.arguments or {}).items())
        self.tool_tree.insert(
            "",
            "end",
            iid=f"tool-{self._tool_rows}",
            values=(
                record.ts,
                record.name,
                record.summary,
                f"{record.elapsed_ms}ms",
            ),
            tags=("ok" if record.ok else "fail",),
        )
        self.tool_tree.tag_configure("fail", foreground=WARN)
        self.tool_tree.tag_configure("ok", foreground=TEXT)
        self._tool_rows += 1
        self.tool_tree.yview_moveto(1.0)
        self._tool_args[f"tool-{self._tool_rows - 1}"] = args

    def _show_tool_detail(self, _event=None) -> None:
        selected = self.tool_tree.selection()
        if not selected:
            return
        iid = selected[0]
        values = self.tool_tree.item(iid, "values")
        args = self._tool_args.get(iid, "")
        messagebox.showinfo(
            "工具调用详情",
            f"工具：{values[1]}\n时间：{values[0]}\n耗时：{values[3]}\n"
            f"参数：{args or '(无)'}\n结果：{values[2]}",
        )

    def _load_kb_tree(self) -> None:
        for case in self.agent.kb.cases:
            self.kb_tree.insert(
                "", "end", iid=case.id, values=(case.id, case.equipment, case.risk)
            )

    def _show_case_detail(self, _event=None) -> None:
        selected = self.kb_tree.selection()
        if not selected:
            return
        case = self.agent.kb.get(selected[0])
        if case is None:
            return
        win = tk.Toplevel(self)
        win.title(f"{case.id} · {case.equipment}")
        win.geometry("560x520")
        win.configure(bg=CARD)
        text = tk.Text(win, wrap="word", bg=CARD, fg=TEXT, font=(FONT, 10), padx=16, pady=12)
        text.pack(fill="both", expand=True)
        lines = [
            f"{case.id}  {case.equipment}",
            f"型号范围：{case.model}",
            f"风险等级：{case.risk}",
            "",
            "故障现象",
            case.symptom,
            "",
            "可能原因",
        ]
        lines += [f"{i}. {c}" for i, c in enumerate(case.causes, 1)]
        lines += ["", "建议处理步骤"]
        lines += [f"{i}. {s}" for i, s in enumerate(case.steps, 1)]
        if case.keywords:
            lines += ["", "关键词：" + "、".join(case.keywords)]
        if case.source:
            lines += ["", f"来源：{case.source}"]
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    def _load_pkb_tree(self) -> None:
        pkb = getattr(self.agent, "project_kb", None)
        if pkb is None:
            return
        category_names = {c["id"]: c["name"] for c in pkb.category_stats()}
        for entry in pkb.entries:
            self.pkb_tree.insert(
                "",
                "end",
                iid=entry.id,
                values=(entry.id, category_names.get(entry.category, entry.category), entry.title),
            )

    def _show_entry_detail(self, _event=None) -> None:
        selected = self.pkb_tree.selection()
        if not selected:
            return
        pkb = getattr(self.agent, "project_kb", None)
        entry = pkb.get(selected[0]) if pkb is not None else None
        if entry is None:
            return
        win = tk.Toplevel(self)
        win.title(f"{entry.id} · {entry.title}")
        win.geometry("640x600")
        win.configure(bg=CARD)
        text = tk.Text(win, wrap="word", bg=CARD, fg=TEXT, font=(FONT, 10), padx=16, pady=12)
        scroll = ttk.Scrollbar(win, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        lines = [f"{entry.id}  {entry.title}", f"分类：{entry.category}｜{entry.version}", ""]
        lines += ["结论", entry.summary, ""]
        if entry.signature:
            lines += ["签名/字段", entry.signature, ""]
        if entry.inputs:
            lines.append("参数规范")
            for item in entry.inputs:
                required = "必填" if item.get("required") else "可选"
                lines.append(
                    f"- {item.get('name')}（{item.get('type')}，{required}，"
                    f"默认 {item.get('default') or '无'}）：{item.get('desc', '')}"
                )
            lines.append("")
        if entry.outputs:
            lines += ["输出", entry.outputs, ""]
        for title, values in (
            ("什么时候用", entry.when_to_use),
            ("使用场景", entry.scenarios),
            ("注意事项", entry.cautions),
        ):
            if values:
                lines.append(title)
                lines.extend(f"{i}. {v}" for i, v in enumerate(values, 1))
                lines.append("")
        if entry.details:
            lines += ["说明", entry.details, ""]
        if entry.tags:
            lines += ["标签", "、".join(entry.tags), ""]
        lines.append(f"适用范围：{entry.scope}")
        if entry.refs:
            lines.append("来源：" + "、".join(entry.refs))
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    # ================= 菜单动作 =================

    def clear_chat(self) -> None:
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.tool_tree.delete(*self.tool_tree.get_children())
        self._tool_args.clear()
        self._tool_rows = 0
        self.transcript.clear()
        self.agent.reset()
        self.status_var.set("已清空对话与工具记录")

    def export_session(self) -> None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        default = EXPORT_DIR / f"会话记录-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            title="导出会话记录",
            initialdir=str(EXPORT_DIR),
            initialfile=default.name,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not path:
            return
        lines = [
            "设备故障咨询 Agent 会话记录",
            f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"运行模式：{self.agent.mode_label}",
            f"知识库：{self.agent.kb.path}（{len(self.agent.kb)} 条）",
            "-" * 60,
        ]
        for ts, role, content in self.transcript:
            lines.append(f"[{ts}] {role}：{content}")
            lines.append("")
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("导出失败", f"无法写入文件：{exc}")
            return
        self.status_var.set(f"会话已导出：{path}")

    def open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("模型设置")
        win.geometry("520x400")
        win.configure(bg=CARD)
        win.transient(self)
        win.grab_set()

        pad = {"padx": 18, "pady": 6}
        tk.Label(win, text="在线模型配置", bg=CARD, fg=TEXT, font=(FONT, 12, "bold")).pack(
            anchor="w", padx=18, pady=(16, 2)
        )
        tk.Label(
            win,
            text="留空 API Key 则保持离线模式；密钥仅保存在本地 config.json，已被 .gitignore 忽略。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            wraplength=470,
            justify="left",
        ).pack(anchor="w", padx=18)

        form = tk.Frame(win, bg=CARD)
        form.pack(fill="x", padx=18, pady=10)

        entries: dict[str, tk.Entry] = {}
        for idx, (label, key, value, secret) in enumerate(
            [
                ("接口地址", "base_url", self.settings.base_url, False),
                ("模型名称", "model", self.settings.model, False),
                ("API Key", "api_key", self.settings.api_key, True),
            ]
        ):
            tk.Label(form, text=label, bg=CARD, fg=TEXT, font=(FONT, 9)).grid(
                row=idx, column=0, sticky="w", pady=5
            )
            entry = tk.Entry(
                form,
                font=(FONT, 9),
                relief="solid",
                borderwidth=1,
                show="*" if secret else "",
            )
            entry.insert(0, str(value))
            entry.grid(row=idx, column=1, sticky="ew", padx=(10, 0), pady=5, ipady=4)
            entries[key] = entry
        form.grid_columnconfigure(1, weight=1)

        force_offline = tk.BooleanVar(value=self.settings.force_offline)
        tk.Checkbutton(
            win,
            text="强制离线模式（即使配置了密钥也不联网）",
            variable=force_offline,
            bg=CARD,
            fg=TEXT,
            font=(FONT, 9),
            activebackground=CARD,
            selectcolor=CARD,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(2, 8))

        hint = tk.Label(
            win,
            text="",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            wraplength=470,
            justify="left",
        )
        hint.pack(anchor="w", padx=18)

        def apply_and_close() -> None:
            self.settings.base_url = entries["base_url"].get().strip() or self.settings.base_url
            self.settings.model = entries["model"].get().strip() or self.settings.model
            self.settings.api_key = entries["api_key"].get().strip()
            self.settings.force_offline = bool(force_offline.get())
            try:
                path = self.settings.save()
            except OSError as exc:
                messagebox.showerror("保存失败", f"配置无法写入：{exc}", parent=win)
                return
            self.agent = Agent(self.settings)
            self.mode_var.set(self._mode_text())
            self.kb_var.set(
                f"案例 {len(self.agent.kb)} 条 · 工程知识 {len(self.agent.project_kb)} 条"
            )
            try:
                self.pkb_tree.delete(*self.pkb_tree.get_children())
                self._load_pkb_tree()
            except (tk.TclError, AttributeError):
                pass
            self._append(
                "sys",
                f"设置已保存到 {path}。当前模式：{self.agent.mode_label}，"
                f"密钥：{self.settings.masked_key()}",
            )
            self.status_var.set("配置已更新并重新加载 Agent")
            win.destroy()

        def test_connection() -> None:
            test_settings = Settings(**{**self.settings.__dict__})
            test_settings.base_url = entries["base_url"].get().strip()
            test_settings.model = entries["model"].get().strip()
            test_settings.api_key = entries["api_key"].get().strip()
            if not test_settings.api_key:
                hint.configure(text="未填写 API Key，无法测试在线连接（离线模式可用）。", fg=WARN)
                return
            hint.configure(text="正在测试连接…", fg=MUTED)
            win.update_idletasks()
            from ..llm import LLMClient, LLMError

            try:
                response = LLMClient(test_settings).chat(
                    [{"role": "user", "content": "回复 ok 两个字符即可"}]
                )
                content = (response.message.get("content") or "").strip()
                hint.configure(text=f"连接成功，模型返回：{content[:40]}", fg=OK)
            except LLMError as exc:
                hint.configure(text=f"连接失败：{exc}", fg=WARN)
            except Exception as exc:  # noqa: BLE001
                hint.configure(text=f"连接异常：{exc}", fg=WARN)

        btn_row = tk.Frame(win, bg=CARD)
        btn_row.pack(fill="x", padx=18, pady=14)
        ttk.Button(btn_row, text="测试连接", style="Ghost.TButton", command=test_connection).pack(
            side="left"
        )
        ttk.Button(btn_row, text="保存并应用", style="Primary.TButton", command=apply_and_close).pack(
            side="right"
        )
        ttk.Button(btn_row, text="取消", style="Ghost.TButton", command=win.destroy).pack(
            side="right", padx=8
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            "设备故障咨询 Agent  v1.1.0\n\n"
            "技术栈：Python 3.10+ / Tkinter / urllib（零第三方依赖）\n"
            "能力：本地 JSON 知识库检索、工具调用可追溯、在线 LLM 与离线规则双模式\n\n"
            "安全声明：本程序只查询本地模拟案例库，不连接真实工业设备，\n"
            "不执行任何设备控制操作，输出内容仅供教学演示。",
        )

    def _on_close(self) -> None:
        self.session.event("app_close")
        self.destroy()

    def destroy(self) -> None:
        """退出前取消定时回调，避免 Tk 报 "invalid command name" 噪声。"""
        self._alive = False
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
        super().destroy()


def launch() -> int:
    app = FaultAgentApp()
    app.mainloop()
    return 0
