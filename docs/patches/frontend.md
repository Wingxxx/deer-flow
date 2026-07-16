# 前端补丁

## A6：`next.config.js` — 路由层重写 `/` 和 `/login` → `/ads-login`

**文件**: `frontend/next.config.js`
**风险**: ✅ 低（`{beforeFiles, afterFiles, fallback}` 为 Next.js 标准 API 格式，不是侵入性改动）

在 `async rewrites()` 中，返回格式从扁平数组改为标准对象格式：

```javascript
return {
  beforeFiles: [
    { source: "/", destination: "/ads-login" },
    { source: "/login", destination: "/ads-login" },
    { source: "/login/:path*", destination: "/ads-login/:path*" },
  ],
  afterFiles: [
    // ... 原有 API proxy rewrites
  ],
  fallback: [],
};
```

**为什么没有更小侵入的方案**:
- `beforeFiles` 是 Next.js 官方路由文档推荐的路径替换方式。扁平数组（`rewrites()` 返回数组）等价于 `afterFiles`，路由优先级低于页面组件，无法覆盖 `/` 和 `/login` 这类已存在的页面路由。
- `redirects()` 返回扁平数组不改格式，但触发 301/302 导致地址栏 URL 变化，用户体验差。
- `{beforeFiles, afterFiles, fallback}` 不是侵入性更改——它是 Next.js 的**完整 API 格式**，扁平数组只是它的简化糖。

---

## A7：`frontend/middleware.ts` — Next.js Middleware 内联（路由保护 + 重写）

**文件**: `frontend/middleware.ts`
**风险**: ✅ 低

之前该文件只有 1 行 re-export：`export { middleware, config } from "./extensions/ads_auth/middleware-handler";`

现在内联为完整 37 行 middleware，包含：

1. **公开路径跳过**: `/_next`、`/favicon.ico`、`/images`、`/ads-login`、`/site.config.json` 直接 `next()`
2. **主页预检（2026-05-29 新增）**: `/` → 先检查 `access_token` cookie，有则 302 到 `/workspace`，无则 rewrite 到 `/ads-login`
3. **登录页重写**: `/login` → rewrite 到 `/ads-login`
4. **Token 守卫**: 无 `access_token` cookie 时 redirect 到 `/login?next=原路径`

**注意**: `next.config.js` 的 `beforeFiles` 优先级高于 middleware，所以第 2、3 步在实际运行中不会被触发（请求到 `/` 已在路由层被改写）。保留它们是为了**文档对称性和回退安全性**——如果未来去掉了 `beforeFiles`，middleware 仍能兜底。

**变更记录**:
- 初始内联（A7）: `/_next`、`/favicon.ico`、`/images`、`/ads-login`
- **2026-06-30 新增** `/site.config.json`: 品牌自定义配置静态文件需绕过中间件认证，否则客户端 `fetch()` 被 307 重定向导致品牌配置加载失败

---

## A8：`frontend/src/core/auth/types.ts` — 登录 URL 路由到 ADS

**文件**: `frontend/src/core/auth/types.ts`
**行号**: L29
**风险**: ✅ 极低

**改动**:
```diff
 export function buildLoginUrl(returnPath: string): string {
-  return `/login?next=${encodeURIComponent(returnPath)}`;
+  return `/ads-login?next=${encodeURIComponent(returnPath)}`;
 }
```

**原因**: `buildLoginUrl` 被客户端代码调用，生成跳转到登录页的 URL。原值 `/login` 会被 `next.config.js` 的 `beforeFiles` rewrite 到 `/ads-login`，但在某些客户端路由场景下，直接输出 `/ads-login` 更可靠（避免客户端 router 绕开 rewrite）。

---

---

## S1：`settings-dialog.tsx` — 4 处 EXTENSION SLOT 插槽

**文件**: `frontend/src/components/workspace/settings/settings-dialog.tsx`
**风险**: ✅ 低（扩展插槽模式，不修改原有行为，向后兼容）

### S1a — Props 中增加扩展插槽（L42-L51）

```typescript
type SettingsDialogProps = React.ComponentProps<typeof Dialog> & {
  defaultSection?: SettingsSection;
  // --- EXTENSION SLOT: begin ---
  additionalSections?: Array<{
    id: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    component: React.ComponentType;
  }>;
  hiddenSectionIds?: string[];
  // --- EXTENSION SLOT: end ---
};
```

**原因**: 新增 `additionalSections`（外部注入的页面配置）和 `hiddenSectionIds`（隐藏内置页面）两个可选 props，第三方扩展可通过该接口向设置弹窗注入自定义设置页面。

### S1b — 解构赋值带默认值（L54-L56）

```typescript
  // --- EXTENSION SLOT: begin ---
  const { defaultSection = "account", additionalSections = [], hiddenSectionIds = [], ...dialogProps } = props;
  // --- EXTENSION SLOT: end ---
```

**变更记录**:
- 初始: `defaultSection = "appearance"`
- **2026-06-30 修改**: 改为 `"account"` — 外观页被隐藏后，默认打开第一个可见 Tab（账号页）

