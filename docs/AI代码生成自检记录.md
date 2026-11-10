# 一、记录说明

本文件记录 **AI 生成代码 → 自检发现问题 → 定位与调整 → 验证结果** 的完整闭环，共三例。三例都取自本项目真实开发过程，且都可复现：日志由脚本现采、截图取自真实运行窗口、提交记录可在仓库内用 `git show` 查证。

| 项目 | 说明 |
| --- | --- |
| 记录对象 | 制造企业设备故障咨询 Agent（Python + Tkinter，零第三方依赖） |
| 代码来源 | 由 AI 生成，人工只提出需求与验收口径 |
| 自检手段 | 单元测试、一致性校验器、可复现脚本、界面自检 |
| 证据形式 | 运行日志（`docs/evidence/*.txt`）、界面截图（`docs/evidence/*.png`）、Git 提交（`git show`） |
| 复现入口 | `python tools/capture_evidence.py --case negative\|layout\|quotes` |

三例的"发现问题"都不是靠肉眼读代码，而是**先跑起来**：测试失败、断言取到 1、编译报错，都属于机器给出的客观信号。

---

# 二、案例一：为知识库新增案例后，两条"未覆盖"用例失效

## 2.1 AI 生成的内容

按"扩充案例库"的需求，AI 生成了迁移脚本 `tools/case_maintain_v22.py`，在原有 12 条案例上新增 12 条，其中包含注塑机模温问题：

| 新增编号 | 设备 | 现象 | 风险 |
| --- | --- | --- | --- |
| EFA-013 | 注塑机 | 模具温度升不到工艺值，产品缩水变形 | 中 |
| EFA-014 | 六轴工业机器人 | 重复定位精度下降，焊点偏移 | 高 |
| EFA-015 | AGV 搬运机器人 | 导航丢失，原地打转 | 中 |

案例库从 12 条扩到 24 条、设备从 12 类扩到 19 类，脚本执行"成功"，数据文件也通过了结构校验。**如果只做这一步，看起来是完成状态。**

## 2.2 自检：跑测试才发现失败

执行 `python run_tests.py` 后出现 2 个失败用例，都出现在"知识库未覆盖"的断言上：

```
FAIL: test_search_uncovered_returns_empty (tests.test_knowledge.TestKnowledge)
AssertionError: Lists differ: [SearchHit(case=..., score=0.632...)] != []

FAIL: test_agent_offline_uncovered (tests.test_agent.TestAgentOffline)
AssertionError: '本地知识库暂无该故障的案例依据' not found in '【判断】最接近的案例是 EFA-013（注塑机）…'
```

也就是说：AI 自己写的测试，在它自己新增的数据上翻车了。

## 2.3 定位：负例被"补"成了正例

两条用例用的是同一句话——"注塑机模具冷却水路堵塞，模温降不下来"。在原 12 条案例里没有注塑机，这句话必然是空命中，所以一直被当作"知识库未覆盖"的负例；而 EFA-013 恰好就是注塑机模温问题，于是负例变成了正例。

用脚本复现这次检索，问题一眼可见（完整输出见 `docs/evidence/log-01-negative-case.txt`）：

```
复现命令：python tools/capture_evidence.py --case negative
案例库：24 条 / 19 类设备

【旧负例】注塑机模具冷却水路堵塞，模温降不下来
  Top1  EFA-013  注塑机  score=0.632
  结论：命中 1 条 → 该负例已失效，测试断言 '期望空命中' 必然失败

【新负例】数控冲床送料机构卡料，送不到位
  结论：命中 0 条 → 仍是有效负例
```

## 2.4 调整

失败不在产品代码，而在**测试用例的假设**：负例绑定了"当时的知识库覆盖范围"。修法是换一个库外设备，并把这条约束写进注释，避免下次再被踩：

```diff
-        answer = self.agent.ask("注塑机模具冷却水路堵塞，模温降不下来")
+        answer = self.agent.ask("数控冲床送料机构卡料，送不到位")

-        hits = self.kb.search("注塑机模具冷却水路堵塞", top_k=3)
+        hits = self.kb.search("数控冲床送料机构卡料", top_k=3)
```

```python
    def test_search_uncovered_returns_empty(self):
        # 负例必须选“库外设备”：一旦为它补了案例，本用例就会变成假失败
        hits = self.kb.search("数控冲床送料机构卡料", top_k=3)
        self.assertEqual(hits, [])
```

