# TI15 预测项目 — 学术方法论调研

调研日期：2026-08-02 | TI15 开赛：2026-08-13（剩 11 天）
调研范围：评分系统 / 电竞预测文献 / 锦标赛模拟 / 选手个人指标 / 评估与陷阱

---

## 完成度表

| 区块 | 状态 | 备注 |
|---|---|---|
| 1. 评分/评级系统 | **完成** | Elo/Glicko-2/TrueSkill(2)/BT/Plackett-Luce/状态空间 全覆盖；含反对 PL 的明确意见 |
| 2. 电竞专门预测文献 | **完成** | 核心结论：赛前上限约 65-70%；>80% 的论文全是实时数据 |
| 3. 锦标赛结果预测（含瑞士轮） | **完成** | 瑞士轮四要点已写；含双败 bracket reset 与解析递推建议 |
| 4. 选手个人指标预测（含 EVT） | **完成** | NB 有文献支持但应改造为层次泊松；EVT 判为过度工程（附条件） |
| 5. 评估与陷阱（含赔率校准） | **完成** | 含对「1/6 夺冠说明赔率校准差」的明确反驳（二项检验） |
| 对比总表 | **完成** | 见文末 |

**未完成/未能获取的部分（诚实记录）**：
- Liquipedia 的 "General Swiss Pairing Rules" 原文：WebFetch 与 curl 各试一次均 HTTP 403，按纪律放弃。瑞士轮配对规则用 Wikipedia 的 Dutch system + CS Major 的 Buchholz 惯例替代，**TI15 的确切配对与晋级规则需由格式核实的 agent 确认**。
- Brandes et al. (2025) "Efficient computation of tournament winning probabilities" 正文：SAGE 403，只有标题。
- Semenov et al. (2016) draft 预测的准确率数字来自二手摘要，未在正文核实。
- 电竞 favourite-longshot bias 的原始论文未定位到（只读到二手转述），因此 5.3(C)3 标为待验证假设。

**证据等级标记约定**：
- `[读正文]` = 抓到了论文正文/详细内容
- `[读摘要]` = 只读到摘要或详细的二手描述
- `[仅标题]` = 只在检索结果里看到标题+一句话，未验证内容
- `[背景知识]` = 我的既有知识，本次未做在线核实（请自行掂量）

---

## 1. 评分/评级系统（rating systems）

### 1.1 Elo

- Elo, A. (1978). *The Rating of Chessplayers, Past and Present*. `[背景知识]`
- Wikipedia 条目（本次核实存在，未逐条读）`[仅标题]` https://en.wikipedia.org/wiki/Elo_rating_system

**假设**：单一标量能力；胜率是能力差的 logistic（或 normal）函数；能力慢变。更新是固定步长 K 的随机梯度下降。
**数据量**：极省。每个实体 20-30 场就有粗略可用值，但方差没有显式建模，新队/久疏队的评级不可信而系统不知道。
**团队项目/阵容变动**：原生不支持。工业界唯一做法是**时间窗 + 衰减**。检索到的行业实践：Riot 的 Global Power Rankings 用**两年滚动窗**来"吸收"阵容变动、地区迁移和版本变化，并且**同时维护队伍 Elo 和赛区 Elo**（`[读摘要]`，来源为二手行业博客 boostroyal，不是同行评审文献——当作行业惯例而非学术证据）。

**对 TI15 的可用性判断：需改造（但值得做）**。理由：Elo 是唯一能在 11 天内从头实现并调好的东西。但裸 Elo 在 TI 上有两个致命点——(a) 跨赛区可比性（中国队和西欧队互打样本少，Elo 图不连通会导致赛区间偏移无法校正）；(b) 阵容变动。改造方向见 1.5。

### 1.2 Glicko / Glicko-2

- Glickman, M. E. (1999). "Parameter Estimation in Large Dynamic Paired Comparison Experiments." *JRSS-C* 48(3), 377-394. `[读摘要]` https://academic.oup.com/jrsssc/article-abstract/48/3/377/6990661
- Glickman, M. E. (2001). "Dynamic paired comparison models with stochastic variances." `[读摘要]` https://www.glicko.net/research/dpcmsv.pdf

**核心增量**：给每个实体的能力加一个**评级偏差 RD（rating deviation）**，即后验方差；不打比赛时 RD 随时间膨胀。Glicko-2 再加一个**波动度 σ（volatility）**，刻画"这支队伍本身有多不稳定"。
**为什么对我们重要**：TI 有队伍长期不打国际赛（尤其东南亚/南美的直邀队），Elo 会给它一个"看起来很确定"的数，Glicko 会诚实地说"我不知道"。**不确定度会直接传导到夺冠概率的宽度**，这正是我们做概率预测需要的。
**数据量**：和 Elo 同量级，但 RD 让小样本时输出可用（宽而诚实）。
**阵容变动**：仍然不原生支持。但有一个便宜的 hack——**阵容一变就人为把 RD 拉大**（等价于"我们对这支队伍重新变得不确定"）。这是一个既符合模型语义又几乎零成本的做法，我认为是我们该用的。

**可用性判断：直接可用（首选的队伍层评级底座）**。

### 1.3 TrueSkill / TrueSkill2

- Herbrich, R., Minka, T., Graepel, T. (2007). "TrueSkill™: A Bayesian Skill Rating System." *NIPS 2006*. `[读摘要]`
- Minka, T., Cleven, R., Zaykov, Y. (2018). "TrueSkill 2: An Improved Bayesian Skill Rating System." Microsoft Research Technical Report MSR-TR-2018-8. `[读摘要 + PDF 抓到但正文被 PDF 流截断，只读到章节结构]` https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/trueskill2.pdf

**TrueSkill 的核心价值（对我们最关键的一点）**：它是**从队伍结果反推个人能力**的因子图模型。队伍表现 = 队内个人表现之和，个人表现 ~ N(skill_i, β²)。这意味着**阵容变动是原生处理的**——换一个人，队伍的先验强度自动重算，不需要任何 hack。这正好命中我们说的"最痛的点"。
**TrueSkill2 的增量**（从抓到的章节结构确认存在这些模块）：squad offset（组队人数对表现的偏移）、experience effects（经验/场次）、individual statistics（个人击杀等统计量直接进入 skill 推断）、quit penalty、以及 batch 模式（全历史联合推断，而不只是在线前向）。
**报告的效果**：搜索摘要给出 TrueSkill2 预测历史比赛 68% 准确率 vs TrueSkill 52%（`[读摘要]`，未在正文核实）。**注意这个 52% 基线低得可疑**——TrueSkill 在自家匹配数据上只有 52% 基本等于随机，很可能是因为匹配系统本身在刻意制造 50/50 对局（匹配平衡会把可预测性抹掉）。**不要把 68% vs 52% 直接外推到 TI**，TI 的对局强弱差异远大于匹配队列。

**数据量**：TrueSkill 本身收敛很快（论文声称比 Elo 少一个数量级的场次）。但 TrueSkill2 要估的超参数多，需要大批历史数据做 batch 拟合。
**可用性判断：需改造，且优先级高**。理由：TrueSkill 的"个人 skill 加总成队伍"结构是我们处理阵容变动的**唯一有原理的办法**，而且它顺带给出**选手个人能力估计**，可以复用到选手个人 prop 上。改造点：Dota2 五个位置不对称（1 号位和 5 号位对胜负的贡献机制完全不同），标准 TrueSkill 的"等权求和"假设不成立，需要加位置权重或位置特异的 β。11 天内，建议实现**简化版 TrueSkill（不带 TrueSkill2 的那堆扩展）**，不要贪。