**原因**: 将新 props 从 props 中解构出来，并设置安全的默认值（空数组），确保未传值时行为不变。

### S1c — sections 数组合并扩展页面（L69-L117）

```typescript
  const sections = useMemo(
    () => [
      // --- EXTENSION SLOT: begin ---
      ...[
        { id: "account", ... },
        { id: "appearance", ... },
        // ... 内置 sections
        { id: "about", ... },
      ].filter((s) => !hiddenSectionIds.includes(s.id)),
      ...additionalSections.map((s) => ({
        id: s.id,
        label: s.label,
        icon: s.icon,
      })),
      // --- EXTENSION SLOT: end ---
    ],
    [
      // ... 原有依赖
      // --- EXTENSION SLOT: begin ---
      hiddenSectionIds.join(","),
      additionalSections,
      // --- EXTENSION SLOT: end ---
    ],
  );
```

**改动要点**:
1. 内置 sections 数组用 spread `...[array].filter(...)` 包起来，通过 `hiddenSectionIds` 过滤
2. 在末尾追加 `...additionalSections.map(...)`，将扩展页面添加到侧边栏导航
3. `useMemo` 的依赖数组中增加 `hiddenSectionIds.join(",")` 和 `additionalSections`

**原因**: 将内置 sections 和扩展 sections 合并为一个渲染数组。使用 `filter` 隐藏可被扩展隐藏的内置页面。

### S1d — 渲染区域增加扩展页面（L171-L173）

```typescript
              {/* --- EXTENSION SLOT: begin --- */}
              {additionalSections?.map((s) => activeSection === s.id ? <s.component /> : null)}
              {/* --- EXTENSION SLOT: end --- */}
```

**原因**: 在 `activeSection` 匹配时渲染扩展组件。原有条件渲染模式不变，扩展组件通过 `additionalSections` 数组匹配渲染。

---

## S2：`registry.ts` — SettingsExtension 注册表（新文件）

**文件**: `frontend/src/core/settings-extensions/registry.ts`
**风险**: ✅ 极低（全新文件，不影响现有代码）

```typescript
import type { LucideIcon } from "lucide-react";

export interface SettingsExtension {
  id: string;
  label: string;
  icon: LucideIcon;
  component: React.ComponentType;
}

const _extensions: SettingsExtension[] = [];

export function registerSettingsExtension(ext: SettingsExtension): void {
  if (_extensions.some((e) => e.id === ext.id)) return;
  _extensions.push(ext);
}

export function getSettingsExtensions(): SettingsExtension[] {
  return [..._extensions];
}

export function clearSettingsExtensions(): void {
  _extensions.length = 0;
}
```

**配套文件**: `frontend/src/core/settings-extensions/index.ts`（re-export）

**原因**: 提供类型安全的正向注册机制：
- `registerSettingsExtension()` — 扩展模块调用，将自身注册到中央列表（id 去重）
- `getSettingsExtensions()` — 返回当前所有已注册扩展的快照
- `clearSettingsExtensions()` — 测试场景中清空注册表

---

## S3：`workspace-nav-menu.tsx` — 集成扩展注册表

**文件**: `frontend/src/components/workspace/workspace-nav-menu.tsx`
**风险**: ✅ 低

### S3a — import 扩展注册表 + 扩展模块（L30-L35）

```typescript
import { getSettingsExtensions } from "@/core/settings-extensions";
// --- EXTENSION IMPORT: begin ---
import "@/core/env-settings/extension";
// --- EXTENSION IMPORT: end ---
```

**原因**: 
- `getSettingsExtensions` — 获取已注册的扩展列表并传入 `SettingsDialog`
- `import "@/core/env-settings/extension"` — side-effect import，触发 `registerSettingsExtension()` 注册 env-settings 扩展页面

### S3b — 将扩展透传到 SettingsDialog（L70-L80）

```typescript
  const extensions = getSettingsExtensions();

  return (
    <>
      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        defaultSection={settingsDefaultSection}
        additionalSections={extensions}
        hiddenSectionIds={[]}
      />
```

**原因**: 
- `getSettingsExtensions()` 获取所有已注册的扩展页面列表
- 通过 `additionalSections` prop 传递给 `SettingsDialog`
- `hiddenSectionIds` 设为空数组（不隐藏任何内置页面）

### S3c — settingsDefaultSection 默认值改为 account（2026-06-30）

**行号**: L65-L67

```typescript
const [settingsDefaultSection, setSettingsDefaultSection] = useState<
  "account" | "appearance" | "memory" | "tools" | "skills" | "notification" | "about"
>("account");
```

**变更**:
- 初始: `"appearance"`（类型不含 `"account"`）
- **2026-06-30 修改**: 类型追加 `"account"`，默认值改为 `"account"`

**原因**: 外观 Tab 已被 `hiddenSectionIds` 隐藏，但默认打开的 Tab 仍为 `"appearance"`，导致设置面板打开时显示空白。改为 `"account"` 使首次打开时聚焦于账号页。

**附带修改**: `SettingsDialog` 的 onClick 行（L107） `setSettingsDefaultSection("appearance")` 同步改为 `"account"`，否则该处会覆盖 state 初始值。

