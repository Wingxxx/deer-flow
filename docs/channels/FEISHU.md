# 飞书 / Lark 配置指南

飞书通道使用 WebSocket 长连接方式，无需公网 IP 或配置 Webhook。

## 创建飞书应用

### 1. 创建应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 登录后进入「开发者后台」
3. 点击「创建企业自建应用」
4. 填写应用名称和描述
5. 创建完成后，在「基本信息」中获取 `App ID` 和 `App Secret`

### 2. 配置权限

1. 进入「权限管理」
2. 添加以下权限：
   - `im:message`（发送消息）
   - `im:message.receive_v1`（接收消息）
   - `im:message.group_at_msg`（群@消息）
   - `im:message.p2p_msg`（私聊消息）
   - `im:message.read`（读取消息）
   - `im:file`（文件操作）

### 3. 配置事件订阅

1. 进入「事件与回调」
2. 启用「使用长连接接收事件」
3. 添加事件：
   - `im.message.receive_v1`（接收消息）

### 4. 配置应用功能

1. 进入「应用功能」→「机器人」
2. 开启「机器人」功能
3. 添加机器人名称和描述

## 配置 config.yaml

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  feishu:
    enabled: true
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET
    # domain: https://open.feishu.cn       # 中国区（默认）
    # domain: https://open.larksuite.com   # 国际版

  # 可选：全局会话设置
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
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
```

## Docker 部署配置

如果使用 Docker 部署，需要使用容器服务名：

```yaml
channels:
  langgraph_url: http://langgraph:2024
  gateway_url: http://gateway:8001

  feishu:
    enabled: true
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET
```

在 `docker/.env` 中设置环境变量：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
```

## 功能特性

- **消息类型**：支持文本、图片、文件、@提及、话题帖子
- **交互方式**：回复会出现在原消息的线程中
- **状态显示**：处理消息时会显示「Working on it...」，完成后显示「DONE」表情
- **Markdown 支持**：支持 Markdown 格式的消息内容
- **会话隔离**：群聊中不同话题使用不同会话线程

## 故障排查

### 1. 应用无法接收消息

- 确认已在飞书开放平台开启「机器人」功能
- 确认已添加 `im.message.receive_v1` 事件订阅
- 确认应用已发布或处于测试状态

### 2. 消息发送失败

- 确认应用具有 `im:message` 权限
- 确认 App ID 和 App Secret 正确
- 检查网关日志中的具体错误信息

### 3. 长连接断开

- 检查网络连接是否稳定
- 确认防火墙没有阻止 WebSocket 连接
- 应用可能需要重新启动以恢复连接

### 4. 权限不足

- 在飞书开放平台的「权限管理」中确认已添加所有必需权限
- 如果应用已发布，可能需要重新审核权限

## 国际版 Lark

如果使用国际版 Lark，需要在配置中指定域名：

```yaml
feishu:
  enabled: true
  app_id: $FEISHU_APP_ID
  app_secret: $FEISHU_APP_SECRET
  domain: https://open.larksuite.com
```

## 相关文档

- [飞书开放平台文档](https://open.feishu.cn/document/home/)
- [长连接文档](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/subscribe-event)
