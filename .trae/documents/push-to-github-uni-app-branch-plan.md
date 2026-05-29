# 推送计划：将本项目推送到 GitHub 作为 uni-app 分支

## 当前状态
- 工作目录：`d:\Wing_D\emto\2026\2026.5\uni-app`
- Git：已初始化（`git init` 完成）
- 远程仓库：已添加 `origin = https://github.com/Wingxxx/deer-flow.git`
- 尚未创建 `.gitignore` 和初始提交

## 执行步骤

### 步骤 1：创建根目录 `.gitignore`

针对 uni-app / HBuilderX 项目的标准忽略规则，排除：
- `node_modules/` — 依赖包（如有）
- `unpackage/` — HBuilderX 编译产出
- `dist/` — 构建产物
- `*.log` — 日志文件
- `.DS_Store` — macOS 元数据

注意：`.trae/` 目录应纳入版本控制，因为它包含项目配置文件。

### 步骤 2：暂存所有文件

```powershell
git add .
```

即将包含的文件清单：
- `CLAUDE.md` — 项目规则
- `DeerFlowApp/` — 主应用源码
- `docs/` — 文档
- `.trae/` — Trae IDE 配置（含技能和文档）

### 步骤 3：创建初始提交

```powershell
git commit -m "feat: init uni-app shell - DeerFlowApp WebView wrapper"
```

### 步骤 4：推送到远程 `uni-app` 分支

```powershell
git push origin HEAD:refs/heads/uni-app
```

### 步骤 5：验证推送结果

```powershell
git ls-remote --heads origin
```

确认 `refs/heads/uni-app` 存在。

---

## 注意事项
- 该远程仓库 `Wingxxx/deer-flow.git` 需确保存在且主子有写入权限
- 首次推送可能需要 GitHub 身份认证（Personal Access Token 或 SSH Key）
- 分支名为 `uni-app`，与仓库现有分支并存，不影响其他分支
