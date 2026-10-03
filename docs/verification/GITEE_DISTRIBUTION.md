# Gitee 免费分发可行性验证

验证日期：2026-10-03。项目基线：`764e25d`，当前发行版 v0.3.31。

结论：免费账号已上传原版 Setup、应用包、依赖包和清单；四个文件均通过匿名下载、大小与 SHA-256 校验。免费路线适合安装包和组件更新，完整便携 ZIP 超过单附件限制，继续保留在 GitHub。更新器与自动发布实现正在验证，尚未发布 v0.3.32；不开通付费服务。

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
- 待验证：CI 使用最小权限令牌进行真实自动上传/校验/转稳定及同版重试；v0.3.32 成品双源发布和原版安装目录的更新验收。尚未做大陆移动、联通、电信的跨网络采样，不把本机结果承诺为全国速度。
