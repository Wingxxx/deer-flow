# Telegram 配置指南

Telegram 通道使用 Bot API 长轮询方式，是配置最简单的方式。

## 创建 Bot

### 1. 通过 @BotFather 创建

1. 在 Telegram 中搜索 `@BotFather`
2. 发送命令 `/newbot`
3. 按提示输入 Bot 名称
4. 输入 Bot 用户名（必须以 `bot` 结尾）
5. 完成后会收到 Token，格式如：`123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`

### 2. 配置 Bot 命令（可选）

1. 与 `@BotFather` 对话
2. 发送 `/setcommands`
3. 选择你的 Bot
4. 输入命令列表：

```
new - 开始新对话
status - 查看当前状态
models - 列出可用模型
memory - 查看记忆状态
help - 显示帮助
```

### 3. 保护 Bot（可选）

1. 与 `@BotFather` 对话
2. 发送 `/setprivacy`
3. 选择你的 Bot
4. 选择「Disable」允许获取所有消息，或「Enable」只接收 @提及

## 配置 config.yaml

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN
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
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
```

## Docker 部署配置

```yaml
channels:
  langgraph_url: http://langgraph:2024
  gateway_url: http://gateway:8001

  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN
    allowed_users: []
```

## 权限控制

通过 `allowed_users` 限制只有特定用户可以使用：

```yaml
telegram:
  enabled: true
  bot_token: $TELEGRAM_BOT_TOKEN
  allowed_users:
    - 123456789
    - 987654321
```

## 功能特性

- **命令支持**：内置 `/start`, `/new`, `/status`, `/models`, `/memory`, `/help`
- **对话模式**：
  - 私聊：所有消息共享同一会话
  - 群组：回复原消息以保持同一会话
- **文件支持**：支持发送图片和文件（图片最大 10MB，文件最大 50MB）

## 使用方式

1. 在 Telegram 中找到你的 Bot
2. 发送 `/start` 或直接发送消息
3. Bot 会回复「Working on it...」然后返回结果
4. 使用 `/new` 开始新对话

## 故障排查

### 1. Bot 无响应

- 确认 Token 正确
- 检查 DeerFlow 日志是否有错误
- 确认 Bot 已经启动（应看到 `[Telegram] channel started`）

### 2. 无法识别用户

- 如果设置了 `allowed_users`，确认用户 ID 正确
- 用户 ID 可以通过 @userinfobot 获取

### 3. 消息发送失败

- 检查网络连接
- 确认 Telegram API 可访问
- 查看 DeerFlow 日志中的具体错误

### 4. 命令不工作

- 确认已在 @BotFather 中配置命令
- 私聊时命令应该总是工作
- 群组中可能需要 @提及 Bot

## 安全建议

1. **设置 allowed_users**：限制只有特定用户可以使用
2. **不要分享 Token**：将 Token 存储在环境变量中
3. **定期轮换 Token**：如有必要，可以通过 @BotFather 生成新 Token

## 相关文档

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [BotFather 指南](https://core.telegram.org/bots#botfather)
