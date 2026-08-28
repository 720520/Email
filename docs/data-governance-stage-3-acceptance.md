# 数据治理阶段 3 验收说明

## 交付结果

- 新增开户机构台账，维护机构类型、牌照代码、联系人及启停状态；机构同时接入统一主体和租户边界。
- 新增监管基础模板与机构材料模板，按账户类型、基金类型、生效日期和版本管理。
- 创建开户申请时合并生效的监管与机构模板，并生成申请专属材料快照；机构模板中同编码材料覆盖监管基础要求。
- 新增开户台账前端，支持建单、选择公司/产品材料、提交、退回补件、审批、确认开户和销户。
- 资料中心开放公司及产品资料上传与版本追加，作为开户清单的受控材料来源。

## 数据与版本规则

Alembic `20260828_0019` 新增：

```text
counterparty_institution
requirement_template
requirement_template_item
account_application
application_requirement
application_supplement
application_event
```

创建申请后，材料名称、来源范围、必需性、盖章和原件要求被复制到
`application_requirement`，后续模板变化不会修改历史申请。首次提交会固定每项
`source_document` 的 ID、版本与 SHA-256；提交后禁止替换主材料。补件写入独立的
`application_supplement` 追加记录，因此原提交版本始终可核对。

## 流程与权限

- 管理员维护机构和模板；租户成员可查看。
- 操作员和管理员可以创建申请；非管理员只能编辑本人负责的申请。
- 只有管理员可以要求补件、审批、确认开户和销户。
- 申请负责人不能审批自己的申请，避免经办与审批为同一人。
- 公司材料只能满足 `organization` 要求，产品材料只能满足对应产品的 `product` 要求，跨主体文件会被拒绝。
- 所有资源查询均受租户条件约束；跨租户机构、申请和文件不可枚举或引用。
- 建单、材料关联、提交、补件、审批、开户和销户同时写入业务事件与追加式审计链。

## 主要接口

```text
GET    /api/v2/institutions
POST   /api/v2/institutions
PATCH  /api/v2/institutions/{id}
GET    /api/v2/requirement-templates
POST   /api/v2/requirement-templates
PATCH  /api/v2/requirement-templates/{id}/state
GET    /api/v2/account-applications
POST   /api/v2/account-applications
GET    /api/v2/account-applications/{id}
PATCH  /api/v2/account-applications/{id}
PUT    /api/v2/account-applications/{id}/requirements/{requirement_id}
POST   /api/v2/account-applications/{id}/submit
POST   /api/v2/account-applications/{id}/supplements
POST   /api/v2/account-applications/{id}/review
GET    /api/v2/account-applications/{id}/available-documents
```

## 验收覆盖

- 同一产品分别向多家机构创建开户申请。
- 同一机构的证券、期货等账户类型匹配不同模板。
- 监管基础模板与机构模板合并及同编码覆盖。
- 公司和指定产品材料的来源范围校验。
- 首次提交后的材料替换保护与补件追加。
- 缺件、提交、要求补件、重新提交、审批、开户和销户事件顺序。
- 经办人自审限制、跨租户访问保护和审计动作。
- 数据库迁移模型一致性、后端全量测试、前端类型检查、测试与生产构建。
