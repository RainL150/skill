# Skill Case Format

`scripts/run_case_replay.py` 支持 JSON 数组或 JSONL。它做确定性元数据检查，不调用模型。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | yes | case ID，稳定、唯一 |
| `prompt` | yes | 用户原始请求 |
| `expect` | yes | `trigger` 或 `no-trigger` |
| `trigger_terms` | no | 对 `trigger` case，至少一个 term 应该出现在 skill metadata 中 |
| `avoid_terms` | no | 对 `no-trigger` case，这些 term 不应出现在 skill metadata 中 |
| `notes` | no | 人类说明，不参与判定 |

## JSON 示例

```json
[
  {
    "id": "skill-new-001",
    "prompt": "帮我创建一个分析 PDF 发票的 skill",
    "expect": "trigger",
    "trigger_terms": ["创建", "skill", "生成"]
  },
  {
    "id": "project-analysis-001",
    "prompt": "分析这个开源项目的架构",
    "expect": "no-trigger",
    "avoid_terms": ["开源项目", "架构分析"]
  }
]
```

## JSONL 示例

```jsonl
{"id":"miss-001","prompt":"这个 skill 老是误触发，帮我调一下","expect":"trigger","trigger_terms":["误触发","调整"]}
{"id":"normal-code-review","prompt":"review 这个 PR","expect":"no-trigger","avoid_terms":["PR review"]}
```

## 使用建议

- 每个新增触发场景至少 2 个 trigger case。
- 每个相邻 skill 至少 1 个 no-trigger case。
- 从真实失败 prompt 提取 case，不要只写理想化 prompt。
- `trigger_terms` 不是用户 prompt 里的关键词，而是你希望 frontmatter 覆盖的路由概念。
- 脚本通过不代表模型一定触发，只说明 metadata 没有明显缺口。
