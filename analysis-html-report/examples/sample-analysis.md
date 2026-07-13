# 示例分析报告

> 分析时间：2026-07-14；分析框架：analysis-html-report smoke test

项目分析：这个示例用来验证 Markdown 能被渲染成 project-analyzer 同款 HTML；重点检查目录、表格、引用块、线框图和 Mermaid 兜底是否工作。

## 结论

这个 skill 的职责很窄：把已经完成的分析结果装进一张可分享、可打印的 HTML 页面。它不重新做研究，只保证输出形式稳定、漂亮，并复用 project-analyzer 的渲染器。

## 能力清单

| 能力 | 说明 |
|---|---|
| Markdown 优先 | 保留一份可审阅的源报告 |
| HTML 渲染 | 调用 project-analyzer 的 `md2html.py` |
| 结构验证 | 检查 TOC、内联样式和运行时依赖 |

## 数据流

```
Markdown 分析稿
      |
      v
render_analysis_html.py
      |
      v
project-analyzer md2html.py
      |
      v
self-contained HTML
```

## Mermaid 示例

```mermaid
flowchart LR
  A[分析结果] --> B[Markdown]
  B --> C[HTML]
  C --> D[验证]
```

## 使用限制

- 它不是投研、项目分析或代码审查 skill。
- Mermaid 需要构建期渲染；失败时保留源码块。
- HTML 内容必须来自同一份 Markdown，避免两份结果不一致。
