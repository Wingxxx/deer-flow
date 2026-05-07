# Slack 配置指南

Slack 通道使用 Socket Mode（WebSocket），无需公网 IP。

## 创建 Slack App

### 1. 创建应用

1. 访问 [Slack API](https://api.slack.com/)
2. 点击「Create an app」
3. 选择「From scratch」
4. 选择你的 Workspace
5. 填写应用名称

### 2. 配置 Bot Token

1. 进入「OAuth & Permissions」
2. 在「Bot Token Scopes」中添加以下权限：
   - `chat:write`
   - `chat:write.public`
   - `files:write`
   - `reactions:write`
   - `im:read`
   - `im:write`
   - `im:history`
   - `mpim:read`
   - `mpim:write`
   - `mpim:history`

### 3. 启用 Socket Mode

1. 进入「Socket Mode」
2. 点击「Enable Socket Mode」
3. 创建 App-Level Token（xapp-...）：
   - 点击「App-Level Tokens」
   - 点击「Generate Token with Scopes」
   - 命名（如 `deerflow-app-token`）
   - 添加 `connections:write` 权限
   - 生成并保存 Token

### 4. 配置事件订阅

1. 进入「Event Subscriptions」
2. 点击「Enable Events」
3. 在「Subscribe to bot events」中添加：
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`
   - `app_mention`

### 5. 开启 Message Content

1. 进入「App Home」
2. 在「Show Tabs」中启用「Home Tab」和「Message Tab」

### 6. 安装应用到 Workspace

1. 进入「Install App」
2. 点击「Install to Workspace」
3. 授权后获取 `Bot User OAuth Token`（xoxb-...）

## 配置 config.yaml

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN     # xoxb-...
    app_token: $SLACK_APP_TOKEN    # xapp-...
    allowed_users: []              # 空 = 允许所有用户

  session:
    assistant_id: lead_agent
    config:
      recursion_limit: 100
    context:
      thinking_enabled: true
```

## 配置环境变量

在 `.env` 文件中添加：

```bash
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx
SLACK_APP_TOKEN=xapp-xxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx
```

## Docker 部署配置

```yaml
channels:
  langgraph_url: http://langgraph:2024
  gateway_url: http://gateway:8001

  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN
    app_token: $SLACK_APP_TOKEN
    allowed_users: []
```

## 功能特性

- **交互方式**：在频道中 @机器人 或发送私信
- **线程支持**：回复会出现在原消息的线程中
- **状态显示**：处理消息时会显示 👀，完成后显示 ✅
- **文件上传**：支持直接上传文件
- **Markdown 转换**：自动将 Markdown 转换为 Slack 格式

## 权限控制

通过 `allowed_users` 限制访问用户：

```yaml
slack:
  enabled: true
  bot_token: $SLACK_BOT_TOKEN
  app_token: $SLACK_APP_TOKEN
  allowed_users:
    - U1234567890
    - U0987654321
```

## 故障排查

### 1. 无法接收消息

- 确认已在 Slack API 启用 Socket Mode
- 确认事件订阅已正确配置
- 检查 `bot_token` 和 `app_token` 是否正确

### 2. Socket Mode 连接失败

- 确认 `app_token` 具有 `connections:write` 权限
- 检查网络是否可以访问 Slack WebSocket 服务器

### 3. 无法发送消息

- 确认 Bot 具有 `chat:write` 权限
- 确认 Bot 已添加到对应频道

### 4. 权限错误

- 在「OAuth & Permissions」中检查 Bot Scopes
- 重新安装应用以获取新权限

## 相关文档

- [Slack Socket Mode](https://api.slack.com/apis/connections/socket)
- [Slack Events API](https://api.slack.com/events-api)
