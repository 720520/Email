# 后端服务

基于 FastAPI、SQLAlchemy 2 和 Alembic 的后端服务。目前已提供配置、日志、健康检查、IMAP 归档、Excel 智能解析、SQLite 模型、事务化净值写入和异常审计。

首次运行前在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

导出每日汇总：

```powershell
.\.venv\Scripts\python.exe -m app.cli.export_daily --date 2026-07-24
```