### 1.4 Bradley-Terry 及扩展

- Bradley, R. A., Terry, M. E. (1952). "Rank Analysis of Incomplete Block Designs." *Biometrika* 39, 324-345. `[背景知识]`
- Cattelan, M., Varin, C., Firth, D. (2013). "Dynamic Bradley–Terry modelling of sports tournaments." *JRSS-C*. `[仅标题]` https://www.researchgate.net/publication/259241214
- Bong, H. et al. (2020). "Nonparametric Estimation in the Dynamic Bradley-Terry Model." *AISTATS 2020* (PMLR v108). `[读摘要]` arXiv:2003.00083
- "The many routes to the ubiquitous Bradley-Terry model." arXiv:2312.13619 `[仅标题]` — 综述性质，如果要写方法论附录可以引。

**为什么 BT 比 Elo 好**：BT 是**似然模型**，可以做最大似然/贝叶斯估计，可以加协变量（主场、版本、赛区、BO 制式），可以算标准误，可以做正则化（对小样本队伍收缩）。Elo 只是它的在线近似。
**对我们最有用的形态**：**带正则化的 BT + 赛区固定效应**。TI 前的跨赛区样本稀疏，加赛区层的随机效应可以把"这个赛区整体强度"和"这支队伍相对本赛区的强度"分开估，缓解 Elo 图不连通的问题。这是 11 天内能落地的（一个 logistic 回归 + ridge 惩罚就是了）。

**可用性判断：直接可用**。成本最低、可解释性最好、能加协变量。建议作为队伍层的**主力模型**（Glicko 作为对照）。

### 1.5 Plackett-Luce（名次而非两两胜负）

- Plackett, R. L. (1975). "The Analysis of Permutations." *JRSS-C* 24(2), 193-202. `[背景知识]`
- Turner, H. L., van Etten, J., Firth, D., Kosmidis, I. (2020). "Modelling rankings in R: the PlackettLuce package." *Computational Statistics* 35, 1027-1057. `[读摘要]` arXiv:1810.12068 / DOI 10.1007/s00180-020-00959-3
- "Efficient inference of rankings from multi-body comparisons." arXiv:2501.16565（2025），同时发表于 *Phys. Rev. E*。`[读摘要]` — 处理"每次比较涉及多于两个实体"的高效推断。
- "Analyzing and Forecasting Success in the Men's Ice Hockey World (Junior) Championships Using a Dynamic Ranking Model." arXiv:2409.05714 `[仅标题]` — **这篇最接近我们的用例**（用动态排名模型预测单届世锦赛名次），值得后续单独抓。

**PL 是什么**：把"最终名次"直接当观测。P(排名序列) = 逐位置的 softmax——第一名从全体里按 worth 抽出，第二名从剩下的抽，以此类推。
**关键性质**：PL 的两两边际就是 BT，P(A beats B) = α_A/(α_A+α_B)（这条在检索结果里明确确认了）。所以 **PL 和 BT 是同一族，可以共享参数**。
**对我们的真实价值**：**没有想象中大**。我要诚实说这一点——PL 的优势是"当你只观测到名次、观测不到每场比赛"时。而 TI 我们**能观测到每一场 BO**，信息量远大于名次。此时用 BT/Elo 拟合场次 + 蒙特卡洛推名次分布，比用 PL 直接拟合名次**更有效率**（用了更多信息）。
**PL 真正该用的地方**：拿**历史各届 TI 的最终名次**做一个先验/健全性检查（"顶级队伍在大赛上的名次分布长什么样"），或者拟合"多队同场"的赛制（Dota2 没有这种赛制，所以用不上）。

**可用性判断：用不上（作为主模型）/ 可选（作为名次先验的校验）**。理由：我们有场级数据，PL 会浪费信息。**任务书里把 PL 列为"对锦标赛名次预测特别关键"——我不同意这个判断，这是本次调研最主要的一条反对意见。** 名次分布应该由「BT/Glicko 估两两胜率 → 蒙特卡洛跑赛制」产生，而不是直接建模名次。

### 1.6 动态状态空间评分

- Glickman (2001) 的 stochastic variance 状态空间模型（见 1.2）`[读摘要]`
- Fahrmeir & Tutz (1994) 类的 dynamic generalized linear model `[背景知识]`
- Ingram, M. (2019). "Gaussian Process Priors for Dynamic Paired Comparison Modelling." arXiv:1902.07378 `[读摘要]` — 用 GP 先验刻画能力的时间演化，比"固定衰减率"更灵活。
- Baker & McHale, "An empirical Bayes model for time-varying paired comparisons ratings: Who is the greatest women's tennis player?" *EJOR* (2017). `[仅标题]`

**判断：用不上（本次）**。理由：状态空间/GP 方法的收益在于**平滑地估计能力轨迹**，而我们只需要**一个时点（8/13）的能力估计**。11 天时间下，这些方法的实现和调参成本远超它带来的边际精度。Glicko-2 的 RD 膨胀已经是状态空间的廉价近似。

---

### 区块 1 小结：TI15 该怎么选

**推荐的队伍层架构（按实现顺序）**：
1. **带 ridge 正则 + 赛区随机效应的 Bradley-Terry**，在近 12 个月的 BO 级数据上拟合 → 主模型。
2. **Glicko-2** 跑同一批数据 → 对照 + 提供不确定度；**阵容变动时手动膨胀 RD**。
3. 如果时间允许，**简化 TrueSkill**（个人 skill 加总）→ 专门解决阵容变动，并复用于选手 prop。
4. **不要**上状态空间/GP/TrueSkill2 全套。**不要**用 Plackett-Luce 直接建名次。

---

## 2. 电竞专门的预测文献

### 2.1 基于 BP 阵容（draft）的预测

- Semenov, A., Romov, P., Korolev, S., Yashkov, D., Neklyudov, K. (2016/2017). "Performance of Machine Learning Algorithms in Predicting Game Outcome from Drafts in Dota 2." *AIST 2016*, CCIS vol. 661. `[读摘要]` https://www.researchgate.net/publication/313010005
  - **这是 draft-only 预测的标准参照**。系统比较 Naive Bayes / Logistic Regression / Gradient Boosted Decision Trees / Factorization Machines，**Factorization Machines 最好**（因为它显式建模英雄两两交互，而 draft 的本质就是英雄组合效应）。
  - **关键数字（`[读摘要]`，需在正文核实）**：只用 draft 的准确率大约在 **58%-63%** 区间（公开赛数据）。这是我们该记住的天花板——**BP 只能解释很小一部分胜负**。
- Summerville, A., Cook, M., Steenhuisen, B. "Draft-Analysis of the Ancients: Predicting Draft Picks in DotA 2 using Machine Learning." *AIIDE 2016 Workshop*. `[读摘要]` — 注意：这篇预测的是**下一手会 pick 谁**，不是预测胜负。对我们只在"如果要做 BP 相关 prop"时有用。
- "Outcome prediction of DOTA2 using machine learning methods." *ICMAI 2018*, DOI 10.1145/3208788.3208800. `[仅标题+一句摘要]` — 把英雄从 17 个维度量化，构造 113 英雄优先表。

