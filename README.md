# 设备故障咨询 Agent（Equipment Fault Consultation Agent）

面向制造企业设备运维场景的**本地知识库 Agent** 演示项目：用户用自然语言描述设备故障，
Agent 自主调用检索工具查询本地案例库，再依据检索结果给出**可能原因**与**处理步骤**；
知识库未覆盖的问题会明确说明"缺乏依据"，不编造案例。

项目同时提供 **Windows 桌面客户端**（Tkinter，零第三方依赖）与 **命令行模式**，
无需安装任何 pip 包即可运行。

> 安全声明：本项目仅查询本地**模拟**案例库，不连接真实工业设备，不执行任何设备控制操作，
> 所有输出仅供教学演示，不可作为真实检修依据。

---

## 一、功能清单

| 编号 | 功能 | 实现说明 |
|---|---|---|
| F1 | 自然语言提问 | 桌面端多行输入框 + 命令行 `--cli`，支持多轮上下文（保留最近 12 条消息） |
| F2 | 本地知识检索 | 12 条模拟案例（JSON），按"设备名 + 关键词 + 文本相似度"加权检索，输出相关度分数 |
| F3 | Agent 自主调用工具 | 在线模式由模型通过 function calling 决定检索时机与关键词；3 个工具可组合调用 |
| F4 | 依据检索结果作答 | 固定四段式结构：判断 / 可能原因 / 处理步骤 / 参考案例编号 |
| F5 | 未覆盖问题不编造 | 相关度低于阈值即判定"无依据"，显式告知并给出当前覆盖设备清单 |
| F6 | 可运行、可复现 | 源码直跑、`start.bat` 一键启动、`uv` 建环境、30 个单元测试 |
| F7 | 异常处理 | 空输入、知识库缺失/损坏、缺密钥、接口鉴权失败、超时、断网、轮次超限 |
| F8 | 工具调用可追溯 | 界面工具面板逐条展示（工具名/参数/摘要/耗时），并写入 `logs/session-*.jsonl` |
| F9 | 离线兜底 | 无密钥或接口不可用时自动切换规则引擎，演示流程不中断，且明确标注模式 |
| F10 | 在线/离线切换 | 「设置」中配置接口地址、模型、密钥，支持一键"测试连接"与强制离线 |

---

## 二、Agent 工作流程

```
用户输入
   │
   ├─ 空输入？ ──是──> 提示补充设备/现象，结束
   │
   ├─ 知识库可用？ ──否──> 提示知识库加载失败及原因，结束
   │
   ├─ 在线模式（配置了 API Key 且未强制离线）
   │     │
   │     ▼
   │  LLM + tools 声明 ──> 模型返回 tool_calls
   │     │                     │
   │     │                     ├─ search_fault_cases(query, top_k)
   │     │                     ├─ get_case_detail(case_id)
   │     │                     └─ list_equipment()
   │     │                     │
   │     │                     ▼
   │     │              工具结果回填 messages ──> 下一轮（最多 6 轮）
   │     ▼
   │  模型输出最终回答（无 tool_calls）──> 校验是否引用案例 ──> 展示
   │
   └─ 离线模式 / 模型调用失败
         │
         ▼
      规则引擎：直接调用 search_fault_cases
         ├─ 有命中 ──> 取 Top1 + get_case_detail ──> 模板化回答
         └─ 无命中 ──> 明确"暂无案例依据" + 建议补充信息
```

**关键设计**：在线与离线**共用同一套 ToolRegistry 与同一份知识库**，区别只在"谁来决定调用"。
这样在无网络、无密钥的课堂上依然能完整演示"检索 → 依据 → 回答"的闭环，
同时不会把固定文本伪装成模型推理结果（回答首行会显式标注运行模式）。

---

## 三、使用的模型与工具

