# 数据治理阶段 1 验收说明

## 已实现底座

- `entity`：租户内统一主体，首批支持公司、产品、投资者、基金经理、机构和金融账户。
- `field_definition`：按主体类型管理字段、数据类型、展示规则和敏感等级。
- `field_value`：追加式保存字段事实、有效期、来源文件、来源位置、置信度和复核人。
- `source_document`：文件按 `document_key + version` 只追加版本，保存 SHA-256、来源渠道和敏感等级。
- `document_relation`：同一来源文件可以关联多个主体。
- `resource_grant`：在默认角色策略之上提供租户级或主体级显式授权。

新接口位于 `/api/v2`，现有 `/api/v1` 行为保持兼容。

## 权限规则

- 所有新表受统一租户查询和写入过滤器保护。
- 租户管理员默认可管理本租户资源。
- 运营人员可读写普通资料，只读用户只能读取普通资料。
- 平台管理员不会因平台身份自动获得敏感或高度敏感文件明文权限。
- 敏感文件下载同时要求 `download` 与 `sensitive_read`，且授权的敏感等级上限必须足够。
- 跨租户主体、字段、来源文件及授权 ID 统一返回不存在，不泄露资源是否真实存在。

## 审计与文件完整性

主体、字段定义、字段事实、文件上传下载和授权变化均进入现有 HMAC 追加式审计链。
下载来源文件前重新计算 SHA-256；磁盘内容与记录不一致时拒绝返回。数据库中的来源文件版本禁止更新和删除。

## 主要接口

```text
GET/POST  /api/v2/entities
GET       /api/v2/entities/{id}
GET/POST  /api/v2/field-definitions
GET/POST  /api/v2/entities/{id}/facts
GET/POST  /api/v2/documents
GET       /api/v2/documents/{id}/download
POST      /api/v2/permissions/grants
```

## 验收覆盖

- 空数据库升级、模型与迁移一致性、完整降级。
- 主体、字段事实及来源定位写入。
- 同一文件逻辑键的不可变版本递增。
- 跨租户主体读取、文件下载及文件关联写入全部失败。
- 平台管理员敏感文件默认拒绝，显式授权后放行。
- 审计动作、文件哈希与版本历史完整。