**我的判断**：draft-based 预测**对 TI15 用不上**。原因很直接——我们要在**赛前**给出夺冠概率和 prop，那时候根本没有 draft。draft 模型只在"比赛已经开始、BP 结束、还没打"这个窗口有用，而这个窗口我们不下注。**除非**我们要做的是实时更新，那另说。

### 2.2 「深度学习相对简单基线到底有没有增益」——这是本区块最重要的发现

任务书里让我留意"很多论文的基线设得很弱"。**核实结果：这个怀疑是对的，而且比想象的更严重。** 具体有三类系统性问题：

**(a) 混淆「赛前预测」和「实时预测」，然后报一个吓人的准确率。**
- Akhmedov, K., Phan, A. H. (2021). "Machine learning models for DOTA 2 outcomes prediction." arXiv:2106.01782. `[读摘要，已抓 abstract 页]`
  - 报告 LR 平均 82%、NN 88%、LSTM 93%。**但正文用的是 GSI（Game State Integration）实时游戏内数据**，不是赛前特征。用第 40 分钟的经济/推塔状态预测胜负，93% 一点也不稀奇——那时候比赛基本已经结束了。**这类数字绝不能拿来和赛前模型比较。**
  - 另一处交叉印证（`[读摘要]`）：某 Dota 2 研究中，纯赛前特征的 LR 基线 **58.69%**，加更多赛前特征到 **71.49%**，加入实时特征后到第 40 分钟才达到 **93.73%**。**这条数字链非常有说服力地划出了边界：赛前上限 ~70%，93% 是实时数据带来的，不是模型带来的。**

**(b) 基线弱到不构成对照。** TrueSkill2 论文里 TrueSkill 基线只有 52%（近乎随机），是因为匹配系统刻意做 50/50 对局；把这个 52% 当"简单方法的能力"是误导。

**(c) 少数诚实的论文承认 LR 赢了深度模型。**
- "Scalable Psychological Momentum Forecasting in Esports." arXiv:2001.11274 `[读摘要]` — 深度网络在动量估计任务上更合适，但**在多人预测任务上 logistic regression 反而胜出**，且**滚动统计量（rolling statistics）作为特征优于其他特征**。这条对我们很有指导意义：**特征（滚动近期表现）比模型架构更重要**。

**其他检索到但未深读的**：
- "Real-time eSports Match Result Prediction." (Yang, Qin et al.) `[仅标题]`
- "Predictive Analysis and Comparison of Various Models on Esports Competitions." `[仅标题]`
- "STATISTICAL LEARNING FOR ESPORTS MATCH PREDICTION"（CalState 硕士论文）`[仅标题]`
- "Round Outcome Prediction in VALORANT Using Tactical Features from Video Analysis." arXiv:2510.17199 `[仅标题]`
- "Prediction of esports competition outcomes using EEG data from expert players." *ScienceDirect* `[仅标题]` — 需要选手脑电，与我们无关。

### 2.3 有没有专门做单次大型锦标赛预测的研究？

**检索结果：几乎没有直接对口的电竞文献。** 我没有找到一篇专门预测某一届 TI / Worlds / Major 的同行评审论文。最接近的是传统体育侧：
- "Analyzing and Forecasting Success in the Men's Ice Hockey World (Junior) Championships Using a Dynamic Ranking Model." arXiv:2409.05714 `[仅标题]` — 单届世锦赛的名次预测，方法论可迁移。
- "Prediction of the 2019 IHF World Men's Handball Championship — An underdispersed sparse count data regression model." arXiv:1901.05722 `[仅标题]` — **这篇的框架和我们要做的事高度同构**（赛前预测一届锦标赛 + 计数数据回归 + 蒙特卡洛推名次），如果只能再读一篇论文，我会读这篇。注意它说的是 **under**dispersed（欠离散），和我们对击杀数的 **over**dispersion 预期相反，值得对照。

### 区块 2 小结与可用性判断

| 子方向 | 判断 | 理由 |
|---|---|---|
| draft-based 预测 | **用不上** | 赛前没有 draft |
| 深度学习（LSTM/NN）赛前预测 | **用不上** | 高准确率全部来自实时数据泄漏式特征；赛前场景下没有证据显示它赢过带好特征的 LR |
| 滚动近期表现特征（rolling stats） | **直接可用，高优先级** | 唯一被论文明确点名"比模型架构更重要"的东西 |
| 单届锦标赛预测文献 | **需改造** | 电竞侧没有；从冰球/手球侧借框架 |

**给项目的硬结论**：**赛前 Dota2 胜负预测的现实准确率上限约 65-70%，不要相信任何声称 >80% 的赛前模型。** 我们的模型如果在留出集上做到 63-67%，那已经是对的量级；如果做到 85%，那一定是泄漏了。这条应该写进项目的健全性检查清单。

---

## 3. 锦标赛结果预测

### 3.1 从两两胜率到夺冠概率：蒙特卡洛是标准做法

标准流水线（学界和业界都是这一套）：
1. 拟合一个**单场胜率模型** p(i beats j)（BT / Elo / Glicko）。
2. 把 BO3/BO5 从单局胜率折算成系列赛胜率：BO3 中 P(赢系列) = p² (3-2p)；BO5 = p³(6p²-15p+10)。**注意这里有个真实的坑**：单局胜率和系列赛胜率不是同一个量，如果你的模型直接在"系列赛结果"上拟合，就不要再做这层折算（会双重放大）。反之如果在局级拟合，必须折算。**先明确你的数据粒度。**
3. **按真实赛制逐轮模拟 N 次**（N ≥ 20,000，理由见下），统计每支队伍到达每个名次的频率。
4. 输出：夺冠概率、名次分布、进入 top4 概率等。

**文献支撑**：
- Brandes, U., Marmulla, G., Smokovic, I. (2025). "Efficient computation of tournament winning probabilities." *Journal of Sports Analytics*, DOI 10.1177/22150218251313905. `[仅标题 — 期刊 403，未读到正文]` — 讲**精确/解析计算**夺冠概率而非模拟。对我们的意义：**如果赛制是固定 bracket（双败淘汰），夺冠概率可以精确递推算出来，不需要蒙特卡洛**，这样能消除模拟噪声。值得在实现淘汰赛部分时采用。
- "The efficacy of tournament designs." arXiv:2103.06023 `[仅标题]` — 比较各种赛制识别真实最强者的能力。
- Monte Carlo Tennis, *SIAM Review*（Newton & Aslam 类工作）`[仅标题]`

**一条重要的数值警告**（`[读摘要]`，来自双败模拟的讨论）：蒙特卡洛在**小概率事件上会系统性高估**（相对解析值），尤其对低胜率选手。这是有限样本 + 离散计数的必然结果。**我们要报"某队夺冠概率 1.5%"这种数字，20,000 次模拟下标准误约 0.09pp，可接受；但要报 0.1% 级别的数字，必须上 100 万次或改用解析递推。**

### 3.2 瑞士轮（Swiss）的模拟 —— 本区块重点

