# **Mavis 多模态端到端任务评测基准设计报告**

随着人工智能从单纯的对话式大语言模型向具备环境交互能力的自主智能体（Agent）演进，评测基准的逻辑也正在经历从“输入-输出匹配”向“目标-交付达成”的根本性转变。Mavis 作为 MiniMax 最新发布的智能体产品，其核心竞争力在于能够在开放任务中理解用户模糊的目标，自主规划复杂的执行路径，并通过跨应用、多步操作实现最终交付 1。为了准确评估 Mavis 在真实用户场景下的端到端能力，必须建立一套超越传统文本评测的、深度整合多模态 I/O（输入/输出）的任务基准。本报告旨在为 Mavis 量身定制一版全维度的评测交付方案，涵盖从设计维度、样本规范、验证逻辑到 Judge Agent 设计及版本回归拦截的全流程体系。

## **智能体评测基准设计的核心维度拆分**

在设计面向 Mavis 的评测基准时，首要任务是识别其作为“个人助理”在数字化办公与生活场景中的核心职能。与评估模型知识储备的 MMLU 或评估代码生成正确性的 HumanEval 不同，智能体评测必须关注其在动态环境中的适应性。该基准被拆分为感知理解、规划推理、工具操作与交付质量四个关键维度，这四个维度共同构成了智能体完成任务的闭环链路 3。

感知理解维度不仅测试 Mavis 对文本指令的遵从能力，更强调其对非结构化视觉信息的提取精度。在多模态 I/O 任务中，智能体经常需要处理图文混排的 PDF 文档、包含复杂报表的网页截图或带有特定情绪特征的语音输入 5。这一维度的评估重点在于“视觉对齐”与“语义解析”的交叉能力，即 Mavis 是否能准确识别截屏中的按钮位置、表单项，并理解其在当前业务流中的含义 7。

规划推理维度是衡量智能体“大脑”成熟度的核心指标。Mavis 被定位为能够处理长程、复杂任务的工具 9。该维度考察其任务拆解的逻辑性（Plan Quality）以及在执行过程中面对意外中断或工具反馈错误时的调整能力（Plan Adherence） 11。评估不仅看最终结果，更关注规划路径是否是最短路径，是否避免了冗余的搜索迭代 12。

工具操作维度聚焦于 Mavis 对 Model Context Protocol (MCP) 以及 shell 命令、浏览器自动化等底层能力的调用 14。由于 Mavis 具备“Computer Use”能力，它必须能够像人类一样操作各种软件 16。这一维度的评估包含工具选择的准确性、参数填充的合规性以及多工具协作的稳定性 11。

交付质量维度是评测基准的“终局判定”。它直接关联到任务的经济价值 18。无论是生成一份带公式的 Excel 财务模型，还是制作一套符合品牌规范的 PPT，交付物必须通过功能性验证（如代码运行成功）与专业审美评估 18。对于法律、医疗等高风险领域，该维度还会引入“零容忍”判准，任何关键事实的遗漏都将被视为交付失败 21。

| 设计维度 | 评估核心 | 对应 Mavis 核心能力 |
| :---- | :---- | :---- |
| **多模态感知 (Perception)** | UI 识别、OCR 提取、多模态语义对齐 | 图像识别与文档分析 1 |
| **层级规划 (Planning)** | 任务拆解、错误恢复、长程记忆维护 | 复杂任务规划与自适应纠错 22 |
| **环境交互 (Action)** | MCP 工具调用、Browser Use、代码运行 | 端到端自动化与代码执行 22 |
| **交付忠实度 (Fidelity)** | 格式合规性、功能正确性、专业度 | Office 套件编辑与专业交付 25 |

## **评测样本字段说明与数据结构规范**

为了构建一个可规模化运行且具备高诊断价值的评测集，每条样本必须包含详尽的元数据和环境约束。参考 GDPval 与 WebArena 等前沿基准，Mavis 评测样本被设计为一个包含九个核心字段的结构化对象 27。

task\_id 与 category 字段用于建立任务的唯一索引与分类体系。category 涵盖金融、法律、软件工程、行政办公等 44 个以上的高价值职业领域 19。difficulty\_level 则按照任务步数和工具依赖程度分为三个层级：Level 1（5 步以内）、Level 2（5-10 步）、Level 3（10 步以上且涉及跨应用协作） 30。

user\_prompt 是评测的起点，提供自然语言描述的任务目标。与之配套的是 input\_artifacts，这是一个包含 PDF、JPG、CSV 等多模态文件的列表，模拟用户向助理提交初始资料的场景 19。为了测试 Mavis 的长时记忆能力，session\_context 字段会预填一段模拟的历史对话，考察智能体是否能从中提取隐含约束 16。

env\_manifest 定义了任务执行所需的隔离沙箱环境，包括特定的 Docker 镜像、网络访问权限（如需访问特定 Web 站点）以及预装的 MCP 服务器列表 14。ground\_truth\_state 则描述了任务完成后的理想环境状态，例如数据库中新增的记录或指定路径下生成的报告 35。

最后，programmatic\_checker 与 expert\_rubric 为后续的自动化评估提供支持。前者是一个可执行的 Python 脚本，用于硬性验证（如 Excel 公式检查）；后者则是为 Judge Agent 准备的语义化评分标准，详细规定了专业度的等级差异 32。

| 字段名称 | 类型 | 说明 |
| :---- | :---- | :---- |
| task\_id | UUID | 全局唯一标识符 |
| domain | String | 任务所属行业分类（如：医疗影像、电商运营） |
| prompt | String | 用户的原始自然语言指令 |
| artifacts | List\[Path\] | 随任务提供的多模态附件路径 |
| harness\_config | JSON | 沙箱环境配置（镜像、工具集、权限） |
| iter\_limit | Integer | 最大迭代步数限制 39 |
| eval\_checker | Script | 最终交付物的功能性自动校验脚本 35 |
| grading\_rubric | Markdown | 详细的 1-5 分评分准则与关键检查点 |

## **最终交付物合格判定与质量标准**

在智能体评测中，判定交付物“合格”的标准不再是简单的字符串匹配，而是一套多层级的验证逻辑。根据 Mavis 的应用定位，合格判定必须结合功能性测试与语义质量评估 17。

### **功能性正确性验证**