| 类别 | 选型 | 说明 |
|---|---|---|
| 语言模型 | 任意 OpenAI 兼容接口（默认 `deepseek-chat`） | 通过 `urllib` 直连 `/chat/completions`，不依赖 openai SDK |
| 工具调用 | OpenAI function calling 协议 | 工具声明见 `src/efa/tools.py::specs()` |
| 界面 | Tkinter / ttk（Python 标准库） | Windows 自带，无安装成本 |
| 数据 | JSON 文件 | 12 条案例，字段：编号/设备/型号/现象/原因/步骤/关键词/风险 |
| 打包 | uv（环境）、Git（版本）、Gitee（托管） | 生产打包可选 PyInstaller（`pyproject.toml` 的 `build` 附加依赖） |

---

## 四、目录结构

```
equipment-fault-agent/
├─ app.py                    # 入口：GUI / --cli / --selftest / --list
├─ run_tests.py              # 测试入口（免安装）
├─ start.bat                 # Windows 一键启动（自动挑选含 Tkinter 的解释器）
├─ pyproject.toml            # 项目元数据（uv 使用）
├─ config.example.json       # 配置模板，复制为 config.json 后填写
├─ data/
│  └─ fault_cases.json       # 模拟故障案例知识库（12 条）
├─ src/efa/
│  ├─ config.py              # 配置加载：环境变量 > config.json > 默认值
│  ├─ knowledge.py           # 知识库加载与加权检索
│  ├─ tools.py               # 工具注册、参数校验、异常兜底、调用记录
│  ├─ llm.py                 # OpenAI 兼容客户端（标准库 urllib）
│  ├─ agent.py               # Agent 主循环（在线 tool-calling / 离线规则）
│  ├─ session.py             # 会话与工具调用日志（JSONL）
│  └─ ui/main_window.py      # Tkinter 主界面
├─ tests/                    # 30 个单元/界面测试
├─ docs/开发记录.md           # 开发与调试记录（问题 → 定位 → 修复 → 验证）
└─ logs/、exports/            # 运行时生成（已 gitignore）
```

---

## 五、环境配置与启动

### 方式一：直接运行（零安装，推荐课堂演示）

```bat
双击 start.bat
```

`start.bat` 会依次尝试 `py -3.15` / `py -3` / `python`，**自动跳过不含 Tkinter 的解释器**，
并用 `pythonw.exe` 启动窗口（不弹黑框）。也可手动执行：

```bat
python app.py                        :: 启动桌面客户端
python app.py --cli "液压站压力上不去"  :: 命令行单次问答
python app.py --selftest             :: 界面自检（构建后立即退出）
python app.py --list                 :: 列出知识库覆盖的设备
python run_tests.py                  :: 运行全部测试
```

要求：Python 3.10 及以上，安装时勾选 *tcl/tk and IDLE*。

### 方式二：uv（作业要求的标准流程）

```bat
uv init --python 3.12                :: 若从零开始
uv lock                              :: 依据 pyproject.toml 生成 uv.lock
uv sync                              :: 创建 .venv 并同步依赖（本项目无第三方依赖）
uv run python app.py                 :: 在 uv 环境中启动
uv run python run_tests.py           :: 在 uv 环境中跑测试
```

### 配置在线模型（可选）

任选其一：

```bat
:: A. 环境变量（推荐，密钥不落盘）
set EFA_API_KEY=sk-xxxxxxxx
set EFA_MODEL=deepseek-chat
set EFA_BASE_URL=https://api.deepseek.com/v1

:: B. 本地配置文件（已被 .gitignore 忽略）
copy config.example.json config.json
:: 编辑 config.json，填入 api_key，并将 force_offline 改为 false
```

也可在客户端界面点「设置」填写，支持「测试连接」立即验证连通性。
**不配置密钥时程序自动运行在离线规则模式，功能完整可演示。**

---

## 六、测试结果

执行 `python run_tests.py`：**30 个用例全部通过**。

```
.............................. 
----------------------------------------------------------------------
Ran 30 tests in 2.751s
OK
```