---

## S4：`account-settings-page.tsx` — ADS 账号字段隐藏

**文件**: `frontend/src/components/workspace/settings/account-settings-page.tsx`
**风险**: ✅ 极低（仅注释隐藏代码，不删除，恢复时删除注释块即可）

### S4a — 隐藏 email/role 显示

原代码显示 `user.email`（固定为 `admin@example.com`）和 `user.system_role`（固定为 `user`），均为 ADS 占位值。改为只显示从 email 前缀提取的 ADS 账号名。

```typescript
{/*
// 🚫 以下两行被隐藏——原因：
//    当前使用 ADS 统一认证登录，返回的 email 为固定的
//    "admin@example.com", system_role 为 "user"，均为占位值
//    不反映实际 ADS 账号信息，显示出来会误导用户。
//    改为只显示 ADS 账号名（从 email 前缀提取）。
// ================================================================
*/}
<span className="text-muted-foreground text-sm">账号</span>
<span className="text-sm font-medium">
  {user?.email ? user.email.replace(/@.*$/, "") : "—"}
</span>
```

### S4b — 隐藏修改密码表单

ADS 密码由统一认证管理，DeerFlow 原生 change-password API 不可用。整个 `SettingsSection` 包裹在 JSX 注释块中。

```typescript
{/*
// 🚫 修改密码表单被隐藏——原因：
//    ADS 密码由统一认证管理，DeerFlow 原生 change-password API 不可用。
// ==================================================================
*/}
<SettingsSection
  title={t.settings.account.changePasswordTitle}
  ...
```

**原因**: ADS 统一认证登录后，user.email 固定为 "admin@example.com"、system_role 为 "user"（占位值），原生修改密码 API 不可用。隐藏不正确的字段和不可用的功能。

**验证命令**:
```bash
# 确认 email/role 被注释隐藏（输出不应显示 email/role 翻译 key）
grep -c "t\.settings\.account\.email\|t\.settings\.account\.role" \
  frontend/src/components/workspace/settings/account-settings-page.tsx
# 应输出 0（已隐藏）

# 确认"账号"行可见
grep -c "账号" frontend/src/components/workspace/settings/account-settings-page.tsx
# 应输出 1（从 email 前缀提取的账号名）

# 确认修改密码表单被注释包裹
grep -c "修改密码表单被隐藏" \
  frontend/src/components/workspace/settings/account-settings-page.tsx
# 应输出 1
```

**恢复方法**: 删除 `{/*` 注释开始标记和 `*/}` 注释结束标记之间的代码块，并删掉新加的"账号"行。

---

## A9：`frontend/extensions/ads_auth/LoginPage.tsx` — loading 转圈（2026-05-29 新增）

**文件**: `frontend/extensions/ads_auth/LoginPage.tsx`
**风险**: ✅ 极低（扩展目录）

**改动**: 新增 `isLoading` 状态变量，初始化时全屏居中显示 `Loader2Icon` 旋转动画。fetch `/auth/me` 确认未认证后才隐藏 loading、渲染表单。

**原因**: 消除已登录用户首次渲染时闪现登录表单的问题（与 middleware 预检配合，双层保障）。

---

## A10：`frontend/src/core/auth/server.ts` — E2E 后门 NODE_ENV 门控（2026-05-29 新增）

**文件**: `frontend/src/core/auth/server.ts`
**行号**: L13
**风险**: ✅ 极低

**改动**:
```typescript
// 修改前：
if (process.env.DEER_FLOW_AUTH_DISABLED === "1") {
// 修改后：
if (process.env.NODE_ENV === "test" && process.env.DEER_FLOW_AUTH_DISABLED === "1") {
```

**原因**: E2E 测试后门不应在非测试环境生效。NODE_ENV 门控后即使环境变量泄露也不影响生产。

---

---

## A11：`workspace-content.tsx` — 移动端侧栏触发按钮接入

**文件**: `frontend/src/app/workspace/workspace-content.tsx`
**行号**: L4, L29
**风险**: ✅ 极低（2 行：1 行 import + 1 行 JSX，其余代码在 `extensions/` 目录）

**改动**:

```diff
 import { cookies } from "next/headers";
 import { Toaster } from "sonner";
+import { MobileSidebarTrigger } from "../../../extensions/mobile-sidebar/mobile-sidebar-trigger";
 import { QueryClientProvider } from "@/components/query-client-provider";
 ...
       <SidebarProvider className="h-screen" defaultOpen={initialSidebarOpen}>
+        <MobileSidebarTrigger />
         <WorkspaceSidebar />
         <SidebarInset className="min-w-0">{children}</SidebarInset>
       </SidebarProvider>
```

**原因**: 移动端（`< 768px`）左侧栏以 Sheet 抽屉形式渲染，关闭后无触发按钮。`MobileSidebarTrigger` 在移动端显示浮动汉堡按钮，点击调用 `toggleSidebar()` 打开 Sheet。

**配套扩展文件**（全在 `frontend/extensions/mobile-sidebar/`，零侵入）：
- `frontend/extensions/mobile-sidebar/mobile-sidebar-trigger.tsx` — 浮动汉堡按钮组件

