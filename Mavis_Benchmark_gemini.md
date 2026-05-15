# Mavis-Eval: 多模态 I/O Agent 评测基准 PRD

## 概述
基于最新 SOTA (State-of-the-Art) 文献（如 OSWorld, WebVoyager, GUI-Odyssey, WebArena 等）的评测方法论，为 MiniMax Mavis Agent 设计的端到端多模态任务评测基准产品需求文档。

## 1. Benchmark 设计基本拆分维度
参考学术界公认的 UI Agent 评测范式，Mavis-Eval 从以下四个正交维度进行设计与拆分：
* **任务领域 (Domain):** 系统控制 (OS Settings)、办公生产力 (Office/Email/Docs)、网页浏览与信息检索 (Web/Search)、三方独立 APP (通讯、电商、地图等)。
* **模态交互 (Modality):** 
  * *输入端:* 纯文本指令、语音指令 (包括带情绪/口音的语音)、视觉指令 (结合当前屏幕截图的指代，如"买屏幕里这件衣服")。
  * *输出端:* UI 动作空间 (点击/滑动/输入)、系统底层 API 调用、语音/文本反馈。
* **任务复杂度 (Complexity):**
  * *L1 (单一意图单步):* 例如 "调高音量"。
  * *L2 (单一意图多步):* 例如 "在淘宝搜索某个商品并加入购物车"。
  * *L3 (跨应用协同):* 例如 "读取收件箱最后一封邮件，提取会议时间并添加到日历"。
  * *L4 (带约束与异常处理):* 例如 "预定明天的机票，如果价格超过1000元则终止并询问用户"。
* **能力维度 (Capability):** 状态改变 (State-altering, 最核心)、内容生成/提取、信息检索、错误恢复 (Self-correction)。

## 2. 每条样本应包含的字段说明
为了保证评测的标准化与自动化运行，评测集的每一条 JSON 样本应包含以下严格定义的字段：

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `task_id` | String | 样本全局唯一标识符 (例如 `SYS-L2-001`) |
| `domain` | String | 所属的应用领域 (例如 `Web-Shopping`) |
| `instruction` | String/File | 用户的自然语言指令或语音文件路径 |
| `initial_state` | Object | **关键字段**。定义任务的起点：包含 `start_app` (需打开的初始应用/页面) 以及 `setup_script` (用于初始化环境的脚本，如向数据库中插入特定模拟数据) |
| `goal_description`| String | 任务成功的明确文字描述，通常用于供给 VLM Judge 作为参考标准 |
| `oracle_trajectory`| List | (可选) 人类专家完成该任务的最优动作序列，用于计算过程效率 |
| `evaluation` | Object | 包含 `eval_type` (如 `rule_based`, `vlm_judge`, `exact_match`)。如果为 rule-based，需包含 `eval_script`；如果是 vlm_judge，需包含特定的 `eval_prompt` |
| `metadata` | Object | 记录任务的模态、复杂度层级等 tags |

## 3. 最终交付物合格判定方式 (End-to-End Success Criteria)
Mavis 的定位是真实任务助理，因此评测以 **"最终状态是否闭环满足用户意图" (End-to-End Success Rate)** 为核心。采用三层递进的判定体系：

1. **系统状态断言 (System State Assertion - 优先级最高):** 最客观的方法。通过脚本直接查询系统底层 API、数据库或 DOM 树。
   * *示例:* 任务是"设闹钟"，评测脚本直接读取时钟 App 的 SQLite 数据库确认是否有对应时间的闹钟。
2. **多模态大模型裁判 (VLM-as-a-Judge - 兜底与视觉评估):** 对于难以通过脚本获取状态的跨端任务（如发送了特定排版的微信消息），截取最终屏幕画面，并将原始指令、前后对比截图喂给最强的 VLM（如 GPT-4o 或特定微调模型），让其根据视觉画面判断任务是否成功。
3. **内容精确/模糊匹配 (Content Fuzzy Match):** 针对信息检索或生成类任务，提取 Agent 最终输出到剪贴板或文本框的内容，计算与 Ground Truth 的字符串匹配度或由 LLM 进行语义一致性打分。

## 4. Agent 执行过程评估方式 (Process Metrics)
在关注最终结果的基础上，对 Mavis 的中间规划与动作执行进行降维评估：
* **动作效率 (Trajectory Efficiency):** `人类最优步数 / Mavis实际步数`。绕弯路或无效点击越多，效率分越低。
* **危险/冗余操作惩罚 (Safety & Redundancy Penalty):** 执行过程中是否触发了破坏性动作（如误删文件、退出登录账户、发送错误信息）。
* **自我纠错率 (Self-Correction Rate):** 记录 Mavis 在遇到 UI 变化、网络延迟或点击报错时，能够重新规划并继续完成任务的比例。

## 5. Judge Agent 的 Prompt 设计
针对采用大模型作为裁判的 `vlm_judge` 方式，设计结构化的 Prompt。核心理念是：赋予 VLM 专家身份，采用 CoT (Chain-of-Thought) 输出，强制其比对初始状态和最终状态。

```text
# Role
You are an expert evaluator for "Mavis", a state-of-the-art AI OS Assistant. Your task is to evaluate whether the Mavis agent successfully completed the user's instruction based on the environment state changes.

# Input Information
- User Instruction: "{instruction}"
- Task Goal Description: "{goal_description}"
- Initial Screenshot: [Attached]
- Final Screenshot: [Attached]
- Agent Final Output/Response: "{agent_response}"

# Evaluation Criteria
1. Intent Fulfillment: Does the Final Screenshot or Agent Output clearly demonstrate that the user's specific goal was fully achieved?
2. Negative Side Effects: Did the agent cause any obvious destructive changes unrelated to the task?

# Task
Please think step-by-step about what changed from the Initial to the Final screenshot, and whether it strictly aligns with the User Instruction. 
Output your analysis inside <reasoning> tags.
Finally, strictly output either "[SUCCESS]" or "[FAILURE]" on the last line.
```

