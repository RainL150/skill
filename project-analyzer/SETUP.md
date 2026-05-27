# 启动指南模板 (`/project-analyzer setup`)

**目的：** 把项目跑起来

**触发词：** `setup`, `启动指南`, `怎么跑起来`

---

## 输出模板

```markdown
# [项目名] 启动指南

> 分析框架: project-analyzer v6
> 分析时间: [日期]

---

## 环境要求

### 必需

| 依赖 | 版本要求 | 检查命令 | 安装指南 |
|------|----------|----------|----------|
| Node.js | >= 18.0 | `node -v` | [nodejs.org](https://nodejs.org) |
| pnpm | >= 8.0 | `pnpm -v` | `npm install -g pnpm` |
| Git | >= 2.0 | `git --version` | 系统自带或 brew install git |

### 可选

| 依赖 | 用途 | 版本要求 | 检查命令 |
|------|------|----------|----------|
| Docker | 容器化运行 | >= 20.0 | `docker -v` |
| PostgreSQL | 数据库 | >= 14.0 | `psql --version` |
| Redis | 缓存 | >= 6.0 | `redis-cli --version` |

---

## 快速启动

### 方式 1: 本地开发

```bash
# 1. 克隆项目
git clone https://github.com/[owner]/[repo].git
cd [repo]

# 2. 安装依赖
pnpm install

# 3. 复制环境配置
cp .env.example .env

# 4. 编辑 .env 文件
# 填入必要的配置项（见下方配置说明）

# 5. 初始化数据库（如需要）
pnpm db:migrate

# 6. 启动开发服务器
pnpm dev
```

### 方式 2: Docker Compose

```bash
# 1. 克隆项目
git clone https://github.com/[owner]/[repo].git
cd [repo]

# 2. 复制环境配置
cp .env.example .env

# 3. 启动所有服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

### 方式 3: 一键脚本（如果有）

```bash
# 下载并运行安装脚本
curl -fsSL https://[domain]/install.sh | bash
```

---

## 配置说明

### 必填配置

| 环境变量 | 说明 | 示例值 | 获取方式 |
|----------|------|--------|----------|
| `DATABASE_URL` | 数据库连接字符串 | `postgres://user:pass@localhost:5432/db` | 本地数据库或云服务 |
| `API_KEY` | API 密钥 | `sk-xxx...` | 从服务商获取 |
| `SECRET_KEY` | 加密密钥 | `random-32-char-string` | `openssl rand -hex 16` |

### 可选配置

| 环境变量 | 说明 | 默认值 | 示例值 |
|----------|------|--------|--------|
| `PORT` | 服务端口 | `3000` | `8080` |
| `LOG_LEVEL` | 日志级别 | `info` | `debug`, `warn`, `error` |
| `REDIS_URL` | Redis 连接 | - | `redis://localhost:6379` |
| `NODE_ENV` | 运行环境 | `development` | `production`, `test` |

### 配置文件示例

```env
# .env.example

# 必填
DATABASE_URL=postgres://user:password@localhost:5432/mydb
API_KEY=your-api-key-here
SECRET_KEY=generate-a-random-string

# 可选
PORT=3000
LOG_LEVEL=info
NODE_ENV=development
```

---

## 开发命令

| 命令 | 作用 | 说明 |
|------|------|------|
| `pnpm dev` | 开发模式启动 | 热重载，适合开发 |
| `pnpm build` | 构建生产版本 | 输出到 dist/ |
| `pnpm start` | 生产模式启动 | 需要先 build |
| `pnpm test` | 运行测试 | 单元测试 + 集成测试 |
| `pnpm test:watch` | 监听模式测试 | 文件变化自动重跑 |
| `pnpm lint` | 代码检查 | ESLint + Prettier |
| `pnpm lint:fix` | 自动修复 | 修复可自动修复的问题 |
| `pnpm typecheck` | 类型检查 | TypeScript 类型验证 |
| `pnpm db:migrate` | 数据库迁移 | 执行 pending migrations |
| `pnpm db:seed` | 数据库填充 | 填充测试数据 |
| `pnpm db:reset` | 数据库重置 | 清空并重建 |

---

## 验证安装

启动后，执行以下检查确认安装成功：

### 健康检查

```bash
# HTTP 健康检查
curl http://localhost:3000/health
# 期望返回: {"status": "ok"}

# 或访问浏览器
open http://localhost:3000
```