对于涉及代码、数据处理或文档编辑的任务，第一层判定标准是“功能可用性”。例如，如果 Mavis 被要求生成一个财务预测模型，评测系统将调用脚本打开生成的 Excel 文件，检查关键单元格的公式逻辑是否闭环，折线图的数据源是否与提取的数据一致 20。如果文件损坏、格式无法打开或核心逻辑错误，该任务将直接被判定为失败 18。在网页操作场景中，验证则体现在后端状态的改变，如“购物车中是否确实存在指定商品”或“GitHub 仓库中是否已提交修复后的 PR” 35。

### **交付物完整性检查**

完整性判定要求智能体严格对齐用户指令中的所有显式与隐式约束。参考 GDPval 的失败模式分析，常见的交付瑕疵包括“遗漏请求的附件”、“缺少主要章节”或“未包含要求的视觉资产” 18。对于高标准的专业任务，采用“All-Pass”判定逻辑，即只有当所有的关键指标（事实准确、格式合规、引用完整）全部达成时，任务才算成功 21。

### **专业度等级评分**

在交付物基本功能正确的前提下，评测系统将引入基于 ELO 系统的专业度评分。通过 Blind Pairwise Comparison（盲测对战），将 Mavis 的交付物与人类专家的“黄金参考”（Gold Deliverable）或竞争对手的输出进行横向对比 29。这一过程主要考察输出的专业深度、逻辑严密性、文档排版美观度以及品牌调性的一致性 45。

| 判定标准 | 评估方式 | 失败示例 |
| :---- | :---- | :---- |
| **功能性 (Functionality)** | 脚本自动化检测、环境状态查询 | Excel 公式循环引用、代码运行报错 |
| **完整性 (Completeness)** | 关键元素提取比对、All-Pass 逻辑 | 总结报告缺少风险评估章节 |
| **格式合规 (Formatting)** | 文件类型校验、UI/UX 规范检查 | 要求 PDF 却交付了 DOCX、文字重叠 18 |
| **语义准确 (Accuracy)** | 事实核查、Judge Agent 逻辑比对 | 提取的合同金额与原件不符 |

## **智能体执行过程评估方式**

孤立地评估最终结果会掩盖智能体执行过程中的效率低下与潜在风险。因此，对 Mavis 执行轨迹（Trajectory）的评估是评测体系中不可或缺的一部分。这种评估旨在回答“智能体是如何得到这个结果的”以及“这个过程是否具备生产环境的可靠性” 37。

### **执行效率与资源消耗**

评估 Mavis 的执行效率不仅是为了降低成本，更是为了提升用户体验。评测基准会记录完成任务所需的总 Token 数、API 调用次数以及消耗的时间 12。一个优秀的执行过程应当展现出“Spec-writing”倾向，即在行动前先进行高水平的架构设计，从而减少后续的无效重试 12。基准中引入“Step Efficiency”指标，其定义为：

![][image1]  
以此衡量 Mavis 与最优执行路径的接近程度 11。

### **规划的一致性与纠错能力**

过程评估的核心在于“规划-行动-反馈”闭环的有效性。评测系统会提取 Mavis 的思维链（\<think\> 块）并将其与实际采取的 Action 进行比对，检查是否存在“言行不一”的情况 11。在长程任务中，还会考察 Mavis 对“上下文腐烂”（Context Rot）的抵抗力，即随着交互轮数的增加，其是否仍能记得初始目标而不偏离航向 4。同时，过程评估会标记所有的错误恢复节点，评估智能体在遇到工具超时或 404 错误时，是选择优雅降级还是陷入死循环 22。

### **角色协作的鲁棒性**

由于 Mavis 采用了“Agent Teams”协作模式，执行过程评测必须包含对内部协作效率的分析 2。这包括 Owner 任务拆解的合理性、Worker 执行的独立性以及 Verifier 是否能准确拦截 Worker 的错误 52。理想的协作轨迹应当显示出 Worker 与 Verifier 之间的“对抗性博弈”，即 Verifier 能够发现隐蔽的逻辑漏洞并强制 Worker 重构交付物 51。

## **Judge Agent 的 Prompt 设计原则**

在大规模智能体评测中，人工评分不仅昂贵且难以保证一致性。因此，设计一个高可靠性的 Judge Agent 是关键环节。根据“Analyze-then-Judge”范式，Judge Agent 必须先通过“系统 2”思考提取证据，然后再给出裁决，以避免被智能体自信的语气误导 54。

### **提示词结构化工程**

Judge Agent 的 Prompt 应当包含明确的角色设定、上下文环境、待评测输入以及结构化的评分量表。为了提高评分的鲁棒性，提示词应要求 Judge Agent 在给出最终分数前，先完成三个步骤：需求提取（Extraction）、证据对齐（Comparison）和功能验证（Verification） 54。

### **典型的 Judge Prompt 模版**

针对 Mavis 的多模态任务，Judge Prompt 被设计为支持 JSON 格式输出，以便于后续的自动化统计分析：

# **Role**

你是一名资深的职业质量审计专家，擅长对 AI 智能体的端到端交付物进行客观、严苛的质量评估。

# **Context**

任务类别: {category}

原始用户意图: {user\_prompt}

参考黄金答案/状态: {ground\_truth}

Mavis 实际生成的交付物/轨迹: {actual\_output}

# **Evaluation Rubric (1-5 评分标准)**

5 (Exemplary): 完全满足所有约束，交付物具备专家级专业度，无任何逻辑或格式瑕疵。

4 (Strong): 满足所有核心需求，仅有极细微的非关键瑕疵（如轻微的样式不统一）。

3 (Acceptable): 核心功能实现，但缺乏深度或存在少量事实性疏漏，交付物仅达及格线。

2 (Weak): 存在严重的功能缺失或明显的事实错误，交付物无法直接使用。

1 (Failed): 完全偏离目标，交付物损坏或提供了完全不相关的内容。

# **Evaluation Steps**

1. 需求解析：请列出原始指令中所有的显式约束和隐式期望。  
2. 证据提取：在交付物中寻找对应以上需求的具体实现。如果是图表，请核对数据来源。  
3. 冲突检测：检查交付物是否违反了任何已知的物理定律、逻辑规则或品牌指引。  
4. 综合评议：请在 JSON 字段中提供详细的扣分理由。