改动随提交 `babf98a`（test+docs: 案例库测试与 v2.2 更新清单）进入仓库，提交差异见 `docs/evidence/git-commits.txt` 第 3 节。

## 2.5 验证

| 验证项 | 结果 |
| --- | --- |
| 全量测试 | `Ran 89 tests in 4.547s` → `OK`（`docs/evidence/log-04-tests.txt`） |
| 负例仍为空命中 | 检索"数控冲床送料机构卡料"命中 0 条 |
| 新增案例仍可用 | 检索"点检周期怎么定"命中 EFA-021，界面正常作答 |
| 界面实际状态 | 知识库页显示 24 条案例（含 EFA-013 注塑机），风险列正常 |

[[FIG1]]

**这一例的教训**：把"知识库当前覆盖范围"写进测试假设，等于把测试和数据绑死；负例要用**结构性保证不会被覆盖**的输入，或者在数据层显式维护"未覆盖清单"。

---

# 三、案例二：界面尺寸断言取到的值一直是 1

## 3.1 AI 生成的内容

为了让界面测试不只验证"控件存在"，AI 生成了带尺寸断言的用例，检查三栏布局是否真的铺开：

```python
self.app = FaultAgentApp()
self.app.update_idletasks()
self.assertGreater(self.app.winfo_width(), 800)
self.assertGreater(self.app.chat.winfo_width(), 100)
```

## 3.2 自检：断言失败，读数是 1

测试失败信息是 `1 not greater than 100`。窗口宽度断言却通过了——这个"一半通过、一半失败"的现象很关键，它说明窗口本身已经定了尺寸，但内部控件还没算出来。

## 3.3 定位：`update_idletasks()` 只处理布局请求，不触发窗口映射

用脚本把两种调用方式并排打出来（`docs/evidence/log-02-tkinter-layout.txt`）：

```
只调用 update_idletasks()：
  winfo_width  = 1180
  winfo_height = 760
  chat 宽度     = 1   <- 子控件仍为 1

补充调用 update() 后：
  winfo_width  = 1180
  winfo_height = 760
  chat 尺寸     = 589 x 492
  input 高度    = 73
```

`update_idletasks()` 只执行 idle 任务（几何管理器已排好位置），但窗口未真正映射到屏幕时，子控件拿到的仍是占位值 1。补一次 `update()`，几何计算与映射都完成后才是真实尺寸。

## 3.4 调整

```diff
         self.app = FaultAgentApp()
         self.app.update_idletasks()
+        self.app.update()
```

改动随提交 `60e862c`（test: 补充 30 个单元与界面测试）入库。

## 3.5 验证

| 验证项 | 期望 | 实测 |
| --- | --- | --- |
| 窗口尺寸 | 1180 × 760 | 1180 × 760 |
| 对话区 | 宽 > 100 | 589 × 492 |
| 输入框 | 高度 > 40 | 73 |
| 全量测试 | 全绿 | 89 项通过 |

[[FIG2]]

**这一例的教训**：GUI 测试里的"尺寸"是异步产物，"创建完就有值"是错的直觉；凡是断言几何，必须先把窗口推到已映射状态。

---

# 四、案例三：中文文案里的 ASCII 引号截断字符串

## 4.1 AI 生成的内容

在给知识库条目写提示文案时，AI 生成了这样一行内容（当时写在迁移脚本的数据模块里）：

```python
TEXT = "检索结果为空时必须写"未收录"，不要臆造实现细节。"
```

## 4.2 自检：编译阶段直接报错

提交前执行 `python -m compileall`，得到：

```
  TEXT = "检索结果为空时必须写"未收录"，不要臆造实现细节。"
                                   ^^^^^^
SyntaxError: invalid syntax. Is this intended to be part of the string?
```

同样的写法分散在 4 个数据模块里，逐个编译都会命中。完整输出见 `docs/evidence/log-03-quote-truncation.txt`。

## 4.3 定位

Python 字符串用双引号定界，中文正文里再写 ASCII 双引号，字符串在"必须写"之后就被闭合了，后面变成非法语法。因为整段是中文，肉眼扫读时极不容易发现——这也正是要靠编译而不是靠读的原因。

## 4.4 调整

| 调整 | 做法 |
| --- | --- |
| 引号统一 | 中文正文内的引述一律改用「」，ASCII 引号只用于代码定界 |
| 拆分数据 | 一次性富化脚本拆成 4 个纯数据模块，逐个 `ast.parse` 校验 |
| 前置检查 | 提交前必跑 `compileall`，把语法问题挡在测试之前 |

