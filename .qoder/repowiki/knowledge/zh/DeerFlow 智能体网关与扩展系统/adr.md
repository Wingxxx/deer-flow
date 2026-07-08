# 采用 Nginx 同源反向代理实现 DeerFlow 嵌入 ADS

_来源：7a9313b → cf0dff2 提交周期内记录的编码计划——内容为规划时意图，实现可能滞后或有出入。_

**状态：** accepted

## 背景
DeerFlow（Next.js + FastAPI）需嵌入 ADS（Spring Boot + Shiro）界面。两者原运行在不同端口（443 vs 2026），导致跨域问题且 Cookie 无法共享。为避免修改 ADS 核心代码并实现单点登录体验，需统一入口。

## 决策驱动
- 同源策略下 Cookie 自动共享，无需 postMessage 或复杂会话同步
- 最小化对 ADS 代码的侵入（仅修改 Nginx配置和少量模板）
- 保持 DeerFlow 独立部署架构，仅通过网关层集成

## 备选方案
- **Nginx 同源反向代理（选定方案）** — 优点：利用浏览器同源特性自动共享 Cookie；ADS 与 DeerFlow 会话隔离（JSESSIONID vs access_token）；无需修改 ADS 后端逻辑；支持 iframe 嵌入；缺点：需维护 Nginx 路由规则；前端需配置 basePath 以适配子路径
- **跨域 iframe + postMessage 通信** — 优点：无需改变现有端口部署结构；缺点：需手动处理登录状态同步；开发复杂度高；存在潜在安全风险；用户体验不如同源无缝

## 决策
在 ADS 的 Nginx 443 服务中通过 include 注入 DeerFlow 的反向代理配置，将 /deerflow/ 路径映射至 DeerFlow 前端，/deerflow/api/ 映射至 Gateway。关闭 DeerFlow 独立的 2026 端口。前端启用 Next.js basePath: '/deerflow'。用户首次访问时通过 DeerFlow 提供的 ADS 登录页完成认证，后续依靠同源 Cookie 维持会话。

## 影响
实现了 ADS 与 DeerFlow 的单点登录体验（一次输入密码，Cookie 自动生效）。DeerFlow 前端所有资源路径自动添加 /deerflow 前缀。ADS 与 DeerFlow 的会话完全隔离，互不干扰。Nginx 配置复杂度略有增加，需维护 deerflow-locations.inc 文件。