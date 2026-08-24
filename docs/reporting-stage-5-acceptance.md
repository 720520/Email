# 报表平台阶段 5 验收记录

## 实现范围

- 固定官方 Document Server 镜像 `onlyoffice/documentserver:9.4.0.1`。
- `onlyoffice.public_url` / `internal_url` / `callback_base_url` / `jwt_secret` /
  `request_timeout` / `max_download_bytes` / `file_token_ttl_seconds` 全部配置化。
- `POST /api/v1/reports/runs/{run_id}/onlyoffice/session` 仅返回 `mode=view`。
- `GET /api/v1/onlyoffice/files/{token}` 使用 HS256 短期令牌，校验租户、
  ReportRun、当前文件版本、路径和大小。
- 编辑器完整 config 使用与 Document Server 一致的 JWT 密钥签名。
- 前端新增 `/reports/runs/:runId/editor`，动态加载 OnlyOffice `api.js`。
- Viewer、Operator 和 Admin 在本阶段都是只读模式。
- Document Server 不可用时页面显示明确错误，并保留 PPTX 下载按钮。

## 安全与自动化验收

- 配置 JWT 为标准三段 HS256，篡改后拒绝。
- 短期文件令牌过期后拒绝。
- 修改令牌内租户或文件版本后无法读取文件。
- Viewer 会话的 `editorConfig.mode=view` 且 `permissions.edit=false`。
- 文件读取只允许 `current_version_id`，不接受任意存储路径。
- 后端 126 项测试通过，前端 14 项测试通过，TypeScript 和生产构建通过。

## 待本机管理员完成的环境验收

当前 Ubuntu 未安装 Docker，且 `sudo` 需要本机终端交互输入管理员密码。
安装 Docker 并重新登录后，执行：

```bash
./一键启动.sh
docker compose -f compose.onlyoffice.yaml ps
curl -fsS http://127.0.0.1:8080/healthcheck
```

然后从报表中心对一份包含多页、中文、图表和图片的 PPTX 点击“在线预览”，
完成最后的浏览器视觉验收。
