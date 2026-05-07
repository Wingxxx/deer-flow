# Discord 配置指南

Discord 通道使用 discord.py 库连接，支持 Discord Bot 的完整功能。

## 创建 Discord Bot

### 1. 创建 Application

1. 访问 [Discord Developer Portal](https://discord.com/developers/applications)
2. 点击「New Application」
3. 输入应用名称
4. 在「General Information」中获取 `Application ID`

### 2. 创建 Bot User

1. 进入「Bot」页面
2. 点击「Add Bot」
3. 确认创建
4. 在「Token」区域点击「Reset Token」生成新 Token
5. **保存生成的 Token**（只显示一次）

### 3. 配置 Intents

1. 在「Bot」页面下拉到底部
2. 找到「Privileged Gateway Intents」
3. 启用以下 Intents：
   - **MESSAGE CONTENT INTENT**（必须启用才能读取消息内容）
   - **SERVER MEMBERS INTENT**（可选，用于获取成员信息）
   - **PRESENCE INTENT**（可选）

### 4. 配置 OAuth2

1. 进入「OAuth2」→「URL Generator」
2. 在「Scopes」中选择：
   - `bot`
   - `applications.commands`
3. 在「Bot Permissions」中选择：
   - `Send Messages`
   - `Create Public Threads`
   - `Send Messages in Threads`
   - `Add Reactions`
   - `Attach Files`
   - `Read Message History`

### 5. 添加 Bot 到服务器

1. 使用上一步生成的 URL
2. 在浏览器中打开并授权
3. 选择要添加到的服务器

## 配置 config.yaml

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  discord:
    enabled: true
    bot_token: $DISCORD_BOT_TOKEN
    allowed_guilds: []              # 空 = 允许所有服务器

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
DISCORD_BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Docker 部署配置

```yaml
channels:
  langgraph_url: http://langgraph:2024
  gateway_url: http://gateway:8001

  discord:
    enabled: true
    bot_token: $DISCORD_BOT_TOKEN
    allowed_guilds: []
```

## 安装依赖

确保已安装 discord.py：

```bash
cd backend
uv add discord.py
```

## 功能特性

- **交互方式**：在频道中 @机器人 或发送私信
- **线程支持**：会自动为消息创建线程
- **文件上传**：支持发送文件
- **长消息分割**：自动分割超过 2000 字符的消息

## 权限控制

### 服务器级别限制

```yaml
discord:
  enabled: true
  bot_token: $DISCORD_BOT_TOKEN
  allowed_guilds:
    - 123456789012345678
    - 987654321098765432
```

### Bot 权限设置

在 Discord Developer Portal 的「OAuth2」→「URL Generator」中，可以生成精确的权限 URL。

## 故障排查

### 1. Bot 无法登录

- 确认 Token 正确
- 检查 Token 是否被重置
- 确认 Bot 账号没有被封禁

### 2. 无法接收消息

- 确认已启用 `MESSAGE CONTENT INTENT`
- 确认 Bot 已添加到服务器
- 检查 Bot 是否具有读取消息的权限

### 3. 无法发送消息

- 确认 Bot 具有「发送消息」权限
- 检查 Bot 是否被禁止在特定频道发言

### 4. 线程创建失败

- 确认服务器具有线程功能
- 检查 Bot 是否具有「创建线程」权限
- 部分频道可能禁用了线程

### 5. 依赖问题

确保安装了正确版本的 discord.py：

```bash
uv add discord.py
```

## 权限检查清单

确保 Bot 在服务器中具有以下权限：

| 权限 | 用途 |
|------|------|
| Send Messages | 发送消息 |
| Create Public Threads | 创建线程 |
| Send Messages in Threads | 在线程中发送消息 |
| Add Reactions | 添加反应 |
| Attach Files | 发送文件 |
| Read Message History | 读取历史消息 |

## 安全建议

1. **保护 Token**：将 Token 存储在环境变量中，不要硬编码
2. **定期轮换**：如有必要，可以在 Developer Portal 重置 Token
3. **限制服务器**：通过 `allowed_guilds` 限制 Bot 只能在特定服务器工作

## 相关文档

- [Discord Developer Portal](https://discord.com/developers/applications)
- [discord.py 文档](https://discordpy.readthedocs.io/)
- [Discord API 文档](https://discord.com/developers/docs)
