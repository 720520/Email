# 报表平台阶段 0～2 验收记录

验收日期：2026-08-21
验收范围：阶段 0 基线保护、阶段 1 动态字段注册中心、阶段 2 模板解析与动态替换。

## 阶段 0：基线整理与测试保护

- 保留既有 `/api/v1/reports` API，并增加兼容领域目录 `app/reporting/`。
- 既有模板上传、预览、单份生成、下载和租户隔离测试纳入完整回归。
- 测试模板由测试代码确定性生成，覆盖重复字段、跨 run、表格、多页、版式占位符、图表、图片和空值。
- 旧的同步 TestClient 用例迁移为 HTTPX ASGI 异步调用；请求内容、Cookie 和断言不变。

结论：通过。

## 阶段 1：动态字段注册中心

- 数据模型：`ReportFieldDefinition`、`ReportFieldValue`、`ReportFieldDefinitionVersion`。
- Provider：Model、Custom、Email、Contract、Metric、System；不执行任意表达式。
- API：列表、新建、编辑、停用、解析、引用查询和产品字段值维护。
- 前端：字段中心页面及字段 API 测试。
- 安全：系统字段只读、自定义字段唯一、数据类型校验、版本与审计、跨租户默认拒绝。

结论：通过。

## 阶段 2：模板解析、校验和动态替换

- 扫描文本框、组合形状、表格、幻灯片母版和版式占位符。
- 支持重复字段、跨 PowerPoint run、日期/百分比/默认值格式化。
- 支持产品信息表、业绩表、净值图和图片锚点。
- 生命周期：`draft → validating → published → archived`；只允许已发布版本生成。
- 发布校验：字段注册和启用状态、必填字段默认值、格式化器类型、组件重复、损坏 PPTX。
- 历史安全：停用字段阻止新模板发布，但已发布模板仍可取值生成；历史快照不修改。
- 测试覆盖两只基金独立生成、模板原文件不变、输出可重新打开、未知字段、损坏文件、发布不可覆盖和跨租户字段拒绝。

结论：通过。

## 自动化验收结果

```text
后端完整测试：117 passed
Ruff：passed
前端 Vitest：passed
前端 TypeScript：passed
前端生产构建：passed
Alembic upgrade head：passed
Alembic check：passed
Alembic downgrade base（隔离测试库）：passed
```

SQLite 在 Python 3.12 下产生 10 条 datetime adapter 弃用警告，不影响本阶段行为，后续数据库生产强化阶段统一处理。

## API 速查

字段平台：

```text
GET    /api/v1/report-fields
POST   /api/v1/report-fields
PATCH  /api/v1/report-fields/{id}
POST   /api/v1/report-fields/{id}/disable
POST   /api/v1/report-fields/resolve
GET    /api/v1/report-fields/{field_key}/usages
GET    /api/v1/report-fields/products/{product_id}/values
PUT    /api/v1/report-fields/products/{product_id}/values/{field_key}
```

模板平台：

```text
GET    /api/v1/reports/templates
POST   /api/v1/reports/templates
POST   /api/v1/reports/templates/{id}/validate
POST   /api/v1/reports/templates/{id}/publish
POST   /api/v1/reports/templates/{id}/versions
```

下一步只能进入阶段 3“单份报告快照、版本与可复现生成”，不提前开发批量任务或 OnlyOffice。
