# 资料、开户与产品运营平台设计及开发测试方案

## 1. 文档目标

本方案用于将现有“备案资料库”升级为一套可维护、可扩展、可追溯且权限框架稳定的业务平台。

平台需要支持：

- 公司资料和产品资料完全分离。
- 一个产品可以在多个券商、期货公司、银行和托管机构开户。
- 后续增加投资者、基金经理、账户、开放日、申赎、份额、持仓和收益模块时，不修改基础权限框架。
- 人工录入、附件上传、邮件附件、批量导入和系统计算均有明确来源。
- 原始附件不可覆盖，历史版本永久可追溯。
- 机器解析结果经过校验和人工确认后才能进入正式数据。
- 高频业务数据使用事件或快照模型，不存入万能 JSON。
- 敏感数据支持脱敏、独立授权和访问审计。

## 2. 设计原则

1. 权限框架稳定，业务对象可扩展。
2. 结构化事实可以更新，原始证据不可覆盖。
3. 每个重要字段都能回答“来自哪里、谁确认、何时生效”。
4. 描述型资料使用动态字段，高频业务数据使用明确业务表。
5. 正式数据与机器解析暂存数据严格分离。
6. 当前状态由事件计算，历史事件不得静默覆盖。
7. 租户隔离是第一层边界，产品和敏感等级是第二层边界。

## 3. 总体架构

```text
主体中心
├─ 管理人公司
├─ 基金产品
├─ 投资者
├─ 基金经理
├─ 交易对手
└─ 金融账户
        │
        ▼
资料中心 ───── 文件与版本中心
        │             │
        ▼             ▼
结构化事实       原始附件/来源定位
        │             │
        └──── 数据血缘 ┘
                      │
                      ▼
开户备案 / 申赎份额 / 持仓收益
                      │
                      ▼
权限策略 / 审批 / 审计
```

模块边界：

- **资料中心**：低频、描述型、证照型信息。
- **业务事件**：申购、赎回、份额调整、账户开销户等状态变化。
- **业务快照**：某个估值日的净值、持仓和投资者份额。
- **计算结果**：收益率、风险指标和归因结果。
- **原始证据**：合同、邮件、Excel、PDF、Word 和图片。
- **权限中心**：统一判断查看、修改、审批、下载和导出权限。

## 4. 数据模型

### 4.1 统一主体

新增 `entity`：

```text
id
tenant_id
entity_type
display_name
external_code
status
created_by_user_id
create_time
update_time
```

初始主体类型：

```text
organization
product
investor
fund_manager
institution
financial_account
```

各类主体使用明确扩展表：

- `organization_profile`
- `fund_product_profile`
- `investor_profile`
- `fund_manager_profile`
- `counterparty_institution`
- `financial_account`

现有 `fund_product` 继续作为产品业务主表，通过迁移增加统一主体关联。

### 4.2 动态字段定义

新增 `field_definition`：

```text
id
tenant_id nullable
entity_type
field_code
label
data_type
category
sensitivity
is_multivalue
validation_schema
display_schema
sort_order
is_system
is_active
```

动态字段适合公司联系人、产品简称、基金经理简介、机构联系人及自定义说明。

申赎流水、份额变动、持仓、净值、收益和审批状态不得存为动态字段。

### 4.3 字段事实与历史

新增 `field_value`：

```text
id
tenant_id
entity_id
field_definition_id
value_json
status
valid_from
valid_to
source_type
source_document_id
source_locator_json
extraction_run_id
confidence
entered_by_user_id
reviewed_by_user_id
recorded_at
```

状态：

```text
draft
extracted
confirmed
superseded
rejected
```

同一字段保留多个历史事实，通过有效期确定当前值。

### 4.4 原始附件

新增 `source_document`：

```text
id
tenant_id
entity_id nullable
document_type_id
original_name
mime_type
content_hash
storage_path
file_size
version
effective_date
expiry_date
source_channel
sensitivity
uploaded_by_user_id
create_time
```

来源渠道：

```text
manual_upload
email_attachment
batch_import
api_sync
system_generated
```

文件不可覆盖，新文件始终产生新版本。相同哈希可以提示重复，但不得静默替换。

新增 `document_relation`，允许一份文件关联多个主体或业务事项：

```text
document_id
entity_id
relation_type
```

### 4.5 文档解析

新增 `extraction_run`：

```text
id
tenant_id
document_id
parser_code
parser_version
schema_version
status
started_at
completed_at
error_message
```

新增 `extraction_candidate`：

