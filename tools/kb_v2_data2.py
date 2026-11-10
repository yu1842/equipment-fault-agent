"""知识库 v2.0 富化数据（二）：接口与工具。纯数据模块。"""

ENRICH_2: dict[str, dict] = {
    # ---------------- api ----------------
    "KB-API-001": {
        "aliases": ["ask", "问答接口", "Agent.ask"],
        "background": "界面、CLI、测试三条调用方都需要同一个入口，否则行为会分叉；ask() 因此承担全部编排职责。",
        "steps": [
            "界面在子线程调用，CLI 直接调用",
            "取 Answer.text 渲染，Answer.mode 决定标签",
            "需要独立会话时先调 reset()",
        ],
        "troubleshooting": [
            {"symptom": "返回 empty_input", "check": "输入是否只有空白字符", "fix": "提示用户补充设备与现象后再发"},
            {"symptom": "返回 kb_unavailable", "check": "知识库文件是否被移动或损坏", "fix": "恢复 data/fault_cases.json 后重试"},
        ],
        "best_practices": ["同步接口不要在主线程直接调用", "判断成功看 Answer.error 是否为空"],
        "related": ["KB-MOD-005", "KB-DATA-004", "KB-API-002"],
    },
    "KB-API-002": {
        "aliases": ["reset", "清空历史", "新会话"],
        "background": "多轮上下文会累积 token 并影响判断，切换话题或跑测试用例时需要显式重置。",
        "steps": ["界面点清空对话时调用", "测试用例 setUp 中调用保证隔离"],
        "troubleshooting": [
            {"symptom": "清空后回答仍受上文影响", "check": "是否只清了界面没清 history", "fix": "确保 clear_chat 调用 agent.reset()"},
        ],
        "best_practices": ["只清历史，不动配置与知识库", "批量测试每条用例前都 reset，避免相互污染"],
        "related": ["KB-API-001", "KB-API-012"],
    },
    "KB-API-003": {
        "aliases": ["search", "检索接口", "KnowledgeBase.search"],
        "background": "检索是整个产品的依据来源，排序错了会直接导致答非所问，因此接口把分数与命中词一并返回，便于解释与调试。",
        "steps": [
            "工具层传 query 与 top_k 调用",
            "需要解释时读 matched 字段",
            "调阈值时同时看分数分布与 Top1 是否正确",
        ],
        "troubleshooting": [
            {"symptom": "Top1 明显不相关", "check": "命中的是设备名还是通用词", "fix": "补案例关键词，或调整设备名权重"},
            {"symptom": "空列表但人工判断相关", "check": "关键词是否覆盖口语说法", "fix": "把口语词加进 keywords 后复测"},
        ],
        "best_practices": ["query 先归一化再匹配", "分数是相对值，不要向用户表述为准确率"],
        "related": ["KB-MOD-002", "KB-CFG-003", "KB-DATA-002"],
    },
    "KB-API-004": {
        "aliases": ["get", "按编号查询", "案例详情"],
        "background": "回答需要完整原因与步骤，检索只返回摘要，详情由编号二次读取，避免一次性把所有案例塞进上下文。",
        "steps": ["从 search 命中取 case_id", "调 get 取完整字段", "编号不存在时让模型改用检索"],
        "troubleshooting": [
            {"symptom": "编号明明存在却取不到", "check": "是否带了空格或全角字符", "fix": "统一 strip 并转大写后比较"},
        ],
        "best_practices": ["返回 None 而非抛异常，由工具层转成可读错误", "编号大小写不敏感，降低模型出错概率"],
        "related": ["KB-TOOL-002", "KB-DATA-001"],
    },
    "KB-API-005": {
        "aliases": ["设备清单", "equipment_names", "覆盖设备"],
        "background": "拒答时告诉用户我们覆盖哪些设备，比单纯说不知道更有用，这个接口就是覆盖范围的唯一来源。",
        "steps": ["工具 list_equipment 调用", "拒答文案里拼接设备列表"],
        "troubleshooting": [
            {"symptom": "列表顺序与预期不一致", "check": "JSON 中案例顺序是否被调整", "fix": "顺序即文件顺序，需要固定就调整 cases 排列"},
        ],
        "best_practices": ["新增设备类型时同时补案例与关键词", "不要把设备清单写死在提示词里"],
        "related": ["KB-TOOL-003", "KB-DATA-001"],
    },
    "KB-API-006": {
        "aliases": ["execute", "执行工具", "工具调用入口"],
        "background": "模型给的参数不可信、工具实现也可能出错，执行层必须做到永不抛出、永远有记录，否则一次异常就毁掉整轮对话。",
        "steps": [
            "统一走 execute，不直接调私有方法",
            "判断成功看 result 里的 ok 字段",
            "需要审计时读返回的 ToolCallRecord",
        ],
        "troubleshooting": [
            {"symptom": "调用后没有记录", "check": "是否绕过了 execute", "fix": "改回 execute 入口"},
            {"symptom": "参数报错但模型不知道", "check": "错误是否以 ok=false 回填给模型", "fix": "保留 error 文案，让模型自行纠正"},
        ],
        "best_practices": ["业务失败用 ToolError，不要用 ValueError 混过去", "参数类型既支持字典也支持 JSON 字符串"],
        "related": ["KB-MOD-003", "KB-ERR-001", "KB-DATA-003"],
    },
    "KB-API-007": {
        "aliases": ["specs", "工具声明", "Schema"],
        "background": "模型只能看到 specs() 里的声明，没声明的工具等于不存在；description 写不清就会漏调或乱调。",
        "steps": ["新增工具后确认 specs 含该 name", "description 写清使用条件与不适用场景", "parameters 给 required"],
        "troubleshooting": [
            {"symptom": "模型反复调错工具", "check": "两个工具 description 是否边界模糊", "fix": "补不适用说明，划清职责边界"},
        ],
        "best_practices": ["声明与实现同步改，避免名字对不上", "工具数量控制在 10 个以内，过多会降低选择准确率"],
        "related": ["KB-MOD-003", "KB-ARCH-003", "KB-TOOL-001"],
    },
    "KB-API-008": {
        "aliases": ["load", "save", "配置读写"],
        "background": "配置需要启动即读、界面可改、密钥不落库，读写拆成 load 与 save 两个动作最简单可靠。",
        "steps": ["启动时 load 一次并注入 Agent", "界面保存时改字段后 save", "保存后重建 Agent 使配置生效"],
        "troubleshooting": [
            {"symptom": "保存后仍用旧配置", "check": "是否重建了 Agent", "fix": "save 后重新实例化 Agent 与工具注册表"},
            {"symptom": "配置文件损坏导致启动异常", "check": "load 是否容错", "fix": "load 对解析失败静默回退默认值，排查时先看文件本身"},
        ],
        "best_practices": ["保存前校验必填项", "密钥字段用密码框输入并掩码显示"],
        "related": ["KB-CFG-001", "KB-CFG-002", "KB-MOD-001"],
    },
    "KB-API-009": {
        "aliases": ["chat", "模型请求", "LLMClient.chat"],
        "background": "不同供应商都兼容 chat/completions，统一封装后换模型只改配置，不用改调用方。",
        "steps": ["组装 messages（system 加历史加本轮）", "传入 tools 声明", "取 message 判断是否有 tool_calls"],
        "troubleshooting": [
            {"symptom": "返回空内容且无 tool_calls", "check": "模型是否被参数截断", "fix": "抛 LLMError 交由上层降级，不要返回空字符串"},
        ],
        "best_practices": ["temperature 保持低值以保证稳定", "超时必填，避免线程永久挂起"],
        "related": ["KB-MOD-004", "KB-ERR-003", "KB-TOOL-001"],
    },
    "KB-API-010": {
        "aliases": ["日志接口", "question/answer", "tool_calls"],
        "background": "问答与工具调用需要分别落盘，才能区分模型说了什么和工具返回了什么。",
        "steps": ["发送前记 question", "渲染后记 answer", "工具记录逐条写 tool_call"],
        "troubleshooting": [
            {"symptom": "统计时发现缺 answer", "check": "异常路径是否提前 return", "fix": "在统一出口记录，保证成败都有日志"},
        ],
        "best_practices": ["方法只做写盘，不做格式化业务", "失败静默但不抛出，避免影响主流程"],
        "related": ["KB-MOD-006", "KB-CONV-002"],
    },
    "KB-API-011": {
        "aliases": ["ProjectKB.search", "工程检索接口"],
        "background": "工程问题的关键词是类名、方法名、配置名，与故障描述的词分布完全不同，因此单独实现打分。",
        "steps": ["工具层或 Agent 调用", "可按 category 先过滤", "读 matched 判断命中的是符号还是标签"],
        "troubleshooting": [
            {"symptom": "搜不到但条目确实存在", "check": "query 是否用了同义词", "fix": "改用 aliases 里的说法或符号名检索"},
            {"symptom": "跨类目命中过多", "check": "是否未指定 category", "fix": "加 category 缩小范围"},
        ],
        "best_practices": ["先 list_kb_categories 再检索，减少无效查询", "条目超过 100 条时考虑倒排索引替代线性打分"],
        "related": ["KB-MOD-009", "KB-TOOL-004", "KB-DATA-006"],
    },
    "KB-API-012": {
        "aliases": ["界面接口", "on_send", "导出会话"],
        "background": "界面方法同时承担交互与状态管理，若不收敛职责，测试只能靠人眼看窗口。",
        "steps": ["on_send 只做校验、置忙、起线程", "渲染交给 _render_answer", "清空与导出各自独立方法"],
        "troubleshooting": [
            {"symptom": "连点发送发起多次请求", "check": "busy 标志是否生效", "fix": "进入前判断 busy 并禁用按钮"},
            {"symptom": "导出的文件内容为空", "check": "transcript 是否被提前清空", "fix": "清空前导出，或按需重建 transcript"},
        ],
        "best_practices": ["界面方法尽量短，业务判断下沉到 Agent", "测试可直接调 _render_answer 绕过线程"],
        "related": ["KB-ARCH-004", "KB-MOD-007", "KB-API-002"],
    },
    # ---------------- tool ----------------
    "KB-TOOL-001": {
        "aliases": ["检索案例", "search_fault_cases", "查案例"],
        "background": "所有故障回答都必须有依据，这个工具是唯一入口；直接生成答案等于放弃可追溯性。",
        "steps": ["提炼设备名加现象作为 query", "读 hit_count 判断是否覆盖", "命中后取 Top1 编号再读详情"],
        "troubleshooting": [
            {"symptom": "命中 0 条但明显同类", "check": "query 里是否只有口语描述、缺设备名", "fix": "补设备名或型号再检索一次"},
            {"symptom": "命中多条难以取舍", "check": "Top1 与 Top2 分数差是否过小", "fix": "读详情对比关键原因，回答中列出次要候选"},
        ],
        "best_practices": ["一次检索不行就换关键词再试，最多两到三次", "命中 0 条必须明说无依据，不许编造编号"],
        "related": ["KB-API-003", "KB-TOOL-002", "KB-GUIDE-003"],
    },
    "KB-TOOL-002": {
        "aliases": ["案例详情", "get_case_detail", "读案例"],
        "background": "检索返回的是摘要，回答需要完整原因与步骤，因此按编号二次读取，避免把整库塞进上下文。",
        "steps": ["从检索结果取 case_id", "读取 causes 与 steps", "按安全优先顺序组织步骤"],
        "troubleshooting": [
            {"symptom": "编号报不存在", "check": "编号是否拼错或来自上一轮上下文", "fix": "重新检索获取有效编号，不要复用过期编号"},
        ],
        "best_practices": ["只读 Top1 与必要候选，避免上下文过长", "步骤输出时保留原始安全提示，不要删减"],
        "related": ["KB-TOOL-001", "KB-API-004", "KB-DATA-001"],
    },
    "KB-TOOL-003": {
        "aliases": ["设备清单", "list_equipment", "覆盖范围"],
        "background": "用户常问你们能查哪些设备，或问题模糊时需要一个范围参照，这个工具用一次调用回答覆盖度。",
        "steps": ["问题模糊时先列设备清单", "拒答时把清单拼进建议"],
        "troubleshooting": [
            {"symptom": "清单里没有用户提到的设备", "check": "是否为已知缺口", "fix": "明确告知未覆盖，并建议补充案例"},
        ],
        "best_practices": ["用它做拒答说明，不要用它猜答案", "清单变化时同步更新 README 的覆盖说明"],
        "related": ["KB-API-005", "KB-DATA-001"],
    },
    "KB-TOOL-004": {
        "aliases": ["工程检索", "search_project_kb", "查项目"],
        "background": "工程问题如果也走案例检索，会得到完全无关的设备建议；因此单独提供入口，并在 description 里划清边界。",
        "steps": ["判断问题是否关于本项目实现", "用模块名或符号名作 query", "必要时加 category 过滤"],
        "troubleshooting": [
            {"symptom": "返回的都是架构类条目", "check": "query 是否过于笼统（如怎么改）", "fix": "换成具体对象，如 ToolRegistry 或 Settings"},
            {"symptom": "分类过滤后为空", "check": "category id 是否拼错", "fix": "先 list_kb_categories 取准确 id"},
        ],
        "best_practices": ["与 search_fault_cases 严格分工，不要互相替代", "命中后通常还需 get_kb_entry 取完整契约"],
        "related": ["KB-TOOL-005", "KB-TOOL-006", "KB-API-011"],
    },
    "KB-TOOL-005": {
        "aliases": ["知识条目详情", "get_kb_entry", "读条目"],
        "background": "检索只给摘要，实现细节（参数、注意事项、适用范围）在完整条目里，按编号读取最省上下文。",
        "steps": ["从检索结果取 entry_id", "读取 inputs 与 cautions", "把 related 作为后续导航线索"],
        "troubleshooting": [
            {"symptom": "条目编号不存在", "check": "是否把案例编号 EFA 当成 KB", "fix": "改用 search_project_kb 重新检索"},
        ],
        "best_practices": ["回答工程问题时引用条目编号，便于对方复核", "不要一次读十个条目，按需逐个读"],
        "related": ["KB-TOOL-004", "KB-DATA-006", "KB-GUIDE-002"],
    },
    "KB-TOOL-006": {
        "aliases": ["分类列表", "list_kb_categories", "知识导航"],
        "background": "检索前先知道有哪些分类，能显著减少无效查询，也方便向用户解释知识库覆盖面。",
        "steps": ["不确定分类时先调用", "用返回的 id 作为 search 的 category 参数"],
        "troubleshooting": [
            {"symptom": "category 传 name 却查不到", "check": "是否误用了中文名而非 id", "fix": "search 只接受 id，name 仅供展示"},
        ],
        "best_practices": ["一次会话内缓存分类结果，避免重复调用", "新增分类时同步更新 categories 与 CATEGORY_ORDER"],
        "related": ["KB-TOOL-004", "KB-DATA-006", "KB-GUIDE-006"],
    },
}