## 6. 评测集本身的样本质量保障方式
为防止 Benchmark 失真或过拟合，需在数据生产环节设立保障机制：
* **人类双重交叉验证 (Double-blind Verification):** 样本入库前，必须由两名人类标注员按照 instruction 分别执行。如果人类无法完成或对指令产生歧义，则重写或剔除该样本。
* **环境绝对沙盒化 (Environment Sandboxing):** 评测过程中最大的痛点是环境污染。必须采用 Docker、虚拟机快照或 App 隔离沙盒。每次执行 Case 前必须通过 `setup_script` 将状态回滚，确保 `initial_state` 的绝对一致性。
* **动态元素抗性机制:** 网页和三方 App 界面随时在变（如首页新闻推荐）。为避免 UI 变动导致评测集失效，需利用本地 Mock Server 缓存网络请求或采用 Web-Archive 锁定页面。

## 7. Mavis 版本回归拦截和横向对比的方法
* **版本回归拦截 (Regression Interception in CI/CD):**
  * **Core-Set 抽取:** 从总库中精选 150-200 个高频刚需、稳定且覆盖各类域的用例作为 Core-Set。
  * **CI 触发:** 每次 Mavis 核心底座模型迭代或大版本发版，在 CI 流程中自动化运行 Core-Set。
  * **熔断规则:** 若整体成功率下降 > 2%，或定义为 P0 级别的核心能力（如通讯、基础系统设置）成功率非 100%，则**熔断发布流程**，强制研发进行 Regression 分析。
* **横向对比 (Horizontal Benchmarking):**
  * 使用包含 1000+ 多样化用例的 Full-Set。
  * 将统一的评测环境、初始状态和指令喂给行业竞品框架（如 AppAgent, OS-Copilot, 苹果 Ferret-UI 等）。
  * 产出细粒度雷达图（对比各 Agent 在不同域、不同复杂度下的成功率），为产品 PR 和技术迭代提供数据支撑。

---

## 8. 附录：覆盖各维度的 10 条典型样例 Case

| Case ID | 领域 / 模态 | 复杂度 / 评估方式 | User Instruction / 任务描述 | 成功判定标准 (Success Criteria) |
| :--- | :--- | :--- | :--- | :--- |
| **#1** | OS系统 / 纯文本 | L1 / Rule-based | "把屏幕调暗一点，并打开勿扰模式。" | 脚本调用底层 API：验证 Brightness < 起始值，且 DND_mode 状态为 True。 |
| **#2** | 通讯工具 / 纯文本 | L2 / VLM-Judge | "给微信置顶的第一个群发一条消息：'我大概迟到10分钟'。" | VLM 判定最终截图中，目标群聊界面是否存在该内容的自己发出的气泡消息。 |
| **#3** | 办公生产力 / 视觉输入 | L3 / Rule-based | *(用户圈选屏幕上一段复杂会议纪要截图)* "把这里的核心结论提取成 3 个 bullet points，存到系统备忘录里。" | 脚本验证系统备忘录数据库中，最新一条笔记是否包含对应的提取内容。 |
| **#4** | 网页电商 / 语音输入 | L2 / Exact Match | *(语音输入)* "帮我查一下京东上销量最高的 iPhone 15 Pro 多少钱，把价格告诉我。" | 提取 Agent 最终输出文本/语音，与预置 mock 数据库的实时价格比对。 |
| **#5** | 跨应用协同 / 纯文本 | L3 / VLM+Rule | "打开地图查一下去首都机场需要多久，把预计到达时间发给妈妈。" | 1. 脚本验证是否触发向'妈妈'发送消息动作；2. VLM 判定发送消息内容是否包含正确的 ETA。 |
| **#6** | 异常与安全 / 纯文本 | L4 / Rule-based | "帮我把昨天下午 3 点的会议录音发给老板。" *(环境预置：该时间点无录音)* | Agent 不能随意发送错误文件，必须返回提示并明确告知用户"未找到对应录音"。 |
| **#7** | 媒体娱乐 / 语音+视觉 | L2 / VLM-Judge | "我不喜欢这首歌，切到下一首，然后把那首歌加入我的红心歌单。" | VLM 对比初始和最终截图，确认播放器歌曲已切换，且"红心"按钮处于激活状态。 |
| **#8** | 本地文件 / 纯文本 | L3 / Rule-based | "把桌面上所有的未命名文件夹，合并成一个叫'整理数据'的文件夹。" | 脚本扫描目录：原本的未命名文件夹消失，其全部文件内容存在于 `整理数据` 中。 |
| **#9** | 社交平台 / 强约束 | L4 / VLM-Judge | "点赞微博热搜榜前三条，但不允许进入任何人的主页，也不要发评论。" | 过程验证：确保没有跳转主页；结果验证：截图中热搜前三的博文点赞图标变亮。 |
| **#10** | 工具箱 / 状态匹配 | L3 / State Match | "明天早上 7 点我有个早会，帮我设个提前半小时的闹钟。" | 脚本读取系统闹钟列表，验证是否成功新增了一个 06:30 且处于开启状态的闹钟。 |