### 功能验证

```bash
# 测试核心功能
curl -X POST http://localhost:3000/api/test \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

---

## 常见问题

### Q: 启动报错 "Cannot find module xxx"

**原因：** 依赖未安装完整

**解决：**
```bash
# 清理并重新安装
rm -rf node_modules pnpm-lock.yaml
pnpm install
```

---

### Q: 数据库连接失败

**原因：** 数据库未启动或配置错误

**解决：**
```bash
# 1. 检查数据库服务
pg_isready -h localhost -p 5432

# 2. 检查连接字符串格式
# postgres://用户名:密码@主机:端口/数据库名

# 3. 测试连接
psql $DATABASE_URL -c "SELECT 1"
```

---

### Q: 端口被占用 "EADDRINUSE"

**原因：** 端口已被其他进程使用

**解决：**
```bash
# 找到占用端口的进程
lsof -i :3000

# 终止进程
kill -9 <PID>

# 或修改 .env 使用其他端口
PORT=3001
```

---

### Q: 权限不足 "EACCES"

**原因：** 文件权限问题

**解决：**
```bash
# 修复 node_modules 权限
sudo chown -R $(whoami) node_modules

# 或使用 --unsafe-perm
pnpm install --unsafe-perm
```

---

### Q: TypeScript 编译错误

**原因：** 类型定义缺失或版本不兼容

**解决：**
```bash
# 重新安装类型定义
pnpm install -D @types/node

# 检查 TypeScript 版本
pnpm list typescript
```

---

### Q: 环境变量未生效

**原因：** .env 文件未加载

**解决：**
```bash
# 确认 .env 文件存在
ls -la .env

# 确认格式正确（无空格）
# 正确: KEY=value
# 错误: KEY = value

# 重启服务
pnpm dev
```

---

## 项目结构速览

```
[repo]/
├── src/               # 源代码
│   ├── index.ts       # 入口文件
│   ├── api/           # API 路由
│   ├── services/      # 业务逻辑
│   └── utils/         # 工具函数
├── tests/             # 测试文件
├── docs/              # 文档
├── scripts/           # 脚本
├── .env.example       # 环境变量模板
├── package.json       # 依赖配置
├── tsconfig.json      # TypeScript 配置
└── README.md          # 项目说明
```

---

## 下一步

启动成功后，建议：

1. **阅读 README.md** — 了解项目概述
2. **运行测试** — `pnpm test` 确保环境正常
3. **查看 API 文档** — 通常在 `/docs` 或 Swagger UI
4. **尝试核心功能** — 按文档示例操作一遍

如需深入理解代码实现，运行 `/project-analyzer modules`。
```

---

## 工作流程

### Phase 1: 检测项目类型

```bash
# 检测包管理器
ls package.json yarn.lock pnpm-lock.yaml package-lock.json 2>/dev/null

# 检测语言/框架
cat package.json | jq '.dependencies, .devDependencies' | head -20

# 检测是否有 Docker
ls Dockerfile docker-compose.yml 2>/dev/null
```

### Phase 2: 提取配置需求

```bash
# 查看 .env.example
cat .env.example 2>/dev/null || cat .env.sample 2>/dev/null

# 查看 README 中的安装说明
rg -A 30 "## Install|## Setup|## Getting Started|## 安装|## 启动" README.md
```

### Phase 3: 识别启动命令

```bash
# 查看 package.json scripts
cat package.json | jq '.scripts'

# 查看 Makefile
cat Makefile 2>/dev/null | head -50
```

### Phase 4: 收集常见问题

```bash
# 查看 Issues 中的常见问题
gh issue list --label "question" --limit 10 2>/dev/null

# 查看 README 中的 FAQ
rg -A 20 "## FAQ|## Troubleshoot|## 常见问题" README.md
```

---

## 质量检查清单

### 必须包含
- [ ] 环境要求表格（必需 + 可选）
- [ ] 至少 1 种启动方式的完整步骤
- [ ] 配置说明（必填 + 可选环境变量）
- [ ] 开发命令表格
- [ ] 验证安装的方法
- [ ] 至少 3 个常见问题解答

### 可选包含
- [ ] Docker Compose 方式
- [ ] 一键安装脚本
- [ ] 项目结构速览

### 禁止
- [ ] 缺少具体命令
- [ ] 只说"参考 README"
- [ ] 环境变量示例值使用占位符而不解释