```text
id
extraction_run_id
field_definition_id
raw_value
normalized_value_json
source_locator_json
confidence
validation_status
review_status
reviewed_by_user_id
```

候选结果只有经过人工复核，才可以生成正式 `field_value`。

### 4.6 开户机构与开户申请

`counterparty_institution`：

```text
entity_id
institution_type
full_name
short_name
license_code
contact_information
is_active
```

机构类型：

```text
broker
futures_company
custodian_bank
commercial_bank
fund_service_provider
other
```

`account_application`：

```text
id
tenant_id
product_id
institution_id
account_type
settlement_mode
status
application_date
completed_date
closed_date
owner_user_id
reviewer_user_id
```

状态：

```text
draft
preparing
pending_seal
submitted
supplement_required
approved
opened
rejected
closed
```

`requirement_template` 保存监管基础模板和机构模板：

```text
id
tenant_id nullable
institution_id nullable
account_type
fund_type
name
version
effective_from
effective_to
is_active
```

创建申请时生成不可变的 `application_requirement` 快照：

```text
application_id
requirement_code
name
source_scope
required
condition_json
seal_requirement
original_required
status
document_id
review_comment
```

`source_scope` 支持 `organization`、`product` 和 `account_application`。

### 4.7 投资者与基金经理

`investor_profile` 保存投资者类型、证件、适当性、税收居民和受益所有人摘要。证件号码、联系方式及银行账户为高度敏感数据。

`product_investor_relation`：

```text
product_id
investor_id
share_class
relation_status
effective_from
effective_to
```

`fund_manager_assignment`：

```text
product_id
fund_manager_id
role
effective_from
effective_to
source_document_id
```

任职和投资关系变更不得覆盖旧记录。

### 4.8 开放日、申赎与份额

`dealing_rule` 保存合同约定：

```text
product_id
operation_type
recurrence_rule
notice_days
settlement_days
valid_from
valid_to
source_document_id
```

`dealing_calendar` 保存实际开放日：

```text
product_id
business_date
operation_type
status
rule_id
adjustment_reason
```

`capital_transaction`：

```text
product_id
investor_id
transaction_type
application_date
confirmation_date
amount
confirmed_units
nav
fee
status
source_document_id
```

`unit_ledger` 采用追加式份额台账：

```text
product_id
investor_id
share_class
event_type
units_delta
effective_date
transaction_id
```

当前份额由已确认事件累计，不允许直接覆盖余额。

### 4.9 持仓与收益

`holding_import_batch`：

```text
product_id
valuation_date
source_document_id
status
parser_version
confirmed_by_user_id
```

`holding_snapshot`：

```text
batch_id
asset_code
asset_name
asset_type
quantity
cost
market_value
currency
```

同日重传生成新批次，比较差异并确认后才能切换当前有效批次。

`performance_metric`：

```text
product_id
metric_code
start_date
end_date
value
calculation_version
input_snapshot_json
calculated_at
```

收益数据必须保留计算公式版本、输入净值版本、基准和复权规则。

### 4.10 双时间模型

重要数据同时保存：

- `effective_at`：业务上何时生效。
- `recorded_at`：系统何时获知和记录。

该设计用于追溯补充协议、基金经理任职、开放规则和历史份额变化。

## 5. 权限框架

### 5.1 权限表达式

统一采用：

```text
用户 + 作用域 + 资源类型 + 数据分类 + 操作
```

作用域：

```text
tenant
product
entity
account_application
```

操作：

```text
view
view_sensitive
create
update
review
approve
download
export
manage_schema
manage_permission
```

数据分类：

```text
public
internal
confidential
highly_sensitive
```

### 5.2 权限数据

新增 `permission_grant`：

```text
tenant_id
user_id
scope_type
scope_id
resource_type
action
data_classification
effect
valid_from
valid_to
```

`effect` 支持 `allow` 和 `deny`，显式拒绝优先。

建议角色包：

- 租户管理员
- 资料管理员
- 产品运营
- 投资运营
- 合规复核
- 只读用户

角色只作为权限模板，后端最终依据权限策略判断。

### 5.3 强制规则

- 所有查询首先校验 `tenant_id`。
- 产品资源继续校验产品授权。
- 高度敏感字段默认脱敏。
- 文件下载独立鉴权，不复用列表查看权限。
- 平台管理员不自动获得业务敏感数据权限。
- 已提交材料不可覆盖。
- 审批人不能审批自己提交的敏感变更。
- 批量导出投资者资料必须记录原因。
- URL 中的实体 ID 不作为授权依据。
- 越权请求不得产生任何数据库或文件写入。

## 6. 数据来源与血缘

