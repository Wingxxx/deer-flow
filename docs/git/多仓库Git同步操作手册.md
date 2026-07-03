# 多仓库 Git 同步操作手册

> 本文档说明三方仓库拓扑及手动同步操作流程。
>
> 内网仓库（`http://192.168.1.222/xuzhanyi/deerflow.git`）为**主开发仓库**，
> GitHub `ads` 分支为**唯一中转枢纽**，内网仓库与字节官方仓库之间无任何直接关联。

---

## 目录

- [仓库拓扑](#仓库拓扑)
- [Remote 配置](#remote-配置)
- [同步链路](#同步链路)
- [首次初始化](#首次初始化)
- [日常操作](#日常操作)
- [上游同步操作](#上游同步操作)
- [注意事项](#注意事项)

---

## 仓库拓扑

```
内网仓库 (http://192.168.1.222/xuzhanyi/deerflow.git)
  └── main          ← 主开发分支（字节上游 + 扩展 + 补丁）

GitHub origin (git@github.com:Wingxxx/deer-flow.git)
  └── ads           ← 唯一中转枢纽分支

字节 upstream (https://github.com/bytedance/deer-flow.git)
  └── main          ← 官方发布分支（只读）
```

```
字节 upstream/main ──────→ GitHub ads ──────→ 内网 main
                              ↑                   │
                              └───────────────────┘
                         （内网开发成果定期推送至 ads）
```

**核心原则**：

- 内网仓库与字节官方仓库**无任何直接关联**，所有跨网数据交换必须经过 GitHub `ads` 分支
- `ads` 分支内容始终与内网 `main` 保持一致
- 所有同步操作均为**手动触发**，无自动化脚本

---

## Remote 配置

在当前工作区配置三方 remote：

```bash
# origin（已有，外网 GitHub）
git remote add origin git@github.com:Wingxxx/deer-flow.git

# upstream（已有，字节官方）
git remote add upstream https://github.com/bytedance/deer-flow.git

# internal（新增，内网仓库）
git remote add internal http://192.168.1.222/xuzhanyi/deerflow.git
```

验证配置：

```bash
git remote -v
# internal    http://192.168.1.222/xuzhanyi/deerflow.git (fetch)
# internal    http://192.168.1.222/xuzhanyi/deerflow.git (push)
# origin      git@github.com:Wingxxx/deer-flow.git (fetch)
# origin      git@github.com:Wingxxx/deer-flow.git (push)
# upstream    https://github.com/bytedance/deer-flow.git (fetch)
# upstream    https://github.com/bytedance/deer-flow.git (push)
```

---

## 同步链路

以下为**串行**手动同步流程，每一步必须在前一步成功完成后执行。

### 日常开发同步（内网 → GitHub）

```
内网 main ──→ GitHub ads
```

将内网开发成果推送到 GitHub `ads` 分支，保持两边一致。

### 上游同步（字节 → GitHub → 内网）

```
字节 upstream/main ──→ GitHub ads ──→ 内网 main
```

**前置条件**：在启动上游同步之前，必须先完成「日常开发同步」，确保内网 `main` 与 GitHub `ads` 完全一致。

### 完整同步链路图

```
① 内网 main → GitHub ads      （日常推送）
② GitHub ads ← 字节 upstream   （拉取上游更新，处理侵入点冲突）
③ GitHub ads → 内网 main       （上游更新同步回内网）
```

> ⚠️ 步骤② 必须在步骤① 完成后执行，步骤③ 在步骤② 完成后执行。

---

## 首次初始化

### Step 1: 推送当前代码到内网仓库

```bash
# 确保当前在 main 分支且工作区干净
git checkout main
git status --short   # 应无输出

# 推送到内网仓库
git push internal main
```

### Step 2: 在 GitHub 创建 ads 分支

```bash
# 基于当前 main 创建 ads 分支并推送
git push origin main:ads
```

### Step 3: 在 GitHub 上设置 ads 为默认分支（可选）

在 GitHub 仓库 Settings → Branches → Default branch 中切换为 `ads`。

---

## 日常操作

### 推送内网成果到 GitHub ads

在内网开发机器上（remote `internal` 指向内网仓库）：

```bash
# 1. 确保在 main 分支，工作区干净
git checkout main
git status --short

# 2. 拉取内网最新代码
git pull internal main

# 3. 推送到 GitHub ads 分支
git push origin main:ads
```

### 从 GitHub ads 拉取到内网

在内网开发机器上：

```bash
# 1. 确保在 main 分支
git checkout main

# 2. 从 GitHub ads 拉取
git pull origin ads
# 或使用 fetch + merge 以获得更精细的控制：
# git fetch origin ads
# git merge origin/ads

# 3. 推送到内网仓库
git push internal main
```

---

## 上游同步操作

> ⚠️ **前置条件**：执行上游同步前，必须先完成「日常操作 — 推送内网成果到 GitHub ads」，确保内网 `main` 与 GitHub `ads` 完全一致。

### Step 1: 备份当前状态

```bash
git branch -f backup-main main
```

### Step 2: 获取上游最新代码

```bash
git fetch upstream --tags
```

### Step 3: 合并上游到 ads

```bash
# 确保在 main 分支
git checkout main

# 合并上游 main 到当前分支
git merge upstream/main
```

### Step 4: 处理侵入点冲突

`git merge` 可能产生冲突。参照 `docs/fork-sync/README.md` 中的冲突分类与处理策略：

| 场景 | 处理策略 |
|------|---------|
| 自动合并 | 验证结果正确 |
| 双方改了相同区域 | 手动编辑，保留双方逻辑（禁止 `--theirs`/`--ours`） |
| 逻辑互斥 | 评估后选择一方 |

**关键原则**：侵入点冲突（`docs/patches/` 中记录的 28 个侵入点）必须人工审查，不得自动丢弃任何一方。

### Step 5: 验证侵入点完整性

```bash
# 参照 docs/patches/README.md 中的快速验证命令
# 确认 28 个侵入点未被覆盖
```

### Step 6: 运行测试

```bash
cd backend && make test
cd frontend && pnpm build
```

### Step 7: 提交合并结果

```bash
git add -A
git commit -m "Upstream sync: merge upstream/main, resolve conflicts"
```

### Step 8: 推送到 GitHub ads

```bash
git push origin main:ads
```

### Step 9: 同步回内网

在内网开发机器上：

```bash
git checkout main
git pull origin ads
git push internal main
```

---

## 注意事项

### 同步顺序铁律

```
① 内网 main → GitHub ads    ← 先内部对齐
② GitHub ads ← 字节 upstream  ← 再拉上游
③ GitHub ads → 内网 main      ← 最后回内网
```

**绝对禁止**在步骤① 未完成时执行步骤②，也禁止跳过步骤① 直接执行步骤③。

### 侵入点保护

上游合并时，以下文件区域的冲突必须人工裁决：

- `backend/app/gateway/app.py` — Boot Loader 注入点
- `backend/app/gateway/auth_middleware.py` — ADS JWT 认证
- `backend/app/gateway/csrf_middleware.py` — CSRF 豁免
- `backend/app/gateway/deps.py` — user_from_state 守卫
- `backend/app/gateway/routers/auth.py` — ADS 登录路由
- `frontend/middleware.ts` — PUBLIC_PATHS + auth guard
- `frontend/next.config.js` — ADS 登录重定向

完整侵入点清单及验证命令见 `docs/fork-sync/README.md`。

### 同步记录

每次上游同步完成后，在 `docs/fork-sync/` 下新建记录文档，命名格式：

```
FORK_SYNC_YYYYMMDD-vVERSION.md
```

并更新 `docs/fork-sync/README.md` 的历史同步记录表。

---

**WING**
