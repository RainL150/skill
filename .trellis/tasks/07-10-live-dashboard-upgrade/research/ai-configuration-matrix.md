# Vibe AI 配置对照矩阵

对照基线（2026-07-10）：

- `/Users/rainless/Desktop/project/Vibe-Research/frontend/src/lib/ai-models.ts`
- `/Users/rainless/Desktop/project/Vibe-Research/frontend/src/lib/llm.ts`
- `/Users/rainless/Desktop/project/Vibe-Research/backend/cli_runtime.py`
- `/Users/rainless/Desktop/project/Vibe-Research/backend/chat.py`

这些绝对路径只用于规划和开发对照，不能成为 STJ 运行时依赖。

## 1. API presets

| provider | model id | 展示名 | 默认 Base URL | 备注 |
| --- | --- | --- | --- | --- |
| `deepseek` | `deepseek-v4-flash` | DeepSeek V4 Flash | `https://api.deepseek.com` | 官方，Base URL 解析时补 `/v1` |
| `deepseek` | `deepseek-v4-pro` | DeepSeek V4 Pro | `https://api.deepseek.com` | 同上 |
| `silicon` | `deepseek-ai/DeepSeek-V3` | SiliconFlow · DeepSeek V3 | `https://api.siliconflow.cn/v1` | 硅基流动 |
| `openai` | `gpt-4o` | OpenAI GPT-4o | `https://api.openai.com/v1` | OpenAI-compatible |
| `minimax` | `MiniMax-M2` | MiniMax M2 | `https://api.minimaxi.com/v1` | MiniMax |
| `openai-compatible` | `doubao-pro` | 豆包 Pro | 用户填写 | model 输入实际 `ep-…` 接入点 ID |
| `openrouter` | `openai/gpt-4o` | OpenRouter · GPT-4o | `https://openrouter.ai/api/v1` | model 可改 |
| `groq` | `llama-3.3-70b-versatile` | Groq · Llama 3.3 70B | `https://api.groq.com/openai/v1` | Groq |
| `together` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Together · Llama 3.3 70B | `https://api.together.xyz/v1` | Together AI |
| `mimo` | `mimo-v2.5-pro` | MiMo V2.5 Pro | 用户填写 | 私有网关 |
| `openai-compatible` | `custom` | 其它 OpenAI 兼容 | 用户填写 | Base URL 与 model 均可编辑 |

实现要求：预设是可编辑默认值，不是硬编码锁定；配置保存 `provider/baseURL/model/apiKey`。Base URL 若未以 `/v1`、`/v3` 或 `/api/v3` 结尾，兼容层默认补 `/v1`，但必须用 provider fixture 验证重写结果。

## 2. Subscription CLI presets

| provider | model id | binary candidates | Vibe delivery / args | STJ 状态 |
| --- | --- | --- | --- | --- |
| `cli-claude` | `claude-code` | `claude`, `openclaude` | system prompt 临时文件；user stdin；`-p --output-format text --system-prompt-file ...` 并禁 Read/Write/Edit/Glob/Grep/Bash/Notebook/Web/Task 等工具 | 可用，保留 no-tool 约束 |
| `cli-qwen` | `qwen-code` | `qwen` | 合并 prompt 走 stdin；Vibe 使用 `--yolo` | 可用前必须验证当前版本的 no-tool/只读隔离；不能盲抄高权限参数 |
| `cli-deepseek` | `deepseek-cli` | `deepseek`, `codewhale` | 合并 prompt 作为位置参数；`exec --auto`；Vibe 限 110,000 bytes | 可用，但 UI/文档提示 prompt 会短暂出现在本机进程参数；优先探测安全 stdin/no-tool 方式 |
| `cli-codex` | `codex` | `codex` | 合并 prompt 走 stdin；`exec --skip-git-repo-check -` | 可用，在空临时目录并使用最小权限 |
| `cli-opencode` | `opencode` | 未实现 | 无 | 即将支持，不可选 |
| `cli-cursor` | `cursor-agent` | 未实现 | 无 | 即将支持，不可选 |
| `cli-kimi` | `kimi` | 未实现 | 无 | 即将支持，不可选 |

所有 CLI 都在空临时目录运行、300 秒硬超时、客户端中止后清理子进程。STJ 要忠实保留模型选择与登录态复用，但不得把 Vibe 中潜在的自动工具权限原样带入；若某 CLI 版本无法实现 no-tool/隔离，该 capability 必须显示风险或不可用，不能声称满足只读约束。

## 3. Vibe runtime behavior to preserve

- Vibe 浏览器只持久化一份 `vr-llm`；STJ 使用独立、版本化的 `stj.ai.config.v1`，仍保持“一次一个当前配置”。
- CLI 只需 model/provider，不需要 API Key；API 需要 Base URL、model 和 key。
- `/api/chat` 使用 NDJSON；浏览器用 AbortController 取消旧请求。
- API 使用 OpenAI-compatible streaming + function calling；最大 6 个工具轮次。
- Vibe 单次工具结果注入模型最多 6,000 字符；STJ 保留该默认上限，并额外限制返回条数与内部 payload。
- Vibe CLI 没有 function calling；页面数据必须先进入 context。
- Vibe 公网姿态由 `VR_API_KEY` 推导；STJ 更名为 `STJ_API_KEY`，默认 loopback，非 loopback 必须鉴权。
- Vibe system prompt 要求客观、双面、不编数字；STJ 在此基础上加入来源、反证/风险和交易纪律，不给 AI 自动交易权限。

## 4. Data tools: Vibe baseline and STJ extension

Vibe 原始 5 个工具：

1. `query_quote`：A 股批量行情。
2. `query_valuation`：A 股行情、预期 EPS 与前向估值。
3. `query_reports`：A 股近期研报。
4. `query_news`：A 股近期新闻。
5. `query_global_stock`：港美（以及 Vibe 中韩股）行情与关键财务。

STJ 不照搬市场割裂的工具名，而是在同一数据 service 上扩展为跨市场、只读的 portfolio/symbol/quote/profile/valuation/financials/news/reports/sector 工具。功能覆盖不得低于上述 5 个工具，具体清单见 `implementation-boundaries.md`。