**TI 的赛制事实**（`[读摘要]`，来自 Liquipedia/媒体二手报道，**请让格式核实的 agent 确认 TI15 具体规则**）：
- TI2025（TI14）是**第一届用瑞士轮**取代小组赛的 TI：16 队、**5 轮**、**BO3**、前三天打完。
- 配对采用 Liquipedia 所谓的 "General Swiss Pairing Rules"（同战绩配对）。
- 注：我检索到的 TI2025 描述里晋级人数说法不一（有说 10 队进淘汰赛的）。**任务书说"砍到 8 队"——这个数字我没能独立核实，请以格式 agent 的结论为准。** Liquipedia 对 WebFetch 和 curl 均返回 403（两次，已按纪律放弃）。

**通用瑞士轮配对算法（Dutch system，`[读正文]` Wikipedia）**：
1. 按当前积分把队伍分成**同分组（score group）**。
2. 组内按**评级/初始种子**排序。
3. **上半区对下半区**：8 队的组里，1 打 5、2 打 6、3 打 7、4 打 8。
4. **避免重赛**：已交手过的不再配，冲突时做局部交换。
5. 同分组人数为奇数时，把一名队伍"下浮（float down）"到下一个分组。
6. 轮数经验值：**N 队需要 ⌈log2 N⌉ 轮**才能分出唯一冠军 → 16 队最少 4 轮。TI 用 5 轮（多一轮用于更细的切分）。
7. **同分排序 tiebreak 用 Buchholz**（对手总分之和），这是 CS Major 的既定做法，并被 esports 圈广泛采用（`[读摘要]`，HLTV 报道 PGL Major 采用 Buchholz seeding）。

**模拟瑞士轮的四个关键要点（这是本次调研最实用的部分）**：

**要点 1：配对是内生的，不能预生成赛程。**
双败淘汰的 bracket 是**固定**的，你可以一次性把树画好然后往里填。瑞士轮不行——第 3 轮谁打谁，取决于第 1、2 轮的结果。**所以模拟必须是逐轮的闭环**：
```
for sim in 1..N:
    records = {team: (0,0)}, history = {}
    for round in 1..5:
        pairs = swiss_pair(records, seeds, history, buchholz)   # 每轮重算
        for (a,b) in pairs: 
            winner = sample(p_series(a,b));  update records, history
    rank = tiebreak_sort(records, buchholz)
```
**这一条是瑞士轮比双败"复杂"的全部原因**。实现上不难，但你必须把配对函数写对，否则整个名次分布是错的。

**要点 2：瑞士轮内建负反馈，会压缩结果分布。**
赢了就去打更强的对手。这意味着强队的赛程会自动变难，**强队"5-0"的概率显著低于"每轮独立按平均胜率赢"算出来的值**。如果你偷懒用二项分布近似（"这队平均胜率 0.6，5 轮拿 4 胜的概率是 C(5,4)·0.6⁴·0.4"），**你会系统性高估强队的高战绩概率、低估中游队伍的上限**。这是真实且可量化的偏差，必须靠逐轮模拟消除。

**要点 3：Buchholz 让名次依赖于"你的对手后来打得怎么样"，必须在模拟里完整记账。**
Buchholz 是**事后**量——同分队伍的排序取决于各自对手的最终战绩。做晋级/淘汰切分时如果切在同分线上，必须真的把 Buchholz 算出来。**很多简易模拟器在这里直接用随机数打破同分，这会让"边缘队晋级概率"这一类预测明显失真。** 我们的 prop 如果涉及"某队能否进淘汰赛"，这块不能省。

**要点 4：Swiss Gambit —— 早期故意输可能有利，但实际影响很小。**
- Cseh, Á., Führlich, P., Lenzner, P. (2023). "The Swiss Gambit." arXiv:2302.10595 [cs.GT]. `[读摘要，含完整 abstract]`
- 结论：故意早输以换取后续弱对手，**理论上可行，但需要极高的赛果可预测性，且即使成功收益也很有限**。方法上他们用**基于 FIDE 官方配对系统的 agent-based 仿真**。
- **对我们的意义**：(a) 不用担心 TI 队伍战术性放水扭曲我们的模型（收益太小、Dota BO3 可预测性远低于象棋）；(b) 但这篇证实了**配对反馈回路是真实且强到能被利用的**，反过来印证了要点 2——不逐轮模拟就会算错。

**其他相关文献**：
- Csató, L. "Most Swiss-system tournaments are unfair." arXiv:2410.19333 `[仅标题]` — 主要讲象棋执白/执黑轮次公平性，**与我们无关**（Dota 无先后手不对称，最多是 BO3 的分边选择）。
- "Multi-Tier Tournaments: Matching and Scoring Players." arXiv:2407.13845 `[仅标题]`
- "Monte-Carlo Simulation of Chess Tournament Classification Systems." *Applied Mathematics* 3(4), 2013. `[仅标题]`
- 可参考的开源实现：`github.com/geckods/chessswissprediction`（Monte Carlo + FIDE 配对 + tiebreak）`[仅标题]` —— 如果我们要抄配对逻辑，这是最省时间的起点。

### 3.3 双败淘汰的模拟要注意什么

- **上路优势必须显式建模**：胜者组决赛的赢家直接进总决赛且享有**盘带优势（bracket reset）**——败者组冠军必须连赢两个 BO5 才夺冠。**如果你的模拟没有实现 bracket reset，上路队伍的夺冠概率会被低估好几个百分点。**（`[读摘要]`）
- **路径长度不对称**：败者组路径更长、场次更多。若模型里有"疲劳"或"状态"项，必须按实际场次而非轮次计。
- **优先用解析递推而非蒙特卡洛**：bracket 固定时，夺冠概率可以从叶到根精确递推，零模拟噪声，且比 20,000 次模拟还快。见 Brandes et al. (2025)。
- **淘汰赛种子来自瑞士轮**，所以瑞士轮的模拟结果必须**逐次**传给淘汰赛（不能先算瑞士轮的期望名次再打淘汰赛——那会丢掉相关性）。**整条链必须在同一个模拟循环内。**

### 3.4 March Madness 预测比赛：胜出方案的共同点

`[读摘要]`，来源为 Kaggle 竞赛复盘与二手总结，非同行评审：
- **胜出的 log loss 量级**：2019 年冠军 **0.41477**，第二 0.42012，第三 0.42698。**前三名差距极小（<0.013）**——这说明在这类问题上，方法之间的真实差距非常小，运气占比很大。
- **共同点 1：梯度提升 + 集成**。GBM 单模型 log loss ~0.409；集成普遍优于单模型。
- **共同点 2：特征工程 > 模型选择**。按赛季按天顺序推进，为每支球队构造截至当日的强度/表现特征。
- **共同点 3：严防未来信息泄漏**。这是时间序列问题，"care must be taken not to let information from the (known) future influence model training"。
- **共同点 4（隐含但重要）**：很多年的冠军其实是**把概率往极端推**赌对了——单赛季 log loss 的方差极大。**这恰恰是我们要避免的**：我们只有一届 TI，不该为了排名去赌极端概率。

**对 TI15 的可用性判断**：
- 蒙特卡洛推名次分布 → **直接可用，且是必需项**。
- 逐轮瑞士轮模拟（含 Buchholz）→ **直接可用，必须自己实现，预计半天到一天工作量**。
- 双败解析递推 → **直接可用**，比模拟更准更快。
- GBM/集成学习那套 March Madness 做法 → **需改造/多半用不上**。NCAA 有几千场赛季内比赛可训练，TI 前的国际赛样本量小两个数量级，GBM 会直接过拟合。**在我们的数据量下，正则化的 BT/logistic 是更诚实的选择。**

