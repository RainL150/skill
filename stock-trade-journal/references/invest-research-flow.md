# STJ 内置投研分析流程

用于 `/stj 分析 <标的>`、`/stj 看看 <标的>`、`买不买/持有吗` 等直接分析请求。

组合级请求（例如“分析我的持仓”“持仓盈利”“分析持仓还有关注”“给我操作推荐”）优先读取并执行：

```text
references/portfolio-watch-analysis-flow.md
```

该流程会同时读取持仓、关注列表、最近交易、行情口径，并按用户指定或当前适用的交易 profile 做复盘约束；不要退回到提示词或图表报告。

本目录已经内置 `invest-research-skills` 的运行时材料，位置为：

- `references/invest-research-skills/SKILL.md`
- `references/invest-research-skills/stock-fundamental/SKILL.md`
- `references/invest-research-skills/stock-fundamental/references/*.md`
- `references/invest-research-skills/sector-research/SKILL.md`
- `references/invest-research-skills/sector-research/references/*.md`
- `references/invest-research-skills/shared-research-context/SKILL.md`
- `references/invest-research-skills/shared-research-context/references/*.md`
- `references/invest-research-skills/research-review/SKILL.md`

不要再依赖外部 `invest-research-skills` 是否安装；本 skill 自带分析框架。

## 第一层：STJ 本地上下文

直接分析前必须先读取本地上下文：

```bash
cd ~/.claude/skills/stock-trade-journal/scripts
python3 analyze_holdings.py context <代码或名称> --json
```

上下文里的 `mode` 决定输出目标：

| mode | 场景 | 主要问题 |
|---|---|---|
| `holding` | 当前持仓 | 继续持有、加仓、减仓、止损/失效、跟踪指标 |
| `watch_candidate` | 关注标的但无持仓 | 是否值得新开仓买入、买入触发条件、仓位计划、失效条件 |
| `unknown` | 本地无记录 | 普通标的研究，不引用个人仓位 |

交易和关注上下文只使用人工笔记、价格、数量、成本和时间；忽略 `source_pdf`、`account`、`settlement`、`IBKR PDF import` 等导入元数据。

如用户要求组合级复盘，还必须读取：

```bash
python3 query_positions.py
python3 watchlist.py ls
```

并按 `references/portfolio-watch-analysis-flow.md` 的规则选择并加载 `profiles/*.md` 作为外部复盘约束。Profile 不固定，不要在主流程中写死某个画像；若交易记录没有写入所选 profile 要求的字段，必须说明缺少哪些字段，不要替用户编造。

## 第二层：内部投研框架加载规则

### 个股分析，默认必须加载

适用于所有具体股票/公司：

1. `references/invest-research-skills/stock-fundamental/SKILL.md`
2. `references/invest-research-skills/shared-research-context/references/research-methodology.md`
3. `references/invest-research-skills/shared-research-context/references/data-quality-levels.md`
4. `references/invest-research-skills/stock-fundamental/references/business-model-types.md`
5. `references/invest-research-skills/stock-fundamental/references/financial-diagnostics.md`
6. `references/invest-research-skills/stock-fundamental/references/competitor-matrix.md`
7. `references/invest-research-skills/stock-fundamental/references/profit-transmission.md`

分析必须覆盖：

- 公司靠什么赚钱，收入和利润的主要来源是什么。
- 增长来自量、价、份额、产品结构、广告变现、订阅、交易抽成、授权，还是并表。
- 主要竞争对手是谁，相对优势是公司特有还是行业红利。
- 财务质量是否验证业务判断：收入、毛利、费用率、利润、经营现金流、自由现金流、一次性项目。
- 外部变量如何传导到利润：利率、广告周期、政策监管、汇率、AI/搜索流量、商品价格、需求周期等。
- 失效条件必须是可观察信号。

### 行业显著影响结论时加载

如果行业景气、政策、周期、技术路线、竞争格局会明显改变个股结论，加载：

