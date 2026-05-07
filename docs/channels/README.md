# DeerFlow 消息通道集成操作手册

DeerFlow 支持通过多种即时通讯平台与 AI Agent 进行交互。所有通道均采用**出站连接**方式（WebSocket 或长轮询），**无需公网 IP** 或暴露 Webhook 接口。

## 支持的平台

| 平台 | 传输方式 | 难度 | 文档 |
|------|----------|------|------|
| Telegram | Bot API（长轮询） | 简单 | [TELEGRAM.md](./TELEGRAM.md) |
| Slack | Socket Mode | 中等 | [SLACK.md](./SLACK.md) |
| 飞书 / Lark | WebSocket | 中等 | [FEISHU.md](./FEISHU.md) |
| 微信 | 腾讯 iLink（长轮询） | 中等 | [WECHAT.md](./WECHAT.md) |
| 企微 | WebSocket | 中等 | [WECOM.md](./WECOM.md) |
| Discord | discord.py | 中等 | [DISCORD.md](./DISCORD.md) |

## 通用配置

所有通道配置均在 `config.yaml` 的 `channels` 段中完成。

### 基础配置

```yaml
channels:
  # LangGraph Server 地址（默认: http://localhost:2024）
  # Docker 部署时使用容器服务名：
  langgraph_url: http://langgraph:2024

  # Gateway API 地址（默认: http://localhost:8001）
  gateway_url: http://gateway:8001

  # 可选：全局会话设置（所有通道的默认值）
  session:
    assistant_id: lead_agent  # 或自定义 Agent 名称
    config:
      recursion_limit: 100
    context:
      thinking_enabled: true
      is_plan_mode: false
      subagent_enabled: false
```

### 环境变量

在 `.env` 文件中设置各平台的凭证：

```bash
# 飞书
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx

# Slack
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxxxxxxxxxx
SLACK_APP_TOKEN=xapp-xxxxxxxxxxxxxxxxxxxx

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ

# 微信
WECHAT_BOT_TOKEN=your_bot_token_here
WECHAT_ILINK_BOT_ID=your_ilink_bot_id

# 企微
WECOM_BOT_ID=your_bot_id
WECOM_BOT_SECRET=your_bot_secret

# Discord
DISCORD_BOT_TOKEN=your_discord_bot_token
```

## 快速开始

1. **选择平台**：根据上方难度等级，推荐新手从 **Telegram** 开始

2. **创建应用**：按照对应文档创建应用并获取凭证

3. **配置 config.yaml**：将凭证配置到 `channels` 段

4. **设置环境变量**：在 `.env` 文件中设置凭证

5. **重启服务**：

   ```bash
   # 本地开发
   make dev

   # Docker 部署
   docker compose down && docker compose up -d
   ```

6. **验证**：向 Bot 发送消息，测试是否正常工作

## 常用命令

各平台支持的命令：

| 命令 | 说明 |
|------|------|
| `/new` | 开始新对话 |
| `/status` | 查看当前状态 |
| `/models` | 列出可用模型 |
| `/memory` | 查看记忆状态 |
| `/help` | 显示帮助信息 |

## 权限控制

可以使用 `allowed_users` 限制只有特定用户可以与 Bot 交互：

```yaml
channels:
  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN
    allowed_users:
      - 123456789
      - 987654321
```

## 文件传输

所有通道都支持发送文件，但有不同的限制：

| 平台 | 图片限制 | 文件限制 |
|------|----------|----------|
| 飞书 | 10MB | 30MB |
| Slack | 无限制 | 无限制 |
| Telegram | 10MB | 50MB |
| 微信 | 20MB | 50MB |
| 企微 | 2MB | 20MB |
| Discord | 8MB（免费版） | 8MB（免费版） |

## 故障排查

1. **检查日志**：
   ```bash
   docker logs deer-flow-gateway --tail 100
   ```

2. **确认通道已启动**：日志中应显示类似 `[Feishu] channel started` 的消息

3. **验证凭证**：确保环境变量已正确设置，且没有引号或空格

4. **检查网络**：确保容器可以访问对应平台的 API

5. **查看通道文档**：每个平台文档都有特定的故障排查章节
