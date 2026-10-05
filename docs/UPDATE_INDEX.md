# 0.4.4 静态更新索引（本地候选，尚未上线）

候选仅修复更新通道；0.4.3 已发布对象不变。客户端拟使用同仓库 `release-index` 分支的 `stable.json`，当前没有创建该远端分支或探测不存在的文件。实际索引上线与候选发布须由 root 审查和用户验收决定。

## 客户端合同

`StaticGiteeClient` 通过原始文件通道发现版本，不调用 Gitee releases/attachments API。索引上限 64 KiB、最多三个已验收稳定版，固定 schema/application/repository/platform/channel；每条版本绑定确切 tag、版本清单文件名、大小和 SHA-256。索引不接受 URL、指令或凭据字段。未知 schema、重复 JSON 字段/版本、HTML、损坏或回退均拒绝。

清单从该仓库固定 tag 的公开附件取得，先核索引声明的摘要，再复用 `ReleaseClient` 的版本、仓库、平台、文件名、runtime_id、组件/安装器大小和摘要校验。原组件下载与安装事务不变；确认后如同版本完整元数据变化，在下载前拒绝。历史版本只有显式确认后才允许回退，继续保留配置并关闭自动升级。Gitee 索引最多三版，更多历史仅在 GitHub 可达时补充。

raw 独立限制为 `gitee.com` → `raw.giteeusercontent.com` 的同一文件路径。只接受已观察到的临时 `metadata/signature` 参数，不保存或记录其值。包下载仍限定 `gitee.com/foruda.gitee.com`；不把 raw host 放进通用下载主机列表。信任锚是固定发布者仓库的 HTTPS 内容；SHA 是完整性约束，未增加或冒充发布者数字签名。令牌仍只在维护者发布进程。

自动检查成功后 6 小时，重启保留检查时间和通知。手动检查至少间隔 60 秒；索引的 60 秒缓存、独立 ETag、已见最高版本和每版清单摘要存于 `generated/updates/gitee-static-cache.json`，清单按 SHA 缓存。失败退避从 15 分钟逐步增至 6 小时，有效 Retry-After 可延后索引请求；重启、点击或历史请求不会绕过失败退避。过期索引不可冒充最新版本，304 只复用来源匹配且已校验的缓存。镜像落后仍查 GitHub，文件下载回退仍固定版本与 SHA。

## 真实 raw 验证

[官方 raw 文档](https://help.gitee.com/repository/file-operate/raw)支持公开小文件匿名访问、独立主机重定向及 60–300 秒缓存。2026-10-05 12:23 UTC，通过 Gitee v0.4.3 文件页面的“原始数据”取得 distribution.json 地址，生产 UA、无 token/cookie 匿名 GET 得到 HTTP200 / text/plain / 139 字节 / max-age=60，与 git tag 字节一致；SHA `0d1da01b7d3a86de34c54ae99e73c61608b7a8801b695752fc3c697a7649d399`。收据见 `generated/p0-0.4.4-native-raw-probe.json`。初始 query guard 拦截及一次 302 检查另留证据；未改 UA/IP、未认证绕过。

这仅证明一个已有文件和本机当次网络。新索引地址、实际可见延迟及跨网络可用性仍待验证；不保证 raw 不会限流或永远可用。两源均不可用时界面给国内发行页与 GitHub 备用下载；0.4.3 自带更新器遇此情况仍需一次手动 Setup 迁移。

## root 审查后的上线顺序

1. 验收候选与精确提交，按现有门禁构建、发布 GitHub，镜像同一份产物到 Gitee；不发布未验收 1.0。
2. 匿名完整下载并核对清单及全部组件/Setup 的大小与 SHA，确认对应两端 tag 与稳定状态。
3. 本地生成索引（不发布）：`python -m tools.build_update_index --repository Llugaes/bilingual-sora-2nd --directory <最终原包目录> --previous <当前已验证索引文件> --output <候选stable.json>`。工具拒绝缺件、改写同版摘要与 latest 回退，保留最近三版。清理旧版本前先移出索引并等待缓存期限。
4. 单发布者在获批准的分支提交该文件，更新前复核旧 tip、正常快进推送，禁止 force。此步骤必须最后执行；任一附件校验失败保留旧指针。现有中转工具未自动写索引，不能把仅运行它当作静态发现已上线。
5. 从该分支文件 UI 取得真实 raw 地址，匿名核 JSON、摘要、最终主机、缓存与可见版本；再用隔离已发 0.4.3 安装布局及 0.4.4 候选验证“禁 Gitee API＋GitHub 不可达”的真实索引/附件路径。失败停止发布，交 root 决定后续。

准备本地索引不是公开发布。客户端无需新服务或凭据；不会改游戏、存档或安装中的进程。
