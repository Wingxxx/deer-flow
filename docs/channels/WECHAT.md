# 微信配置指南

微信通道通过腾讯 iLink 接口连接，支持长轮询方式接收消息。

## iLink 机器人简介

iLink 是腾讯提供的企业微信/微信机器人接口服务。使用此通道需要：

1. 企业微信账号（推荐）
2. 或使用 iLink 平台提供的 QR 码登录功能

## 配置方式一：使用 Bot Token

### 1. 获取企业微信应用

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/)
2. 进入「应用管理」
3. 创建自建应用或使用现有应用
4. 获取 `AgentId` 和 `Secret`

### 2. 配置应用权限

1. 在企业微信管理后台，进入应用详情
2. 确保应用具有「发消息」权限

### 3. 配置应用监听

企业微信使用回调模式，需要：
- 公网可访问的 Webhook URL
- 设置回调 Token 和 EncodingAESKey

**注意**：此方式需要公网 IP 或内网穿透配置，相对复杂。

## 配置方式二：使用 QR 码登录（推荐）

如果无法使用企业微信，可以启用 QR 码登录功能：

```yaml
channels:
  wechat:
    enabled: true
    qrcode_login_enabled: true     # 启用 QR 码登录
    allowed_users: []
    polling_timeout: 35
    state_dir: ./.deer-flow/wechat/state
```

首次启动时，系统会生成 QR 码供扫描授权。

## 配置 config.yaml

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  wechat:
    enabled: true
    bot_token: $WECHAT_BOT_TOKEN
    ilink_bot_id: $WECHAT_ILINK_BOT_ID
    qrcode_login_enabled: false     # 是否启用 QR 码登录
    allowed_users: []               # 空 = 允许所有用户
    polling_timeout: 35             # 长轮询超时（秒）
    state_dir: ./.deer-flow/wechat/state

    # 可选：通道级会话覆盖
    session:
      assistant_id: mobile-agent
      context:
        thinking_enabled: false

    # 可选：文件大小限制
    max_inbound_image_bytes: 20971520      # 20MB
    max_outbound_image_bytes: 20971520     # 20MB
    max_inbound_file_bytes: 52428800        # 50MB
    max_outbound_file_bytes: 52428800       # 50MB

    # 可选：允许的文件类型
    allowed_file_extensions:
      - ".txt"
      - ".md"
      - ".pdf"
      - ".csv"
      - ".json"
      - ".yaml"
      - ".doc"
      - ".docx"
      - ".xls"
      - ".xlsx"
```

## 配置环境变量

在 `.env` 文件中添加：

```bash
WECHAT_BOT_TOKEN=your_bot_token_here
WECHAT_ILINK_BOT_ID=your_ilink_bot_id
```

## Docker 部署配置

```yaml
channels:
  langgraph_url: http://langgraph:2024
  gateway_url: http://gateway:8001

  wechat:
    enabled: true
    bot_token: $WECHAT_BOT_TOKEN
    ilink_bot_id: $WECHAT_ILINK_BOT_ID
    qrcode_login_enabled: false
    allowed_users: []
    state_dir: ./.deer-flow/wechat/state
```

## 功能特性

- **消息类型**：支持文本、图片、文件
- **加密传输**：所有消息使用 AES-128-ECB 加密
- **长轮询**：无需 Webhook，节省服务器资源
- **状态持久化**：轮询游标和认证状态保存到本地文件

## 文件限制

| 类型 | 入站 | 出站 |
|------|------|------|
| 图片 | 20MB | 20MB |
| 文件 | 50MB | 50MB |

## 故障排查

### 1. 无法连接

- 确认 `bot_token` 和 `ilink_bot_id` 正确
- 检查网络是否可以访问 iLink 服务器

### 2. QR 码登录失败

- 确认 `qrcode_login_enabled` 设置正确
- 检查日志中的 QR 码状态
- 扫码超时时间默认 180 秒

### 3. Token 过期

- 如果 Bot Token 过期，需要重新获取并更新配置
- 日志会显示 `[WeChat] bot token expired` 信息

### 4. 消息接收不到

- 检查 `allowed_users` 配置
- 确认应用具有接收消息的权限

### 5. 文件传输失败

- 检查文件大小是否超过限制
- 确认文件类型在允许列表中

## 状态文件

微信通道会在 `state_dir` 目录保存状态：

- `wechat-auth.json`：认证信息和 Token
- `wechat-getupdates.json`：轮询游标
- `downloads/`：接收的文件

## 相关文档

- [企业微信开发文档](https://developer.work.weixin.qq.com/document/)
- [iLink 接口文档](https://ilinkai.weixin.qq.com/)