每个正式字段必须记录来源类型和来源定位。

定位方式：

- Excel：Sheet、行号、列名和单元格范围。
- PDF：页码、段落或文本区域。
- Word：标题路径、表格编号和行列。
- 邮件：邮件 ID、附件 ID、发件人和接收时间。
- 图片：OCR 页码及坐标区域。
- 人工录入：录入人、原因和参考说明。
- 系统计算：公式版本和输入数据版本。

前端字段展示来源标签，点击后可以打开原附件并定位到对应位置。

来源状态：

```text
extracted   机器解析、待确认
confirmed   人工确认后生效
manual      人工直接录入
calculated  系统计算
imported    可信接口或批量模板导入
```

## 7. 附件解析

### 7.1 上传流程

```text
上传
→ 文件签名与 MIME 检查
→ 病毒、大小和压缩包安全检查
→ 哈希去重
→ 原始文件不可变保存
→ 文档类型识别
→ 选择解析器
→ 生成暂存候选结果
→ 规则校验
→ 人工复核
→ 正式入库
```

### 7.2 文件类型策略

- XLS/XLSX/CSV：模板映射和表头识别，适合净值、份额、持仓和投资者清单。
- DOCX：解析标题、段落和表格，适合合同及说明文件。
- 文本 PDF：解析文本和表格。
- 扫描 PDF/图片：OCR 后默认进入人工复核。
- PPTX：以元数据和文本提取为主，不直接写核心业务数据。
- 压缩包：限制目录深度、文件数量和解压总体积。
- 未知文件：只归档，不自动提取。

解析器选择不得只依赖扩展名，必须检查文件签名和 MIME。

### 7.3 解析器注册表

每个解析器声明：

```text
支持 MIME
目标文档类型
目标主体类型
输出字段
规则版本
最低置信度
是否必须人工复核
```

解析器升级不得改变已确认的历史正式数据。

## 8. API 设计

新增接口逐步放入 `/api/v2`，现有 `/filing-profile` 作为兼容层。

### 8.1 主体

```text
GET    /api/v2/entities
POST   /api/v2/entities
GET    /api/v2/entities/{id}
PATCH  /api/v2/entities/{id}
```

### 8.2 资料事实

```text
GET    /api/v2/entities/{id}/facts
PUT    /api/v2/entities/{id}/facts/{field_code}
GET    /api/v2/entities/{id}/facts/{field_code}/history
```

### 8.3 文件与解析

```text
POST   /api/v2/documents
GET    /api/v2/documents/{id}
GET    /api/v2/documents/{id}/download
GET    /api/v2/documents/{id}/versions
POST   /api/v2/documents/{id}/extract
GET    /api/v2/extractions/{id}
POST   /api/v2/extractions/{id}/review
POST   /api/v2/extractions/{id}/commit
```

### 8.4 开户

```text
GET    /api/v2/account-applications
POST   /api/v2/account-applications
GET    /api/v2/account-applications/{id}
PATCH  /api/v2/account-applications/{id}
POST   /api/v2/account-applications/{id}/submit
POST   /api/v2/account-applications/{id}/supplements
```

### 8.5 产品运营

```text
GET/POST /api/v2/products/{id}/dealing-rules
GET/POST /api/v2/products/{id}/transactions
GET      /api/v2/products/{id}/unit-ledger
POST     /api/v2/products/{id}/holding-imports
GET      /api/v2/products/{id}/performance
```

## 9. 前端信息架构

```text
资料与主体
├─ 公司资料
├─ 产品资料
├─ 投资者
├─ 基金经理
└─ 机构与账户

业务办理
├─ 开户台账
├─ 备案事项
└─ 材料解析中心

产品运营
├─ 开放日历
├─ 申赎管理
├─ 份额台账
├─ 持仓管理
└─ 收益分析
```

统一前端组件：

- 主体选择器
- 字段来源标签
- 敏感数据遮罩
- 文件版本时间线
- 来源附件定位器
- 差异复核面板
- 权限不足提示
- 资料完整度检查
- 审批时间线

## 10. 开发阶段

### 阶段 0：基线冻结与测试补齐

工作内容：

- 固化现有数据库和 API 行为。
- 补齐备案资料库集成测试。
- 补齐文件上传、下载及跨租户越权测试。
- 准备脱敏测试数据。
- 建立数据库和文件备份恢复脚本。

验收标准：

- 现有测试全部通过。
- 可以从备份恢复数据库和文件。
- 测试中不包含真实身份证、账户或客户资料。

### 阶段 1：主体、来源和权限底座

工作内容：