# **Output Format**

严格返回以下 JSON 结构：

{

"score": integer,

"reasoning\_steps": \["step1", "step2",...\],

"pros": \["points"\],

"cons": \["points"\],

"factual\_errors": \["list"\],

"final\_verdict": "Pass/Fail"

}

45

## **评测集样本质量保障方式**

一个失效的样本（如任务本身不可解）会导致评测结果产生噪声，从而误导研发决策。为了确保 Mavis 基准的权威性，评测集本身必须经过多层质量保障流程。

首先是专家审核制。所有的评测任务必须由在该领域具有 10 年以上经验的专业人士手工创建 18。每个任务必须附带一份由人类撰写的“参考交付物”，这不仅用于基准评分，更用于验证任务在当前环境下的可解性 19。如果在多轮测试中，连最顶尖的模型（如 GPT-5 或 M2.7）都无法达成 0.1% 的成功率，则必须对该任务进行“模糊性审计”，检查指令是否存在歧义 38。

其次是环境确定性保障。智能体任务极度依赖环境状态。评测集必须支持“快照重置”功能，确保每次测试开始时，沙箱中的文件系统、数据库记录和网络状态完全一致 28。对于依赖真实网站的任务，应当使用容器化的静态网页快照（如 WebRecorder）以避免因网站更新导致的评测失效 59。

最后是数据污染检测与去重。为了防止模型通过记忆测试样本来“刷榜”，评测集需定期进行动态更新，引入新鲜的任务场景 60。通过计算样本间的语义余弦距离（Cosine Distance），剔除重复度过高的平庸任务，保持评测集的高熵和区分度 40。同时，对测试集进行加密存储，仅在推理时动态解密，以降低训练数据渗透的风险 24。

## **版本回归拦截与横向对比方法**

在 Mavis 的快速迭代过程中，评测基准承担着“守门员”和“罗盘”的双重角色。通过科学的方法论，评测结果能够转化为可量化的版本拦截信号和竞争定位 43。

### **基于“黄金任务”的回归拦截策略**

在 Mavis 的 CI/CD 流水中，建立一套包含 50-100 个核心高价值任务的“黄金回归集” 47。

* **硬拦截指标：** 任何模型更新若导致黄金集中的 Pass@1 成功率下降超过 2% 或出现新的安全违规（如泄露隐私数据），则自动触发拦截脚本，禁止合并代码 11。  
* **行为指纹对比：** 利用“Back-to-Back”测试，比较新旧版本在相同输入下的执行轨迹。如果新版本在步数效率上显著下降（即使结果仍正确），研发团队也需要深入调查原因 63。

### **竞争格局的横向对比方法**

为了确定 Mavis 在全球 Agent 市场中的位置，需采用以下多维对比体系：

* **ELO 动态排行榜：** 在 GDPval-AA 或 GAIA 等基准上运行 Mavis 与 Claude 4.6、GPT-5.5 等竞品，基于胜率计算 ELO 分值 43。这能直观展示模型在“专业知识交付”上的相对水位。  
* **效能-情报象限分析：** 横坐标为“任务完成成本”（Token Cost per Task），纵坐标为“任务成功率”。Mavis 的目标是占据“高智能、极低成本”的领导者象限 68。  
* **多维度能力图谱：** 针对 Browser Use、代码修复、文档合成等专项能力绘制雷达图。通过横向对比，可以清晰识别出 Mavis 在哪个细分领域（如中文场景的 Browser Use）具备超越全球竞品的优势 12。

| 对比维度 | Mavis (当前版本) | 竞品 A (SOTA) | 拦截/目标门槛 |
| :---- | :---- | :---- | :---- |
| **Pass@1 成功率** | 80.2% 68 | 80.8% | \> 78% (拦截) |
| **平均完成步数** | 8 步 | 12 步 | \< 10 步 (目标) |
| **单任务 Token 消耗** | 3.52M 48 | 3.72M | 下降 5% (拦截) |
| **ELO 分值 (GDPval-AA)** | 1495 25 | 1633 | \> 1450 (拦截) |

## **评测案例 1：多模态跨表财务对账与报告**

该案例模拟一名财务助理，需要处理模糊的图片输入并转化为结构化的专业交付物。这不仅测试了 Mavis 的 OCR 与图表识别能力，还考察了其在 Excel 复杂公式填充中的精确度 20。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | FIN-AUDIT-001 |
| **Domain** | 金融与会计 |
| **Difficulty** | Level 2 |
| **User Prompt** | “请检查附件中 Q3 季度的两张采购发票照片，并将其数据录入到提供的 Budget\_Control.xlsx 中。如果发现超支项，请在 Excel 中用红色标记，并生成一份简短的 PDF 邮件草案告知采购主管原因。” |
| **Artifacts** | invoice\_photo\_01.jpg, invoice\_photo\_02.png, Budget\_Control.xlsx |
| **Env Config** | 包含 Excel 渲染引擎的 Sandbox, SMTP 邮件模拟服务 |
| **Success Criteria** | 1\. Excel 中新增两条记录，数据与图片发票 100% 对齐；2. 超支项公式触发正确并应用红色样式；3. PDF 中准确说明了超支的具体发票号和金额。 |

## **评测案例 2：法律合同风险红线审查**

此任务聚焦于法律行业的专业交付，强调对细微事实的捕捉和对既定规则的坚持（Rule Persistence）。在处理此类任务时，Verifier 角色的“对抗性”审查至关重要 21。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | LEG-REVIEW-002 |
| **Domain** | 法律合规 |
| **Difficulty** | Level 3 |
| **User Prompt** | “对比附件中的 Target\_Lease.pdf 和公司的 Standard\_Policy.docx。识别所有涉及‘控制权变更’的冲突条款。请在 Word 中开启修订模式，直接修改冲突条款使其符合公司政策，并添加批注解释修改理由。” |
| **Artifacts** | Target\_Lease.pdf, Standard\_Policy.docx |
| **Env Config** | 支持多模式文档编辑的虚拟桌面环境，预装法律术语 MCP |
| **Success Criteria** | 1\. 识别出所有 3 处冲突条款；2. Word 交付物包含修订轨迹（Track Changes）；3. 批注中准确引用了标准政策的对应条款号。 |

