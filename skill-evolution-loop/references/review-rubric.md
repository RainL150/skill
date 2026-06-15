# Skill Review Rubric

用这个 rubric 做独立评审。评审者不要只看“写得像不像”，要看证据能否支撑合入。

## 评级

| 评级 | 含义 |
|---|---|
| ACCEPT | gates 通过，风险可接受 |
| ACCEPT_WITH_NOTES | 可合入，但需记录低风险事项 |
| REVISE | 有明确问题，修改后再评 |
| SPLIT | 改动过大，应拆成多个 skill 或多个 slice |
| REJECT | 方向错误或引入高风险误触发 |

## P0 / P1 / P2

| 优先级 | 定义 | 示例 |
|---|---|---|
| P0 | 会让 skill 不可加载或明显错误触发 | frontmatter 缺 name，引用核心文件不存在 |
| P1 | 会显著影响使用可靠性 | description 过宽、没有 no-trigger case |
| P2 | 可后续改善 | 输出格式不够优雅、case 数量偏少 |

## 检查清单

### Routing

- description 是否能让模型在正确场景触发？
- 是否包含用户真实会说的话，而不是只包含作者术语？
- 是否会抢走相邻 skill 的任务？
- 是否明确不适用场景？

### Context Design

- `SKILL.md` 是否只放核心流程？
- 长表格、样例、模板是否拆到 `references/`？
- 可执行、重复性强的逻辑是否放到 `scripts/`？
- 引用文件是否一层可达，避免深层追引用？

### Workflow

- 触发后第一步是否明确？
- 是否要求先读证据再判断？
- 是否有验收/验证方法？
- 是否有失败/阻塞处理？

### Maintainability

- 文件命名是否稳定？
- 脚本是否无外部依赖或清楚声明依赖？
- 是否避免写死本机路径、密钥、账号？
- 是否能从 case 和 gates 看懂为什么这么设计？

## Review Output

```markdown
## Verdict

ACCEPT / ACCEPT_WITH_NOTES / REVISE / SPLIT / REJECT

## Findings

| Priority | Finding | Evidence | Required Change |
|---|---|---|---|

## Gate Evidence

| Gate | Result | Evidence |
|---|---|---|

## Residual Risk

[仍未被测试覆盖的地方]
```