- 统一主体表。
- 字段定义和字段事实表。
- 文件、版本、关系和来源定位表。
- 权限策略服务。
- 统一审计服务。
- 接入现有租户上下文。

验收标准：

- 所有主体使用同一权限入口。
- 字段历史和文件版本可追溯。
- 跨租户枚举全部失败。
- 平台管理员不能自动读取敏感文件。

### 阶段 2：公司与产品资料拆分

工作内容：

- 公司资料页面。
- 产品资料页面。
- 旧资料分类迁移。
- 产品材料人工归属流程。
- 旧接口兼容适配器。

验收标准：

- 公司资料只保存一份。
- 每个产品拥有独立资料。
- 同名材料不会跨产品串用。
- 原文件哈希和版本保持不变。
- 旧页面进入只读兼容模式。

### 阶段 3：机构模板与开户台账

工作内容：

- 机构管理。
- 账户类型和结算模式。
- 监管基础模板。
- 机构自定义材料模板。
- 开户申请、清单、补件和状态流转。
- 公司及产品材料引用。

验收标准：

- 一个产品可以关联多个开户机构。
- 同一机构不同账户类型使用不同模板。
- 申请提交后材料版本固化。
- 缺件、退回和补件过程完整留痕。

### 阶段 4：附件解析与复核中心

工作内容：

- 文件类型识别。
- Excel、CSV、DOCX 和 PDF 解析器。
- OCR 接口预留。
- 暂存候选结果。
- 差异比较和人工复核。
- 解析器版本管理。

验收标准：

- 机器解析不直接写正式数据。
- 字段可以定位到附件页码或单元格。
- 低置信度数据必须人工确认。
- 重复上传不覆盖历史附件。
- 恶意压缩包和伪造扩展名被拒绝。

### 阶段 5：投资者与基金经理

工作内容：

- 投资者档案。
- 适当性、税收居民及受益所有人资料。
- 基金经理档案。
- 产品任职关系。
- 产品级用户授权。
- 敏感数据脱敏和导出控制。

验收标准：

- 运营人员只能访问授权产品。
- 投资者敏感信息默认脱敏。
- 任职和投资者关系具有生效区间。
- 导出及明文查看进入审计链。

### 阶段 6：开放日、申赎与份额

工作内容：

- 开放规则及实际日历。
- 临时开放日调整。
- 认购、申购和赎回事件。
- 追加式份额台账。
- 对账和异常处理。

验收标准：

- 当前份额可以从事件重算。
- 取消或更正不覆盖原事件。
- 开放规则变更不影响历史日历。
- 申赎状态受权限和审批控制。

### 阶段 7：持仓与收益

工作内容：

- 持仓导入批次。
- 差异校验和有效批次切换。
- 收益计算服务。
- 计算版本和输入快照。
- 产品收益及异常页面。

验收标准：

- 同日重传不会静默覆盖。
- 旧持仓批次可追溯。
- 收益可以使用保存的输入重算。
- 公式、基准和程序版本明确。

### 阶段 8：迁移、灰度和旧模块下线

工作内容：

- 全量数据迁移。
- 文件哈希核对。
- 新旧接口双读比较。
- 按租户灰度启用。
- 旧页面只读和最终下线。

验收标准：

- 数据数量、文件哈希、归属和权限全部核对。
- 回滚演练成功。
- 灰度期无跨租户或跨产品异常。

## 11. 测试方案

### 11.1 单元测试

覆盖：

- 权限策略计算。
- 敏感字段脱敏。
- 字段有效期选择。
- 文件哈希及版本号。
- MIME 和文件签名识别。
- 解析规则和标准化。
- 份额事件累计。
- 开放日规则生成。
- 收益计算和计算版本。

覆盖率目标：

- 权限和账务计算分支不低于 95%。
- 其他新增模块不低于 85%。

### 11.2 API 集成测试

每种资源至少测试：

- 未登录访问。
- 只读用户访问。
- 未授权产品用户访问。
- 产品运营访问。
- 租户管理员访问。
- 平台管理员访问。
- 跨租户 ID。
- 跨产品 ID。
- 敏感字段明文访问。
- 文件直接下载。
- 已提交记录修改。
- 双人复核限制。

关键断言：

- 越权请求不产生数据库写入。
- 失败事务不残留文件或孤立记录。
- 下载地址不能绕过 API 权限。
- 响应不能包含被脱敏字段原值。

### 11.3 数据库测试

