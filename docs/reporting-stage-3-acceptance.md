# 报表平台阶段 3 验收记录

验收日期：2026-08-21
范围：单份报告快照、版本与可复现生成。

## 实现结果

- `ReportRun` 固定 `template_version_id`、字段定义版本集合和完整输入快照。
- 新增不可变 `ReportFileVersion`，记录版本号、来源、路径、SHA-256、文件大小和创建人。
- `current_version_id` 明确指向当前下载版本，旧 `output_path/output_filename` 继续兼容。
- 生成顺序为：创建 Run → 冻结字段 → 临时渲染 → 重新打开校验 → SHA-256 → 原子移动 → 创建 v1 → 标记成功。
- 失败记录 `error_stage`、`error_code`、简化消息、输入快照和审计事件，并清理临时文件。
- 支持按原快照重新生成，在同一 Run 下创建新的不可变文件版本。
- 提供版本列表、历史版本下载和当前版本下载；所有下载写审计日志。
- 前端生成记录显示当前文件版本，并提供“按快照重生成”。

## API

```text
POST /api/v1/reports/generate
GET  /api/v1/reports/runs
GET  /api/v1/reports/runs/{run_id}/download
POST /api/v1/reports/runs/{run_id}/regenerate
GET  /api/v1/reports/runs/{run_id}/versions
GET  /api/v1/reports/runs/{run_id}/versions/{version_id}/download
```

## 自动化验收

```text
后端完整测试：117 passed
前端测试：12 passed
Ruff：passed
前端 TypeScript：passed
前端生产构建：passed
Alembic 当前版本：20260821_0011 (head)
Alembic check：passed
迁移升级与回退：passed
```

闭环测试验证：数据库字段修改后历史快照不变；重生成 v2 仍使用原字段值；文件 SHA-256 与数据库一致；失败不留下临时 PPTX；下载当前版本并产生审计记录。

阶段 3 完成后才能进入阶段 4“大批量异步生成”。
