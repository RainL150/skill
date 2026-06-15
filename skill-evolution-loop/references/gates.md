# Skill Evolution Gates

用这些 gates 约束 skill 的生成与调整。每次改动前先选 gates，改动后逐条给证据。

## Gate A: Routing

| 检查 | 通过标准 | 证据 |
|---|---|---|
| 必触发场景 | 每个目标场景至少有一个 case | `cases.json` |
| 不触发场景 | 相邻 skill/普通任务有 no-trigger case | `cases.json` |
| Description 精度 | description 说明“做什么”和“什么时候用” | `SKILL.md` frontmatter |
| 触发词不过宽 | 避免“分析”“帮我看看”等单独泛词 | frontmatter review |

## Gate B: Structure

| 检查 | 通过标准 |
|---|---|
| `SKILL.md` 存在 | 必须存在且非空 |
| frontmatter | 至少有 `name` 和 `description` |
| 命名 | skill 目录名与 `name` 一致，使用 lowercase hyphen |
| 主体长度 | 默认小于 500 行；超过则必须解释 |
| Progressive disclosure | 细节、模板、长案例拆到 `references/` 或 `scripts/` |
| 引用路径 | Markdown 相对链接全部存在 |

## Gate C: Behavior Contract

| 检查 | 通过标准 |
|---|---|
| 第一动作 | 明确触发后第一步读什么/问什么/做什么 |
| 输出格式 | 给出默认输出结构或交付物要求 |
| 验证方式 | 写明如何验证结果，不只靠主观判断 |
| 失败处理 | 明确何时停下、何时问用户、何时降级 |
| 安全边界 | 覆盖覆盖文件、联网、凭证、破坏性操作等风险 |

## Gate D: Resource Integrity

| 检查 | 通过标准 |
|---|---|
| `references/` | 被 `SKILL.md` 提到的文件必须存在 |
| `scripts/` | 脚本能通过基本语法检查 |
| `agents/openai.yaml` | UI 描述和默认 prompt 与 skill 一致 |
| 无噪音文档 | 不添加不会被 agent 使用的 README/CHANGELOG/安装说明 |

## Gate E: Regression

| 检查 | 通过标准 |
|---|---|
| 原通过 case | 调整后仍通过 |
| 原 no-trigger case | 调整后仍不应触发 |
| 旧输出合同 | 除非 gate 明确改变，否则保持兼容 |
| 上下文成本 | 新增内容有明确价值，避免把长细节塞进主文件 |

## 推荐 Gate 文件模板

```markdown
# Gate: <skill-name> <change-name>

## Objective

[这次要改善什么，为什么]

## In Scope

- [允许修改的文件/能力]

## Out of Scope

- [明确不做的事]

## Acceptance Gates

| Gate | Command / Evidence | Threshold |
|---|---|---|
| Structure | `python scripts/validate_skill.py <skill>` | 0 errors |
| Routing cases | `python scripts/run_case_replay.py <skill> <cases>` | all pass |
| Review | human/agent review table | no P0/P1 issue |

## Cases

- [case file path]

## Freeze Note

This gate was written before editing the candidate skill.
```