**恢复方法**: 删除 import 行和 JSX 行，删除 `frontend/extensions/mobile-sidebar/` 目录。

**验证命令**:

```bash
# 确认 import 存在
grep -n "MobileSidebarTrigger" frontend/src/app/workspace/workspace-content.tsx

# 确认扩展组件存在
ls frontend/extensions/mobile-sidebar/mobile-sidebar-trigger.tsx
```

---

## A12：`query-client-provider.tsx` — TanStack Query 缓存配置（2026-04-17）

**文件**: `frontend/src/components/query-client-provider.tsx`
**行号**: L7-L14
**风险**: ✅ 极低（纯配置修改，不改任何逻辑）

**改动**:

```diff
- const queryClient = new QueryClient();
+ const queryClient = new QueryClient({
+   defaultOptions: {
+     queries: {
+       gcTime: 1000 * 60 * 3,      // 3 分钟
+       staleTime: 1000 * 60,        // 1 分钟
+       refetchOnWindowFocus: false,
+     },
+   },
+ });
```

**原因**: 
- 默认 `gcTime`（5 分钟）和 `staleTime`（0 秒）导致前端频繁请求后端 API，增加服务器负载和内存占用
- 对非实时数据（如模型列表、设置）没必要每次 focus 都重新请求
- 此项已在 `docs/operations/OPERATIONS.md` 中作为内存优化配置记录

---

## 验证命令

```bash
# === A6: beforeFiles rewrites ===
grep -n "beforeFiles" frontend/next.config.js

# === A7: middleware ts ads_token ===
grep -n "ads_token\|PUBLIC_PATHS" frontend/middleware.ts

# === A8: types.ts buildLoginUrl ===
grep -n "buildLoginUrl\|ads-login" frontend/src/core/auth/types.ts

# === A10: server.ts NODE_ENV gate ===
grep -n "NODE_ENV.*test\|DEER_FLOW_AUTH_DISABLED" frontend/src/core/auth/server.ts

# === A11: workspace-content.tsx MobileSidebarTrigger ===
grep -n "MobileSidebarTrigger" frontend/src/app/workspace/workspace-content.tsx

# === A12: query-client-provider.tsx ===
grep -n "gcTime\|staleTime" frontend/src/components/query-client-provider.tsx

# === S1a: settings-dialog.tsx EXTENSION SLOT ===
grep -c "EXTENSION SLOT" frontend/src/components/workspace/settings/settings-dialog.tsx

# === S1b: settings-dialog.tsx additionalSections ===
grep -n "additionalSections" frontend/src/components/workspace/settings/settings-dialog.tsx | head -5

# === S1c: settings-dialog.tsx hiddenSectionIds ===
grep -n "hiddenSectionIds" frontend/src/components/workspace/settings/settings-dialog.tsx

# === S2: registry.ts ===
grep -c "registerSettingsExtension" frontend/src/core/settings-extensions/registry.ts

# === S3a: workspace-nav-menu.tsx getSettingsExtensions ===
grep -n "getSettingsExtensions" frontend/src/components/workspace/workspace-nav-menu.tsx

# === S3b: workspace-nav-menu.tsx EXTENSION IMPORT ===
grep -n "EXTENSION IMPORT" frontend/src/components/workspace/workspace-nav-menu.tsx

# === S5: 隐藏菜单注释 ===
grep -c "🚫 以下菜单项被隐藏" frontend/src/components/workspace/workspace-nav-menu.tsx

# === IS1: input-box.tsx EXTENSION IMPORT ===
grep -n "EXTENSION IMPORT" frontend/src/components/workspace/input-box.tsx

# === input-suggestions registry ===
grep -c "registerInputSuggestion" frontend/extensions/input-suggestions/registry.ts
```

---

---

## S5：`workspace-nav-menu.tsx` — 隐藏"设置和更多"下拉菜单多余按钮

**文件**: `frontend/src/components/workspace/workspace-nav-menu.tsx`
**行号**: L107-L164
**风险**: ✅ 极低（纯注释隐藏，不删除代码，恢复时删除注释块即可）

### 改动说明

左下角"设置和更多"下拉菜单中，除"设置"按钮外，其余 6 项菜单按钮全部以 `{/* 🚫 ... */}` 注释块隐藏。隐藏的按钮：

1. **分隔线**（L108 后的 `<DropdownMenuSeparator />`）
2. **访问 DeerFlow 官方网站**（L109-L118）
3. **在 Github 上查看 DeerFlow**（L119-L128）
4. **分隔线**（L129 的 `<DropdownMenuSeparator />`）
5. **报告问题**（L130-L139）
6. **联系我们**（L140-L145）
7. **分隔线**（L147 的外部 `<DropdownMenuSeparator />`）
8. **关于 DeerFlow**（L148-L156）

注释块内保留了全部原始代码，并在注释头中说明了隐藏原因和恢复方法。