```python
TEXT = "检索结果为空时必须写「未收录」，不要臆造实现细节。"
```

## 4.5 验证

| 验证项 | 结果 |
| --- | --- |
| 写法 A（ASCII 引号） | `py_compile` 失败，`通过=False` |
| 写法 B（「」） | `py_compile` 通过，stderr 为空 |
| 4 个数据模块 | 全部 `ast.parse` 通过 |
| 迁移脚本执行 | 52 条富化 + 13 条新增成功，条目 52→65 |

**这一例的教训**：中文内容里的标点不是"排版细节"，它会改变代码语义；机器能查的（编译）不要交给人眼看。

---

# 五、三例对照

| 维度 | 案例一 | 案例二 | 案例三 |
| --- | --- | --- | --- |
| AI 生成物 | 新增 12 条案例数据 | 界面尺寸测试用例 | 知识库文案数据模块 |
| 自检手段 | 单元测试 | 单元测试 | 编译检查 |
| 客观信号 | 2 个 FAIL | `1 not greater than 100` | `SyntaxError` |
| 根因层级 | 测试假设 | 测试前置条件 | 数据字面量 |
| 修复位置 | `tests/` 负例 | `tests/` setUp | 数据模块文案 |
| 验证方式 | 89 项全绿 + 检索复现 | 尺寸实测 + 89 项全绿 | 编译通过 + 迁移成功 |
| 沉淀 | 负例必须选库外设备 | 几何断言先 `update()` | 中文引述用「」 |

三例有一个共同点：**问题都不是"代码写错"，而是"假设过期"**。案例一是"知识库还没覆盖它"的假设过期，案例二是"创建完就有尺寸"的假设过期，案例三是"中文引号不影响语法"的假设过期。所以修复的重点不是改逻辑，而是把过期假设换成可验证的约束。

---

# 六、自检机制如何固化

单次修好不算能力，把检查变成默认动作才算。项目里固化了四层：

| 层级 | 机制 | 作用 |
| --- | --- | --- |
| 编译 | `python -m compileall src app.py tools` | 语法与引号类问题在测试前拦截 |
| 测试 | `python run_tests.py`（89 项） | 行为回归，含负例与降级路径 |
| 数据校验 | `tools/verify_cases.py`、`tools/verify_kb.py` | 案例与知识库的字段、可检索性、索引同步 |
| 证据采集 | `tools/capture_evidence.py` | 把"问题现象"变成可复现日志，随文档交付 |

---

# 七、证据清单

| 编号 | 文件 | 内容 | 生成方式 |
| --- | --- | --- | --- |
| 1 | `docs/evidence/log-01-negative-case.txt` | 旧负例命中 EFA-013（0.632）、新负例 0 条 | `capture_evidence.py --case negative` |
| 2 | `docs/evidence/log-02-tkinter-layout.txt` | `chat=1` 与 `589×492` 的对照 | `capture_evidence.py --case layout` |
| 3 | `docs/evidence/log-03-quote-truncation.txt` | ASCII 引号导致 `SyntaxError`、改「」后通过 | `capture_evidence.py --case quotes` |
| 4 | `docs/evidence/log-04-tests.txt` | `Ran 89 tests … OK` | `python run_tests.py` |
| 5 | `docs/evidence/git-commits.txt` | 相关提交、修复 diff | `git log` / `git show` |
| 6 | `docs/evidence/shot-01-app.png` | 客户端真实运行：命中 EFA-001、工具调用 2 次、匹配度 0.701 | 运行程序后截取窗口 |
| 7 | `docs/evidence/shot-02-kb.png` | 知识库页：24 条案例，含 EFA-013 注塑机 | 同上 |

复现全部证据只需三条命令：

```
python tools/capture_evidence.py --case negative
python tools/capture_evidence.py --case layout
python tools/capture_evidence.py --case quotes
```

---

# 八、附：截图是怎么来的

截图不是拼图，是从真实进程窗口截的：

1. 用辅助脚本启动 `FaultAgentApp`，把问题写进输入框并调用 `on_send()`；
2. 等待后台线程返回答案（离线模式，约 1 秒），把对话区滚到顶部；
3. 读取窗口的 `winfo_rootx/rooty/width/height`，按该矩形截屏，落盘为 PNG；
4. 截完即关闭进程，不留下常驻窗口。

因此图 1、图 2 里的时间、匹配度、工具耗时都是那一次真实运行的结果，不是后期标注。

**文档结束**
