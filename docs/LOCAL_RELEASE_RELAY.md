# 本地中转发布

唯一构建来源仍为 GitHub：源码和版本标签只在 GitHub 维护，GitHub Windows CI 完成测试、构建、安装器验收并发布正式版。本机只下载原始附件并转发给 Gitee，不运行第二次构建，不注册通用 CI runner。

```text
GitHub CI → GitHub 正式发行版 → 本机下载及 SHA-256 校验
    → Gitee 预览版 → 全部附件匿名下载校验 → Gitee 稳定版
```

两端的 Setup、应用 ZIP、运行依赖 ZIP 和 update.json 字节相同，客户端继续按同一版本、文件大小和摘要切换下载源。完整便携 ZIP 超过 Gitee 单附件限制，只保留在 GitHub。

## 执行入口

以下操作仅用于维护者电脑，不会被安装到玩家机器，也不会修改游戏或 MOD 配置。使用已建立 `.venv` 的项目检出目录，Python 3.14；上传需要 Windows 自带 `curl.exe`。

只验证 GitHub 取包，不上传、不需要 Gitee 凭据：

```powershell
.venv\Scripts\python.exe -X utf8 -m tools.relay_gitee --repository Llugaes/bilingual-sora-2nd --download-only
```

默认取 GitHub 最新公开稳定版，可用 `--tag v0.3.31` 固定版本。已验证下载保存在 `.local/gitee-relay/packages`；失败重跑复用已有合格文件，未变的依赖包跨版本复用。不执行下载的安装包。

一次性发布入口：先在当前进程环境配置 `GITEE_RELEASE_TOKEN`，再移除 `--download-only`。不要在命令行参数、聊天、源码或日志中写令牌。

## 当前用户的自动任务

在 Gitee 创建仅限本仓库、`projects` 权限的令牌，建议 90 天有效期。Gitee 强制附带的 `user_info` 不用于发布。令牌属于本地中转凭据，独立于 GitHub Actions 中已有的凭据；不要尝试导出 Actions secret。

```powershell
# 提示输入令牌时不回显；Windows DPAPI 按当前用户和电脑加密保存。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Install

# 查看任务、最近退出码和下次执行时间。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Status

# 立即执行一次；仍复用缓存，输出写入中转日志。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Run

# 停止并移除任务和本机发布凭据，保留下载缓存。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Remove
```

任务名称为 `Sora Bilingual - Gitee Release Relay`，当前用户登录时及每 15 分钟检查一次；普通用户权限，不安装管理员服务。没有常驻 Python 进程；每次执行完成后退出。程序和日志位于维护者项目目录的 `.local/gitee-relay`，不能移动检出目录后继续沿用旧任务。

电脑关机、用户注销、休眠或网络不可用时，Gitee 同步延后，GitHub 发版保持独立。恢复后检查最新稳定版；离线期间的中间版本不承诺补齐。Gitee 保留最新三个已验证的镜像，GitHub 保留完整历史。

## 重试与证据

- SHA-256 同时绑定 GitHub 发布清单和真实文件。预览、草稿、跨仓库、路径异常、大小或摘要错误都不上传。
- 同时只允许一个中转进程使用缓存。上传结果未知时，下次先读取 Gitee 附件清单，再复用已经存在的文件；每个附件匿名校验后才允许转为稳定版。
- 本地 `verified.json` 只在远端完整发布成功后写入，记录源与目标的公开发布/附件身份。后续先核对两端身份，不变时不下载或上传大文件。
- 日志 `relay.log` 超过 1 MiB 后保留一份 previous，凭据不写入日志。任务退出码 0 表示成功或已同步，1 表示失败；失败不影响下次执行。
- 删除或替换远端附件会使成功记录失效，触发重新核对。稳定版的冲突附件拒绝覆盖，需维护者核查；不以重新构建掩盖摘要不符。
- 新版验证成功后，清理工具标记的第四个及更旧 Gitee 稳定版；人工和预览记录不自动删除。当地缓存只清理可识别的旧版原包，保留当前版本及未知文件。

`gitee-mirror.yml` 保留为手动应急入口，不是默认发布路径：实测 GitHub 托管机跨站上传明显慢于适合本项目的速度。自动中转的实际启用和整链路验收状态见 [验证记录](verification/GITEE_DISTRIBUTION.md)。