**同时注释的导入**：
- `BugIcon`、`GlobeIcon`、`InfoIcon`、`MailIcon`（来自 `lucide-react`）
- `DropdownMenuSeparator`（来自 `@/components/ui/dropdown-menu`）
- `GithubIcon`（来自 `./github-icon`）

恢复菜单项时需同时取消这些导入的注释。

### 原因

根据功能自定义需求，左下角"设置和更多"下拉菜单只保留"设置"按钮。官方网站、Github、报告问题、联系我们、关于 DeerFlow 等按钮均隐藏，简化菜单内容。

### 恢复方法

删除 `{/*` 注释开始标记和 `*/}` 注释结束标记之间的代码块。

### 验证命令

```bash
# 确认隐藏按钮的注释标记存在
grep -c "🚫 以下菜单项被隐藏" frontend/src/components/workspace/workspace-nav-menu.tsx
# 应输出 1

# 确认"设置"按钮仍然可见（不会被注释包裹）
grep -c "t.common.settings" frontend/src/components/workspace/workspace-nav-menu.tsx
# 应输出 1（未被注释）
```

---

## IS1：`input-box.tsx` — 输入建议按钮扩展注册

**文件**: `frontend/src/components/workspace/input-box.tsx`
**风险**: ✅ 极低

### IS1a — 顶部增加扩展 import（L67-L70）

```typescript
// --- EXTENSION IMPORT: input suggestions ---
import { getInputSuggestions } from "../../../extensions/input-suggestions/registry";
import { useInputSuggestionsReady } from "../../../extensions/input-suggestions/context";
// --- EXTENSION IMPORT: end ---
```

**原因**: `getInputSuggestions` 提供从扩展注册表动态获取按钮列表的能力，`useInputSuggestionsReady` hook 订阅 Context 状态变化，在 Provider 加载完成后触发组件重渲染。

### IS1b — SuggestionList 改为动态注册模式

**代码位置**: SuggestionList 组件内（L926-L1000）

原有的硬编码按钮（小惊喜/写作/研究/收集/学习/网页/图片/视频/技能）通过 JSX 注释块保留，替换为从扩展注册表动态加载的模式：

```typescript
  // 订阅 Context：Provider 加载完成后触发重渲染
  useInputSuggestionsReady();

  const allSuggestions = getInputSuggestions();
  const mainSuggestions = allSuggestions.filter(s => s.group === "main");
  const createSuggestions = allSuggestions.filter(s => s.group === "create");
```

**配套扩展文件**（全在 `frontend/extensions/`，零侵入）：
- `frontend/extensions/input-suggestions/registry.ts` — 注册表
- `frontend/extensions/input-suggestions/config.ts` — 运行时 fetch 加载器（替换原编译时硬编码注册）
- `frontend/extensions/input-suggestions/context.tsx` — Context Provider + hook（驱动重渲染）
- `frontend/extensions/input-suggestions/types.ts` — 配置项 JSON 类型

**运行时数据流**:
```
site.config.json (inputSuggestions 数组)
    → config.ts fetch → 校验 → 缓存
    → context.tsx InputSuggestionsProvider useEffect
        → clearInputSuggestions()
        → forEach: resolveIcon(iconName) → registerInputSuggestion(...)
        → useState(getInputSuggestions()) 触发重渲染
    → useInputSuggestionsReady() hook 在 input-box.tsx 中订阅
```

**原因**: 
- 旧代码从 `t.inputBox.suggestions`（i18n 硬编码）渲染按钮，无法自定义
- 新代码通过运行时 fetch site.config.json 动态加载按钮，仅需修改 JSON 即可增删改
- Provider 的 useState + Context 机制确保注册完成后自动触发 UI 重渲染
- 配置缺失/网络失败时零渲染，不影响正常使用

**恢复方法**: 
1. 删除 `--- EXTENSION IMPORT ---` 注释块内的 2 行 import
2. 删除 SuggestionList 中的 hook 调用 + 动态渲染代码
3. 取消 JSX 注释块，恢复旧按钮代码
4. 取消注释已注释的 import：`SparklesIcon`、`ConfettiButton`、`DropdownMenuSeparator`

**验证命令**:
```bash
# 确认 EXTENSION IMPORT 存在
grep -n "EXTENSION IMPORT" frontend/src/components/workspace/input-box.tsx

# 确认 useInputSuggestionsReady hook 已接入
grep -n "useInputSuggestionsReady" frontend/src/components/workspace/input-box.tsx

# 确认 config.ts 为运行时模式（不应有直接 registerInputSuggestion 调用）
grep -c "registerInputSuggestion" frontend/extensions/input-suggestions/config.ts
# 应输出 0（config.ts 不再直接注册，由 Provider 调用 loadAndRegisterSuggestions）

# 确认扩展目录完整性
ls frontend/extensions/input-suggestions/types.ts \
   frontend/extensions/input-suggestions/config.ts \
   frontend/extensions/input-suggestions/context.tsx \
   frontend/extensions/input-suggestions/registry.ts
```

---

## WS: env-settings 渠道配置

**文件**: `frontend/extensions/env-settings/`
**风险**: ✅ 极低（扩展目录，零侵入）

### WS1 — api.ts 路径拆分 + 新增渠道 API