---

## 4. 选手个人指标预测

### 4.1 层次贝叶斯 / 部分池化 / 收缩估计

- **Efron, B., Morris, C. (1975). "Data Analysis Using Stein's Estimator and Its Generalizations." *JASA* 70(350), 311-319.** `[读摘要]`
  - 经典中的经典：1970 年 18 名各有 45 次打击的球员，用 James-Stein 收缩预测赛季剩余打击率，**大幅优于各自的样本均值**。
  - **对我们的直接对应**：TI 前每名选手的国际赛样本都很小，"这个选手场均 8.3 杀"的裸样本均值是**噪声主导**的。必须向群体均值（或"同位置选手均值"）收缩。
- Stan / rstanarm 官方案例 "Hierarchical Partial Pooling for Repeated Binary Trials"（Carpenter 等，用的就是 Efron-Morris 那份棒球数据）`[读摘要]` https://mc-stan.org/rstanarm/articles/pooling.html — **这是可以直接照抄的实现模板**。
- PyMC 官方案例 "Hierarchical Partial Pooling" `[仅标题]` https://www.pymc.io/projects/examples/en/latest/case_studies/hierarchical_partial_pooling.html
- "Modeling Player and Team Performance in Basketball." arXiv:2007.10550 `[仅标题]` — 综述性质，讲球员/球队层次建模的现代做法。
- "Limiting the Shrinkage for the Exceptional by Objective Robust Bayesian Analysis: the 'Clemente Problem'." arXiv:2506.10114 `[仅标题]` — **这篇的问题意识对我们特别相关**：James-Stein 会把**真正的异类**（Clemente）过度收缩回均值。我们池子里有 Yatoro / Ame 这种真·离群选手，标准收缩会低估他们。解法是用**重尾先验（t 分布而非正态）**，让极端值不被拉回来。

**建议的层次结构**（三层，直接可实现）：
```
全体职业选手 → 位置（1/2/3/4/5 号位）→ 战队 → 选手
```
位置层是必须的：1 号位和 5 号位的击杀分布完全不是一回事，混在一起池化会两头都错。

**可用性判断：直接可用，且是选手 prop 的地基。** 成本低（Stan/PyMC 半天），收益明确。

### 4.2 极值统计（EVT）—— 阈值型 prop 的正确姿势

**先把问题类型说清楚。** 我们的 prop 是"本届会不会出现一个 26 杀以上的局"。这**不是**"估计某个选手的击杀均值"，而是：

> P( max over 所有 (选手 × 局) 的击杀 ≥ 26 )

这是一个**「大量试验中的最大值/超阈次数」**问题，正确的分解是：

$$P(\text{至少一次} \ge u) = 1 - \prod_i (1 - p_i),\quad p_i = P(X_i \ge u)$$

或等价地把超阈次数建成 Poisson，率 $\lambda = \sum_i p_i$，则 $P(\ge 1) = 1 - e^{-\lambda}$。

**核心洞察（这条最重要）**：TI15 的选手-局数（16 队瑞士轮 BO3 约 100 局 + 淘汰赛，每局 10 名选手 → **量级 1500-2000 个 (选手,局) 观测**）。当 N 这么大时，**答案几乎完全由分布的尾部形状决定，而不是由均值决定**。均值估计错 5% 无所谓；尾部形状错一点，$p_i$ 会差几倍，$\lambda$ 就差几倍。**所以"泊松 vs 负二项"这个选择在这里不是学究问题，它直接决定答案。**（详见 4.3）

**EVT 文献（都是传统体育侧，`[读摘要]` 级别）**：
- Einmahl, J. H. J., Magnus, J. R. "Records in Athletics through Extreme-Value Theory." *JASA* (2008). `[仅标题]` https://research.tilburguniversity.edu/en/publications/records-in-athletics-through-extreme-value-theory/ — 田径世界纪录的"终极极限"估计，是 EVT 用于体育的标杆论文。
- Gomes, D. T., Henriques-Rodrigues, L. (2019). "Swimming performance index based on extreme value theory." *Int. J. Sports Science & Coaching* 14(1). DOI 10.1177/1747954118808068 `[读摘要]` — **方法论最对口的一篇**：用 POT（peaks over threshold）+ 超阈概率构造一个"表现指数"。
- "Extreme Value Theory — Application of the Peaks Over Threshold Method and the Generalized Pareto Distribution to Athletics Decathlon and Heptathlon." Springer (2021), DOI 10.1007/978-981-16-5063-5_75 `[读摘要]` — 明确指出 **POT 比 block maxima 更有效率（用了更多数据）**，以及**阈值 u 的选择是最大难点**（不能太高也不能太低）。
- Smith, R. L. 的 "Extreme Values" 讲义（UNC）`[仅标题]` https://rls.sites.oasis.unc.edu/s834-2023/ExtremeValues.pdf — 若要写方法附录，这是标准教材级参考。

**但我要给一条明确的反对意见：EVT 对我们多数 prop 是过度工程。**
理由：EVT（GPD/GEV）的**存在价值是外推到数据之外**。而我们的情形是——历史职业局的 (选手,局) 击杀观测有**几万到几十万条**，26 杀这个阈值大概在 99.5 分位附近，**历史上已经出现过很多次**。当阈值处**还有几十上百个实际观测**时，直接用**经验频率 + 层次模型平滑**比拟合 GPD 更稳、更少假设、更快。GPD 拟合还会引入"阈值选择"这个新的自由度（也就是新的过拟合来源）。

**EVT 真正该出场的场合**：某个 prop 的阈值**超出历史观测范围**（比如"会不会有人单局 35 杀"而历史最高是 33）。这时经验频率给 0，是错的；只有 GPD 能给出一个有原理的正数。**建议：默认走经验+层次路线，只对"历史近乎从未发生"的 prop 单独拉 GPD 做一次外推。**

**可用性判断：需改造 / 选择性使用。** 不要把 EVT 当成所有阈值题的通用答案。

### 4.3 计数分布：泊松 vs 负二项 —— 文献支持我们的倾向

**结论：文献明确支持负二项，我们的既有倾向是对的。** 而且理由比"泊松低估尾部"更结构化。

- **Reep, C., Pollard, R., Benjamin, B. (1971). "Skill and Chance in Ball Games." *JRSS-A* 134(4), 623-629** 以及后续的 "Goal-Scoring and the Negative Binomial Distribution"（*The Mathematical Gazette*）`[读摘要]` — 足球进球数的经典发现：**观测方差 > 均值（过离散），负二项拟合优于泊松**。这是体育计数数据用 NB 的源头文献。
- 现代综述性表述（`[读摘要]`，来自多篇足球预测论文的共同表述）："Poisson models assume equal mean and variance, which may not hold in real-world football data — especially where overdispersion is observed"；"a common approach is to replace each Poisson marginal with a negative binomial"。
- "Bayesian weighted discrete-time dynamic models for association football prediction." arXiv:2508.05891 `[仅标题]` — 当代 NB 用法示例。
- "Flexible models for overdispersed and underdispersed count data." arXiv:2001.08912 `[仅标题]` — Conway-Maxwell-Poisson 等更灵活的族，**如果 NB 还不够可以看这个，但我不建议在 11 天里走这条路**。
- **反向证据（必须记录）**：Groll et al., "Prediction of the 2019 IHF World Men's Handball Championship — An underdispersed sparse count data regression model." arXiv:1901.05722 `[仅标题]` — 手球进球数是**欠离散（underdispersed）**的。**教训：不要假设，要先在自己的数据上量一遍 Var/Mean。** 对 Dota 击杀我强烈预期过离散（因为局长和"血腥度"波动巨大），但这是一个必须实测的 5 分钟检查。