## **评测案例 3：SRE 生产环境故障分级与自动化修复**

本案例挑战 Mavis 在底层系统运维中的深度理解和代码-运行-修复（Code-Run-Fix）循环能力。这要求智能体能够理解复杂的日志逻辑并操作 Linux 终端 25。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | SRE-FIX-003 |
| **Domain** | 软件工程 / 系统运维 |
| **Difficulty** | Level 3 |
| **User Prompt** | “我们的训练流水线出现了异常流量波动。请 triage /var/log/syslog，定位耗时最长的 Python 进程。如果该进程是因为数据加载死锁，请修改 dataloader.py 逻辑以支持非阻塞加载，并运行 smoke test 确认修复。” |
| **Artifacts** | 模拟故障的 Ubuntu 容器访问权限 |
| **Env Config** | 隔离的 Linux Shell, 预装 Python 调试工具 |
| **Success Criteria** | 1\. 成功定位到正确的 PID；2. 修改后的代码逻辑消除了死锁；3. Smoke test 脚本返回成功，且系统 CPU 占用恢复正常。 |

## **评测案例 4：基于 Browser Use 的全流程电商竞品调研**

利用 Mavis 领先的浏览器控制能力，模拟复杂的 Web 操作和非结构化信息的聚合。该任务考察了其多标签页切换和应对动态 UI 的鲁棒性 22。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | WEB-MARKET-004 |
| **Domain** | 市场营销 |
| **Difficulty** | Level 2 |
| **User Prompt** | “在 Amazon 和 eBay 上搜索‘Ergonomic Chair’。找到好评率超过 4.5 且价格在 200-400 美元之间的前三款产品。将它们的参数对比整理成一份 PPT，每张幻灯片必须包含产品的主图截图和购买链接。” |
| **Artifacts** | 品牌 PPT 模版 .potx |
| **Env Config** | 带有 Stealth Proxy 的 Chromium 浏览器, PPT 生成引擎 |
| **Success Criteria** | 1\. 爬取的数据准确且符合过滤条件；2. PPT 布局美观，图片未变形；3. 所有超链接均可正常跳转。 |

## **评测案例 5：多模态身份核验与表单自动化填充**

此任务测试 Mavis 对敏感证件信息的 OCR 识别及在政府/政务系统中的数据转换合规性 73。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | ADM-FORM-005 |
| **Domain** | 行政办公 |
| **Difficulty** | Level 1 |
| **User Prompt** | “根据附件中的护照扫描件，填写‘签证申请模拟门户’。请注意将所有日期格式统一为 YYYY-MM-DD。如果护照有效期不足 6 个月，请停止填写并立即弹窗警告我。” |
| **Artifacts** | user\_passport\_scan.jpg, 签证门户 URL |
| **Env Config** | 模拟政务沙箱内网，包含 OCR 增强包 |
| **Success Criteria** | 1\. 姓名、护照号提取零错误；2. 日期格式转换正确；3. 逻辑分支测试：在输入即将过期的护照时，智能体必须触发停止动作。 |

## **评测案例 6：多智能体协作下的复杂软件交付**

利用“Agent Teams”架构，模拟从需求分析到代码测试的全生命周期。这是对 Mavis 内部 Worker-Verifier 协作机制的极限压力测试 2。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | SYS-COWORK-006 |
| **Domain** | 全栈开发 |
| **Difficulty** | Level 3 |
| **User Prompt** | “开发一个简单的‘会议室预约系统’网页应用。要求：前端使用 React，后端使用 Node.js。必须包含用户认证和冲突检测功能。请由 Owner 拆分任务，Worker 开发代码，Verifier 运行测试套件并修复发现的 bug。” |
| **Artifacts** | 公司内部 UI 组件库截图 |
| **Env Config** | 完整的全栈开发沙箱，支持实时预览和自动化测试运行 |
| **Success Criteria** | 1\. 应用可正常启动；2. 冲突检测逻辑有效（即不能在同一时间段预约两次）；3. 执行轨迹显示 Verifier 至少驳回并修复了一次代码。 |

## **评测案例 7：STEM 领域的视觉推理与数据可视化**

该案例模拟科研场景，测试 Mavis 在处理专业学科图像（如显微镜照片、化学结构式）时的深度推理能力 32。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | SCI-RESEARCH-007 |
| **Domain** | 生命科学 / 基础研究 |
| **Difficulty** | Level 2 |
| **User Prompt** | “分析附件中 5 张细胞分裂的显微镜图像。统计处于‘中期’和‘后期’的细胞数量占比。请编写一段 Python 代码处理这些统计数据，并生成一个饼图嵌入到你的研究简报中。” |
| **Artifacts** | cell\_01.png \~ cell\_05.png |
| **Env Config** | 预装 OpenCV 和 Matplotlib 的科研沙箱 |
| **Success Criteria** | 1\. 视觉分类结果与专家标注一致；2. 饼图中的百分比计算准确；3. 简报中包含了对观察到的生物学现象的合理解释。 |

## **评测案例 8：电商后台的大规模数据清洗与自动化运营**

模拟处理海量低质量数据并输出商业洞察，考察智能体在长上下文环境下的性能稳定性 78。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | ECO-OPERATE-008 |
| **Domain** | 电商数据分析 |
| **Difficulty** | Level 3 |
| **User Prompt** | “从后台导出过去一年的‘客户投诉记录.csv’（约 5 万行）。清洗掉重复的投诉，并识别出排名前三的‘质量问题关键词’。将分析结果写入一份给供应商的 Word 警告信，并附带故障趋势折线图。” |
| **Artifacts** | 大规模原始 CSV 文件 |
| **Env Config** | 高内存数据处理沙箱，支持 pandas 大文件操作 |
| **Success Criteria** | 1\. 关键词提取具有代表性；2. 警告信语气得体且逻辑连贯；3. 处理过程中未出现“上下文遗忘”导致的数据统计偏差。 |

## **评测案例 9：多模态个人行程规划与动态预订**

