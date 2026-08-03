# 阶段 5：数据库存储与幂等导入

## 落库边界

系统将数据分为三类保存：

1. 原始证据：EML、Excel 附件和 JSON 清单按接收日期归档。
2. 业务事实：标准化后的基金净值只新增、不覆盖。
3. 运营审计：邮件状态、附件状态、解析异常和任务运行记录。

邮件归档记录与其附件在一个事务中提交；单个附件产生的净值、异常和最终状态也在一个事务中提交。Excel 解析在事务外完成，避免长时间占用 SQLite 写锁。

## 数据表

| 表 | 作用 | 关键约束 |
| --- | --- | --- |
| `fund_nav` | 标准化基金净值 | `product_code + nav_date` 唯一 |
| `email_record` | 邮件审计 | `mailbox_key + uid_validity + message_uid` 唯一 |
| `attachment_record` | 附件归档与解析状态 | `email_id + stored_path` 唯一 |
| `exception_record` | 解析、重复及完整性异常 | 关联邮件、附件、工作表和行号 |
| `job_run` | 调度和人工任务审计 | 保存触发方式、计数和结束状态 |
| `app_user` | Web 后台用户 | 用户名唯一 |

`email_record` 与 `attachment_record` 分表，避免一封多附件邮件重复保存主题、发送人与接收时间，也能对每个附件单独重新解析。

## 防重复与历史保护

- 基金代码在入库边界统一为大写并去除首尾空格。
- 仓储层只公开 `insert_if_absent`，没有覆盖历史净值的更新方法。
- 正常重复先通过业务键查询识别。
- 并发写入由数据库唯一约束兜底，并通过嵌套保存点恢复外层事务。
- 被拒绝的重复记录生成 `duplicate_nav` 异常，包含原记录 ID、原来源文件和本次来源文件。
- 不同净值日期会分别保留，构成产品历史净值序列。

## 文件完整性

附件归档时保存 SHA-256。解析前重新计算文件哈希；文件缺失、无法读取或哈希变化时停止解析，并生成以下异常之一：

- `attachment_missing`
- `attachment_read_error`
- `attachment_integrity_error`

这可以避免人工误改原始附件后产生无法解释的数据变化。

## 状态规则

附件状态包括归档、解析中、成功、部分成功、失败、重复和不支持。邮件状态由其附件状态汇总：全部成功时为成功；部分附件成功时为部分成功；全部结束且无成功附件时为失败。

解析器发现的字段缺失、格式歧义、无效日期、无效数字、空净值和文件内重复都会写入 `exception_record`。警告保留审计记录，但只有错误会使附件进入部分成功或失败状态。

## 迁移与验证

首个迁移文件为 `backend/alembic/versions/20260728_0001_initial_schema.py`。

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check
```

自动测试覆盖迁移升级/降级、模型差异检查、邮件幂等归档、净值重复保护、历史日期保留、异常明细、文件哈希验证和事务回滚。