**为什么 NB 是对的——机制层解释（比引用更有说服力）**：
负二项 = **gamma 混合的泊松**。也就是说，"用 NB" 在数学上**等同于**"承认每一局有一个自己的击杀率 λ_game，而 λ_game 服从 gamma 分布"。而 Dota 的现实就是这样：
- 局长差异巨大（25 分钟速推 vs 60 分钟拉锯）；
- 版本/天梯 meta 决定整体节奏（7.xx 大改会整体抬高或压低击杀）；
- 对局形态（碾压局 vs 拉锯局）决定"血腥度"。

**所以"NB vs Poisson"和"要不要加局级随机效应"是同一件事的两种说法。** 这给了我们一个更好的实现路径：**不要直接套 NB，而是建一个带局级随机效应的层次泊松**，这样你可以把**局长、版本、双方强度差**作为协变量放进去解释掉一部分过离散，剩下的用随机效应吸收。**这比裸 NB 更准，且实现成本几乎一样。**

### 4.4 事件间不独立：beta-binomial / 相关伯努利

- **关键公式（`[读摘要]`，标准结果）**：m 次成对正相关（相关系数 ρ）的伯努利试验，其方差是二项方差的 **(1 + (m-1)ρ)** 倍。**注意 m 是乘在里面的**——试验数越多，同样的小相关造成的方差膨胀越大。这对我们尤其致命：一届 TI 有上千个 (选手,局) 观测，即便 ρ = 0.02 这种"看起来可以忽略"的相关，方差膨胀因子也是 1 + 1500×0.02 = 31 倍。**忽略相关性会让我们的区间窄到荒谬。**
- Beta-binomial = **beta 混合的二项**，是处理这类过离散的标准工具。`[读摘要]` — 参考：JMP 统计知识库条目；"A combined beta and normal random-effects model for repeated, overdispersed binary and binomial data." *J. Multivariate Analysis* (2012)。
- "Beta-binomial/gamma-Poisson regression models for repeated counts with random parameters." arXiv:1003.1325 `[仅标题]` — **把 4.3 和 4.4 统一起来的框架**（beta-binomial 管二值、gamma-Poisson=NB 管计数，同一套随机参数思想）。
- "Accounting for overdispersion and clustering in binomial data from N-of-1 trials." arXiv:2607.08722 `[仅标题]`

**我们数据里的相关性来源（必须显式建模，不能靠 ρ 一个数糊过去）**：
1. **同局同队相关**：一局碾压，赢方五人击杀集体偏高 → 局级随机效应。
2. **同选手跨局相关**：某选手就是打法激进 → 选手级随机效应（这正是 4.1 的层次结构）。
3. **版本相关**：整届 TI 打同一个版本，**所有局共享一个版本效应**。这是最阴的一条——它意味着**一届 TI 内部的观测远没有名义样本量那么多信息**，而且它无法从历史数据中被平均掉。

**可用性判断：直接可用，且第 3 条必须写进模型。** 版本级共同冲击是"本届会不会出现 X"这类 prop 的**主导不确定性来源**，比选手个体差异重要得多。

### 区块 4 推荐架构（一句话）
**带局级 + 选手级 + 版本级随机效应的层次泊松（= 结构化的负二项），位置分层，重尾先验防过度收缩；阈值 prop 用模型的后验预测分布做蒙特卡洛数超阈次数；只有当阈值超出历史观测范围时才额外拉 GPD 外推。**

---

## 5. 评估与陷阱

### 5.1 评分规则：Brier / log loss / RPS

- **Brier, G. W. (1950). "Verification of Forecasts Expressed in Terms of Probability." *Monthly Weather Review* 78(1), 1-3.** `[背景知识]`
- **Constantinou, A. C., Fenton, N. E. (2012). "Solving the Problem of Inadequate Scoring Rules for Assessing Probabilistic Football Forecast Models." *Journal of Quantitative Analysis in Sports* 8(1).** `[读摘要]` — 力推 **RPS**，理由是足球结果是**有序（ordinal）**的（主胜 → 平 → 客胜），Brier 对"预测偏了多远"不敏感。
- **Wheatcroft, E. (2021). "Evaluating probabilistic forecasts of football matches: the case against the ranked probability score." *JQAS*. arXiv:1908.08980, DOI 10.1515/jqas-2019-0089** `[读摘要]` — **明确反驳上一篇**：RPS 的"距离敏感"在实践中不带来有意义的优势。
- Bröcker, J., Smith, L. A. "Reliability, Sufficiency, and the Decomposition of Proper Scores." arXiv:0806.0813 `[仅标题]` — Brier 分解（reliability / resolution / uncertainty）的理论基础。

**给 TI15 的具体建议**：
- **胜负 prop 是二值的，Dota 没有平局，RPS 的整个立论（有序三分类）不适用 → 直接用 Brier + log loss，别纠结 RPS。**
- **名次预测是有序的**（第 1 名 vs 第 16 名），这里 RPS **确实**适用，可以作为"名次分布"预测的评分。但见 5.2——我们根本没有足够样本让这个分数有意义。
- **log loss 对 0/1 附近的自信错误惩罚极重**（预测 0.99 结果错了 → 无穷大附近）。TI 只有一届，一次自信的错就毁掉整个 log loss。**如果我们的目标是"看起来分数好"，就该保守；如果目标是"真的赚钱"，就该报真实信念。这两个目标在小样本下是冲突的，请项目层面先明确要哪个。**

### 5.2 一届 TI 只有一次观测 —— 怎么评估？（这块必须泼冷水）

**硬事实：单届 TI 的赛果无法用来评估模型好坏。** 这不是保守，是数学。

- 冠军预测：1 个观测。任何 log loss / Brier 都是纯噪声。
- 即便算上所有 prop（假设 50 道题），50 个**高度相关**（同一届、同一版本、同一批队伍）的观测，**有效样本量远小于 50**。
- 文献侧的支撑（`[读摘要]`）："all scoring-rule-based approaches are inherently ill-suited for eliciting properties realized only in rare or tail events"；"Assessment based on the expectation of a proper score is not suitable for extremes"，小样本下期望型评估直接失效。
  - 相关文献：Allen, S. et al. "Tail calibration of probabilistic forecasts." arXiv:2407.03167 `[读摘要]`；"Evaluating probabilistic forecasts of extremes using CRPS distributions." *Int. J. Forecasting* (2022) `[仅标题]`；"An Imbalance-Robust Evaluation Framework for Extreme Risk Forecasts." arXiv:2512.00916 `[仅标题]`。

**那该怎么做？三条可执行的替代**：
1. **在历史上做时序留出（walk-forward）评估**：用 TI10-TI14（或所有大赛）做回测，严格按时间切分，只用赛前可得信息。**这是唯一能给出可信精度估计的路径**，必须在开赛前做完。
2. **用赛中的场级结果做在线评估**：TI15 期间会打上百场 BO3，**场级预测有上百个观测，这个是能评估的**。把"每场谁赢"的 Brier 记下来，赛程过半就能知道模型是不是在正常范围（Brier ≈ 0.21-0.24 是健康区间，对应 63-67% 准确率）。**强烈建议把这个做成实时监控。**
3. **对冠军/名次类预测，放弃"评估"，改做"事前健全性检查"**：概率和为 1、和赔率的分歧点是否有可解释的理由、去掉任意单一特征后排序是否稳定。

