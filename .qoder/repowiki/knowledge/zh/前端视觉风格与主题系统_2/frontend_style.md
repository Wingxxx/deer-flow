## 1. 核心系统与工具链
DeerFlow 前端采用 **Next.js (App Router)** 结合 **Tailwind CSS v4** 的现代化技术栈。视觉风格基于 **shadcn/ui** 组件库构建，遵循“New York”设计风格，强调简洁、高对比度和现代化的交互体验。

- **CSS 框架**: Tailwind CSS v4（使用 `@tailwindcss/postcss` 插件）。
- **动画库**: `tw-animate-css` 提供基础动画，配合自定义 CSS Keyframes（如 `fade-in`, `aurora`, `shine`）。
- **图标库**: `lucide-react`。
- **颜色系统**: 基于 **OKLCH** 色彩空间的设计令牌（Design Tokens），支持高精度的色彩感知一致性。

## 2. 主题与设计令牌 (Design Tokens)
项目通过 CSS 变量实现了一套完整的设计令牌系统，定义在 `frontend/src/styles/globals.css` 中。

### 颜色变量
所有颜色均使用 OKLCH 格式定义，支持浅色（Light）和深色（Dark）双模式：
- **基础色**: `--background`, `--foreground`, `--card`, `--popover`。
- **功能色**: `--primary` (主色调), `--secondary`, `--accent`, `--destructive` (警告/删除)。
- **界面色**: `--border`, `--input`, `--ring`, `--muted`。
- **侧边栏专用**: `--sidebar`, `--sidebar-primary`, `--sidebar-accent` 等，确保侧边栏在不同主题下的视觉独立性。

### 圆角系统
定义了统一的圆角基准 `--radius` (0.625rem)，并衍生出 `sm`, `md`, `lg`, `xl` 等层级，确保 UI 元素（按钮、卡片、输入框）的视觉圆润度一致。

## 3. 组件架构与样式约定
### shadcn/ui 集成
- **配置**: `components.json` 配置了 `style: "new-york"` 和 `cssVariables: true`。
- **变体管理**: 使用 `class-variance-authority` (CVA) 管理组件的多态样式。例如 `Button` 组件定义了 `default`, `destructive`, `outline`, `secondary`, `ghost`, `link` 六种变体。
- **实用函数**: 通过 `@/lib/utils` 中的 `cn` 函数合并 Tailwind 类名，处理条件样式冲突。

### 特殊视觉效果
- **Ambilight (环境光)**: 在 `globals.css` 中定义了 `.ambilight` 类，通过伪元素和彩虹渐变背景实现动态流光效果，常用于增强视觉吸引力。
- **Aurora & Shine**: 自定义了极光背景和光泽边框动画，用于提升关键 UI 元素的质感。
- **Golden Text**: 定义了 `.golden-text` 类，使用线性渐变裁剪文本，用于展示高级或特殊状态的文字。

## 4. 响应式与布局策略
- **容器查询**: 在 `globals.css` 中定义了 `.container-md`，利用 CSS `@media (width >= ...)` 实现流式布局，最大宽度适配不同屏幕尺寸（40rem 到 80rem）。
- **移动端适配**: 通过 `use-mobile.ts` Hook 检测视口宽度，配合 Tailwind 的断点类（如 `md:hidden`, `lg:block`）实现响应式组件切换。

## 5. 开发者规范
1. **样式编写**: 优先使用 Tailwind 实用类。避免在组件内编写内联 `style`，除非涉及动态计算值。
2. **主题扩展**: 新增颜色或动画时，应在 `globals.css` 的 `@theme` 块或 `:root`/`.dark` 选择器中定义 CSS 变量，保持设计令牌的中心化管理。
3. **组件变体**: 创建新 UI 组件时，应使用 CVA 定义 `variants` 和 `defaultVariants`，确保样式可配置且符合现有设计语言。
4. **深色模式**: 所有新组件必须验证在 `.dark` 类下的表现，确保使用语义化颜色变量（如 `bg-background` 而非 `bg-white`）。