| 场景 | 输入 | 期望 | 实测结果 |
|---|---|---|---|
| 正常问题 | 液压站压力上不去，油缸动作很慢 | 命中 EFA-001，给出原因与步骤 | 命中 1 条，Top1=EFA-001，匹配度 0.701，工具调用 2 次，5 ms |
| 未知故障 | 注塑机模具冷却水路堵塞，模温降不下来 | 明确说明知识库未覆盖，不编造 | 输出"本地知识库暂无该故障的案例依据"，列出已覆盖的 12 类设备 |
| 异常输入 | 空字符串 | 友好提示，不崩溃 | 提示"请输入需要咨询的设备故障描述"，返回 `empty_input` |
| 模型不可用 | 错误 base_url + 无效密钥 | 自动降级到离线模式 | 返回 `llm_failed`，切换离线并仍给出 EFA-012 的完整建议 |
| 知识库损坏 | 指向不存在的 JSON | 提示加载失败原因 | 输出"知识库未能加载：知识库文件不存在…" |
| 界面自检 | `--selftest` | 控件与数据均就绪 | 窗口标题/知识库 12 条/列表 12 行/对话/输入/工具表 全部 True |

界面渲染回归测试（`tests/test_ui.py`）验证：窗口默认 1180×760、对话区 589×492、
输入框 73 px，回答渲染后工具面板出现记录、清空后界面归零。

---

## 七、遇到的问题与解决办法

| # | 问题现象 | 定位过程 | 解决办法 |
|---|---|---|---|
| 1 | 启动脚本报 `SyntaxError`，Agent 无法导入 | 逐行核对签名，发现 `def execute(...)` 后面漏了冒号，换行写返回类型 | 合并为一行签名；调用 `python -c "import efa.tools"` 验证导入正常 |
| 2 | 测试结束时报 `invalid command name "…_drain_queue"` | 窗口 `destroy()` 后，`after(120, ...)` 定时回调仍在队列中执行 | 记录 `_poll_id`，重写 `destroy()` 先 `after_cancel`；增加 `_alive` 标志位；复测输出干净 |
| 3 | 界面测试断言失败：`chat.winfo_width() == 1` | `update_idletasks()` 只处理布局请求，不触发窗口映射 | 改为 `update_idletasks()` + `update()`，实测窗口 1180×760、对话区 589×492 |
| 4 | 直接用 `python app.py` 报 `No module named 'tkinter'` | 该解释器是精简版 Python，未带 tcl/tk | `start.bat` 遍历候选解释器并用 `import tkinter` 探测，命中后改用 `pythonw.exe` 启动 |
| 5 | 知识库未覆盖时，模型倾向"编造"相似案例 | 观察离线输出与提示词，发现缺少硬约束 | 提示词写入"必须说明缺乏依据"；检索层低于阈值直接返回空命中；单元测试锁定该行为 |

完整记录（含代码片段与验收命令）见 `docs/开发记录.md`。

---

## 八、安全与合规

1. **只读模拟数据**：仅查询 `data/fault_cases.json`，无设备 I/O、无 PLC/OPC-UA 连接、无控制指令。
2. **密钥管理**：优先读环境变量；`config.json` 已在 `.gitignore` 中，禁止提交真实密钥。
3. **作业数据**：知识库全部为教学模拟案例，不含企业内部数据与个人信息。
4. **输出边界**：回答附免责声明；涉及高温、高压、旋转部件时优先提示断电挂牌、泄压、降温。

---

## 九、开源参考

本项目为**从零实现**（未复制第三方代码），设计阶段参考了以下公开资料的方法论：

- OpenAI Function Calling 文档：工具声明与 `tool_calls` 消息回填协议
- `anthropics/anthropic-quickstarts`：Agent 循环与工具注册的工程组织方式
- 通用设备维修手册中的故障树描述方式（用于构造模拟案例字段结构）

实现代码、提示词、知识库内容均为本项目原创，未引入第三方源代码文件。

---

## 十、后续扩展方向

- 知识库换用 SQLite + 向量检索（`sqlite-vec` / FAISS），支持千级案例与语义召回
- 增加案例反馈闭环（有用/无用标注 → 调整排序权重）
- 支持工单导出（CSV/企业微信机器人），对接 MES 设备台账
- 打包为单文件 exe（PyInstaller）并增加自动更新