**避免过拟合的具体纪律**：
- **参数数量上限**：可用的独立观测（近 12 个月国际赛 BO3 数）大概几百到一两千场。**队伍层模型的自由参数不应超过观测数的 1/20**。16 队 + 赛区效应 + 几个协变量 ≈ 25 个参数，对应需要 500 场，勉强够。**再多任何东西都是过拟合。**
- **不要做特征选择**。在这个样本量下，"试了 20 个特征选出最好的 5 个"等于把噪声固化。先验决定特征，然后全部保留 + 正则化。
- **不要调 hyperparameter 到验证集最优**。用先验合理的值（例如 ridge 强度按"等价于给每队加 N 场 50% 战绩"来设）。

### 5.3 「市场赔率作为 benchmark」—— 文献共识与对 TI 的具体判断

**（A）文献共识：赔率非常难打败。** `[读摘要]`，多篇独立来源一致：
- 赔率在预测比赛胜负和进球总数上**优于**基于场均得分、进球、Elo 评级的方法。
- 把包含大量可量化变量的统计模型与赔率对比，**统计模型没能跑赢开盘者**。
  - Forrest, D., Goddard, J., Simmons, R. (2005). "Odds-setters as forecasters: The case of English football." *Int. J. Forecasting* 21(3). `[读摘要]`
- 存在的偏差"rather small and thus hardly provide opportunities to systematically beat the odds"。
- 少数成功案例是**窄口径**的：xG 类模型捕捉到市场未完全反映的信号，ROI ~10%；"both teams to score" 这种特定盘口有机会。
  - 参考：Wilkens, S. (2026). "Can simple models predict football — and beat the odds? Lessons from the German Bundesliga." *Journal of Sports Analytics*. `[仅标题]`
  - Kaunitz, L., Zhong, S., Kreiner, J. (2017). "Beating the bookies with their own numbers." arXiv:1710.02824 `[仅标题]` — 著名案例：用**赔率本身**构造策略盈利，但作者报告**账号被限制/封禁**，即"能赢但赢不了多久"。

**（B）关于「TI 赛前赔率头名只有 1/6 夺冠」—— 我必须明确反对这个推论。**

这个观测**根本不是**赔率校准差的证据。做个二项检验就清楚了（下表是我现算的）：

| 头名真实夺冠概率 p | 6 届期望夺冠次数 | P(6 届中 ≤1 次) |
|---|---|---|
| 0.20 | 1.20 | 0.655 |
| 0.25 | 1.50 | 0.534 |
| 0.30 | 1.80 | 0.420 |
| 0.35 | 2.10 | 0.319 |
| 0.50 | 3.00 | 0.109 |
| 0.60 | 3.60 | **0.041** |

**要让"1/6"在 5% 水平上构成校准失败的证据，头名的真实夺冠概率必须高达 ~60%。** 而在 16 队规模的 Dota 大赛里，**没有任何一支队伍的赛前夺冠概率接近 60%**——历史上最强的赛前热门大概也就 25-30%。在 p=0.25 时，观测到 6 届只赢 1 届的概率是 **53%**，比抛硬币还平常。

**结论：1/6 完全符合校准良好的赔率。用它来论证"赔率不可信"是统计上的错误推论，如果项目基于这个判断去大幅偏离市场，会亏钱。** —— 这是本次调研里我最想让项目组听进去的一条。

**（C）但赔率在 TI 上确实有值得警惕的地方——真正的理由是这三条，不是那个 1/6：**

1. **outright（夺冠盘）的抽水远高于赛果盘。** `[读摘要]` "Futures markets carry higher margins because they involve many possible outcomes and longer timelines"。16 路夺冠盘的 overround 常在 1.20-1.40。**必须先去抽水（normalize / no-vig）再当概率用**，否则你会看到"每支队都被高估"的假象——那是抽水，不是错价。**这是最容易犯、后果最直接的错误。**
2. **Dota 2 的盘口确实在变薄。** `[读摘要]`（行业报告，非学术）：Dota 2 在电竞总投注额中的份额 2025 年降至 **7.7%**（2024 年为 10.5%），CS2 + LoL 占约 84%。薄市场的定价修正更慢、抽水更高。行业侧的说法是"Big Three 大赛决赛的盘口是有效的，小赛事的线才松"——**TI 是最大的 Dota 赛事，恰恰是这个项目里盘口最有效的部分。**
3. **电竞有实证的方向性偏差，且方向和传统体育相反。** `[读摘要]`：CS:GO 投注中发现的是**反向 favourite-longshot bias**（大众过度买入热门），基于"买冷门"的简单策略在样本内外都有显著正收益；且在**有人气冷门**的比赛里，情绪偏差反而**减小**了这种无效性。
   - **可操作含义**：如果这个偏差在 Dota 上也成立，那么**系统性地相对市场调低热门、调高冷门**是有先验支持的方向。**但这条我只读到二手摘要，没有读到原论文正文，且是 CS:GO 不是 Dota，请当作一条待验证的假设而不是结论。**

**（D）最实用的一条：不要"打败"赔率，要"融合"赔率。** `[读摘要]`
文献和实务的共识是**组合优于单一来源**——把去抽水后的市场概率当作一个强先验，把自己的模型当作另一个信息源，做对数几率（log-odds）加权平均。权重给市场 60-80% 是文献支持的量级。**只在模型和市场分歧最大、且分歧有明确可解释原因（例如市场明显没消化某次换人）的几个题上，才允许大幅偏离。**

### 5.4 数据泄漏、幸存者偏差、分布漂移

**（1）数据泄漏 —— 我们最可能栽的地方**
- **时间泄漏**：用 TI 期间或之后的数据训练"预测 TI"的模型。March Madness 复盘明确点名这一条（"care must be taken not to let information from the (known) future influence model training"）。**具体到我们：赛区积分、队伍排名、选手评分这些数据源，很多是"当前值"而非"历史时点值"（point-in-time）。抓 Liquipedia / Dotabuff 的当前评级去回测过去，就是教科书式的泄漏。**
- **特征泄漏**：把游戏内结果类统计（GPM/XPM/击杀）当赛前特征。第 2 区块已经证明这会让准确率虚高到 90%+。
- **赛制泄漏**：模拟里如果用了"实际已经产生的对阵表"，就是泄漏。瑞士轮必须从第 1 轮的真实种子开始模拟。

**（2）幸存者偏差**
- **只用"打进过 TI 的队伍"的历史数据训练**，会系统性高估这批队伍的能力（它们是被选择出来的）。
- **选手侧更严重**：只统计"还在打职业的选手"的数据，会把"表现下滑就退役"这个筛选机制烤进模型，让选手能力看起来比实际稳定。
- **对 prop 尤其致命**：如果只用"名场面/精彩集锦"或高关注度比赛的数据估极值率，会大幅高估 26+ 杀这类事件的频率。**数据必须是全量赛事，不能是被媒体筛过的。**