1. `references/invest-research-skills/sector-research/SKILL.md`
2. `references/invest-research-skills/sector-research/references/stage-analysis.md`
3. `references/invest-research-skills/sector-research/references/data-sources.md`
4. `references/invest-research-skills/sector-research/references/valuation-multiples.md`
5. 对应行业 reference：
   - 互联网平台：`sector-other-internet-platforms.md`
   - 游戏：`sector-other-gaming.md`
   - 软件/SaaS：`sector-tech-software-saas.md`
   - 银行/券商/保险：对应 `sector-financial-*.md`
   - 新能源、周期、消费、医药、半导体：按文件名选择对应 reference

行业分析只补足影响个股判断的部分，不要把单股分析膨胀成完整行业报告。

### 护城河、生命周期、外部变量按需加载

当结论涉及竞争壁垒、生命周期或宏观/外部变量时加载：

- `references/invest-research-skills/shared-research-context/references/moat-framework.md`
- `references/invest-research-skills/shared-research-context/references/lifecycle-framework.md`
- `references/invest-research-skills/shared-research-context/references/external-factors.md`
- `references/invest-research-skills/shared-research-context/references/time-consistency.md`
- `references/invest-research-skills/shared-research-context/references/pitfalls.md`

### 需要复核已有分析时加载

当用户要求“复核、挑错、这份分析靠谱吗、上面结论有没有问题”时加载：

- `references/invest-research-skills/research-review/SKILL.md`
- `references/invest-research-skills/research-review/references/review-checklist.md`

## 第三层：实时数据要求

直接分析必须获取最新数据；不要只用训练知识或本地旧价格。

优先级：

1. 公司官方 IR、财报、业绩公告、电话会材料。
2. SEC/交易所公告。
3. 东方财富等行情/财务数据库。
4. 可信财经新闻和分析师一致预期。

必须带时间口径，例如 `2026Q1`、`2025 全年`、`截至 2026-06-12`。若无法确认最新数据，要明确说明数据边界。

行情价格必须保持口径一致：

- A 股、港股、常见美股优先使用东方财富 push2 行情接口或同等可核验行情库。
- 东方财富取不到的 ETF/商品类标的，使用发行方、Yahoo Finance、交易所或可信报价页，并说明收盘日。
- 原币种盈亏和人民币等值权重必须分开；汇率只用于粗估组合权重。
- 不要把不同网页片段拼成“精确实时价”；如果报价时间不同，必须明示。

## 第四层：输出规则

### 输出顺序

1. **结论**：一句话给动作判断，并说明是持仓处理、买入候选还是普通研究。
2. **关键依据**：3-5 条，每条必须是“数据/事实 -> 推论”。
3. **交易/持仓处理**：结合本地成本、关注记录、交易记录给条件。
4. **失效条件**：哪些数据或价格行为出现时要重审。
5. **跟踪清单**：3-5 个后续跟踪指标。

组合级输出按 `references/portfolio-watch-analysis-flow.md`：先给数据口径和盈亏表，再给集中度/相关性风险、持仓动作、关注候选和需要补齐的画像字段。

### 持仓场景

必须结合：

- 持仓数量、均价、成本、买入日期。
- 当前价格和相对成本的浮盈/浮亏。
- 最近交易记录和人工笔记。

回答重点：

- 是否继续持有。
- 是否加仓或减仓。
- 成本线、止损线或重审线。
- 哪些基本面/价格信号会推翻结论。

### 关注标的场景

必须结合：

- 关注记录里的买入观察、触发条件、目标价/止损价。
- 当前价格和最近趋势。

回答重点：

- 现在能不能买。
- 如果不能买，差哪些确认信号。
- 买入触发条件、分批方式、失效条件。

### 禁止事项

- 不要只输出提示词；用户说“分析/看看/买不买/持有吗”时必须直接给分析结论。
- 不要机械套标题。框架是检查清单，不是输出模板。
- 不要输出无数据支撑的“基本面良好、竞争力强、估值合理”。
- 不要把行业判断、宏观判断、市场热点混进个股结论而不说明传导链。
- 不要把导入来源信息当作投资笔记。