测试 Mavis 在面对冲突约束和实时 Web 变动时的决策质量 1。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | LIFE-PLAN-009 |
| **Domain** | 生活助理 |
| **Difficulty** | Level 2 |
| **User Prompt** | “帮我规划一个为期两天的上海出差行程。要求：酒店必须在南京路附近，且评分高于 4.8。第一天晚上要预订一家可以看外滩江景的餐厅，且该餐厅必须有素食选项。请生成 HTML 格式的行程单，并附上 Google Maps 路线链接。” |
| **Artifacts** | 用户的日程表截图（用于避开冲突时间） |
| **Env Config** | 实时网页访问权限，包含地图与评论 MCP 接口 |
| **Success Criteria** | 1\. 餐厅预订确认包含‘江景’和‘素食’标签；2. 酒店位置与评分完全符合约束；3. 行程单排版精美，各环节衔接合理。 |

## **评测案例 10：自进化智能体技能开发与验证**

这是面向高级开发者的任务，测试 Mavis 是否能通过编写元指令来增强自身的能力边界 75。

| 字段 | 详细内容 |
| :---- | :---- |
| **Task ID** | SYS-EVOLVE-010 |
| **Domain** | AI 工程 |
| **Difficulty** | Level 3 |
| **User Prompt** | “我发现 Mavis 在处理复杂的 SVG 渲染任务时容易出错。请设计一个专门的‘SVG 校验技能’（Skill），它能够通过对比渲染后的像素图和代码逻辑来自动修复代码。请在沙箱中运行 3 个测试用例来验证这个新技能的有效性。” |
| **Artifacts** | 存在渲染 bug 的 SVG 代码片段 |
| **Env Config** | Mavis 技能开发 Harness, 图像比对工具 |
| **Success Criteria** | 1\. 新技能代码逻辑无语法错误；2. 测试用例显示该技能能成功修复至少两个明显的渲染 bug；3. Mavis 的 \<think\> 块展示了对“如何优化自身技能”的深度反思。 |

## **结论与战略建议**

面向 Mavis 的多模态 I/O 评测基准不应仅被视为一个性能计分板，而应当成为智能体向生产力工具进化的核心驱动力。通过将评测重点从“语义相似度”转向“经济交付能力”，Mavis 能够更真实地展现其在数字化工作流中的代换阈值 83。

建议 Mavis 研发团队在后续工作中重点关注以下三点：首先，进一步强化“Verifier”的独立审计能力，通过基准中的 Trajectory 评估发现 Worker 的隐蔽幻觉，实现交付物质量的阶跃提升 51。其次，持续扩充基于 GDP 贡献行业的专业任务库，确保 Mavis 在高价值垂直领域（如金融审计、法律审查）的竞争力 18。最后，将该评测基准转化为“Digital Agent Activities (DAA)”标准，推动行业形成“以干了多少活、交付了多少结果”为核心的新价值评价体系 41。通过这种科学、严苛且贴近实战的评测方法，Mavis 将真正从一个“会聊天的助理”转型为“能交付的数字员工”。

#### **Works cited**

