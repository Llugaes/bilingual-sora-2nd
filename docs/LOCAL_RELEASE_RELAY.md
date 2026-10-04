# 本地中转发布

唯一构建来源仍为 GitHub：源码和版本标签只在 GitHub 维护，GitHub Windows CI 完成测试、构建、安装器验收后创建草稿，维护者核对用户验收与成品后公开正式版。本机只下载原始附件并转发给 Gitee，不运行第二次构建，不注册通用 CI runner。

```text
推送版本标签 → GitHub CI 创建完整草稿 → 核对用户已验收候选并公开
    → 主动启动本机一次性中转命令
    → GitHub 正式发行版 → 本机下载及 SHA-256 校验
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

每次推送版本标签后，由维护者或负责发版的 Agent 主动执行一次。等待只存在于这次前台发版任务，没有日常定时轮询、登录触发、后台接收程序；命令完成就退出。电脑当时关机也没有关系，开机后主动执行即可补发最新稳定版。

```powershell
# 日常发版：推送版本标签后执行，等待此版本发布，再自动中转并退出。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Run -Tag v0.3.32 -WaitForRelease

# GitHub 已发布时无需等待；省略 -Tag 则补发最新稳定版。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Run -Tag v0.3.32
```

命令显示进度并保存日志。只有完整同步并校验成功才返回退出码 0；失败保留缓存，再执行同一命令重试。不需要重新输入令牌。`-WaitForRelease` 必须指定 `-Tag`，只等待这个版本变成公开稳定版，每分钟检查一次，最多等 45 分钟，Ctrl+C 可以取消；超时、网络或 API 错误退出，不留下后台进程。未加等待选项时，未发布版本立即报错。两端发布成功才算本次分发交付完成。

## 首次配置与维护

在 Gitee 创建仅限本仓库、`projects` 权限的令牌，建议 90 天有效期。Gitee 强制附带的 `user_info` 不用于发布。令牌属于本地中转凭据，独立于 GitHub Actions 中已有的凭据；不要尝试导出 Actions secret。

```powershell
# 提示输入令牌时不回显；Windows DPAPI 按当前用户和电脑加密保存。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Setup

# 查看凭据是否已配置、最近验证版本及日志位置，不联网。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Status

# 移除本机发布凭据，保留下载缓存；这不是停止定时任务的入口。
powershell.exe -NoProfile -File tools/local_release_relay.ps1 -Mode Remove
```

续期时在同一个 PowerShell 会话执行 `& .\tools\local_release_relay.ps1 -Mode Setup -Token (Read-Host 'New Gitee token' -AsSecureString)`，替换加密凭据。令牌不能作为明文命令行参数。底层 Python 入口也可以使用当前进程的 `GITEE_RELEASE_TOKEN` 环境变量；不要把令牌写进聊天、源码或日志。

`Setup` 仅加密保存凭据；已有凭据直接复用。旧 `Install` 命令作为兼容别名保留，也只执行相同配置，不再安装任务。`Setup` 或 `Run` 会移除属于当前检出目录的旧 `Sora Bilingual - Gitee Release Relay` 定时任务，同时保留凭据和缓存；旧任务正在执行时先禁止后续触发，等本次执行结束再重试，不打断上传。

程序、凭据、日志和缓存位于维护者项目目录的 `.local/gitee-relay`。本地凭据由 Windows DPAPI 绑定当前用户与电脑；换电脑需要重新配置。中转不影响 GitHub 独立发布；Gitee 保留最新三个已验证的镜像，GitHub 保留完整历史。

## 重试与证据

- SHA-256 同时绑定 GitHub 发布清单和真实文件。预览、草稿、跨仓库、路径异常、大小或摘要错误都不上传。
- 同时只允许一个中转进程使用缓存。上传结果未知时，下次先读取 Gitee 附件清单，再复用已经存在的文件；每个附件匿名校验后才允许转为稳定版。
- 本地 `verified.json` 只在远端完整发布成功后写入，记录源与目标的公开发布/附件身份。后续先核对两端身份，不变时不下载或上传大文件。
- 日志 `relay.log` 超过 1 MiB 后保留一份 previous，凭据不写入日志。命令退出码 0 表示成功或已同步，1 表示失败；失败不影响下次主动执行。
- 删除或替换远端附件会使成功记录失效，触发重新核对。稳定版的冲突附件拒绝覆盖，需维护者核查；不以重新构建掩盖摘要不符。
- 新版验证成功后，清理工具标记的第四个及更旧 Gitee 稳定版；人工和预览记录不自动删除。当地缓存只清理可识别的旧版原包，保留当前版本及未知文件。

`gitee-mirror.yml` 保留为手动应急入口，不是默认发布路径：实测 GitHub 托管机跨站上传明显慢于适合本项目的速度。本机一次性中转的整链路验收状态见 [验证记录](verification/GITEE_DISTRIBUTION.md)。
