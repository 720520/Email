# 数据治理阶段 0：基线与恢复手册

## 冻结范围

阶段 0 以提交 `3882b7a` 为功能基线。现有 `/api/v1` 接口、Alembic 迁移链、租户过滤器、
备案资料动态字段及不可变文件版本行为均作为后续重构的兼容边界。阶段 1 的新资源优先进入
`/api/v2`，不得静默改变现有接口响应和权限语义。

## 脱敏测试约束

- 测试用户、租户、产品、证件号和文件内容必须为明确的合成值。
- 不得复制生产数据库、客户附件、邮箱正文或访问令牌进入仓库。
- 文件测试只使用短字节串或程序生成的工作簿，不保存真实身份证、账户和联系方式。
- 测试配置通过临时目录和固定测试密钥创建，与开发机 `.env` 隔离。

## 备份

停止后端及 Worker 后执行：

```bash
./scripts/start.sh --stop
./scripts/backup.sh
```

脚本默认备份 `data/`、`.env`、`config/config.local.yaml` 和当前 Git 提交，并生成
`SHA256SUMS`。可用 `--data-dir`、`--backup-root` 和 `--label` 指定测试或外部存储位置。

## 恢复演练

先恢复到空目录检查：

```bash
./scripts/restore.sh --backup backups/备份名称 --data-dir /tmp/fund-nav-restore-check
```

校验数据库、附件数量和哈希后，才允许恢复正式 `data/`。正式目录非空时必须显式传
`--force`；旧目录会移动为 `.pre-restore-时间` 回滚副本，不会直接删除。

## 阶段 0 验收命令

```bash
./.venv/bin/python -m pytest backend/tests -q
cd frontend
../scripts/pnpm.sh type-check
../scripts/pnpm.sh test -- --run
../scripts/pnpm.sh build
```

验收必须同时覆盖备案资料读写、不可变文件版本、跨租户 ID、文件下载、备份恢复和篡改检测。