1. MiniMax Agent Features \- AI Tools for Productivity, Creativity & Learning, accessed May 16, 2026, [https://agent.minimax.io/features/en.html](https://agent.minimax.io/features/en.html)  
2. MiniMax Agent Officially Renamed Mavis Launches Multi-Agent Collaboration \- AI NEWS, accessed May 16, 2026, [https://news.aibase.com/news/27990](https://news.aibase.com/news/27990)  
3. GAIA Benchmark: evaluating intelligent agents \- WorkOS, accessed May 16, 2026, [https://workos.com/blog/gaia-benchmark-evaluating-intelligent-agents](https://workos.com/blog/gaia-benchmark-evaluating-intelligent-agents)  
4. LLM Agent Evaluation: Assessing Tool Use, Task Completion, Agentic Reasoning, and More, accessed May 16, 2026, [https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)  
5. MMMU: A Massive Multi-discipline Multimodal Understanding and Reasoning Benchmark for Expert AGI, accessed May 16, 2026, [https://mmmu-benchmark.github.io/](https://mmmu-benchmark.github.io/)  
6. Evaluating AI Agents in Contact Centers: Introducing the Multi-modal Agents Score, accessed May 16, 2026, [https://www.microsoft.com/en-us/dynamics-365/blog/it-professional/2026/02/04/multimodal-agent-score/](https://www.microsoft.com/en-us/dynamics-365/blog/it-professional/2026/02/04/multimodal-agent-score/)  
7. OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks ..., accessed May 16, 2026, [https://os-world.github.io/](https://os-world.github.io/)  
8. Multimodal Agent \- Berkeley RDI, accessed May 16, 2026, [https://rdi.berkeley.edu/adv-llm-agents/slides/Multimodal\_Agent\_caiming.pdf](https://rdi.berkeley.edu/adv-llm-agents/slides/Multimodal_Agent_caiming.pdf)  
9. MiniMax \- Your AI Agent \- App Store, accessed May 16, 2026, [https://apps.apple.com/kg/app/minimax-your-ai-agent/id6742651446](https://apps.apple.com/kg/app/minimax-your-ai-agent/id6742651446)  
10. MiniMax \- Your AI Agent \- App Store \- Apple, accessed May 16, 2026, [https://apps.apple.com/my/app/minimax-your-ai-agent/id6742651446](https://apps.apple.com/my/app/minimax-your-ai-agent/id6742651446)  
11. AI agent evaluation: A practical framework for testing multi-step agents \- Articles \- Braintrust, accessed May 16, 2026, [https://www.braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)  
12. MiniMaxAI/MiniMax-M2.5 · Hugging Face, accessed May 16, 2026, [https://huggingface.co/MiniMaxAI/MiniMax-M2.5](https://huggingface.co/MiniMaxAI/MiniMax-M2.5)  
13. Agent Evaluation Benchmarks in Practice: A Performance Testing Guide from AgentBench to DeepEval, accessed May 16, 2026, [https://eastondev.com/blog/en/posts/ai/20260503-agent-evaluation-benchmark/](https://eastondev.com/blog/en/posts/ai/20260503-agent-evaluation-benchmark/)  
14. MiniMax Agent — 2025 AI Agent Index, accessed May 16, 2026, [https://aiagentindex.mit.edu/2025/minimax-agent/](https://aiagentindex.mit.edu/2025/minimax-agent/)  
15. MiniMax-M2.5 Tool Calling Guide \- GitHub, accessed May 16, 2026, [https://github.com/MiniMax-AI/MiniMax-M2.5/blob/main/docs/tool\_calling\_guide.md](https://github.com/MiniMax-AI/MiniMax-M2.5/blob/main/docs/tool_calling_guide.md)  
16. 2026 Agentic AI十大发展趋势：技术突破与商业落地全景 \- OFweek, accessed May 16, 2026, [https://m.ofweek.com/ai/2026-01/ART-201700-8420-30678222.html](https://m.ofweek.com/ai/2026-01/ART-201700-8420-30678222.html)  
17. Benchmarking AI Agents: A Practical Evaluation Framework \- VerbaFlo, accessed May 16, 2026, [https://www.verbaflo.ai/blog/benchmarking-ai-agents](https://www.verbaflo.ai/blog/benchmarking-ai-agents)  
18. GDPval: Evaluating AI Model Performance on Real-World Economically Valuable Tasks, accessed May 16, 2026, [https://openreview.net/forum?id=hcuEdq6eKD](https://openreview.net/forum?id=hcuEdq6eKD)  
19. Measuring the performance of our models on real-world tasks \- OpenAI, accessed May 16, 2026, [https://openai.com/index/gdpval/](https://openai.com/index/gdpval/)  
20. MiniMax M2.5 Guide: How It Works, Use Cases & More \- DataCamp, accessed May 16, 2026, [https://www.datacamp.com/blog/mini-max-m2-5](https://www.datacamp.com/blog/mini-max-m2-5)  
21. Introducing Harvey's Legal Agent Benchmark, accessed May 16, 2026, [https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark](https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark)  
22. This New AI Agent Controls Your Browser (Minimax Is INSANE) : r/AISEOInsider \- Reddit, accessed May 16, 2026, [https://www.reddit.com/r/AISEOInsider/comments/1qxm2u6/this\_new\_ai\_agent\_controls\_your\_browser\_minimax/](https://www.reddit.com/r/AISEOInsider/comments/1qxm2u6/this_new_ai_agent_controls_your_browser_minimax/)  
23. MiniMax Agent Made Me Realize We've Been Overworking AI Systems, accessed May 16, 2026, [https://ai.plainenglish.io/minimax-agent-made-me-realize-weve-been-overworking-ai-systems-96653a192e75](https://ai.plainenglish.io/minimax-agent-made-me-realize-weve-been-overworking-ai-systems-96653a192e75)  
24. Browser Agent Benchmark: Comparing LLM Models for Web Automation, accessed May 16, 2026, [https://browser-use.com/posts/ai-browser-agent-benchmark](https://browser-use.com/posts/ai-browser-agent-benchmark)  
25. MiniMax M2.7: Early Echoes of Self-Evolution, accessed May 16, 2026, [https://www.minimax.io/news/minimax-m27-en](https://www.minimax.io/news/minimax-m27-en)  
26. MiniMax Agent User Guide – Get Started with AI Agent, accessed May 16, 2026, [https://agent.minimax.io/docs/user-guide](https://agent.minimax.io/docs/user-guide)  
27. agentquest/agentquest/benchmarks/gaia/README.md at main · nec-research/agentquest \- GitHub, accessed May 16, 2026, [https://github.com/nec-research/agentquest/blob/main/agentquest/benchmarks/gaia/README.md](https://github.com/nec-research/agentquest/blob/main/agentquest/benchmarks/gaia/README.md)  
28. Benchmarking AI Agents on Workspace Tasks with Large-Scale File Dependencies \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2605.03596v3](https://arxiv.org/html/2605.03596v3)  
29. GDPval | Epoch AI, accessed May 16, 2026, [https://epoch.ai/benchmarks/gdpval](https://epoch.ai/benchmarks/gdpval)  
30. General AI Assistants Benchmark (GAIA) \- Agentic Design Patterns, accessed May 16, 2026, [https://agentic-design.ai/patterns/evaluation-monitoring/gaia-benchmark](https://agentic-design.ai/patterns/evaluation-monitoring/gaia-benchmark)  
31. What is GAIA? \- Hugging Face, accessed May 16, 2026, [https://huggingface.co/learn/agents-course/unit4/what-is-gaia](https://huggingface.co/learn/agents-course/unit4/what-is-gaia)  
32. 70 expert-curated agentic tasks across Physics, Biology, Chemistry, and Math. \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2604.09836v2](https://arxiv.org/html/2604.09836v2)  
33. Mini-Agent: Build Your First Intelligent Assistant \- MiniMax API Docs, accessed May 16, 2026, [https://platform.minimax.io/docs/solutions/mini-agent](https://platform.minimax.io/docs/solutions/mini-agent)  
34. ScaleCUA/evaluation/WebArenaLiteV2/README.md at main \- GitHub, accessed May 16, 2026, [https://github.com/OpenGVLab/ScaleCUA/blob/main/evaluation/WebArenaLiteV2/README.md](https://github.com/OpenGVLab/ScaleCUA/blob/main/evaluation/WebArenaLiteV2/README.md)  
35. A Realistic Web Environment for Building Autonomous Agents \- WebArena, accessed May 16, 2026, [https://webarena.dev/og/](https://webarena.dev/og/)  
36. WebArena Benchmark: Evaluating Web Agents \- Emergent Mind, accessed May 16, 2026, [https://www.emergentmind.com/topics/webarena-benchmark](https://www.emergentmind.com/topics/webarena-benchmark)  
37. How to Build an Agent Evaluation Framework With Metrics, Rubrics, and Benchmarks, accessed May 16, 2026, [https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)  
38. WebArena Verified \- OpenReview, accessed May 16, 2026, [https://openreview.net/pdf?id=94tlGxmqkN](https://openreview.net/pdf?id=94tlGxmqkN)  
39. AgentBench: Evaluating LLMs as Agents \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2308.03688v3](https://arxiv.org/html/2308.03688v3)  
40. WebArena-Infinity: Generating Browser Environments with Verifiable Tasks at Scale, accessed May 16, 2026, [https://webarena.dev/webarena-infinity/](https://webarena.dev/webarena-infinity/)  
41. 从百度的自我进化看Agent时代的无限游戏- 智能体, accessed May 16, 2026, [https://finance.sina.cn/stock/jdts/2026-05-13/detail-inhxuncf4396750.d.html?vt=4\&cid=76993\&node\_id=76993](https://finance.sina.cn/stock/jdts/2026-05-13/detail-inhxuncf4396750.d.html?vt=4&cid=76993&node_id=76993)  
42. AI in Excel – Features and Benefits \- Microsoft, accessed May 16, 2026, [https://www.microsoft.com/en-us/microsoft-365/excel/ai-for-excel](https://www.microsoft.com/en-us/microsoft-365/excel/ai-for-excel)  
43. GDPval-AA Leaderboard \- Artificial Analysis, accessed May 16, 2026, [https://artificialanalysis.ai/evaluations/gdpval-aa](https://artificialanalysis.ai/evaluations/gdpval-aa)  
44. GDPval-AA Benchmark Leaderboard \- LLM Stats, accessed May 16, 2026, [https://llm-stats.com/benchmarks/gdpval-aa](https://llm-stats.com/benchmarks/gdpval-aa)  
45. Rubrics reference guide \- Microsoft Copilot Studio, accessed May 16, 2026, [https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/kit-rubrics-reference](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/kit-rubrics-reference)  
46. Metric prompt templates for model-based evaluation | Generative AI on Vertex AI, accessed May 16, 2026, [https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/metrics-templates](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/metrics-templates)  
47. LLM Evaluation Framework: Trajectories vs. Outputs \- LangChain, accessed May 16, 2026, [https://www.langchain.com/articles/llm-evaluation-framework](https://www.langchain.com/articles/llm-evaluation-framework)  
48. MiniMax M2.5: Intelligence too cheap to meter, RL process rewards, real-world productivity, accessed May 16, 2026, [https://www.baseten.co/blog/minimax-m2-5-intelligence-too-cheap-to-meter-rl-process-rewards-real-world-produc/](https://www.baseten.co/blog/minimax-m2-5-intelligence-too-cheap-to-meter-rl-process-rewards-real-world-produc/)  
49. The 5 pillars of AI model performance \- Blog \- Braintrust, accessed May 16, 2026, [https://www.braintrust.dev/blog/model-measurement](https://www.braintrust.dev/blog/model-measurement)  
50. AgentRewardBench: Evaluating Automatic Evaluations of Web Agent Trajectories \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2504.08942v2](https://arxiv.org/html/2504.08942v2)  
51. MiniMax desktop has been renamed to Mavis and launched multi-Agent team collaboration., accessed May 16, 2026, [https://news.futunn.com/en/flash/20299463/minimax-desktop-has-been-renamed-to-mavis-and-launched-multi](https://news.futunn.com/en/flash/20299463/minimax-desktop-has-been-renamed-to-mavis-and-launched-multi)  
52. Multi-agent systems are a runtime problem, not a prompt problem \- Reddit, accessed May 16, 2026, [https://www.reddit.com/r/ArtificialInteligence/comments/1tcrlo6/multiagent\_systems\_are\_a\_runtime\_problem\_not\_a/](https://www.reddit.com/r/ArtificialInteligence/comments/1tcrlo6/multiagent_systems_are_a_runtime_problem_not_a/)  
53. MiniMax renames its desktop agent product to Mavis and launches multi-agent team collaboration. | KuCoin, accessed May 16, 2026, [https://www.kucoin.com/news/flash/minimax-renames-desktop-agent-product-to-mavis-launches-multi-agent-team-collaboration](https://www.kucoin.com/news/flash/minimax-renames-desktop-agent-product-to-mavis-launches-multi-agent-team-collaboration)  
54. How to Build Reliable Multimodal AI Evaluators Using VLM Judges ..., accessed May 16, 2026, [https://medium.com/@jiyang.kang/how-to-build-reliable-multimodal-ai-evaluators-using-vlm-judges-ca5663e3272a](https://medium.com/@jiyang.kang/how-to-build-reliable-multimodal-ai-evaluators-using-vlm-judges-ca5663e3272a)  
55. From Art to Engineering: A Practical Rubric for GPT-4.1 Prompt Design \- Medium, accessed May 16, 2026, [https://medium.com/@reveriano.francisco/from-art-to-engineering-a-practical-rubric-for-gpt-4-1-prompt-design-e4cc9f9d55de](https://medium.com/@reveriano.francisco/from-art-to-engineering-a-practical-rubric-for-gpt-4-1-prompt-design-e4cc9f9d55de)  
56. LLM as a Judge \- Primer and Pre-Built Evaluators \- Arize AI, accessed May 16, 2026, [https://arize.com/llm-as-a-judge/](https://arize.com/llm-as-a-judge/)  
57. Demystifying evals for AI agents \- Anthropic, accessed May 16, 2026, [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)  
58. NeurIPS Poster OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments, accessed May 16, 2026, [https://neurips.cc/virtual/2024/poster/97468](https://neurips.cc/virtual/2024/poster/97468)  
59. How to Benchmark AI Web Agents: Metrics, Strategies, and Challenges \- Foundry, accessed May 16, 2026, [https://www.foundryrl.com/blog/benchmark-ai-web-agents](https://www.foundryrl.com/blog/benchmark-ai-web-agents)  
60. Artificial Analysis Intelligence Benchmarking Methodology, accessed May 16, 2026, [https://artificialanalysis.ai/methodology/intelligence-benchmarking](https://artificialanalysis.ai/methodology/intelligence-benchmarking)  
61. AI Model Evaluations \- Artificial Analysis, accessed May 16, 2026, [https://artificialanalysis.ai/evaluations](https://artificialanalysis.ai/evaluations)  
62. General-Purpose Benchmark GAIA \- Emergent Mind, accessed May 16, 2026, [https://www.emergentmind.com/topics/general-purpose-benchmark-gaia](https://www.emergentmind.com/topics/general-purpose-benchmark-gaia)  
63. What is Back-to-Back Testing? Meaning, Examples, and When to Use It \- testRigor AI-Based Automated Testing Tool, accessed May 16, 2026, [https://testrigor.com/blog/what-is-back-to-back-testing/](https://testrigor.com/blog/what-is-back-to-back-testing/)  
64. AI Model Validation Best Practices in ML | Galileo, accessed May 16, 2026, [https://galileo.ai/blog/best-practices-for-ai-model-validation-in-machine-learning](https://galileo.ai/blog/best-practices-for-ai-model-validation-in-machine-learning)  
65. Rubric-Based Evaluation for Agentic Systems | by AI4HUMAN \- Medium, accessed May 16, 2026, [https://medium.com/@aiforhuman/rubric-based-evaluation-for-agentic-systems-db6cb14d8526](https://medium.com/@aiforhuman/rubric-based-evaluation-for-agentic-systems-db6cb14d8526)  
66. AgentAssay: Token-Efficient Regression Testing for Non-Deterministic AI Agent Workflows Technical Report \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2603.02601v1](https://arxiv.org/html/2603.02601v1)  
67. GDPval-AA Benchmark 2026: 4 model averages | BenchLM.ai, accessed May 16, 2026, [https://benchlm.ai/benchmarks/gdpvalAa](https://benchlm.ai/benchmarks/gdpvalAa)  
68. MiniMax M2.5: Coding Benchmarks, Pricing, and Guide \- Digital Applied, accessed May 16, 2026, [https://www.digitalapplied.com/blog/minimax-m25-ai-model-coding-benchmarks-guide](https://www.digitalapplied.com/blog/minimax-m25-ai-model-coding-benchmarks-guide)  
69. Build Real-World Productivity Agents on SambaCloud with MiniMax 2.5 \- SambaNova, accessed May 16, 2026, [https://sambanova.ai/blog/build-real-world-productivity-agents-on-sambacloud-with-minimax-2-5](https://sambanova.ai/blog/build-real-world-productivity-agents-on-sambacloud-with-minimax-2-5)  
70. MiniMax M2.5 vs GPT-5.2 vs Claude Opus 4.6 vs Gemini 3.1 Pro \- Clarifai, accessed May 16, 2026, [https://www.clarifai.com/blog/minimax-m2.5-vs-gpt-5.2-vs-claude-opus-4.6-vs-gemini-3.1-pro](https://www.clarifai.com/blog/minimax-m2.5-vs-gpt-5.2-vs-claude-opus-4.6-vs-gemini-3.1-pro)  
71. MiniMax-M2, a model built for Max coding & agentic workflows. \- GitHub, accessed May 16, 2026, [https://github.com/MiniMax-AI/MiniMax-M2](https://github.com/MiniMax-AI/MiniMax-M2)  
72. MiniMax Matches GPT-5.3-Codex on Software Engineering Tasks | Let's Data Science, accessed May 16, 2026, [https://letsdatascience.com/news/minimax-matches-gpt-53-codex-on-software-engineering-tasks-164f3d81](https://letsdatascience.com/news/minimax-matches-gpt-53-codex-on-software-engineering-tasks-164f3d81)  
73. MiniMax launches Mavis agent mode \- KrASIA, accessed May 16, 2026, [https://kr-asia.com/pulses/161957](https://kr-asia.com/pulses/161957)  
74. WebArena Benchmark 2026: 15 model averages \- BenchLM.ai, accessed May 16, 2026, [https://benchlm.ai/benchmarks/webArena](https://benchlm.ai/benchmarks/webArena)  
75. MiniMax M2.7: A LLM Managing Decentralized Agent Teams | by My Social \- Medium, accessed May 16, 2026, [https://medium.com/aimonks/minimax-m2-7-a-llm-managing-decentralized-agent-teams-acc4e551df4d](https://medium.com/aimonks/minimax-m2-7-a-llm-managing-decentralized-agent-teams-acc4e551df4d)  
76. MMMU Pro \- Vals AI, accessed May 16, 2026, [https://www.vals.ai/benchmarks/mmmu](https://www.vals.ai/benchmarks/mmmu)  
77. Uni-MMMU: A Massive Multi-discipline Multimodal Unified Benchmark \- arXiv, accessed May 16, 2026, [https://arxiv.org/html/2510.13759v3](https://arxiv.org/html/2510.13759v3)  
78. GitHub \- subconscious-systems/subconscious-browser-bench: Browser automation benchmarks for evaluating AI agents on web tasks. 130 tasks across WebArena (sandboxed sites) and BU Bench (live internet), with deterministic and LLM-based evaluation., accessed May 16, 2026, [https://github.com/subconscious-systems/subconscious-browser-bench](https://github.com/subconscious-systems/subconscious-browser-bench)  
79. WebChoreArena: LLM Web Agent Benchmark \- Emergent Mind, accessed May 16, 2026, [https://www.emergentmind.com/topics/webchorearena](https://www.emergentmind.com/topics/webchorearena)  
80. How to Benchmark AI Agents Effectively \- Galileo AI: The AI Observability and Evaluation Platform, accessed May 16, 2026, [https://galileo.ai/learn/benchmark-ai-agents](https://galileo.ai/learn/benchmark-ai-agents)  
81. MiniMax M2.7: The Self-Evolving AI Model That Rivals Claude and GPT at a Fraction of the Cost \- WaveSpeed AI, accessed May 16, 2026, [https://wavespeed.ai/blog/posts/minimax-m2-7-self-evolving-agent-model-features-benchmarks-2026/](https://wavespeed.ai/blog/posts/minimax-m2-7-self-evolving-agent-model-features-benchmarks-2026/)  
82. What Is MiniMax M2.7? The Self-Evolving AI Model That Handles 30–50% of Its Own Training | MindStudio, accessed May 16, 2026, [https://www.mindstudio.ai/blog/what-is-minimax-m27-self-evolving-model](https://www.mindstudio.ai/blog/what-is-minimax-m27-self-evolving-model)  
83. CVPR Poster MMMU: A Massive Multi-discipline Multimodal Understanding and Reasoning Benchmark for Expert AGI, accessed May 16, 2026, [https://cvpr.thecvf.com/virtual/2024/poster/31040](https://cvpr.thecvf.com/virtual/2024/poster/31040)  
84. GDPVAL: Evaluating AI Model Performance on Real-World Economically Valuable Tasks, accessed May 16, 2026, [https://www.researchgate.net/publication/400195012\_GDPVAL\_Evaluating\_AI\_Model\_Performance\_on\_Real-World\_Economically\_Valuable\_Tasks](https://www.researchgate.net/publication/400195012_GDPVAL_Evaluating_AI_Model_Performance_on_Real-World_Economically_Valuable_Tasks)

[image1]: <data:image/png;base64,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>