- 所有迁移可以在空数据库执行。
- 旧版本数据库可以逐级升级。
- 唯一约束和外键有效。
- 租户过滤器覆盖所有新表。
- 事件台账禁止物理覆盖。
- 被业务引用的文件版本禁止删除。
- 升级失败可以恢复备份。

### 11.4 文件安全测试

测试样本：

- 正常 XLSX、DOCX、PDF 和图片。
- 扩展名与 MIME 不一致。
- 超大、空白、损坏及加密文件。
- 宏文件。
- 路径穿越压缩包。
- 压缩炸弹。
- 重复文件。
- 同名不同内容文件。
- CSV 公式注入。

### 11.5 解析准确性测试

建立固定金标样本：

```text
附件
→ 期望字段
→ 期望原始位置
→ 期望置信度
→ 是否要求人工复核
```

每次解析器升级比较：

- 新增识别数量。
- 丢失字段数量。
- 值变化数量。
- 来源定位变化。
- 误识别率。
- 低置信度召回率。

### 11.6 前端测试

- 路由和按钮权限。
- 敏感数据遮罩。
- 公司、产品及主体切换。
- 来源定位。
- 文件版本展示。
- 解析差异确认。
- 开户状态流转。
- 未保存提醒。
- 分页、筛选和空状态。
- 大文件上传进度。
- 403、409、422 和 500 错误提示。

### 11.7 端到端测试

核心业务链：

1. 创建产品并上传基金合同。
2. 解析合同并复核产品信息。
3. 创建券商开户申请。
4. 引用公司和产品材料。
5. 补充机构专属文件。
6. 提交、退回、补件并完成开户。
7. 创建投资者并录入申购。
8. 确认份额变化。
9. 导入持仓。
10. 计算并核对收益。
11. 查看任意字段的完整来源链。
12. 使用未授权账号验证所有越权入口。

### 11.8 性能测试

基准数据：

- 100 个租户。
- 每租户 500 个产品。
- 每产品 5,000 个投资者。
- 每产品 10 年净值。
- 每日 10,000 条持仓。
- 100 万个文件版本和审计事件。

建议指标：

- 普通列表 P95 小于 500ms。
- 主体详情 P95 小于 800ms。
- 权限判断 P95 小于 30ms。
- 大文件使用流式上传和下载。
- 解析、持仓和收益计算异步执行。

### 11.9 安全测试

- IDOR 水平越权。
- 垂直权限提升。
- 文件路径穿越。
- 恶意 MIME 和文件名 XSS。
- CSV 公式注入及 Excel 宏风险。
- JWT 重放和下载令牌过期。
- 批量导出越权。
- 审计链篡改。
- 日志敏感信息泄漏。

## 12. 持续集成流程

每次提交依次执行：

```text
代码格式和静态检查
→ 后端单元测试
→ 前端类型检查
→ 前端单元测试
→ 数据库迁移测试
→ API 集成测试
→ 前端生产构建
→ 文件安全测试
→ 权限回归测试
```

主分支合并后执行：

```text
构建发布包
→ 创建脱敏数据库副本
→ 完整迁移演练
→ 端到端测试
→ 生成测试报告
→ 人工审批发布
```

## 13. 发布与回滚

每次发布必须：

- 备份数据库、文件目录、`.env` 和本地配置。
- 保存发布前 Git commit。
- 运行数据库迁移预检。
- 执行迁移后数据数量和文件哈希核对。
- 新旧接口短期双读比较。
- 先对测试租户开放。
- 再按租户逐步灰度。
- 保留旧接口和旧页面至少一个发布周期。

数据库迁移遵循“扩展—迁移—切换—清理”：

1. 新增表和字段。
2. 后台迁移旧数据。
3. 新旧逻辑并行读取。
4. 切换新逻辑。
5. 旧结构转为只读。
6. 确认稳定后删除旧结构。

不得在同一发布中同时迁移数据并删除旧表。

## 14. 阶段完成标准

每个阶段只有同时满足以下条件才能结束：

- 功能实现完成。
- 权限矩阵验证完成。
- 审计和来源追溯完整。
- 单元、集成和端到端测试通过。
- 数据库升级和回滚演练通过。
- 无真实敏感数据进入测试样本。
- 文档、API 和迁移说明同步更新。
- 没有未解释的测试跳过项。
- 用户验收场景完成。

## 15. 推荐启动顺序

首先实施阶段 0 和阶段 1，冻结现有行为并建设主体、来源、文件版本和权限底座。

底座通过权限和迁移验收后，再实施公司与产品资料拆分。开户、投资者、基金经理、申赎、份额、持仓和收益模块均在同一框架内增量开发，避免后续再次进行结构性重写。

