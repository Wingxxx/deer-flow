## 1. 核心样式体系
DeerFlow 前端采用 **Tailwind CSS v4** 作为核心样式引擎，配合 **shadcn/ui** 组件库构建统一的视觉语言。项目摒弃了传统的 `tailwind.config.js`，转而使用 Tailwind v4 的 CSS-first 配置方式（在 `globals.css` 中通过 `@theme` 定义设计令牌）。

### 关键技术栈
- **CSS 框架**: Tailwind CSS v4 (`@tailwindcss/postcss`)
- **动画库**: `tw-animate-css` (提供标准化的进入/退出动画)
- **组件库**: shadcn/ui (基于 Radix UI primitives)
- **图标库**: Lucide React
- **工具函数**: `clsx` + `tailwind-merge` (通过 `cn()` 处理类名合并冲突)

## 2. 设计令牌与主题 (Design Tokens)
项目在 `frontend/src/styles/globals.css` 中定义了基于 **OKLCH** 色彩空间的设计令牌，支持精细化的明暗模式切换。

### 色彩系统
- **基础色板**: 使用 OKLCH 格式定义 `--background`, `--foreground`, `--primary`, `--secondary`, `--muted`, `--accent` 等语义化颜色。
- **浅色模式**: 背景为极浅的暖灰色 (`oklch(0.9855 ...)`), 主色为纯黑 (`oklch(0 0 0)`)。
- **深色模式**: 背景为深灰褐色 (`oklch(0.24 ...)`), 主色为纯白 (`oklch(1 0 0)`)，并降低了字体粗细 (`font-weight: 300`) 以提升可读性。
- **图表色**: 定义了 5 种专用的图表颜色 (`--chart-1` 至 `--chart-5`)，确保数据可视化的一致性。

### 圆角与间距
- **圆角变量**: 定义了从 `--radius-sm` 到 `--radius-4xl` 的层级化圆角系统，基准值为 `0.625rem`。
- **响应式容器**: 自定义了 `.container-md` 类，在不同断点下限制最大宽度。

## 3. 动画与交互效果
项目集成了丰富的微交互动画，增强 AI 交互的流畅感：
- **内置动画**: 在 `@theme` 中定义了 `fade-in`, `fade-in-up`, `bouncing` (用于加载状态), `skeleton-entrance`, `aurora` (极光背景) 等关键帧。
- **特殊效果**:
  - **Ambilight**: 实现了类似环境光的彩色渐变边框效果，仅在特定条件下启用。
  - **Golden Text**: 定义了金色渐变文字样式，用于强调关键信息。
  - **Shine & Aurora**: 用于卡片或边框的动态光泽效果。

## 4. 架构约定与开发规范
### 组件组织
- **UI 原语**: 所有基础 UI 组件位于 `frontend/src/components/ui/`，遵循 shadcn/ui 的目录结构。
- **业务组件**: 复杂交互组件位于 `frontend/src/components/workspace/` 和 `frontend/src/components/ai-elements/`。
- **扩展机制**: 通过 `frontend/extensions/` 目录支持插件化 UI 扩展（如 ADS 认证登录页、环境设置页）。

### 样式编写规范
1. **优先使用 Utility Classes**: 直接在 JSX 中使用 Tailwind 类名，避免编写自定义 CSS。
2. **使用 `cn()` 工具**: 在组件内部合并类名时，必须使用 `src/lib/utils.ts` 导出的 `cn()` 函数，以确保 `tailwind-merge` 能正确处理冲突类名。
3. **语义化颜色**: 严禁硬编码颜色值（如 `bg-gray-100`），应使用语义化变量（如 `bg-muted`, `text-foreground`）以适配主题切换。
4. **主题强制**: 首页 (`/`) 强制使用深色模式，其他页面跟随用户系统偏好或本地存储设置（通过 `next-themes` 管理）。

## 5. 关键文件索引
- `frontend/src/styles/globals.css`: 全局样式入口，包含 Tailwind 导入、设计令牌定义及自定义动画。
- `frontend/components.json`: shadcn/ui 配置文件，定义了组件别名、图标库及注册表来源。
- `frontend/src/components/theme-provider.tsx`: 主题上下文提供者，处理明暗模式逻辑。
- `frontend/src/lib/utils.ts`: 提供 `cn()` 类名合并工具及通用链接样式常量。