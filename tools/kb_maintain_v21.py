"""知识库 v2.0 → v2.1 维护脚本：修正、合并、新增、重建索引。

维护动作分三类，执行后打印 新增/修改/删除 计数：
  PATCHES    —— 修正过时表述、补别名、合并被删除条目的有效内容
  DELETIONS  —— 删除与其他条目重复的薄条目（内容已并入目标条目）
  ADDITIONS  —— 新增覆盖新能力与新规则的条目

运行：python tools/kb_maintain_v21.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "project_kb.json"

CATEGORY_ORDER = [
    "guide", "architecture", "module", "api", "tool",
    "data", "config", "error", "dependency", "convention", "boundary",
]

FIELD_ORDER = [
    "id", "category", "title", "summary", "symbol", "signature", "aliases",
    "background", "when_to_use", "inputs", "outputs", "steps", "scenarios",
    "cautions", "troubleshooting", "best_practices", "related", "scope",
    "version", "tags", "refs", "details",
]

# ---------------------------------------------------------------- 删除

DELETIONS = {
    "KB-DATA-002": "检索结果结构已并入 KB-API-003 的输出说明，独立成条信息量不足",
    "KB-DATA-005": "案例库文件结构已并入 KB-DATA-001 的说明，与字段规范高度重复",
}

# ---------------------------------------------------------------- 修改

PATCHES: dict[str, dict] = {
    "KB-API-003": {
        "title": "KnowledgeBase.search 检索接口",
        "summary": "案例库加权检索，返回按相关度降序的命中列表，空列表表示无依据。",
        "aliases": ["检索接口", "search", "检索结果", "命中结构", "SearchHit"],
        "outputs": "list[SearchHit]；每个含 case（FaultCase）、score（0~1）、matched（命中词）；brief(rank) 输出精简结构",
        "details": (
            "score = 0.42*设备名命中 + 0.20*关键词命中(上限 4) + 0.55*dice(query, symptom) "
            "+ 0.20*dice(query, 全文)；再经 1-exp(-1.15*score) 压缩到 0~1，排序键 (-score, case.id)。"
            "命中项 SearchHit 提供 brief(rank) 生成工具返回用的精简结构："
            "rank/case_id/equipment/symptom/risk/score/matched_terms（截断 6 个）。"
        ),
        "cautions": [
            "query 为空时直接返回 []，不抛异常",
            "score 是相对值不是概率，不要向用户表述为准确率",
            "打分公式改动会同时影响有依据/无依据判定，必须回归测试",
        ],
        "related": ["KB-MOD-002", "KB-CFG-003", "KB-DATA-001", "KB-TOOL-001"],
    },
    "KB-DATA-001": {
        "aliases": ["案例字段", "FaultCase", "案例结构", "fault_cases.json", "案例库文件"],
        "background": "案例是检索与回答的唯一素材，字段设计与文件结构直接决定召回质量：现象用于相似度，关键词用于命中，步骤用于回答。",
        "details": (
            "id 形如 EFA-001 全局唯一；equipment 为设备类型名（用于设备命中加权 0.42）；model 为型号范围；"
            "symptom 参与相似度计算；causes/steps 为字符串数组且至少 1 条；risk 取高/中/低；source 记录数据来源；"
            "from_dict 会丢弃空字符串项。文件顶层结构：version、updated_at、disclaimer 与 cases 数组；"
            "disclaimer 会拼进离线回答末尾，version 仅用于展示；顶层若直接是数组也兼容。"
        ),
        "cautions": [
            "keywords 是检索命中率的关键，至少 3 个且要包含口语化说法",
            "steps 必须把安全措施放在最前",
            "文件必须是合法 JSON（无注释、无尾逗号），cases 为空数组视为知识库为空",
        ],
        "related": ["KB-DATA-006", "KB-API-003", "KB-GUIDE-005", "KB-MOD-002"],
    },
    "KB-API-008": {
        "title": "Settings.load / save 与配置优先级",
        "summary": "读配置（环境变量 > config.json > 默认值）与写回本地 config.json，决定运行模式与密钥来源。",
        "aliases": ["配置读写", "load", "save", "配置优先级", "环境变量优先级", "密钥管理"],
        "when_to_use": ["程序启动", "界面保存并应用", "排查配置冲突或密钥未生效"],
        "details": (
            "load() 顺序：实例化默认值 → 读 CONFIG_FILE 覆盖 → 环境变量覆盖"
            "（EFA_BASE_URL/EFA_MODEL/EFA_TIMEOUT/EFA_FORCE_OFFLINE 与密钥）→ 数值兜底与范围收敛"
            "（top_k 1~5、max_rounds 1~12）。save() 用 asdict() 全量写回。"
            "密钥按 EFA_API_KEY、OPENAI_API_KEY、DEEPSEEK_API_KEY 顺序取第一个非空值。"
        ),
        "related": ["KB-MOD-001", "KB-CFG-001", "KB-BND-001", "KB-API-009"],
    },
    "KB-GUIDE-001": {
        "steps": [
            "双击 start.bat 或执行 python app.py，确认窗口能开",
            "运行 python run_tests.py，确认 67 项全部通过",
            "读 src/efa/agent.py 的 ask()，理解选路与降级",
            "改一处文案或新增一条案例，跑测试确认无回归",
            "数据改动后执行 python tools/rebuild_index.py，再跑 python tools/verify_kb.py",
        ],
        "details": "路线可压缩到 30 分钟：5 分钟跑起来、5 分钟跑测试、10 分钟读 agent.py、5 分钟改一处、5 分钟验证。卡住时去排障索引按症状查。数据与索引必须成对更新，否则检索会退回线性扫描。",
    },
    "KB-GUIDE-005": {
        "steps": [
            "定主题：一条目只讲一件事，先定 category 与 id",
            "写内容：背景、调用条件、参数、步骤、注意事项、排障、最佳实践",
            "连引用：related 双向补齐，refs 指向真实文件",
            "重建索引：python tools/rebuild_index.py",
            "跑校验：python tools/verify_kb.py 必须 0 错误",
            "跑测试：python run_tests.py 全绿后提交",
        ],
        "details": "流程分六步：定主题、写内容、连引用、重建索引、跑校验、跑测试。校验不通过不允许提交；索引未重建会让 ProjectKB 标记 stale 并退回线性扫描。新增字段时先改 KBEntry 与 kbcheck，再批量补数据。",
    },
    "KB-GUIDE-006": {
        "details": "版本线：v1.0.0 三工具与桌面客户端；v1.1.0 项目知识库（52 条、10 类、3 个知识工具、一致性校验）；v2.0.0 字段体系扩展（背景、步骤、排障、最佳实践、交叉引用）与导航层；v2.1.0 维护迭代（修正过时表述、合并 2 条重复条目、补 6 条新能力与规则、引入倒排索引）。",
        "aliases": ["版本", "变更记录", "changelog", "版本约束", "发布记录"],
    },
    "KB-TOOL-006": {
        "summary": "列出项目知识库的 11 个分类及各自条目数，用于先缩小检索范围。",
    },
    "KB-GUIDE-002": {
        "details": (
            "核心术语：Agent（编排层，决定调用哪个工具）、工具调用（模型输出 tool_calls 并由程序执行）、"
            "案例库（fault_cases.json，设备维修知识）、项目知识库（project_kb.json，工程知识）、"
            "检索打分（加权后压缩到 0~1 的相关度）、降级（模型不可用时切离线规则）、"
            "条目（KB-xxx 一条记录）、命中（检索返回的结果项）、倒排索引（词项到条目编号的映射，"
            "由 tools/rebuild_index.py 生成）、索引状态（fresh/stale/missing）。"
        ),
    },
    "KB-GUIDE-004": {
        "details": (
            "高频问题：能否接真实设备（不能，安全边界）；能否换模型（能，改 base_url 与 model）；"
            "没密钥能用吗（能，离线规则模式）；为什么不用 LangChain（规模不需要，零依赖优先）；"
            "案例从哪来（模拟数据，非真实工单）；能否多人使用（当前单机，P2 服务化）；"
            "支持语音吗（不支持，与验证目标无关）；数据存哪（本地 JSON 与 logs）；"
            "为什么要重建索引（索引记录数据哈希，数据变了必须重建，否则退回线性扫描）。"
        ),
    },
    "KB-API-010": {
        "title": "SessionLog 写日志方法",
        "aliases": ["日志接口", "SessionLog", "会话日志方法", "question/answer", "tool_calls"],
        "tags": ["日志", "接口", "记录", "会话"],
    },
    "KB-API-012": {
        "aliases": ["界面接口", "on_send", "导出会话", "清空对话", "界面交互"],
    },
    "KB-MOD-009": {
        "cautions": [
            "条目内容必须与源码一致，改动代码后要跑 tools/verify_kb.py",
            "新增条目要指定 category，否则检索过滤失效",
            "检索接口细节见 KB-API-011，字段规范见 KB-DATA-006，三者分工不同不要互相抄",
        ],
    },
    "KB-ARCH-002": {
        "cautions": [
            "离线回答首行必须标注离线规则模式，不得伪装成模型输出",
            "两条路径的工具调用记录都会被写入日志，可对比",
            "路由判定见 KB-API-013，降级原因分类见 KB-ERR-003",
        ],
    },
}

# ---------------------------------------------------------------- 新增

ADDITIONS: list[dict] = [
    {
        "id": "KB-API-014",
        "category": "api",
        "title": "ProjectKB.stats 与 related_entries",
        "summary": "输出知识库统计（字段覆盖率、引用密度、索引状态），并按 related 取关联条目。",
        "symbol": "ProjectKB.stats",
        "signature": "stats(self) -> dict；related_entries(self, entry: KBEntry) -> list[KBEntry]",
        "aliases": ["知识库统计", "stats", "关联条目", "related_entries", "覆盖率"],
        "background": "知识库是否健康需要可量化：覆盖率、引用密度、索引状态三个指标一旦能看到，退化就能被及时发现。",
        "when_to_use": ["写维护报告前取数", "判断索引是否过期", "从条目跳转到关联内容"],
        "inputs": [
            {"name": "entry", "type": "KBEntry", "required": True, "default": "", "desc": "related_entries 的入参，通常来自 get() 的返回"}
        ],
        "outputs": "stats 返回 {entries, categories, avg_related, coverage, troubleshooting_items, steps_items, index, index_terms}；related_entries 返回按声明顺序的条目列表",
        "steps": [
            "调 stats() 取覆盖率与索引状态",
            "覆盖率任一小于 1.0 说明有字段空缺，需补内容",
            "index 为 stale/missing 时先跑 tools/rebuild_index.py",
        ],
        "scenarios": ["生成更新清单", "巡检索引新鲜度", "回答条目之间如何关联"],
        "cautions": [
            "stats 只做统计不改数据，可在任何时刻调用",
            "related_entries 会忽略已失效编号，不会抛异常",
        ],
        "troubleshooting": [
            {"symptom": "stats 显示 index=stale", "check": "数据是否改过但没重建索引", "fix": "执行 python tools/rebuild_index.py"},
            {"symptom": "avg_related 突然下降", "check": "是否新增条目未写 related", "fix": "按维护流程补齐双向引用"},
        ],
        "best_practices": ["把 stats 的输出直接写进维护报告，避免手抄数字", "覆盖率掉到 1.0 以下视为质量门禁不通过"],
        "related": ["KB-MOD-009", "KB-GUIDE-005", "KB-DATA-007"],
        "scope": "src/efa/project_kb.py",
        "version": ">=2.1.0",
        "tags": ["统计", "接口", "索引", "质量"],
        "refs": ["src/efa/project_kb.py"],
        "details": "stats 的 coverage 覆盖 background/when_to_use/steps/troubleshooting/best_practices/related/aliases 七个字段，值为占比。index 取 fresh、stale、missing 三态，对应倒排索引是否与数据同版本。",
    },
    {
        "id": "KB-DATA-007",
        "category": "data",
        "title": "知识库元信息与字段规范元数据",
        "summary": "project_kb.json 顶层的 schema_version、field_spec、categories 三个元信息块，是格式契约的自我描述。",
        "symbol": "",
        "signature": "",
        "aliases": ["schema_version", "field_spec", "元信息", "格式契约"],
        "background": "字段规范只写在文档里容易与数据脱节；把它放进数据文件顶层，读取方与校验脚本都能就地取用。",
        "when_to_use": ["新增或调整字段", "写数据迁移脚本", "确认当前 schema 版本"],
        "inputs": [],
        "outputs": "顶层字段：schema_version（字符串）、field_spec（字段到说明的映射）、categories（分类定义数组）",
        "steps": [
            "改字段前先读 field_spec，确认是否已有定义",
            "新增字段要同时改 KBEntry、kbcheck 与 field_spec",
            "改完重建索引并跑校验",
        ],
        "scenarios": ["字段演进", "数据迁移", "对外解释格式"],
        "cautions": [
            "schema_version 与 entries 版本不是一回事：前者是格式版本，后者是内容适用版本",
            "field_spec 是说明性元数据，不参与检索打分",
        ],
        "troubleshooting": [
            {"symptom": "迁移脚本读不到字段说明", "check": "schema_version 是否仍为 2.0", "fix": "v2.1 仍沿用 2.0 格式，仅内容与索引变化"},
        ],
        "best_practices": ["格式变更必须升 schema_version 并写迁移脚本", "field_spec 用一句话说明，避免写成第二份文档"],
        "related": ["KB-DATA-006", "KB-API-014", "KB-GUIDE-005"],
        "scope": "data/project_kb.json",
        "version": ">=2.0.0",
        "tags": ["数据结构", "元信息", "契约"],
        "refs": ["data/project_kb.json"],
        "details": "field_spec 覆盖 id/summary/aliases/background/when_to_use/inputs/outputs/steps/scenarios/cautions/troubleshooting/best_practices/related/scope/version/tags/refs 共 17 项说明，其余字段语义由 KB-DATA-006 承担。",
    },
    {
        "id": "KB-ERR-005",
        "category": "error",
        "title": "知识库校验错误码表",
        "summary": "verify_kb 输出的 9 类错误码与 6 类警告码，按码定位比逐条读文案更快。",
        "symbol": "",
        "signature": "",
        "aliases": ["校验错误码", "BAD_SYMBOL", "DANGLING_RELATED", "verify 报错"],
        "background": "校验失败时如果只看到一句中文，很难判断是数据问题还是代码问题；错误码把处置路径固定下来。",
        "when_to_use": ["verify_kb 报错时", "给校验规则补新维度时"],
        "inputs": [],
        "outputs": "",
        "steps": [
            "看错误码首段定位类别",
            "按码查下表对应处置动作",
            "修完重建索引并复跑校验",
        ],
        "scenarios": ["符号改名后校验失败", "新增条目引用写错", "版本号格式写错"],
        "cautions": [
            "E 级会阻止提交，W 级只提示但不应长期忽略",
            "不要为了消除警告而删掉正常的提示性内容",
        ],
        "troubleshooting": [
            {"symptom": "BAD_SYMBOL 但类存在", "check": "符号是否写成了模块路径", "fix": "改用 类名 或 类名.方法"},
            {"symptom": "DANGLING_RELATED", "check": "related 里的编号是否已删除", "fix": "改为现存条目，或同步删除引用"},
            {"symptom": "STALE_NUMBER", "check": "正文中的数量断言是否过期", "fix": "按实际数量更新，或删掉易过期的具体数字"},
            {"symptom": "PLACEHOLDER", "check": "是否残留 TODO/待补充", "fix": "补完内容或删除该段"},
        ],
        "best_practices": ["提交前固定跑一次 verify_kb", "新增校验维度时同步补一条反例测试"],
        "related": ["KB-MOD-010", "KB-GUIDE-005", "KB-DATA-006"],
        "scope": "src/efa/kbcheck.py",
        "version": ">=2.1.0",
        "tags": ["校验", "错误码", "排障"],
        "refs": ["src/efa/kbcheck.py"],
        "details": "E 级：KB_LOAD、DUP_ID、MISSING_FIELD、BAD_CATEGORY、BAD_REF、BAD_SYMBOL、BAD_SIGNATURE、BAD_FIELDS、TOOL_NOT_EXPOSED、TOOL_UNDOCUMENTED、CFG_DRIFT、STALE_NUMBER、BAD_ID_PREFIX、ID_CATEGORY_MISMATCH、DUP_TITLE、BAD_VERSION、BAD_TROUBLESHOOTING、SELF_REFERENCE、DANGLING_RELATED、PLACEHOLDER。W 级：EMPTY_LIST、ORPHAN_CATEGORY、TITLE_LENGTH、SUMMARY_LENGTH、BACKGROUND_THIN、TOO_FEW、TOO_MANY、ASYMMETRIC_RELATED。",
    },
    {
        "id": "KB-CONV-006",
        "category": "convention",
        "title": "文档构建规范（Markdown 转 Word）",
        "summary": "交付文档的构建规则：分段插入、禁用特定结构、失败整份重建，避免重复章节。",
        "symbol": "",
        "signature": "",
        "aliases": ["文档构建", "docx_build", "生成 Word", "排版规范"],
        "background": "编辑器单次插入过长内容会整段失败，且失败会留下半截内容；不把这些经验固化，每次生成文档都要重新踩坑。",
        "when_to_use": ["修改交付文档后重新生成", "新增一份需要 Word 版的文档"],
        "inputs": [],
        "outputs": "排版规范的 docx：封面、目录、标题层级、正文样式",
        "steps": [
            "把内容写成 Markdown，标题层级不超过三级",
            "执行 python tools/docx_build.py --source ... --cover ... --output ...",
            "打开生成结果，确认目录与章节无重复",
        ],
        "scenarios": ["交付文档改版", "生成更新报告"],
        "cautions": [
            "代码块里不要出现由等号组成的整行分隔线，会让插入整段失败",
            "封面最后一段应是普通段落，避免在表格末尾插入正文",
            "失败后不要在同一文档内重试，必须整份重建",
        ],
        "troubleshooting": [
            {"symptom": "报 HTML segment insertion failed", "check": "失败片段是否含长表格或特殊分隔线", "fix": "改为段落级切块，或把分隔线换成文字"},
            {"symptom": "文档出现重复章节", "check": "是否在同一文档内重试过", "fix": "删除产物重新构建"},
        ],
        "best_practices": ["构建后用脚本核对一级标题出现次数", "封面文案改动后确认标题坐标仍正确"],
        "related": ["KB-CONV-004", "KB-GUIDE-005", "KB-DEP-003"],
        "scope": "tools/docx_build.py",
        "version": ">=2.1.0",
        "tags": ["文档", "构建", "规范"],
        "refs": ["tools/docx_build.py"],
        "details": "构建器按段落块切分（默认 900 字，失败降到 600、400），每次插入前取文档末尾可操作位置；封面标题坐标从文档结构解析；保存后尝试写入 updateFields 以便 Word 刷新目录。标题层级：一级用于部分，二级用于小节，三级用于子节。",
    },
    {
        "id": "KB-DEP-005",
        "category": "dependency",
        "title": "双远程发布流程（GitHub 与 Gitee）",
        "summary": "一份代码推两个远程的固定动作：提交分组、打标签、并行推送、失败处置。",
        "symbol": "",
        "signature": "",
        "aliases": ["双远程", "发布流程", "push", "推送失败", "打标签"],
        "background": "国内网络访问 GitHub 不稳定，单一远程会让交付卡住；双远程既保证可达，也保留了备份。",
        "when_to_use": ["每次迭代收尾", "需要给他人分享代码时", "推送失败需要判断是网络还是权限"],
        "inputs": [],
        "outputs": "两个远程指向同一提交，标签同步",
        "steps": [
            "按 feat/fix/test/docs/chore 分组提交",
            "git tag -a vX.Y.Z 并写清该版本变化",
            "git push gitee main --tags 与 git push origin main --tags",
            "失败时先用 git ls-remote 判断连通性，再重试",
        ],
        "scenarios": ["版本发布", "网络波动", "双人协作"],
        "cautions": [
            "推送失败可能是代理返回 502，不是权限问题，重试或换网络",
            "标签要随分支一起推，避免远程缺版本",
        ],
        "troubleshooting": [
            {"symptom": "CONNECT tunnel failed 502", "check": "代理与网络连通性", "fix": "换网络或稍后重试，另一个远程先推"},
            {"symptom": "鉴权失败", "check": "凭据是否过期", "fix": "重新登录或使用令牌，令牌不写入仓库配置"},
        ],
        "best_practices": ["先推可达的远程，另一个留待网络恢复", "推送前跑测试与一致性校验"],
        "related": ["KB-DEP-003", "KB-CONV-005", "KB-GUIDE-006"],
        "scope": "仓库根目录",
        "version": ">=2.1.0",
        "tags": ["发布", "远程", "流程"],
        "refs": ["README.md", "docs/开发记录.md"],
        "details": "远程约定：origin 指 GitHub，gitee 指 Gitee，两者指向同一提交。令牌只用于单条命令的临时 URL，不写入 .git/config；推送后用 git ls-remote 核对分支与标签。",
    },
    {
        "id": "KB-GUIDE-007",
        "category": "guide",
        "title": "检索权重与调优规则",
        "summary": "工程知识检索的打分构成与调参边界：符号 0.50、别名 0.26、标签 0.18、症状 0.30、阈值 0.18。",
        "symbol": "",
        "signature": "",
        "aliases": ["检索权重", "打分规则", "阈值", "调优", "为什么搜不到"],
        "background": "检索效果不稳定时，如果不知道各项权重与阈值，只能靠猜；把规则写清楚，调参才有依据。",
        "when_to_use": ["检索结果不符合预期", "新增条目后命中率低", "调整召回范围"],
        "inputs": [],
        "outputs": "",
        "steps": [
            "先用标题检索，确认该条目自身能否排第一",
            "不能则补 aliases 或 tags，而不是先调阈值",
            "仍需放宽时，下调 min_score（默认 0.18）",
        ],
        "scenarios": ["新条目搜不到", "同义说法无命中", "跨类目命中过多"],
        "cautions": [
            "权重与阈值是全局的，为单个条目调参会影响其他条目",
            "调低阈值会引入噪声，宁可补别名",
        ],
        "troubleshooting": [
            {"symptom": "条目存在但搜不到", "check": "标题是否含专有名词、别名是否覆盖口语", "fix": "补 2~3 个别名与标签"},
            {"symptom": "命中了不相干条目", "check": "是否只命中通用词（如配置、异常）", "fix": "加 category 过滤，或改用更具体的词"},
        ],
        "best_practices": ["每次调参只改一个变量并记录结果", "把调参结论写进维护记录，避免反复试错"],
        "related": ["KB-API-011", "KB-CFG-003", "KB-GUIDE-005"],
        "scope": "src/efa/project_kb.py",
        "version": ">=2.1.0",
        "tags": ["检索", "权重", "调优", "导航"],
        "refs": ["src/efa/project_kb.py"],
        "details": "权威命中 +0.50；别名每项 +0.26（最多 2 项）；标签每项 +0.18（最多 4 项）；排障症状相似度 ≥0.25 时 +0.30；标题相似度最高 0.45；背景与说明 0.12。总分经 1-exp(-1.1*score) 压缩，默认阈值 0.18，返回前 1~5 条。",
    },
]


def main() -> int:
    raw = json.loads(KB_PATH.read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in raw["entries"]}
    before = len(entries)

    deleted = []
    for eid in DELETIONS:
        if eid in entries:
            entries.pop(eid)
            deleted.append(eid)

    modified = 0
    for eid, patch in PATCHES.items():
        if eid not in entries:
            raise SystemExit(f"补丁目标不存在：{eid}")
        entries[eid].update(patch)
        modified += 1

    added = 0
    for entry in ADDITIONS:
        if entry["id"] in entries:
            raise SystemExit(f"新增条目编号冲突：{entry['id']}")
        entries[entry["id"]] = entry
        added += 1

    # 清理指向已删除条目的引用
    for entry in entries.values():
        entry["related"] = [r for r in entry.get("related", []) if r in entries]

    # related 双向闭合
    for eid, entry in entries.items():
        for target in list(entry.get("related", [])):
            if target == eid:
                entry["related"].remove(target)
            elif eid not in entries[target].setdefault("related", []):
                entries[target]["related"].append(eid)

    for entry in entries.values():
        entry["related"] = [r for r in entry.get("related", []) if r != entry["id"]]

    normalized = []
    for entry in entries.values():
        fixed = {key: entry.get(key) for key in FIELD_ORDER}
        normalized.append(fixed)
    order = {cid: i for i, cid in enumerate(CATEGORY_ORDER)}
    normalized.sort(key=lambda e: (order.get(e["category"], 99), e["id"]))

    raw["entries"] = normalized
    raw["version"] = "2.1.0"
    raw["project_version"] = "2.1.0"
    raw["updated_at"] = "2026-11-10"
    KB_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"删除 {len(deleted)} 条：{', '.join(deleted)}")
    print(f"修改 {modified} 条")
    print(f"新增 {added} 条：{', '.join(e['id'] for e in ADDITIONS)}")
    print(f"条目总数 {before} -> {len(normalized)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