1. 现有 4 个函数的 URL 路径从 `/api/env-settings` 改为 `/api/env-settings/providers`
2. 新增 4 个渠道 API 函数：`loadChannelSettings`、`updateChannel`、`deleteChannel`、`verifyChannel`

### WS2 — types.ts 新增渠道类型

新增 `ChannelInfo`、`ChannelSettingsResponse`、`ChannelUpdateRequest` 三个接口。

### WS3 — hooks.ts 新增渠道 hooks

新增 `useChannelSettings`、`useUpdateChannel`、`useDeleteChannel`、`useVerifyChannel` 四个 hooks（原有 hooks 名称不变）。

### WS4 — channel-settings-page.tsx（新文件）

独立的"渠道配置"标签页，包含 WeCom Bot ID/Secret 配置表单、安全重启逻辑、审计日志。

### WS5 — extension.ts 双注册

注册两个扩展：`id:"api"`（API Keys）+ `id:"channels"`（渠道配置）。

### WS6 — 多渠道扩展（2026-06-08）

**文件**: `frontend/extensions/env-settings/`
**风险**: ✅ 极低（扩展目录，零侵入）

将渠道配置从 WeCom 专用改为多渠道（企业微信/飞书/钉钉/微信）通用界面。

#### WS6a — channels.ts 新建渠道元数据

新增文件，定义 4 个国内 IM 渠道的 `ChannelMeta` 元数据（`credentialFields` 凭据字段列表），前端据此动态渲染输入表单。

#### WS6b — types.ts 凭据字典化

`ChannelInfo.bot_id_exists`/`bot_id_masked`/`bot_secret_exists` 合并为 `credentials: Record<string, string>`，`ChannelUpdateRequest` 同理，新增 `ChannelVerifyRequest`。

#### WS6c — api.ts verifyChannel 签名更新

`verifyChannel(channel, botId, botSecret)` → `verifyChannel(channel, credentials)`。

#### WS6d — hooks.ts 适配

`useVerifyChannel` mutation 参数改为 `{ channel, credentials }`。

#### WS6e — channel-settings-page.tsx 多渠道重构

- 新增渠道选择器（Select 下拉框，从 `CHANNELS` 元数据渲染）
- 凭据表单根据 `selectedMeta.credentialFields` 动态渲染
- 眼睛按钮按 `field.key` 独立控制
- 删除确认弹窗引用 `selectedMeta.name`
- 切换渠道时重置 formValues/showFields

---

## FIX1：`dialog.tsx` — suppressHydrationWarning 修复

**文件**: `frontend/src/components/ui/dialog.tsx`
**行号**: L127
**风险**: ✅ 极低（1 行，CSS 预渲染兼容）

**改动**:
```diff
     className={cn("text-muted-foreground text-sm", className)}
+    suppressHydrationWarning
     {...props}
```

**原因**: 品牌动态内容导致服务端/客户端 HTML 不一致，Next.js hydration 报错。`suppressHydrationWarning` 消除已知差异的警告。

**验证命令**:
```bash
grep -c "suppressHydrationWarning" frontend/src/components/ui/dialog.tsx
# 应输出 1
```

---

## G1：`globals.css` — 登录页全局样式侵入

**文件**: `frontend/src/styles/globals.css`
**风险**: ✅ 低（上游源文件修改，CSS 变量级改动）

### G1a — `:root` 颜色变量修改（2026-06-23，提交 `a8952cdf`）

```diff
-  --background: oklch(0.9855 0.0098 87.47);
+  --background: #ffffff;
   ...
-  --sidebar: oklch(0.965 0.0098 87.47);
+  --sidebar: #f9fafb;
   --sidebar-foreground: oklch(0.145 0 0);
-  --sidebar-primary: oklch(0.205 0.0098 87.47);
-  --sidebar-primary-foreground: oklch(0.985 0 0);
-  --sidebar-accent: oklch(0.925 0.0098 87.47);
-  --sidebar-accent-foreground: oklch(0.205 0 0);
+  --sidebar-accent: #002B74;
+  --sidebar-accent-foreground: #ffffff;
+  --sidebar-accent: #002B74;
+  --sidebar-accent-foreground: #ffffff;
```

### G1b — 新增 `.border-solid` 工具类（2026-06-23，提交 `a8952cdf`）

```css
.border-solid {
  border: 1px solid #000 !important;
}
```

**改动要点**:
- L226: `--background` 由 `oklch(...)` 改为纯白 `#ffffff`
- L250: `--sidebar` 改为 `#f9fafb`
- L252-L255: `--sidebar-primary`/`--sidebar-primary-foreground` 移除；`--sidebar-accent` 替换为品牌色 `#002B74`，`--sidebar-accent-foreground` 替换为 `#ffffff`（含重复声明）
- L393-L395: 新增 `.border-solid` 黑色实线边框工具类

**原因**: 配合登录页 UI 重构，调整全局背景色为纯白、sidebar 配色为品牌色，新增边框工具类供登录表单使用。

