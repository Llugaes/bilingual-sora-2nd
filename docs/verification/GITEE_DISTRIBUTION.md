# Gitee 免费分发可行性验证

验证日期：2026-10-03。原版升级基线 v0.3.31，正式交付版本 v0.3.32，发布提交 `80900272f48edf128d287fab8ffc96fbba370d97`。

结论：v0.3.32 已在 GitHub 和 Gitee 正式发布。GitHub 是唯一构建来源，本机中转原始附件，四个 Gitee 文件均通过匿名下载、大小与 SHA-256 校验；新旧更新器的两条真实组件升级验收通过。用户随后选择发版时主动执行一次，完成即退出，取消定时轮询。完整便携 ZIP 超过 Gitee 单附件限制，继续保留在 GitHub。不使用 GitHub 托管机向 Gitee 传大包，不开通付费服务。

## 官方合同与免费范围

[Gitee 当前帮助](https://help.gitee.com/enterprise/introduce/feature) 明确社区版面向个人开发者免费，并支持 Release、Open API；服务表列出社区开源项目附件总容量 3G。但目标免费账号的发行创建页明确显示：单附件不超过 100M，每仓库附件不超过 1G，统计同时包含仓库附件和发行版附件。两处说明不一致，实施按实际上传页较小的额度约束。98.83 MiB 的运行依赖包上传成功，证明它没有按十进制 100 MB 拒绝本次文件。表中的代码文件大小限制不能直接当作 Release 附件限制。

本次读取的 [当前 OpenAPI 规范](https://gitee.com/api/v5/doc_json) 为 `5.4.93`，定义以下能力：

- `GET /v5/repos/{owner}/{repo}/releases/latest`：最新发行版。
- `GET /v5/repos/{owner}/{repo}/releases/{release_id}/attach_files`：附件列表，含 `id`、`name`、`size`、`browser_download_url`；分页上限 100 不等于每个发行版的附件数量上限。
- `POST /v5/repos/{owner}/{repo}/releases`：创建发行版；支持 `prerelease`。
- `POST /v5/repos/{owner}/{repo}/releases/{release_id}/attach_files`：multipart 上传附件。

读取接口的 `access_token` 参数非必填，与下面的匿名实测一致；这不意味着写入接口允许匿名上传。

## 匿名实测结果

请求使用 Python 标准库 HTTPS 客户端，`User-Agent: Sora-Bilingual-Updater/1`，未提供账号、Token 或 Cookie。以下仅代表本机本次网络结果，不代表大陆三网或大规模并发承诺。

| 检查 | 结果 |
|---|---|
| 官方 SDK 的 `releases/latest` | HTTP 200 JSON，返回 `v5.4.86`，单次约 0.23 秒 |
| J2Cache 的 `releases/latest` | HTTP 200 JSON，返回 `2.8.4-release`，单次约 0.24 秒 |
| J2Cache 指定发行版附件列表 | HTTP 200 JSON，取得附件名称、大小和规范下载地址 |
| J2Cache 公开附件完整下载 | HTTP 200 二进制，实际与声明大小均为 `141098` 字节，单次约 1.39 秒，无需登录或验证码 |
| 对同一附件发送 `Range: bytes=0-1023` | 返回 HTTP 200，没有 `Content-Range`，未按分段请求响应；不能假设总能断点续传 |
| Gitee 官方 MCP 项目最新发行版 | HTTP 200，列出 Windows 等平台的发行附件 |

复现入口：[SDK latest API](https://gitee.com/api/v5/repos/sdk/typescript-sdk-v5/releases/latest)、[J2Cache latest API](https://gitee.com/api/v5/repos/ld/J2Cache/releases/latest)、[附件列表](https://gitee.com/api/v5/repos/ld/J2Cache/releases/189697/attach_files)、[公开附件](https://gitee.com/ld/J2Cache/releases/download/2.8.4-release/j2cache-core-2.8.4-release.jar)、[官方 MCP latest API](https://gitee.com/api/v5/repos/oschina/mcp-gitee/releases/latest)。

完整下载的 SHA-256 为 `18e101d41da515a373d670c9bb63e1d4a548229e096fe951885359ba0872087e`，仅作为本次采集收据，不是发布者签名或独立可信摘要。

下载过程从 `gitee.com/.../releases/download/...` 经同站附件地址跳转到 `foruda.gitee.com`。最终地址带临时签名参数：更新器应保存规范下载地址，重试时重新跟随跳转，不把临时地址写入持久清单或日志。每一跳仍须验证 HTTPS 和明确的服务商主机；不能任意放开域名。

## 本项目原版发行包实测

[验证发行版](https://gitee.com/Llugaes/bilingual-sora-2nd/releases/tag/v0.3.31-gitee-validation) 使用独立预览标签，附件直接来自 GitHub v0.3.31，没有重打包。下列下载未使用账号、Token 或 Cookie，完整内容与 GitHub 发布清单校验一致；耗时仅代表本机网络。

| 文件 | 字节数 | 匿名下载 | SHA-256 |
|---|---:|---:|---|
| Setup | 79,578,400 | 37.550 秒 | `fa8436a753a8497acc88383e542ea9c2e6f2c1a00371db8dd43fb946282af3e9` |
| 应用更新包 | 5,510,677 | 3.077 秒 | `32592a8dc104639bbc11e981141d279f74482f089db68e6476f06126a85f0e26` |
| 运行依赖包 | 103,629,162 | 49.529 秒 | `426a480c93a9b01a01ba0f57c01411ec0cffbae70dcfc036348287a84a5352a2` |
| 更新清单 | 1,009 | 0.919 秒 | `e3d2bcdecf98c4d487bf4cb5febb8f2c69cd7a48e4e2e098592670fdd805088a` |

完整便携包为 109,139,817 字节（104.08 MiB），超过网页单附件限制，未尝试绕过；国内源采用 Setup＋已有的应用/运行依赖组件，不增加玩家安装步骤。

特别验证：目标仓库只有预览版时，`releases/latest` 仍返回 HTTP 200，且 `prerelease=true`。客户端不能沿用 GitHub latest 的稳定版语义，改为 `releases?direction=desc&per_page=100`，过滤预览版和非稳定标签后选择最高版本。

## 实施与验收

- 已配置仅限本仓库的 Gitee `projects` 发布令牌，保存在 GitHub Actions secret `GITEE_RELEASE_TOKEN`。令牌不写入源码、客户端或测试收据；本次凭据到期日为 2027-01-01，续期时只更新 secret。
- 用户已同意：Gitee 保留最新三个完整稳定版，新版匿名下载校验并转为稳定版之后才清理旧镜像；GitHub 保留全部历史。自动清理仅处理发布工具专用标记的稳定版，人工/预览记录不纳入删除。
- 单附件 100 MiB、总量 1 GiB 在上传前检查；不分卷，不创建大量仓库绕额度。依赖包未来增大超限时明确停止镜像发布，GitHub 发布保持可用。
- 共享下载器与元数据校验已提取，复用现有安装事务。已通过更新相关回归：预览过滤、缺件回退、双源离线、镜像落后、下载中断回退固定版本/摘要、范围和域名约束、重试复用、配额/本地文件篡改、保留三版、上传失败禁止转稳定，以及仅经 Gitee 组件更新后保留配置和复用依赖的集成测试。
- CI 已证实最小权限令牌可创建预览发行并上传真实应用 ZIP；随后改用本地中转，完成原版 v0.3.31 和 v0.3.32 全部上传、匿名校验及转稳定。v0.3.32 成品双源发布和隔离原版安装目录更新验收通过（见下）。尚未做大陆移动、联通、电信的跨网络采样，不把本机结果承诺为全国速度。

## 自动传输与独立构建的调查记录

- [Ubuntu 流式上传试验](https://github.com/Llugaes/bilingual-sora-2nd/actions/runs/37111844801)：09:05:22 UTC 开始发送 Setup，09:15:15 才发送完 16 MiB，随后达到十分钟上限停止。预览版没有转为稳定版。
- [Windows / curl 试验](https://github.com/Llugaes/bilingual-sora-2nd/actions/runs/37112609440)：5,510,677 字节应用 ZIP 上传返回 HTTP 201，multipart 共发送 5,511,065 字节，用时 162.97 秒，平均 33,816 B/s。它证明上传接口与凭据可用，但这台托管机的跨站传输速度不适合完整包发布。用户决定改为两端独立构建后停止了后续 Setup 试传。
- 曾评估同一提交和标签分别推到 GitHub、Gitee，两端独立构建发布；在 Windows 托管条件未证实后，用户明确优先改用下述本地中转。手动跨站镜像工具仅保留为应急入口，GitHub 正式发布不自动调用它。
- 当前代码需要真实 Windows x64：`build_portable.py` 检查平台、调用 .NET Framework `csc.exe`，`build_installer.py` 使用 Inno Setup，原生测试和安装器验收也需要 Windows。仅有 Linux 容器不能直接代替这条链路。
- [Gitee 云端自定义任务](https://help.gitee.com/enterprise/pipeline/plugin/image-script-run)文档说明 Docker 镜像执行；[PowerShell / Bat 支持](https://help.gitee.com/enterprise/pipeline/plugin/shell-script-run)属于预先纳管的自有主机。尚未找到免费托管 Windows 执行环境的证据，不能宣称 Gitee 端已经能独立出包。
- [企业版计费文档](https://help.gitee.com/enterprise/pipeline/billing)列有每月 1,000 核分免费额度；[社区产品页](https://gitee.com/features/gitee-go)列有仓库开通赠送 200 分钟。适用主体不同，不能把企业每月额度直接许诺给本个人仓库。已进入目标仓库的未保存流水线编辑器检查；未购买额度、未添加自有主机、未运行 Gitee 构建。
- 独立构建还需修订产物身份合同：ZIP 时间戳和 Windows 编译结果可能导致同版本摘要不同。当前客户端的文件级回退有意要求同一摘要，不能直接给它接两份不同构建的包。应先确定可复现构建或整次更新切源的方案，并验证同提交、同版本、清单和组件一致性。

## 本地中转（当前实施）

- GitHub 继续唯一构建、测试及发布，本机只中转同一份原包；无需更改客户端的同摘要回退合同，也不运行 Gitee 构建或配置自托管构建节点。
- `tools.relay_gitee --tag v0.3.31 --download-only` 已在空缓存上取得四个原版文件，共 188,719,248 字节，全部与 GitHub 清单、附件 API 摘要一致。仅证明本机下载段；不将其等同于自动上传完成。
- 中转及 Gitee 共 24 项 Python 回归通过，覆盖源文件不变、失败无成功收据、重试复用缓存、成功后的轻量核对、目标附件变化、预览/草稿过滤、摘要错误、路径限制、并发互斥、配额和保留三版。PowerShell 定时入口语法及未安装状态查询通过。
- 仓库范围、`projects`、90 天有效的凭据已由 Windows DPAPI 加密保存，不写入日志或源码。曾按用户授权配置登录及每 15 分钟触发；18:10:06 按后续要求停用，改为发版时主动执行一次，以下自动任务记录仅为当时验收证据。
- 首次真实自动任务于 17:47:52–17:50:27（UTC+8）完成：复用 GitHub 原版缓存和 Gitee 已有应用包，Setup 上传 24.58 秒、依赖包 30.36 秒、清单 1.04 秒，均 HTTP 201；四个附件匿名 SHA-256 校验全部通过，[v0.3.31 正式镜像](https://gitee.com/Llugaes/bilingual-sora-2nd/releases/tag/v0.3.31)已公开，任务退出码 0。本机实测不能推广为所有网络速度。
- 同一正式版再次由 Windows 自动任务执行，返回 `Already verified on Gitee: v0.3.31; no packages transferred` 和退出码 0，未重复传输大包。首次任务发现并修正 PowerShell 5 的混合日志编码，第二次日志 UTF-8 正常。
- 当前一次性执行和维护命令见 [本地中转发布](../LOCAL_RELEASE_RELAY.md)。付费服务、DNS、游戏进程及玩家配置均未修改。

### 后续改为主动触发

- 按用户最终选择移除本机旧定时任务，`Status` 确认 `LegacyScheduledTask: Absent`；已有 DPAPI 凭据内容保持不变。`Setup` 和旧 `Install` 别名都只配置凭据，不再注册登录或定时触发。
- 推送版本标签后，可主动执行 `-Mode Run -Tag <版本> -WaitForRelease`，只在此次前台任务中等待指定版本正式发布，再中转并退出；已发布时立即开始。等待上限 45 分钟，支持 Ctrl+C，错误和超时不会留下常驻程序。
- 27 项中转及 Gitee 回归通过，新增覆盖发布前 404、预览转正式、指定版本约束、超时退出、API 错误不盲目重试；已发布版本无需等待。PowerShell 语法检查及兼容入口实测通过。
- 18:16:43.934–18:16:45.311（UTC+8）真实运行 `-Mode Run -Tag v0.3.32 -WaitForRelease`：确认两端收据一致，输出 `Already verified on Gitee: v0.3.32; no packages transferred`，退出码 0。结束后无中转 Python 或 PowerShell 进程。
- 此次调整只影响维护者发版入口；已发布的 v0.3.32 玩家程序与四个镜像附件未重打包、未替换。

## v0.3.32 正式交付验收

- [正式发布 CI](https://github.com/Llugaes/bilingual-sora-2nd/actions/runs/37114533716)验证和发布两阶段均成功。Python 共 495 项（9 项按环境跳过），JavaScript 和独立原生宿主检查通过；发行包独立 EXE 启动、真实安装器安装/修复/卸载检查通过。
- [GitHub 正式版](https://github.com/Llugaes/bilingual-sora-2nd/releases/tag/v0.3.32)包含五个附件；[Gitee 正式版](https://gitee.com/Llugaes/bilingual-sora-2nd/releases/tag/v0.3.32)包含原版 Setup、应用 ZIP、运行依赖 ZIP 和清单，未重新构建。四个文件均通过匿名下载 SHA-256 验证。
- Windows 定时任务于 18:03:15 自动触发，18:06:20 完成，退出码 0；没有手动触发该次同步。应用包上传 3.40 秒、Setup 24.29 秒、依赖包 33.68 秒、清单 1.04 秒。均为本机本次网络实测。

升级验证使用原版 v0.3.31 完整 ZIP 创建隔离目录，没有改动用户安装目录或设置。第二条测试的更新器代码取自第一条实际升级后的 v0.3.32 发行文件，没有借用开发目录的实现。

| 检查 | 结果 |
|---|---|
| 原版 v0.3.31 自带的更新器经 GitHub 更新到 v0.3.32 | 通过，9.461 秒 |
| 已发布 v0.3.32 更新器向 v0.3.31 隔离安装目录应用 Gitee 组件更新 | 通过，13.041 秒；GitHub 被禁止访问，实际调用 0 次 |
| 两条路径的原配置 | 逐字节保留 |
| 两条路径的未变运行依赖 | 复用原目录，未下载运行依赖包，python.exe 修改时间不变 |
| 两条路径升级后的安装文件 | 654 个文件全部与安装收据 SHA-256 一致 |

旧版客户端仍需先经 GitHub 更新，或使用 Gitee 的新版 Setup 覆盖安装，才会认识国内更新源；不能把第二条隔离测试描述为旧版客户端原本就支持 Gitee。
