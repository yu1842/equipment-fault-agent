"""知识库 v2.0 富化数据（三）：数据、配置、异常、依赖、约定、边界。纯数据模块。"""

ENRICH_3: dict[str, dict] = {
    # ---------------- data ----------------
    "KB-DATA-001": {
        "aliases": ["案例字段", "FaultCase", "案例结构"],
        "background": "案例是检索与回答的唯一素材，字段设计直接决定召回质量：现象用于相似度，关键词用于命中，步骤用于回答。",
        "steps": [
            "复制现有案例结构新增一条",
            "keywords 至少 3 个，必须包含口语说法",
            "steps 把安全措施写在最前",
            "跑 --cli 验证能否被检索命中",
        ],
        "troubleshooting": [
            {"symptom": "新案例始终检索不到", "check": "keywords 是否只写了书面语", "fix": "补口语说法（如压力上不去、没劲）"},
            {"symptom": "加载后案例数没变", "check": "JSON 是否合法、id 是否重复", "fix": "用 json 解析器验证文件，修正重复编号"},
        ],
        "best_practices": ["一个案例只描述一类故障，不要把多个现象混在一条", "source 字段写清数据来源，便于追溯"],
        "related": ["KB-DATA-005", "KB-API-003", "KB-GUIDE-005"],
    },
    "KB-DATA-002": {
        "aliases": ["命中结构", "SearchHit", "检索结果"],
        "background": "检索结果需要同时携带案例、分数与命中词，才能支持排序、解释与调试三件事。",
        "steps": ["展示时用 brief 生成精简结构", "调试时读 matched 看命中来源"],
        "troubleshooting": [
            {"symptom": "分数都是 0.2 左右无法区分", "check": "是否只命中了通用词", "fix": "补设备名或提高关键词区分度"},
        ],
        "best_practices": ["对外展示分数保留三位小数即可", "不要把分数当置信概率对外承诺"],
        "related": ["KB-API-003", "KB-DATA-001"],
    },
    "KB-DATA-003": {
        "aliases": ["调用记录", "ToolCallRecord", "工具日志"],
        "background": "一次工具调用要能被界面展示、被日志留存、被统计脚本消费，因此把参数、结果摘要、耗时一次性记全。",
        "steps": ["execute 内部自动创建，无需手工构造", "界面按 ts 与 name 展示", "日志按 to_dict 原样写入"],
        "troubleshooting": [
            {"symptom": "界面显示的参数是空的", "check": "arguments 是否被序列化成字符串", "fix": "展示前统一格式化，不要直接 str 字典"},
        ],
        "best_practices": ["summary 要人可读，避免整段 JSON", "耗时为 0 时也记录，便于发现缓存命中"],
        "related": ["KB-API-006", "KB-MOD-006", "KB-CONV-002"],
    },
    "KB-DATA-004": {
        "aliases": ["回答结构", "Answer", "问答结果"],
        "background": "界面、CLI、测试都需要判断一次问答是否成功、走了哪条路径、用了哪些依据，Answer 把这些信息一次性带出。",
        "steps": ["渲染 text 与 mode", "用 citations 做依据展示", "用 error 判断是否需要提示"],
        "troubleshooting": [
            {"symptom": "降级了但界面没提示", "check": "是否判断了 error 前缀 llm_failed", "fix": "在 meta 行追加已自动降级"},
        ],
        "best_practices": ["ok 等价于 error 为空，不要另外造状态", "citations 去重后展示，最多五个"],
        "related": ["KB-API-001", "KB-ERR-002"],
    },
    "KB-DATA-005": {
        "aliases": ["案例库文件", "fault_cases.json", "数据结构"],
        "background": "案例库是纯数据文件，改它不需要改代码，因此格式稳定性比灵活扩展更重要。",
        "steps": ["新增案例追加到 cases 数组", "保持 version 与 updated_at 更新", "改完跑测试确认条数与检索正常"],
        "troubleshooting": [
            {"symptom": "启动提示知识库为空", "check": "cases 是否被误清空、键名是否写错", "fix": "恢复 cases 数组，键名保持 cases 全小写"},
            {"symptom": "中文显示乱码", "check": "文件是否以 UTF-8 保存", "fix": "统一 UTF-8 无 BOM 保存"},
        ],
        "best_practices": ["改数据也提交 Git，便于回溯", "批量导入前先备份，导入后抽查三条"],
        "related": ["KB-DATA-001", "KB-MOD-002", "KB-GUIDE-005"],
    },
    "KB-DATA-006": {
        "aliases": ["条目结构", "KBEntry", "项目知识库结构"],
        "background": "工程知识需要比案例更多的结构化字段（签名、参数、适用范围、注意事项），字段一旦随意增删，检索与校验都会失效。",
        "steps": [
            "按 FIELD_ORDER 顺序写条目",
            "category 必须是已定义分类 id",
            "related 只能填已存在的条目编号",
            "跑 verify_kb.py 确认无漂移",
        ],
        "troubleshooting": [
            {"symptom": "verify 报 related 指向不存在的条目", "check": "编号是否拼错或条目已删除", "fix": "修正编号，或先补上被引用条目"},
            {"symptom": "分类过滤查不到新条目", "check": "category 是否写成中文名", "fix": "改成分类 id，如 module、api"},
        ],
        "best_practices": ["新增字段先改 KBEntry 再改数据，避免读不出来", "related 双向补齐，方便从任意入口导航"],
        "related": ["KB-MOD-009", "KB-TOOL-005", "KB-GUIDE-005"],
    },
    # ---------------- config ----------------
    "KB-CFG-001": {
        "aliases": ["配置字段", "Settings 字段", "默认值"],
        "background": "配置项决定了模型接入、检索行为与运行模式，字段默认值即开箱可用状态，不能依赖用户先改配置。",
        "steps": ["查默认值看 dataclass 定义", "改默认值要评估对现有测试的影响", "新增字段同步更新 config.example.json"],
        "troubleshooting": [
            {"symptom": "示例配置照抄后行为异常", "check": "config.example.json 是否落后于代码", "fix": "以 dataclass 为准更新示例文件"},
        ],
        "best_practices": ["示例文件里 force_offline 默认 true，避免误联网", "数值型字段写清合法区间"],
        "related": ["KB-MOD-001", "KB-CFG-002", "KB-API-008"],
    },
    "KB-CFG-002": {
        "aliases": ["配置优先级", "环境变量", "密钥管理"],
        "background": "同一份代码要跑在课堂、内网与 CI 三种环境，靠优先级覆盖比维护多份配置文件更可靠。",
        "steps": ["CI 用环境变量注入密钥", "本地用 config.json 覆盖模型与地址", "强制离线用 EFA_FORCE_OFFLINE=1"],
        "troubleshooting": [
            {"symptom": "环境变量与文件冲突", "check": "load 的覆盖顺序", "fix": "记住优先级：环境变量高于文件高于默认"},
            {"symptom": "密钥被误提交", "check": "git status 是否包含 config.json", "fix": "确认 gitignore 生效，必要时 rotate 密钥"},
        ],
        "best_practices": ["密钥优先环境变量，文件只做本地兜底", "任何日志与界面都只显示掩码"],
        "related": ["KB-MOD-001", "KB-API-008", "KB-BND-001"],
    },
    "KB-CFG-003": {
        "aliases": ["检索调参", "阈值", "top_k"],
        "background": "召回与精度是一对矛盾：阈值高则经常无依据，阈值低则容易答错；默认值要在演示与真实使用之间折中。",
        "steps": ["先用默认值跑 10 个真实问题", "统计无依据率与 Top1 正确率", "只调一个参数并记录结果"],
        "troubleshooting": [
            {"symptom": "大量问题被判无依据", "check": "是否关键词覆盖不足而非阈值问题", "fix": "先补关键词，再考虑降阈值"},
            {"symptom": "回答引用了不相关案例", "check": "Top1 分数是否刚过阈值", "fix": "适当提高阈值或补负例关键词"},
        ],
        "best_practices": ["一次只改一个参数，改完跑全量测试", "把调参结论写进开发记录，避免反复试错"],
        "related": ["KB-API-003", "KB-MOD-002", "KB-GUIDE-005"],
    },
    # ---------------- error ----------------
    "KB-ERR-001": {
        "aliases": ["统一返回", "ok error", "返回约定"],
        "background": "模型不理解异常栈，只理解文本；因此工具失败也必须以结构化字典返回，让模型能读懂并自行纠正。",
        "steps": ["成功返回 ok=true 加业务字段", "失败返回 ok=false 加 error 文案", "调用方只判 ok，不捕异常"],
        "troubleshooting": [
            {"symptom": "调用方仍然写了 try", "check": "是否信任 execute 的兜底", "fix": "去掉多余 try，改为判 ok，避免掩盖真问题"},
        ],
        "best_practices": ["error 文案面向下一步动作，不写内部堆栈", "失败也要有 ToolCallRecord"],
        "related": ["KB-MOD-003", "KB-API-006", "KB-ERR-004"],
    },
    "KB-ERR-002": {
        "aliases": ["错误标识", "error 字段", "状态码"],
        "background": "界面需要根据错误类型决定展示方式：空输入要提示，知识库问题要指引修复，降级要标注模式。",
        "steps": ["新增标识先定义语义", "界面按前缀判断展示", "日志统计各标识占比"],
        "troubleshooting": [
            {"symptom": "错误提示都一样", "check": "是否只用了统一文案", "fix": "按标识区分提示，给出不同下一步"},
        ],
        "best_practices": ["标识用英文小写下划线，文案用中文", "llm_failed 后统一跟冒号与原因"],
        "related": ["KB-DATA-004", "KB-ERR-003", "KB-ERR-004"],
    },
    "KB-ERR-003": {
        "aliases": ["LLMError", "接口失败", "降级原因"],
        "background": "接口失败的成因差别很大（密钥、限流、网络、配置错误），若不分类，用户只能看到一句请求失败，无法自助排查。",
        "steps": ["按 HTTP 状态与异常类型分档", "每档给可执行提示", "上层捕获后统一降级"],
        "troubleshooting": [
            {"symptom": "只看到请求失败", "check": "是否吞掉了 HTTP 状态码", "fix": "把状态码与响应体前 300 字带上"},
            {"symptom": "偶发超时", "check": "timeout 与网络质量", "fix": "适当调大超时，必要时提示用户重试"},
        ],
        "best_practices": ["错误信息里绝不回显密钥", "同一请求不要自动无限重试"],
        "related": ["KB-MOD-004", "KB-ARCH-002", "KB-API-009"],
    },
    # ---------------- dependency ----------------
    "KB-DEP-001": {
        "aliases": ["标准库", "内置模块", "依赖清单"],
        "background": "交付目标是双击即用，任何第三方包都会让目标机器多一步安装，因此技术选型优先在标准库内解决。",
        "steps": ["新需求先查标准库是否有等价能力", "确实不够再评估第三方包的成本", "引入前写清降级路径"],
        "troubleshooting": [
            {"symptom": "某机器缺 tkinter", "check": "解释器是否为精简版", "fix": "用 start.bat 探测并切换到完整版解释器"},
        ],
        "best_practices": ["能用 20 行标准库解决的，不引 2MB 依赖", "依赖说明写进 README，不靠口头传达"],
        "related": ["KB-DEP-002", "KB-BND-002", "KB-MOD-004"],
    },
    "KB-DEP-002": {
        "aliases": ["零依赖", "dependencies", "交付约束"],
        "background": "评审与演示常在陌生机器上进行，装包失败会直接毁掉演示，因此把零依赖当成硬约束而不是偏好。",
        "steps": ["新增依赖前先评估：是否影响零安装", "必要时放 optional-dependencies", "在 README 说明可选依赖"],
        "troubleshooting": [
            {"symptom": "uv sync 后仍提示缺包", "check": "是否误写进 dependencies", "fix": "移到 optional 分组，核心路径不依赖它"},
        ],
        "best_practices": ["核心路径只用标准库", "打包工具等重型依赖放 build 分组"],
        "related": ["KB-DEP-001", "KB-DEP-003", "KB-DEP-004"],
    },
    "KB-DEP-003": {
        "aliases": ["uv", "Git 工作流", "仓库托管"],
        "background": "环境与版本是复现的两条腿：uv 固定依赖，Git 固定代码，两者都缺失时问题不可复现。",
        "steps": ["uv lock 生成锁文件并提交", "uv sync 建环境", "改动按 feat/fix/test/docs 前缀提交", "推送 origin 与 gitee 双远程"],
        "troubleshooting": [
            {"symptom": "uv.lock 缺失导致版本漂移", "check": "是否执行过 uv lock 并提交", "fix": "在本机执行 uv lock 后提交锁文件"},
            {"symptom": "推送因网络失败", "check": "代理或连通性", "fix": "换网络重试，或先推内网远程"},
        ],
        "best_practices": ["一次提交只做一件事", "提交前跑测试与一致性校验"],
        "related": ["KB-DEP-002", "KB-CONV-005", "KB-MOD-008"],
    },
    # ---------------- convention ----------------
    "KB-CONV-001": {
        "aliases": ["命名规范", "目录规范", "代码风格"],
        "background": "小项目也怕随手命名：一旦出现 utils.py 这类收纳模块，半年后就没人知道逻辑该放哪。",
        "steps": ["按职责建文件，不按类型建文件", "类用大驼峰，函数用下划线，常量全大写", "测试文件以 test_ 开头"],
        "troubleshooting": [
            {"symptom": "测试没被 discover 到", "check": "文件名是否以 test_ 开头", "fix": "重命名文件或在 run_tests 中显式指定"},
        ],
        "best_practices": ["目录名用英文，界面文案用中文", "新增模块先写职责注释再写实现"],
        "related": ["KB-ARCH-001", "KB-CONV-004", "KB-CONV-005"],
    },
    "KB-CONV-002": {
        "aliases": ["日志规范", "JSONL 格式", "日志字段"],
        "background": "日志要既能被人读，也能被脚本统计；JSONL 一行一条正好兼顾，且追加写入不会破坏历史。",
        "steps": ["统一用 SessionLog 写", "新增字段放进 payload", "统计用脚本按 kind 过滤"],
        "troubleshooting": [
            {"symptom": "解析日志报 JSON 错误", "check": "是否写入了换行", "fix": "禁止多行字符串，必要时先转义"},
        ],
        "best_practices": ["字段名保持稳定，新增不删旧", "敏感字段一律不写"],
        "related": ["KB-MOD-006", "KB-API-010", "KB-DATA-003"],
    },
    "KB-CONV-003": {
        "aliases": ["测试规范", "单元测试", "回归"],
        "background": "这个项目的正确性靠两类断言守住：检索排序不能退步，未覆盖时不能编造；两者都必须有测试，否则改一处坏一片。",
        "steps": ["新增功能先想断言什么行为", "领域逻辑写单测，界面写构建与渲染测试", "改动后跑全量 run_tests"],
        "troubleshooting": [
            {"symptom": "测试在无图形环境失败", "check": "是否缺少 skipUnless", "fix": "对 Tkinter 相关用例加跳过条件"},
            {"symptom": "重构后测试全红", "check": "断言是否耦合实现细节", "fix": "断言行为而非内部调用顺序"},
        ],
        "best_practices": ["先写失败用例再修 bug", "测试名描述行为，不写 test1"],
        "related": ["KB-CONV-004", "KB-MOD-009", "KB-GUIDE-005"],
    },
    # ---------------- boundary ----------------
    "KB-BND-001": {
        "aliases": ["安全边界", "只读", "合规"],
        "background": "设备咨询一旦越界成设备控制，风险就从答错升级为安全事故，因此边界必须在架构层面封死，而不是靠提示词约束。",
        "steps": ["评审新功能是否引入写操作", "确认无设备通信协议栈", "确认密钥与数据不入库"],
        "troubleshooting": [
            {"symptom": "有人要求远程启停设备", "check": "是否属于范围外", "fix": "明确拒绝，说明本工具只做咨询建议"},
        ],
        "best_practices": ["回答涉及高温高压先给安全隔离提示", "涉敏数据不进模拟库"],
        "related": ["KB-CFG-002", "KB-BND-003", "KB-ERR-004"],
    },
    "KB-BND-002": {
        "aliases": ["版本兼容", "Python 版本", "Windows 兼容"],
        "background": "目标机器可能是 Windows 10 上的精简 Python，语法用了 3.11 特性或依赖 Tkinter 新版本都会直接启动失败。",
        "steps": ["写代码避开 3.11+ 独有语法", "start.bat 探测解释器能力", "界面按最小尺寸设计"],
        "troubleshooting": [
            {"symptom": "报无 tkinter 模块", "check": "解释器是否为精简发行版", "fix": "改用完整版，或退回 CLI 模式"},
            {"symptom": "高分屏字体重叠", "check": "是否写死像素字号", "fix": "用相对布局与最小尺寸约束"},
        ],
        "best_practices": ["声明 requires-python 并与实际语法一致", "在两种 Windows 版本上各启动一次"],
        "related": ["KB-DEP-001", "KB-MOD-008", "KB-BND-004"],
    },
    "KB-BND-003": {
        "aliases": ["已知限制", "不做清单", "范围边界"],
        "background": "把不做的事写清楚，比承诺更多功能更能建立信任；也避免后续需求不断挤压 MVP 范围。",
        "steps": ["新需求先对照不做清单", "超出范围时给出演进路径而非硬做", "把结论写回条目"],
        "troubleshooting": [
            {"symptom": "需求要求支持千条案例", "check": "当前检索是否线性扫描", "fix": "先换倒排或向量检索，再扩数据量"},
        ],
        "best_practices": ["不做清单要写理由，不只是结论", "演进路径分阶段，避免一次性重构"],
        "related": ["KB-BND-001", "KB-BND-004", "KB-GUIDE-006"],
    },
}