**（3）分布漂移 —— 对 Dota 而言这是头号风险，不是次要风险**
- **版本（patch）**：TI 通常在一个新版本上打。击杀率、局长、英雄池全变。**用旧版本数据估计的击杀分布，直接套到新版本上是错的，而且错的方向不可预测。**
- **赛制变更**：TI2025 才第一次用瑞士轮，**历史 TI 的名次分布数据在赛制层面不可比**。
- **阵容变动**：赛前转会窗后的阵容和历史数据里的阵容不是同一支队。
- **对策（务实版）**：
  a. 对历史数据做**时间加权**（近 3-6 个月权重高）；
  b. **显式加版本固定效应**，并对 TI15 版本用"最近同版本比赛"重新校准整体水平（这需要 TI 前的赛事在同版本上跑过）；
  c. **对最终概率做主动展宽**：在小样本 + 已知漂移下，模型自信度一定虚高。**把最终概率往均匀分布方向收缩 10-20%（temperature scaling）是几乎无损的保险**，尤其在 log loss 下。

### 区块 5 可用性判断

| 项 | 判断 |
|---|---|
| Brier + log loss 评二值 prop | **直接可用** |
| RPS | **用不上**（Dota 无平局；名次维度样本不够） |
| 单届 TI 结果做模型评估 | **用不上**（数学上不可能） |
| 历史 walk-forward 回测 | **直接可用，必做** |
| 赛中场级 Brier 实时监控 | **直接可用，强烈推荐** |
| 去抽水后的市场概率作先验 | **直接可用，强烈推荐** |
| 「赔率校准差所以要大幅偏离市场」 | **危险，应否决**（见 5.3B） |
| temperature scaling 展宽 | **直接可用，低成本保险** |

---

## 总对比表：方法 × 需要的数据 × 实现成本 × 预期效果

成本单位：**人日**（假设一个熟练实现者）。"预期效果"是我对**在 TI15 这个具体场景下**的边际贡献判断，不是方法本身的学术价值。

### 队伍层（夺冠/名次）

| 方法 | 需要的数据 | 实现成本 | 预期效果 | 判断 |
|---|---|---|---|---|
| **正则化 Bradley-Terry + 赛区效应** | 近 12 月 BO 级赛果 + 赛区标签 | **0.5 日** | **高** — 主力模型，能加协变量、能算标准误 | **必做** |
| Glicko-2（阵容变动时膨胀 RD） | 同上 + 阵容变动日期 | 0.5 日 | 中高 — 提供不确定度，作对照 | 建议做 |
| 简化 TrueSkill（个人 skill 加总） | 需要**选手级**参赛记录 | 2 日 | 中 — 唯一有原理地处理阵容变动；副产品是选手能力 | 时间够才做 |
| 裸 Elo | 赛果 | 0.2 日 | 低 — 无不确定度、跨赛区不可比 | 只作 sanity check |
| TrueSkill2 全套 | 海量个人统计 + 超参拟合 | 5+ 日 | 低（对我们） | **不做** |
| Plackett-Luce 直接建名次 | 历届最终名次 | 1 日 | **负** — 丢弃场级信息 | **不做** |
| 状态空间 / GP 动态评级 | 长历史赛果 | 3+ 日 | 低 — 只需单时点估计 | **不做** |
| GBM / 深度学习赛前模型 | 需要几千场同分布数据 | 2 日 | **负** — 样本量不足，必过拟合 | **不做** |
| **去抽水后的市场概率作先验** | outright 赔率快照 | **0.3 日** | **最高性价比** | **必做** |

### 赛制模拟

| 方法 | 需要的数据 | 实现成本 | 预期效果 | 判断 |
|---|---|---|---|---|
| **逐轮瑞士轮蒙特卡洛（含 Buchholz）** | 配对规则 + 初始种子 + p(i>j) | **1 日** | **高** — 无替代方案；近似法会系统性出错 | **必做** |
| 双败淘汰**解析递推**（含 bracket reset） | bracket 结构 + p(i>j) | 0.5 日 | 高 — 比模拟更准更快 | **必做** |
| 二项近似代替瑞士轮模拟 | — | 0.1 日 | **负** — 高估强队高战绩概率 | **不做** |
| BO3/BO5 折算 | 明确数据粒度（局 or 系列） | 0.1 日 | 高 — 但要小心不要双重折算 | 必做 |

### 选手个人 prop

| 方法 | 需要的数据 | 实现成本 | 预期效果 | 判断 |
|---|---|---|---|---|
| **层次泊松 + 局/选手/版本随机效应**（= 结构化 NB） | 全量职业局的 (选手,局) 计数 + 局长 + 版本 | **1.5 日** | **高** — 尾部题的地基 | **必做** |
| 位置分层（1-5 号位） | 选手位置标注 | 0.2 日 | 高 — 不分层两头都错 | **必做** |
| 重尾（t）先验防过度收缩 | — | 0.1 日 | 中高 — 保住真·离群选手 | 建议做 |
| 后验预测 + 蒙特卡洛数超阈次数 | 上面的模型 + TI15 预计局数 | 0.3 日 | 高 — 阈值题的正确算法 | **必做** |
| 裸负二项（无协变量） | 计数数据 | 0.3 日 | 中 — 比泊松好，但不如层次版 | 作退路 |
| 裸泊松 | 计数数据 | 0.1 日 | **负** — 系统性低估尾部，1500 次抽样下误差被放大 | **不做** |
| beta-binomial（二值型 prop） | 二值事件记录 | 0.5 日 | 中高 — 命中率类 prop 用 | 视 prop 类型 |
| **GPD / POT 外推** | 阈值附近的历史观测 | 1.5 日 | 低（多数题）/ **不可替代**（阈值超出历史范围的题） | **选择性使用** |
| 选手样本均值直接外推 | 计数数据 | 0.1 日 | **负** — 小样本噪声主导 | **不做** |

### 评估

| 方法 | 需要的数据 | 实现成本 | 预期效果 | 判断 |
|---|---|---|---|---|
| **历史 walk-forward 回测**（严格 PIT） | 有时点标记的历史数据 | **1.5 日** | **最高** — 唯一可信的精度来源 | **必做** |
| 赛中场级 Brier 实时监控 | TI15 期间赛果 | 0.3 日 | 高 — 唯一能在赛期内验证模型的东西 | **强烈推荐** |
| temperature scaling 展宽 | 回测集 | 0.2 日 | 中高 — 低成本保险 | 建议做 |
| Brier / log loss（二值 prop） | — | 0.1 日 | 标配 | 必做 |
| RPS | — | 0.3 日 | **低** — Dota 无平局；名次样本不足 | **不做** |
| 用单届 TI 结果评估模型 | — | — | **无意义** | **不做** |

---

## 一句话总纲

**队伍层：正则化 BT + Glicko-2 不确定度 → 与去抽水的市场概率做 log-odds 融合（市场权重 60-80%）→ 逐轮瑞士轮蒙特卡洛 + 双败解析递推 → 名次分布。**
**选手层：带局/选手/版本随机效应的层次泊松 + 位置分层 + 重尾先验 → 后验预测蒙特卡洛数超阈 → 阈值 prop 概率。**
**评估：历史 walk-forward 定精度，赛中场级 Brier 做监控，最终概率统一做温度展宽。**
**别做：深度学习、GBM、Plackett-Luce 建名次、状态空间评级、裸泊松、以及基于「1/6 夺冠」去大幅偏离市场。**

