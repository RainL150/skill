# Claude Code Skills

Personal collection of Claude Code skills.

## project-analyzer (v5)

深度拆解开源项目的分析工具。

**功能**：能力清单、核心机制、设计权衡、使用陷阱分析，输出"能帮我做什么"+"怎么做到的"+"什么情况会出问题"，附带成熟度评分。

**适用场景**：学习开源项目、技术选型、竞品分析。

### 安装

```bash
# 复制到你的项目
cp -r project-analyzer /path/to/your-project/.claude/skills/
```

### 使用

在 Claude Code 中调用：
```
/project-analyzer <项目路径或 GitHub URL>
```
