"""知识库 v2.0 富化数据（一）：架构与模块。纯数据模块，供 kb_enrich_v2.py 合并。"""

ENRICH_1: dict[str, dict] = {
    # ---------------- architecture ----------------
    "KB-ARCH-001": {
        "aliases": ["分层架构", "依赖方向", "四层模型", "代码该放哪"],
        "background": "单机项目最容易写成界面直接调模型，一旦要换 UI 或补测试就无从下手，因此先用分层把 IO 与业务逻辑切开。",
        "steps": [
            "判断改动属于表现（渲染）、应用（编排）、领域（规则）还是基础设施（IO）",
            "只允许上层引用下层，新增反向依赖一律在评审时拦下",
            "领域层保持无 IO：不 import tkinter、不发网络请求",
        ],
        "troubleshooting": [
            {"symptom": "改界面时被迫改 agent.py", "check": "界面是否直接操作工具或知识库对象", "fix": "改为只调用 Agent.ask 并渲染 Answer，界面不参与业务判断"},
            {"symptom": "单测必须建窗口才能跑", "check": "被测模块是否 import 了 tkinter", "fix": "把界面逻辑收在 ui/，领域逻辑留在 knowledge/tools，测试只引后者"},
        ],
        "best_practices": [
            "新文件先写一句职责，写不出来说明它不该独立存在",
            "跨层调用要在评审里说明理由，并补一条知识条目",
        ],
        "related": ["KB-MOD-005", "KB-ARCH-003", "KB-CONV-001"],
    },
    "KB-ARCH-002": {
        "aliases": ["双模式", "离线兜底", "降级链路", "在线离线"],
        "background": "课堂与内网环境经常没有可用密钥，只做在线一条路会导致演示直接失败；但也不能用假数据冒充模型输出。",
        "steps": [
            "ask() 先判 online_ready（有密钥且未强制离线）",
            "在线失败时捕获 LLMError，转 _ask_offline 并在首行说明降级原因",
            "离线路径同样走 ToolRegistry，保证检索结果真实可追溯",
        ],
        "troubleshooting": [
            {"symptom": "配了密钥却仍显示离线", "check": "settings.online_ready 是否为假", "fix": "检查 force_offline、密钥是否为空、是否被环境变量覆盖"},
            {"symptom": "回答像模板却标着在线", "check": "Answer.mode 与实际执行路径是否一致", "fix": "以 mode 为准渲染标签，禁止用文案冒充模式"},
        ],
        "best_practices": [
            "两条路径共用同一套工具，避免演示能跑而真机不能用",
            "降级必须留痕：日志记 llm_failed 原因，界面显示已降级",
        ],
        "related": ["KB-MOD-005", "KB-ERR-003", "KB-API-001"],
    },
    "KB-ARCH-003": {
        "aliases": ["扩展点", "新增工具", "插件式", "怎么加功能"],
        "background": "工具会持续增加（工单、设备台账、报警码检索），若每加一个都改 agent，编排层很快退化成 if-else 迷宫。",
        "steps": [
            "在 ToolRegistry._impl 登记 name → 方法",
            "在 specs() 补一条 function 声明（name/description/parameters）",
            "实现方法并统一返回 {ok: bool, ...}",
            "可选：在 _summarize 补摘要规则、在提示词补引导语",
        ],
        "troubleshooting": [
            {"symptom": "模型从不调用新工具", "check": "specs() 是否包含该工具、description 是否写清使用条件", "fix": "补声明，并把什么时候用写进 description"},
            {"symptom": "工具报参数不合法", "check": "parameters.required 与实际必填是否一致", "fix": "对齐 required 列表，方法参数给默认值"},
        ],
        "best_practices": ["工具只读或无副作用，写操作单独走确认流程", "不要在 agent.py 写 if name 等于某工具名的分支"],
        "related": ["KB-MOD-003", "KB-API-006", "KB-API-007"],
    },
    "KB-ARCH-004": {
        "aliases": ["线程模型", "界面卡死", "队列刷新", "异步"],
        "background": "模型调用可能持续数秒，主线程直接调用会让窗口无响应；而 Tk 控件又只能在主线程更新，因此必须线程加队列。",
        "steps": [
            "发送后置 busy 标志并禁用按钮",
            "起 daemon 线程执行 agent.ask，结果 put 进 queue",
            "主线程用 after(120) 轮询消费并渲染",
            "destroy 前 after_cancel，避免回调打到已销毁的控件",
        ],
        "troubleshooting": [
            {"symptom": "点发送后窗口假死", "check": "是否在主线程直接调用 agent.ask", "fix": "改为线程加队列，主线程只做渲染"},
            {"symptom": "测试输出 invalid command name", "check": "destroy 后 after 回调是否仍在队列", "fix": "保存 _poll_id 并在 destroy 中取消"},
        ],
        "best_practices": ["子线程绝不碰 Tk 控件", "异常也要回传队列，否则按钮会永久禁用"],
        "related": ["KB-MOD-007", "KB-API-012", "KB-CONV-003"],
    },
    # ---------------- module ----------------
    "KB-MOD-001": {
        "aliases": ["配置模块", "Settings", "环境变量优先级"],
        "background": "配置散落在各处时，换模型、改超时都要翻代码；集中到 Settings 后一处改动全局生效。",
        "steps": [
            "新增字段时在 dataclass 上给默认值",
            "需要环境变量覆盖，就在 load() 的 env_map 增加映射",
            "需要持久化就调 save()，注意 config.json 已被 gitignore",
        ],
        "troubleshooting": [
            {"symptom": "新增字段后启动报缺参数", "check": "config.json 是否为旧版本、缺该字段", "fix": "字段必须给默认值，或用 field(default=...)"},
            {"symptom": "改了环境变量没生效", "check": "load() 的覆盖顺序", "fix": "环境变量在 config.json 之后读取，同名以环境变量为准"},
        ],
        "best_practices": ["路径常量集中在 config.py，别在模块里手拼相对路径", "api_key 只经 Settings 流转，不落日志"],
        "related": ["KB-CFG-001", "KB-CFG-002", "KB-API-008"],
    },
    "KB-MOD-002": {
        "aliases": ["案例库", "检索模块", "knowledge.py", "打分"],
        "background": "案例只有十几条，引入向量库属于过度设计；但纯关键词又召回不住口语化描述，于是用规则加权加字符相似度折中。",
        "steps": [
            "新增案例：往 fault_cases.json 的 cases 追加，字段齐全",
            "调排序：改 search() 里的权重，同步更新 test_knowledge",
            "验证：跑 --cli 看 Top1 是否正确、分数是否在预期区间",
        ],
        "troubleshooting": [
            {"symptom": "明明有案例却查不到", "check": "min_score 是否过高、关键词是否缺口语说法", "fix": "补 keywords，或临时调低阈值验证召回"},
            {"symptom": "返回了不相关案例", "check": "是否只命中了通用词（如报警）", "fix": "提高设备名权重，或给通用词降权"},
        ],
        "best_practices": ["打分公式改动必须跑 test_knowledge 全量回归", "无命中用空列表表达，不要抛异常"],
        "related": ["KB-API-003", "KB-DATA-001", "KB-CFG-003"],
    },
    "KB-MOD-003": {
        "aliases": ["工具注册表", "tools.py", "工具执行"],
        "background": "模型返回的工具参数是字符串且可能非法，工具内部也可能抛异常；若直接冒泡，整轮问答就中断了。",
        "steps": [
            "execute(name, arguments) 解析参数（字符串则 json.loads）",
            "查 _impl 取方法，未注册直接返回 ok=false",
            "捕获 ToolError、TypeError 与其他异常，统一转结构化错误",
            "返回 (result, ToolCallRecord)，记录耗时与摘要",
        ],
        "troubleshooting": [
            {"symptom": "模型传了非法 JSON", "check": "arguments 的解析分支", "fix": "解析失败包成 _raw 字典并返回参数不合法"},
            {"symptom": "工具失败但界面无记录", "check": "是否在 execute 之外调用了私有方法", "fix": "一律走 execute，保证记录被创建"},
        ],
        "best_practices": ["错误文案要能指导下一步，例如编号不存在可改用检索", "耗时用 perf_counter 记录到毫秒"],
        "related": ["KB-API-006", "KB-ARCH-003", "KB-ERR-001"],
    },
    "KB-MOD-004": {
        "aliases": ["模型客户端", "llm.py", "HTTP 调用"],
        "background": "全程只有一次 POST，引 requests 或 openai SDK 会破坏零依赖交付；因此用 urllib 直连，并把各类失败翻译成可读中文。",
        "steps": [
            "组装 payload（model/messages/temperature/stream）",
            "有 tools 时附 tools 与 tool_choice=auto",
            "按 HTTP 状态码分档捕获，统一转 LLMError",
            "取 choices 首条 message 与 usage 返回",
        ],
        "troubleshooting": [
            {"symptom": "401 鉴权失败", "check": "密钥是否正确、是否带 Bearer 头", "fix": "核对 api_key 与 Authorization 头"},
            {"symptom": "返回非 JSON 内容", "check": "base_url 是否少了 /v1", "fix": "补全 base_url，或用设置里的测试连接验证"},
            {"symptom": "请求超时", "check": "网络状况与 timeout 设置", "fix": "调大 timeout 或换更快的模型"},
        ],
        "best_practices": ["不在客户端内重试，重试策略放上层", "错误信息里不要回显密钥"],
        "related": ["KB-API-009", "KB-ERR-003", "KB-DEP-001"],
    },
    "KB-MOD-005": {
        "aliases": ["编排层", "agent.py", "问答生命周期"],
        "background": "选路、工具循环、降级、历史裁剪如果散在界面里，CLI 模式就得复制一遍；集中到 Agent 后两种入口共用一套逻辑。",
        "steps": [
            "ask() 做输入与知识库校验",
            "按 online_ready 选择 _ask_llm 或 _ask_offline",
            "在线失败捕获 LLMError 后降级",
            "回答后 _push_history 并裁剪到 12 条",
        ],
        "troubleshooting": [
            {"symptom": "回答不带案例编号", "check": "提示词是否要求引用、检索是否命中", "fix": "检查 prompt 第 3/4 条与检索结果，必要时补样例"},
            {"symptom": "多轮后回答变慢变贵", "check": "history 是否无限增长", "fix": "确认 MAX_HISTORY_MESSAGES 为 12 且裁剪生效"},
        ],
        "best_practices": ["改提示词必须回归三条核心用例", "新增分支先判断它是否该放在工具层"],
        "related": ["KB-API-001", "KB-ARCH-002", "KB-API-002"],
    },
    "KB-MOD-006": {
        "aliases": ["会话日志", "JSONL", "取证"],
        "background": "作业要求证明真实工具调用，截图容易被质疑，结构化日志能逐条复算，也能统计命中率与耗时。",
        "steps": [
            "构造 SessionLog 时确定文件名（按会话切分）",
            "问答前后分别调 question 与 answer",
            "工具执行后调 tool_calls 落盘",
            "统计时按 kind 过滤 JSONL",
        ],
        "troubleshooting": [
            {"symptom": "logs 目录为空", "check": "目录是否可写、_ready 是否为真", "fix": "检查权限；写失败是静默降级，不影响问答"},
            {"symptom": "日志出现敏感信息", "check": "是否记录了完整密钥", "fix": "只记掩码，密钥永不入日志"},
        ],
        "best_practices": ["一行一条 JSON，禁止多行美化", "kind 只增不改，保持向后可解析"],
        "related": ["KB-API-010", "KB-CONV-002", "KB-DATA-003"],
    },
    "KB-MOD-007": {
        "aliases": ["界面模块", "Tkinter", "main_window"],
        "background": "界面是唯一直接面向演示的部分，布局混乱或信息缺失会直接影响评审印象，因此把样式与布局集中管理。",
        "steps": [
            "新增控件先归位（顶栏、左区、右区、状态栏）",
            "样式统一在 _setup_style 里加，不在控件上散写颜色",
            "新增页签后补对应的 _load_ 初始化数据",
        ],
        "troubleshooting": [
            {"symptom": "新增页签空白", "check": "是否调用了对应 _load_ 方法", "fix": "在 _build_side 末尾补加载调用"},
            {"symptom": "窗口缩放后控件重叠", "check": "是否使用了固定像素布局", "fix": "用 pack/grid 权重加最小尺寸约束"},
        ],
        "best_practices": ["配色用文件头常量，改主题只改一处", "耗时操作一律异步，保持界面可交互"],
        "related": ["KB-ARCH-004", "KB-API-012", "KB-GUIDE-001"],
    },
    "KB-MOD-008": {
        "aliases": ["入口", "命令行模式", "selftest"],
        "background": "演示需要窗口，自动化验证又需要无界面入口；把四种模式统一收在 app.py，避免启动逻辑多处维护。",
        "steps": [
            "GUI：直接运行或走 start.bat",
            "验证：--cli 单问、--json 结构化、--selftest 建窗口即退、--list 列设备",
            "新增模式时在 argparse 增加参数并分流",
        ],
        "troubleshooting": [
            {"symptom": "CLI 模式也报 Tkinter 缺失", "check": "是否在模块顶层 import 了 ui", "fix": "把 GUI import 放进分支内，保持 CLI 可独立运行"},
            {"symptom": "脚本取不到退出码", "check": "是否用 start 启动了窗口", "fix": "CLI 模式直接执行，按返回值判断"},
        ],
        "best_practices": ["CI 用 --selftest 加 --cli 组合做冒烟", "退出码语义稳定：0 成功、1 业务失败、2 环境不可用"],
        "related": ["KB-API-012", "KB-GUIDE-001", "KB-DEP-003"],
    },
    "KB-MOD-009": {
        "aliases": ["项目知识库模块", "project_kb.py", "工程知识检索"],
        "background": "案例库回答设备怎么修，工程问题需要另一套字段（签名、适用范围、注意事项），混库会互相污染排序。",
        "steps": [
            "新增条目写进 data/project_kb.json 的 entries",
            "category 必须是已有分类 id，否则过滤不中",
            "改完跑 tools/verify_kb.py 校验一致性",
        ],
        "troubleshooting": [
            {"symptom": "检索结果为空", "check": "query 是否过泛、category 是否写错", "fix": "先用 list_kb_categories 确认 id，再用符号名或模块名检索"},
            {"symptom": "条目与实际实现不符", "check": "是否改了代码没改文档", "fix": "跑 verify_kb.py，按报错定位并更新条目"},
        ],
        "best_practices": ["一条目只讲一个主题，过长就拆", "symbol 与 signature 必须可被 AST 校验，不能凭印象填"],
        "related": ["KB-API-011", "KB-DATA-006", "KB-TOOL-004"],
    },
}