**验证命令**:
```bash
grep -c "002B74" frontend/src/styles/globals.css
# 应输出 2（light 主题 sidebar-accent + accent-foreground）

grep -c "border-solid" frontend/src/styles/globals.css
# 应输出 1
```

**恢复方法**: 还原 `a8952cdf` 中 `globals.css` 的 diff。

---

## B1：品牌自定义配置扩展层

**文件集合**:
- `frontend/extensions/branding/types.ts` — BrandingConfig 接口
- `frontend/extensions/branding/config.ts` — /site.config.json 加载器（含 _cached 缓存）
- `frontend/extensions/branding/context.tsx` — BrandingProvider + useBranding hook
- `frontend/public/site.config.json` — 运行时配置文件
- `frontend/src/app/layout.tsx` — 包裹 BrandingProvider + generateMetadata 动态标题
- `frontend/src/components/workspace/workspace-header.tsx` — useBranding 替换硬编码 DF / DeerFlow
- `frontend/src/components/workspace/welcome.tsx` — 消费端叠加 branding.welcome
- `frontend/extensions/ads_auth/LoginPage.tsx` — 品牌标题槽位
- `frontend/src/components/workspace/workspace-nav-menu.tsx` — hiddenSectionIds 限制为 Account / API Keys / 渠道配置
- `frontend/middleware.ts` — 公开路径新增 `/site.config.json`（绕过中间件认证）
- `frontend/src/components/workspace/settings/settings-dialog.tsx` — 注释掉 title 下的 description 行（内容含 "DeerFlow" 品牌名，与自定义品牌不一致）

**隐藏的设置页 section**: appearance, notification, memory, tools, skills, about（只保留 account + api + channels）

**风险**: ✅ 低（所有字段均为可选，缺失时降级到 i18n 默认值或硬编码回退值）

**验证命令**:
```bash
# 验证侧栏品牌名已替换
grep -c "useBranding" frontend/src/components/workspace/workspace-header.tsx

# 验证 metadata title 已动态
grep -n "title" frontend/src/app/layout.tsx | head -3

# 验证登录页品牌槽位
grep -c "useBranding\|loginPage" frontend/extensions/ads_auth/LoginPage.tsx

# 验证欢迎页叠加
grep -c "useBranding" frontend/src/components/workspace/welcome.tsx

# 验证设置页限制
grep -n "hiddenSectionIds" frontend/src/components/workspace/workspace-nav-menu.tsx

# 验证扩展目录完整性
ls frontend/extensions/branding/types.ts frontend/extensions/branding/config.ts frontend/extensions/branding/context.tsx

# 验证本补丁记录
grep -c "品牌" docs/patches/frontend.md
```

---

## C1：`workspace-content.tsx` — ClarificationProvider 挂载（⚠️ 已封存）

> **状态**：侵入点已清理（2026-07-03）。`ClarificationProvider` import 和 JSX 包裹已移除。扩展组件保留在 `frontend/extensions/human-intervention/` 供未来参考。

**文件**: `frontend/src/app/workspace/workspace-content.tsx`
**行号**: 原 L10 (import), L35-L44 (JSX 包裹)（已删除）
**风险**: ✅ 极低（2 行：1 行 import + 1 层 JSX 包裹，其余代码在 `extensions/` 目录）

**改动**:

```diff
+import { ClarificationProvider } from "../../../extensions/human-intervention/config";
 ...
       <QueryClientProvider>
+        <ClarificationProvider>
           <MobileSidebarTrigger />
           <WorkspaceSidebar />
           <SidebarInset>{children}</SidebarInset>
+        </ClarificationProvider>
       </QueryClientProvider>
```

**原因**: `ClarificationProvider` React Context 在全局层级传播提交状态（activeClarificationId、isSubmitting），使 Widget 按钮和 InputBox 都能感知当前的澄清状态。

**配套扩展文件**（全在 `frontend/extensions/human-intervention/`，零侵入）：
- `ClarificationProvider.tsx` — React Context 定义
- `config.ts` — 注册入口（re-export Provider/Widget/hooks）

**恢复方法**: 删除 import 行和 `<ClarificationProvider>...</ClarificationProvider>` 包裹，删除 `frontend/extensions/human-intervention/` 目录。

**验证命令**:
```bash
# 确认已封存（grep 应返回空）
grep -rn "ClarificationProvider" frontend/src/app/workspace/workspace-content.tsx || echo "✓ C1 侵入点已清理"

# 确认扩展组件存在
ls frontend/extensions/human-intervention/ClarificationProvider.tsx
```

---

## C2：`page.tsx` — useClarificationSubmit 注入（⚠️ 已封存）

> **状态**：侵入点已清理（2026-07-03）。`useClarificationSubmit` import 和 hook 调用已移除。扩展 hook 保留在 `frontend/extensions/human-intervention/hooks.ts` 供未来参考。

**文件**: `frontend/src/app/workspace/chats/[thread_id]/page.tsx`
**行号**: 原 L7 (import), L123 (hook 调用)（已删除）
**风险**: ✅ 极低（2 行：1 行 import + 1 行 hook 调用）

**改动**:

