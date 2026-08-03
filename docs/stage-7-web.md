# 阶段 7：Web 运营后台

## 1. 阶段目标

本阶段完成 FastAPI 管理接口和 Vue 3 管理后台，使运营人员能够在本机完成数据查看、异常复核、日报导出和失败附件重解析。

基金净值邮件处理被实现为“运营工作台”的一个独立业务模块，而不是整个系统的固定边界。后续新增托管对账、资金指令、份额登记或信息披露模块时，可以共享登录、权限、布局和 API 基础设施。

## 2. 分层结构

```text
frontend/src/
├── platform/                   # 跨业务基础设施
│   ├── api/                    # HTTP 客户端与通用响应
│   ├── auth/                   # 登录状态
│   └── modules/                # 业务模块契约
├── modules/
│   ├── index.ts                # 模块注册、排序与重复校验
│   └── fund-operations/        # 基金运营业务模块
│       ├── api/
│       ├── components/
│       └── views/
├── layouts/                    # 运营工作台公共框架
├── components/                 # 跨模块组件
└── router/                     # 登录保护与角色路由守卫
```

新增业务模块时，实现 `BusinessModule` 契约并在 `frontend/src/modules/index.ts` 注册即可。注册中心会拒绝重复的模块 ID、路由名称和导航路径，防止模块扩展时产生静默冲突。

后端继续使用原有的 `api → service → repository/model` 分层。阶段 7 新增的查询接口不会改变历史数据；人工重解析也复用阶段 4、5 的解析与持久化服务。

## 3. 登录与权限

系统使用本地账号和三种角色：

| 角色 | 查询 | Excel 导出 | 处置异常 | 人工重解析 |
|---|---:|---:|---:|---:|
| `admin` | 是 | 是 | 是 | 是 |
| `operator` | 是 | 是 | 是 | 是 |
| `viewer` | 是 | 是 | 否 | 否 |

密码使用 scrypt 加盐哈希保存。登录后签发 HMAC-SHA256 签名的 HttpOnly Cookie，会话默认有效 480 分钟；前端不使用 `localStorage` 或 `sessionStorage` 保存令牌。Cookie 使用 `SameSite=Strict`，生产 HTTPS 环境必须同时启用 `secure_cookie`。

生产环境配置示例：

```powershell
$env:FUND_NAV_APP__ENVIRONMENT = "production"
$env:FUND_NAV_SECURITY__SECRET_KEY = "替换为至少32位的随机密钥"
$env:FUND_NAV_SECURITY__SECURE_COOKIE = "true"
```

生产环境若仍使用默认密钥或密钥短于 32 个字符，后端会拒绝启动。

## 4. 初始化与启动

从项目根目录执行数据库迁移并创建第一个管理员：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m app.cli.create_admin --username admin
```

密码由终端交互输入，不会显示，也不会进入 PowerShell 历史。用户名统一转为小写；密码至少 10 个字符。

启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

启动前端：

```powershell
Set-Location frontend
pnpm.cmd install
pnpm.cmd dev
```

访问 <http://127.0.0.1:5173> 并使用刚创建的管理员登录。

## 5. 页面与接口

| 页面 | 主要接口 | 说明 |
|---|---|---|
| 登录 | `POST /api/v1/auth/login` | 登录并设置 HttpOnly Cookie |
| 运营概览 | `GET /api/v1/dashboard` | 返回当天邮件、成功数、基金数、开放异常和最新批次 |
| 邮件管理 | `GET /api/v1/emails` | 支持关键词、状态、日期与分页 |
| 邮箱配置 | `GET /api/v1/emails/connection` | 返回实际加载的非敏感 IMAP 配置信息 |
| 连接检测 | `POST /api/v1/emails/connection/test` | 只读验证网络、认证和邮箱目录，不返回凭据 |
| 立即同步 | `POST /api/v1/emails/sync` | 互斥执行邮件搜索、匹配、归档、解析与入库，并记录任务审计 |
| 基金净值 | `GET /api/v1/fund-nav` | 支持产品关键词、日期与分页 |
| 历史曲线 | `GET /api/v1/fund-nav/history` | 按产品代码返回最多 5,000 个历史点 |
| 日报导出 | `GET /api/v1/fund-nav/export` | 复用阶段 6 导出器并返回 `.xlsx` |
| 异常管理 | `GET/PATCH /api/v1/exceptions` | 查询异常并更新开放、解决、忽略状态 |
| 人工处理 | `POST /api/v1/operations/manual-reparse` | 上传单个 Excel 并执行归档、解析、入库 |

所有业务接口均要求登录。状态修改与人工重解析还会在后端再次校验角色，不能仅依赖前端隐藏按钮。

## 6. 人工重解析的审计语义

人工上传不会覆盖原始附件：

1. 文件先保存到 `data/YYYY/MM/DD/attachments/`，文件名包含唯一操作 ID。
2. 创建独立的 `job_run`、`email_record` 和 `attachment_record`。
3. 调用与自动邮件相同的 Excel 识别、标准化和数据库入库流程。
4. 已存在的 `产品代码 + 日期` 保持原记录不变，并写入重复异常。
5. 若操作失败，任务状态和错误信息仍被保留；没有审计记录的孤立文件会被安全清理。

## 7. 异常分类扩展

异常页面使用稳定的运营类别，底层解析器可以持续增加更细的异常类型。映射集中维护在 `backend/app/domain/exception_categories.py`；未登记的托管平台特有类型会自动进入“其他异常”，不会在筛选中丢失。

## 8. 验证结果

阶段 7 完成时已执行：

```text
后端 Ruff：通过
后端 pytest：63 passed
Alembic：升级到 20260729_0002，check 无差异
前端 vue-tsc：通过
前端 Vitest：3 passed
前端 Vite 生产构建：通过
```

阶段 8 将补充 Docker Compose、前端静态资源容器和统一启动方式。
