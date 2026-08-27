# 数据治理阶段 2 验收说明

## 拆分结果

- 每个租户建立唯一 `organization_profile`，公司事实和公司文件归入公司主体。
- 每个 `fund_product` 建立唯一产品主体和 `fund_product_profile`；历史产品与后续邮件中新产品使用同一初始化服务。
- 资料中心前端分为“公司资料”“产品资料”和管理员可见的“待归属材料”。
- 旧 `/api/v1/filing-profile` 查询、文本导出和文件下载继续可用；修改字段、资料值和上传文件统一返回
  `410 FILING_PROFILE_READ_ONLY`。

## 旧资料迁移

Alembic `20260827_0018` 按租户执行以下分类迁移：

1. 旧文本字段迁为公司主体的 `field_definition` 和已确认 `field_value`。
2. 公司证照及通用材料迁为公司 `source_document`，并增加 `legacy_company_material` 关系。
3. 基金备案、合同、托管账户、持有人名册、证券账户、承诺函和基金协议等产品材料迁为
   `source_document`，先进入 `product_material_attribution` 待归属队列。
4. 管理员确认产品后仅新增 `product_material` 关系，不修改来源文件本体。

迁移保留旧文件的 `stored_path`、SHA-256、文件大小和版本号，并保存旧字段及文件版本 ID，
因此可核对迁移前后的文件身份。

## 权限与兼容

- 公司和产品资料读取继续经过阶段 1 的统一资源权限服务；敏感资料不会因平台管理员身份自动放行。
- 待归属材料列表和确认操作只允许租户管理员，确认操作写入追加式审计链。
- 已归属材料重复提交返回 409，避免同一历史材料被静默改挂到其他产品。
- 新建租户自动创建公司资料主体，新解析出的产品自动创建产品资料主体。

## 主要接口

```text
GET   /api/v2/profiles/company
GET   /api/v2/profiles/products
GET   /api/v2/profiles/products/{entity_id}
GET   /api/v2/product-material-attributions?status=pending
POST  /api/v2/product-material-attributions/{id}/assign
```

## 验收覆盖

- 从阶段 1 数据库升级并核对公司、产品、字段事实和材料分类。
- 迁移前后文件路径、哈希和版本完全一致。
- 公司资料与不同产品资料互不串用。
- 待归属材料确认、重复确认保护和审计事件。
- 旧接口查询可用、全部写入口只读。
- 数据库迁移模型一致性、后端全量测试、前端类型检查、单元测试和生产构建。
