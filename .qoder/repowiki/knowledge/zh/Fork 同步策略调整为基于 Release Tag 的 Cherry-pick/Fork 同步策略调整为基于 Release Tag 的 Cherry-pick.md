---
kind: design
name: Fork 同步策略调整为基于 Release Tag 的 Cherry-pick
source: session
category: adr
---

# Fork 同步策略调整为基于 Release Tag 的 Cherry-pick

_来源：7a9313b → cf0dff2 提交周期内记录的编码计划——内容为规划时意图，实现可能滞后或有出入。_

**状态：** accepted

## 背景
作为 bytedance/deer-flow 的 Fork，项目包含大量自定义功能（ADS 认证、数据采集等）。此前同步上游 main 分支导致合并冲突多、风险高（如引入未测试的 OIDC SSO 代码）。需建立更稳定的同步机制。

## 决策驱动
- 稳定性：避免引入上游未发布的实验性功能
- 可维护性：减少合并冲突频率和解决难度
- 版本锚定：明确同步基线，便于回溯和问题定位

## 备选方案
- **基于 Release Tag 同步（选定方案）** — 优点：目标版本经过上游测试，稳定性高；提交范围明确；冲突相对可控；缺点：同步频率受上游发版节奏限制；可能滞后于上游最新开发进度
- **同步至 upstream/main HEAD** — 优点：始终拥有最新功能；缺点：包含大量未测试提交（如 OIDC SSO），风险不可控；合并冲突频繁且复杂
- **Rebase 方式同步** — 优点：提交历史线性整洁；缺点：本地大量自定义提交需反复解决冲突，操作成本极高

## 决策
放弃直接同步 upstream/main，改为以 Release Tag（如 v2.0.0-rc1）为同步节点。使用 cherry-pick 方式将上游 Tag 范围内的提交应用到本地。更新同步文档 docs/fork-sync/README.md，明确步骤为 fetch tags 并指定 <LAST_SYNCED_COMMIT>..<TARGET_TAG> 范围。同时建立侵入点清单（如 pyproject.toml, app.py 等）并在同步后执行自动化验证。

## 影响
同步过程更加可控，避免了不稳定代码的引入。需要维护一份“侵入点清单”并在每次同步后执行验证脚本以确保自定义功能未被覆盖。同步频率可能与上游发版节奏绑定。