```diff
+import { useClarificationSubmit } from "../../../../../extensions/human-intervention/hooks";
 ...
   });
+
+  useClarificationSubmit(sendMessage, threadId, thread.isLoading);
```

**原因**: `ClarificationProvider` 的 `submitClarification` 通过 `clarification:submit` CustomEvent 通信。`useClarificationSubmit` hook 监听该事件，提取 answer，并调用 `sendMessage(threadId, { text: answer, files: [] })` 将用户回答发送回 AI Agent。

**配套扩展文件**（全在 `frontend/extensions/human-intervention/`，零侵入）：
- `hooks.ts` — useClarificationSubmit hook（事件监听 + sendMessage 桥接）

**恢复方法**: 删除 import 行和 `useClarificationSubmit(...)` 行，删除 `frontend/extensions/human-intervention/` 目录。

**验证命令**:
```bash
# 确认已封存（grep 应返回空）
grep -rn "useClarificationSubmit" frontend/src/app/workspace/chats/*/page.tsx 2>/dev/null || echo "✓ C2 侵入点已清理"

# 确认扩展组件存在
ls frontend/extensions/human-intervention/hooks.ts
```

---
### WS6f — invite-section.tsx 邀请成员卡片（2026-07-15）（注：全部文件在扩展目录内，非核心改动，见 patches/README.md L27）

**文件**: `frontend/extensions/env-settings/`
**风险**: ✅ 极低（扩展目录，零侵入）

新增邀请码生成卡片组件 `invite-section.tsx`，在渠道凭据配置完成后显示「邀请成员」区域。

#### 新增文件

- `frontend/extensions/env-settings/invite-section.tsx`（295 行）— 三态机组件

#### 修改的文件

##### types.ts

- 标记 `ChannelSaveResult.connectInfo` 为 `@deprecated`
- 新增 `InviteCodeResult { code, instruction, expiresIn }` 接口

##### channel-adapter.ts

- `AdaptedChannelInfo` 新增 `authMode: string` 字段
- `mapProvider()` 透传 `p.auth_mode`
- `saveChannel()` 移除 `connectInfo` 自动提取和返回（不再绑定 auto-fetch 逻辑）
- 新增 `generateInviteCode(provider) → InviteCodeResult` 函数

##### hooks.ts

- 新增 `useGenerateInvite()` mutation hook

##### channel-settings-page.tsx

- 删除 `bindingInfo` / `copied` 状态管理
- 删除 `handleSave` 中的 `connectInfo` 自动提取
- 删除旧的绑定码指导 JSX（约 50 行）
- 插入 `<InviteSection key={selectedChannelId} ...>` 组件

#### 组件设计

**三态机**: `IDLE → ACTIVE → EXPIRED`

- **IDLE**: 显示标题 + 副标题 + 「暂无邀请码」+ 生成按钮
- **ACTIVE**: 显示绑定码 + 二维码 + 倒计时（10 分钟）+ 复制按钮 + 重新生成
- **EXPIRED**: 显示已过期 + 重新生成按钮

**竞态防护**:

- `generationIdRef` 递增原子锁 — 快速双击不触发重复请求
- `mountedRef` 防止卸载后 `setState`

**性能优化**:

- `deadlineRef` 存储绝对 Timestamp，倒计时 tick 不依赖闭包
- `qrCacheRef` 缓存已生成的 QR DataURL
- `pollRef` 管理连接轮询生命周期

**渠道切换重置**: `key={selectedChannelId}` 确保组件卸载/挂载时回到 IDLE

#### 验证命令

```bash
# TypeScript 类型检查（仅扩展目录）
grep -n "tsc" Makefile && npx tsc --noEmit --pretty 2>&1 | head -30

# 确认 invite-section.tsx 存在
ls frontend/extensions/env-settings/invite-section.tsx

# 确认 bindingInfo 已从 channel-settings-page 删除
grep -c "bindingInfo" frontend/extensions/env-settings/channel-settings-page.tsx
# 应输出 0

# 确认 connectInfo 已标记 deprecated
grep -c "@deprecated" frontend/extensions/env-settings/types.ts
# 应输出 2

# 确认 key={selectedChannelId}
grep -n "InviteSection" frontend/extensions/env-settings/channel-settings-page.tsx
```

---

## 验证命令（human-intervention 封存状态检查）

```bash
# === 侵入点已清理确认（全部应返回空）===
grep -rn "ClarificationProvider" frontend/src/app/workspace/workspace-content.tsx || echo "✓ C1 已清理"
grep -rn "useClarificationSubmit" frontend/src/app/workspace/chats/*/page.tsx 2>/dev/null || echo "✓ C2 已清理"
grep -rn "ClarificationWidget" frontend/src/components/workspace/messages/message-list.tsx || echo "✓ C3 已清理"

# === 扩展目录完整性（应存在） ===
ls frontend/extensions/human-intervention/ClarificationProvider.tsx \
   frontend/extensions/human-intervention/ClarificationWidget.tsx \
   frontend/extensions/human-intervention/hooks.ts \
   frontend/extensions/human-intervention/config.ts \
   frontend/extensions/human-intervention/types.ts \
   frontend/extensions/human-intervention/schema.ts
```