---
name: skill-evolution-loop
description: 复刻 architect-loop 的冻结 gates、repo memory、隔离候选版本、case replay、独立评审机制，用于分析、生成、调整和验收 Codex/Claude skills。适用于创建新 skill、优化 SKILL.md、诊断误触发/漏触发、设计 skill 评估用例、审查 skill 质量、把一次性提示沉淀成可维护 skill、或要求“复刻机制去分析 skill 的生成和调整”的场景。
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Task
metadata:
  author: rainless
  version: "1.0"
---

# Skill Evolution Loop

用一套可审计的循环来生成、调整、验证 skill。核心原则：**先冻结验收标准，再改 skill；候选版本隔离；生成者只提交证据，评审者决定是否合入**。

## 什么时候用

- 用户要创建一个新 skill，且希望它可维护、可验证。
- 用户要优化已有 `SKILL.md` 的触发、结构、引用文件或脚本。
- 用户遇到 skill 误触发、漏触发、上下文过胖、输出不稳定。
- 用户想给 skill 加评估 case、质量门槛、发布前校验。
- 用户明确提到 skill 生成、skill 调整、skill 进化、skill 评估、复刻 architect-loop 机制。

不适用：普通代码审查、普通项目分析、一次性提示润色。除非用户想把它沉淀成 skill。

## 工作流

### Phase 0: Ground

先读当前 skill 或目标仓库，不要凭空设计：

1. 找到目标 skill 目录和 `SKILL.md`。
2. 读取 frontmatter、主体结构、引用文件、脚本、测试/样例。
3. 确认用户目标：新建、修复、重构、增强评估，还是审查。
4. 如果已有失败样例，保留原始 prompt、实际行为、期望行为。

> 证据优先。没有 case 的“感觉不好用”只能作为假设，不能直接当结论。

### Phase 1: Freeze Gates

改动前先写验收门槛。若目标仓库已有 `docs/gates/`，写入：

```text
docs/gates/<skill-name>-<change>.md
```

否则在回复中明确列出 gates，或创建候选目录内的 `gates.md`。Gate 至少覆盖：

- 路由：哪些请求必须触发，哪些请求不得触发。
- 结构：`SKILL.md` 是否保持精简，细节是否拆到 `references/`。
- 资源：引用文件、脚本、模板是否存在且路径正确。
- 行为：输出格式、验证步骤、安全边界是否明确。
- 回归：原来通过的 case 不应被破坏。

详细 gate 模板见 `references/gates.md`。

### Phase 2: Build Candidate

新建或调整 skill 时优先产出候选版本，不要直接覆盖稳定版本：

```text
candidates/<skill-name>-vN/
```

如果用户明确要求直接实现到目标目录，可以直接改，但仍要保留 diff 和验证结果。

候选内容建议：

```text
<skill-name>/
├── SKILL.md
├── references/
│   ├── gates.md
│   ├── case-format.md
│   └── review-rubric.md
├── scripts/
│   ├── validate_skill.py
│   └── run_case_replay.py
└── agents/
    └── openai.yaml
```

只放会被 agent 使用的文件。不要为 skill 包添加普通 README、安装手册、变更日志，除非用户明确要求。

### Phase 3: Validate

优先跑确定性检查：

```bash
python scripts/validate_skill.py path/to/skill
python scripts/run_case_replay.py path/to/skill path/to/cases.json
```

第一个脚本检查 skill 包结构、frontmatter、引用文件、代码块、脚本语法、`agents/openai.yaml`。第二个脚本用 JSON/JSONL case 检查触发元数据覆盖和误触发风险。case 格式见 `references/case-format.md`。

> 这些脚本不能证明模型一定会按预期行动，只能证明“包结构和触发元数据没有明显问题”。复杂 skill 还需要人工或子代理做真实任务 forward-test。

### Phase 4: Review

生成者不要自己宣布“更好了”。提交评审包：

- 改动摘要：改了哪些文件，为什么。
- Gate 结果：逐条 PASS / FAIL / NOT MEASURED。
- Case replay 表：每个 case 是否覆盖。
- 风险：可能误触发、上下文成本、依赖工具、不可验证项。
- 建议：接受、退回、拆小、继续补 case。

评审 rubric 见 `references/review-rubric.md`。

### Phase 5: Integrate

只有当 gates 有证据支撑时才合入稳定目录。合入后：

1. 删除临时候选目录或保留在用户指定位置。
2. 更新相关 case。
3. 记录关键决策到目标仓库的 handoff/memory 文件；如果没有，就在最终回复里写清楚。
4. 提醒用户下一步应该用真实任务再跑一次 forward-test。

## 常用判断

| 症状 | 可能原因 | 处理方式 |
|---|---|---|
| skill 经常误触发 | description 太宽、触发词泛化 | 收紧 description，增加 no-trigger case |
| skill 漏触发 | description 未覆盖用户真实说法 | 从失败 prompt 提取触发模式 |
| `SKILL.md` 很长 | 细节塞进主文件 | 拆到 `references/`，主文件只保留路由和流程 |
| agent 不知道先做什么 | 工作流缺入口步骤 | 在 Phase 0 写明确第一步 |
| 每次输出格式漂移 | 缺少输出 contract | 写 gates 和模板 |
| 脚本总被重写 | 可重复逻辑未固化 | 放进 `scripts/` 并在 SKILL.md 引用 |

## 输出格式

默认输出：

```markdown
## Skill Evolution 结论

[一句话判断：新建/调整/审查是否可接受]

## Gates

| Gate | 结果 | 证据 |
|---|---|---|

## 改动

| 文件 | 变化 | 原因 |
|---|---|---|

## 风险

[剩余风险和不可验证项]

## Next Action

[一个具体下一步]
```

若用户要求直接实现，完成实现、验证、提交证据，再给简短总结。
