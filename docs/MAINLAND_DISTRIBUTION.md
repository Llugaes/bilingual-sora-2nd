# 大陆下载与自动更新方案

查证日期：2026-10-03。仅引用服务商官方文档、官方定价页或服务商维护的官方仓库；“已证实”是页面明确写出的事实，“推断”是基于这些事实对本项目用途的判断，“待确认”是官方当前公开资料没有给出或需在目标账号/地域复核的内容。

状态：付费方案保留，尚未开通存储/CDN或修改 DNS。Gitee 免费发行包上传和匿名下载已验证，更新器接入正在验收。代码核对基线为 `8f6969c`（v0.3.31）。部署域名在接入时单独确认，本文件使用 `<项目子域名>` 占位。

当前执行选择：保留付费方案，暂不开通；Gitee 免费下载已验证。跨站大包上传慢，且未找到 Gitee 免费托管 Windows 的证据，用户选择优先保持 GitHub 单一构建来源，经维护者本机转发原包到 Gitee。每次正式发版后主动执行一次，完成即退出，不设置定时轮询。[本地中转入口](LOCAL_RELEASE_RELAY.md)；GitHub 保留完整历史。[实测记录与未通过项](verification/GITEE_DISTRIBUTION.md)。以下 COS/CDN 内容仍是备选提案。

## 付费备选方案（暂不实施）

后续若需要独立容量和服务保障，可使用腾讯云中国大陆 COS 标准存储 + 静态 CDN（下载大文件），通过自有已备案子域名提供下载页、版本清单和安装/更新包。GitHub 继续保存源码、发布记录和备用下载；发布流水线把同一次构建的产物同步到两端。无需另建常驻服务器或数据库。

依据：腾讯云支持已备案域名接入大陆 CDN、COS 私有桶授权回源，以及软件安装包/应用更新的大文件下载场景；仅配置项目子域名即可。账号实名认证、域名归属验证、HTTPS 证书和计费开通仍需在目标账号完成。[CDN 配置指南](https://cloud.tencent.com/document/product/228/3149/)

玩家预期体验：首次安装从国内下载页直接取得 Setup；以后在工具内自动检查、下载和安装，国内源失败自动尝试 GitHub，不要求玩家配置代理、云账号或手工挑选镜像。网络与下载工作继续在后台线程执行，沿用现有安装时机和配置保留规则。

## 当前更新链路的实际改造点

- **版本发现也要迁移。** [GitHubClient](../sora_bilingual/updates/github_updates.py) 的 `latest()` 访问 GitHub API，`metadata()` 和 `download()` 再取 GitHub 附件。只镜像 Setup 或 ZIP 仍会让检查更新依赖 GitHub。
- **保留来源校验。** 当前仅接受指定 GitHub HTTPS 主机和仓库发布路径，并逐跳校验重定向；不能用任意 URL 替换绕过。将来源适配集中在更新客户端，以统一的版本/组件描述交给 [UpdateService](../sora_bilingual/updates/update_service.py)，避免让业务层模拟 GitHub API JSON。
- **复用安装事务。** [安装器](../sora_bilingual/updates/update_installer.py) 已有逐文件校验、路径限制、备份回滚和配置保留。新增分发源不复制一套安装器。
- **改善弱网恢复。** 当前单次网络超时 20 秒，失败后自动检查等待 15 分钟；未完成的 `.part` 文件会删除。新增源时需要整次检查的总时限、有限重试/自动回退，以及绑定版本、大小和摘要的断点续传；服务器不正确支持 Range 时从头下载，最终仍校验完整 SHA-256。已完成且校验通过的 ZIP 继续复用。
- **来源状态不能误导。** 国内源失败后进入备用源或明确失败；无法刷新缓存时显示上次成功检查时间，不能把网络失败当成“已是最新”。手动重试不能被自动重试间隔阻塞。

## 发布、缓存与可信更新

1. 扩展现有 [release workflow](../.github/workflows/release.yml)，构建和验证一次，上传相同文件到 GitHub 与 COS。版本路径不可覆盖；运行依赖以现有 `runtime_id` 复用。
2. 完整上传并核验后，最后更新国内稳定版入口；任一文件失败都不推进该入口。同步失败须在 CI 显示并支持对同一产物重试，不能宣称两端已同步。
3. 版本文件长缓存，稳定版清单短缓存（建议初值 60 秒，上线实测后调整），发布时刷新清单并预热安装包。大文件启用适配的 Range 回源；下载页说明和图片也应本地托管，避免依赖 GitHub 图片才能看安装教程。[CDN 缓存与分片回源](https://cloud.tencent.com/document/product/228/3149/)
4. 包摘要检验下载完整性，发布清单签名验证发布者；客户端固定可信公钥和允许的下载来源。清单应绑定版本、平台、组件大小和摘要，并拒绝降级。采用成熟签名实现，不自写密码算法；若引入清单过期时间，必须同时安排无新版本时的续签，避免长期未发版后正常更新不可用。[TUF 的更新元数据设计依据](https://theupdateframework.io/docs/overview/)
5. CI 凭据仅授权发布存储路径及必要的刷新操作；配置用量告警和 CDN 用量封顶措施。告警不等于严格的费用硬上限，阈值与停服动作在开通时确认。

## 旧版本怎样接上国内源

v0.3.31 及之前的现有更新器没有自有域名入口，不能靠更改 DNS 自动迁移。需要发布一个同时认识国内源和 GitHub 的过渡版本：能访问 GitHub 的老用户按原流程更新；连 GitHub 都打不开的用户从国内下载页获取相同 Setup，按现有覆盖安装流程保留配置。迁移后，两端继续使用同一版本和同一产物，不分裂成国内特供版本。

## 用真实发行包估算费用

v0.3.31 的 [官方发行附件](https://github.com/Llugaes/bilingual-sora-2nd/releases/tag/v0.3.31) 清单记录：Setup `79,578,400` 字节，应用更新包 `5,510,677` 字节，运行依赖包 `103,629,162` 字节。依赖未变时只下载应用更新包。以下按十进制 GB、腾讯大陆 CDN 首档 `0.21 元/GB` 计算，仅估算下行流量费；不含活动折扣、失败重传、COS 存储/请求/回源和超额 HTTPS 请求。[官方 CDN 定价](https://buy.cloud.tencent.com/pricing/cdn)

| 场景 | 下载量 | CDN 下行费估算 |
|---|---:|---:|
| 1,000 次首次安装 | 79.58 GB | 16.71 元 |
| 1,000 次普通应用更新 | 5.51 GB | 1.16 元 |
| 10,000 次首次安装 | 795.78 GB | 167.11 元 |
| 10,000 次普通应用更新 | 55.11 GB | 11.57 元 |

依赖有变化的更新需额外下载运行依赖；新引入依赖的过渡版也可能触发这一点，不能把 5.51 MB 承诺为每个版本的固定大小。回源量取决于节点命中、预热和缓存配置，不能简单按“每个版本只回源一次”估计。小规模先按量计费观察实际账单，再决定是否购买流量包；开通收费服务前确认预算。

## 上线验收要求（尚未执行）

- 禁止 GitHub 网络访问时，首次 Setup 下载、版本发现、组件更新均能仅靠国内源完成；国内源故障时能切回 GitHub。
- 旧版经 GitHub 更新和经国内 Setup 覆盖安装两条迁移路径均保留配置；未变依赖不重复下载。
- 中断续传、服务端忽略 Range、摘要/签名错误、旧清单、部分上传、CDN 旧缓存、超时和取消均有确定结果，不把失败显示为已更新。
- 安装后的文件与 CI 验证产物一致；下载页、版本清单和工具显示版本一致。
- 大陆移动、联通、电信分别采样首次下载和热缓存下载，记录检查耗时、下载完成率和速度。单台开发机结果不能证明全国体验；只有实测通过才能称国内链路已可用。

## 服务商资料比较

| 候选 | 下载与域名事实 | 自动发布 | 持续费用口径（长期标准价，不含新客优惠） | 适配判断 |
|---|---|---|---|---|
| 腾讯云 COS 中国大陆 + 腾讯云 CDN | [已证实] COS 默认域名按存储桶和地域生成；对象支持任意类型，2024-01-01 后新桶用默认域名访问文件是直接下载。自定义源站域名可不开 CDN；接入中国大陆 CDN 的域名须已备案。 | [已证实] PUT Object、SDK、COSCMD 均可上传；[推断] 可由 CI 上传 `.exe`、`.zip` 与版本元数据。 | [已证实] COS 外网下行 0.50 元/GB、CDN 回源 0.15 元/GB；大陆 CDN 下行首阶 0–2 TB/月 0.21 元/GB，按月阶梯；HTTPS 每账号每自然月 300 万次免费，超出 0.05 元/万次。存储、读写请求另计。 | [推断] 推荐作为大陆首次下载和自动更新主源；正式接入仍需完成域名验证、计费与缓存配置。 |
| 阿里云 OSS 中国内地 + 阿里云 CDN | [已证实] OSS 可上传任何类型文件；默认 Bucket 域名为 `<bucket>.oss-<region-id>.aliyuncs.com`，公网访问可直接下载；中国内地 Bucket 绑定自定义域名须 ICP 备案，CDN 加速区域含中国内地时也须备案。 | [已证实] PutObject/SDK/ossutil；[推断] 可由 CI 上传发布物。 | [已证实] OSS 外网流出按时段计费（官方价格页：闲时 0.25 元/GB、忙时 0.50 元/GB）；大陆 CDN 首阶 0–10 TB/月 0.24 元/GB，随后 0.23/0.21/0.18/0.15 元/GB 阶梯。存储、请求、OSS CDN 回源另计。 | [推断] 技术上可作主源替代；当前建议优先使用腾讯云方案，减少跨服务商配置。 |
| Cloudflare R2 自定义域名；香港区域 OSS 备用 | [已证实] R2 自定义域名要求域名已在同一 Cloudflare 账号成为 zone；`r2.dev` 仅开发用途且限流。Cloudflare China Network 文档明确：R2 不能在中国大陆创建，且该服务不支持 R2 自定义域名在大陆节点接入。阿里云 OSS 中国香港 `cn-hongkong` 有公网 Endpoint；非中国内地 Bucket 绑定自定义域名按阿里云文档无需 ICP。 | [已证实] R2 有 S3-compatible、Workers API；OSS 有 PutObject/SDK。 | [已证实] R2 Standard：$0.015/GB-month，Class A $4.50/百万次，Class B $0.36/百万次，互联网出网免费。香港 OSS 仍按存储、请求、外网流出计费，精确值按官方地域价格页复核。 | [推断] R2 不能保证大陆访问速度，香港 OSS 也可能受跨境链路影响；适合作补充/故障切换候选，不应据此承诺大陆体验。 |
| Gitee Releases | [已证实] Gitee 官方博客给出发行版附件下载 URL：`https://gitee.com/{namespace}/{repo}/releases/download/{git_tag}/{attach_file_path}`。官方维护的 SDK 发布说明列出发行版附件查询、上传、删除、下载接口。 | [已证实] 有 OpenAPI/官方维护 CLI 线索；[实测] 仓库级 projects 令牌可配置；自动上传正在 CI 验收。 | [已证实] 个人社区版免费。实际上传页显示单附件 100M、每仓库附件 1G，与帮助站的 3G 说明不一致，按实际较小额度实施。 | [实测] 本项目 Setup、应用包、依赖包和清单均上传及匿名校验成功。Gitee 保留最新三版，完整便携包和全部历史保留 GitHub。 |

## 1. 腾讯云 COS 中国大陆 + CDN

### 已证实事实

- COS 文档列出大陆默认域名格式 `<BucketName-APPID>.cos.<Region>.myqcloud.com`，并说明默认域名由系统按存储桶名称和地域生成；香港也有独立 `ap-hongkong` 默认域名。来源：[地域和访问域名](https://intl.cloud.tencent.com/zh/document/product/436/6224)。
- COS 支持控制台、工具、API/SDK 上传；PUT Object 是官方上传 API。来源：[上传与下载](https://cloud.tencent.com/document/product/436/30740/)、[PUT Object](https://cloud.tencent.com/document/product/436/7749)。
- 腾讯云明确写出：2024-01-01 后创建的桶，默认域名访问任意类型文件不支持预览而是直接下载；公有读对象可由 URL 直接下载。因此 `.exe`/`.zip` 作为对象可用，默认域名行为是下载而不是浏览器预览。来源：[上传与下载](https://cloud.tencent.com/document/product/436/30740/)。
- 自定义源站域名通过 CNAME 绑定，且不必开启 CDN；若接入国内 CDN，域名需已备案，海外 CDN 不要求备案。腾讯云还说明自定义 CDN 域名会产生 CDN 回源流量费和 CDN 下行流量费。来源：[自定义源站域名](https://cloud.tencent.com/document/product/436/56559)。
- 腾讯云 CDN 明确把软件安装包、压缩包列为静态 CDN/下载加速场景。来源：[CDN 新手指引](https://cloud.tencent.com/document/product/228/43827)。

### 价格与自动化证据

- COS 产品定价页当前公示的标准公有云表格包含：标准存储 0.118 元/GB/月、外网下行 0.50 元/GB、CDN 回源 0.15 元/GB、标准读/写请求 0.01 元/万次。实际应在目标地域和计费模式下复核：[COS 产品定价](https://buy.cloud.tencent.com/price/cos)。
- CDN 中国大陆按流量计费为月度阶梯：0–2 TB 0.21 元/GB、2–10 TB 0.20、10–50 TB 0.18、50–100 TB 0.15、≥100 TB 0.11 元/GB；按带宽是另一计费模式，不能混用：[CDN 定价](https://buy.cloud.tencent.com/pricing/cdn)。
- CDN HTTPS 为增值项：每账号每自然月 300 万次（含）免费，超出按 0.05 元/万次；HTTP 请求不另行计费：[HTTPS 计费常见问题](https://cloud.tencent.com/document/product/228/43799)、[增值服务计费](https://cloud.tencent.com/document/product/228/75563)。
- COS 作为 CDN 源站时，COS 侧计 CDN 回源流量和请求，CDN 侧计下行流量；这不是 COS 外网下行与 CDN 下行同时按同一份缓存命中流量重复计算的简单相加，最终以账单和命中/回源情况核对：[流量费用](https://cloud.tencent.com/document/product/436/53863)。

## 2. 阿里云 OSS 中国内地 + CDN

- [已证实] 阿里云文档明确可上传任何类型文件，PutObject 单次直传上限 5 GB，较大文件使用分片上传：[上传文件到 OSS 的多种方式](https://help.aliyun.com/zh/oss/user-guide/upload-objects-to-oss/)、[PutObject](https://help.aliyun.com/zh/oss/developer-reference/putobject)。
- [已证实] 外网 Bucket 域名为 `<bucket-name>.oss-<region-id>.aliyuncs.com`，默认可用；自定义域名通过 CNAME，绑定中国内地 Bucket 必须 ICP 备案，非中国内地节点（含中国香港）按该页说明无需 ICP：[访问域名类型](https://help.aliyun.com/zh/oss/user-guide/access-oss-via-bucket-domain-name)、[自定义域名](https://help.aliyun.com/zh/oss/user-guide/access-buckets-via-custom-domain-names)。
- [已证实] OSS 接入 CDN 的静态资源范围包括附件和文件下载；加速区域包含中国内地时，加速域名需备案：[CDN 加速 OSS](https://help.aliyun.com/zh/oss/user-guide/cdn-acceleration)。
- [已证实] 阿里云 CDN 中国内地按流量首阶为 0–10 TB 0.24 元/GB，后续阶梯为 0.23/0.21/0.18/0.15 元/GB；OSS 直接外网流出价格页显示闲时 0.25、忙时 0.50 元/GB：[CDN 基础服务定价规则](https://help.aliyun.com/zh/cdn/product-overview/billing-rules-of-basic-services/)、[OSS 产品定价](https://cn.aliyun.com/price/detail/oss)。
- [待确认] 目标账号、地域冗余类型、CDN 计费模式会改变存储、请求和回源精确账单；不要把历史示例价或新用户试用额度当长期报价。

## 3. R2 与香港区域对象存储补充

- [已证实] R2 自定义域名可启用 Cloudflare Cache，但域名必须先作为同一账号的 zone；`r2.dev` 有可变请求/带宽限流，仅供测试：[Public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/)、[R2 limits](https://developers.cloudflare.com/r2/platform/limits/)。
- [已证实] Cloudflare China Network 官方可用性页明确写出 R2 不能在中国大陆创建，且该服务不支持 R2 自定义域名在大陆节点接入，可另看 Global Acceleration 等产品。这描述产品接入能力，不代表大陆用户一定无法访问境外 R2 域名；本笔记没有实测该跨境链路：[China Network 可用产品](https://developers.cloudflare.com/china-network/reference/available-products/)。
- [已证实] R2 Standard 定价为 $0.015/GB-month、Class A $4.50/百万请求、Class B $0.36/百万请求，互联网出网免费；S3 API endpoint 和 `PutObject` 能用于自动上传：[R2 pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 upload objects](https://developers.cloudflare.com/r2/objects/upload-objects/)、[S3 API compatibility](https://developers.cloudflare.com/r2/api/s3/api/)。
- [已证实] 阿里云 OSS 中国香港地域 ID 为 `cn-hongkong`，公网 Endpoint 为 `oss-cn-hongkong.aliyuncs.com`；非中国内地 Bucket 的自定义域名按官方文档无需 ICP，但文档同时提示大陆访问境外节点可能延迟增大：[地域与 Endpoint](https://help.aliyun.com/zh/oss/user-guide/regions-and-endpoints)、[自定义域名](https://help.aliyun.com/zh/oss/user-guide/access-buckets-via-custom-domain-names)。
- [待确认] 香港 OSS 的精确存储/请求/外网流出账单要按地域、存储冗余和计费时段在官方价格页复核；大陆链路质量需实测。适配判断：仅作补充或故障切换候选。

## 4. Gitee Releases 免费路线

- [已证实] Gitee 官方博客给出发行版附件下载路径，附件可被稳定地引用为版本和文件名 URL：[发行版附件 URL 更新](https://blog.gitee.com/2022/08/18/update/)。
- [已证实] Gitee 官方维护的 TypeScript SDK 发布页列出“指定 Release 附件清单、上传、删除、下载”接口；官方前端组维护的 `gitee-release-cli` 也展示了用 token 执行 `assets upload` 的命令：[SDK v5 release](https://gitee.com/sdk/typescript-sdk-v5/releases)、[gitee-release-cli](https://gitee.com/gitee-frontend/gitee-release-cli)。
- [已证实] 新帮助站说明个人社区版免费、支持 Release/Open API，并列出开源项目附件总容量 3G；实际账号上传页进一步显示单附件 100M、每仓库合计 1G（仓库附件与发行附件合并），实施按此较小额度检查。仓库文件配额不能代替发行附件配额：[社区版功能与服务对比](https://help.gitee.com/enterprise/introduce/feature)。
- [实测] 本项目原版 Setup、应用包、依赖包和清单均已通过上传与匿名下载 SHA-256 校验。`latest` 会包含预览版，客户端必须自行过滤；完整便携包超过附件上限，仅保留 GitHub。自动发布与正式更新器接入仍以验证记录中的阶段为准。[验证记录](verification/GITEE_DISTRIBUTION.md)

## 接入前仍需确认

1. 腾讯云目标账号是否可直接开通大陆静态 CDN、域名接入和 HTTPS 证书；正式接入前用 `<项目子域名>` 做控制台预检。
2. 选定地域、标准存储/多 AZ、CDN 按流量或按带宽后，按实际包大小和月下载量核对 COS、CDN 回源、CDN 下行、HTTPS 请求和请求次数账单。
3. 香港/R2/Gitee 只承担补充时，需实测大陆三网首次下载、断点续传、Range、TLS 与失败回退；本研究没有把跨境链路当作可保证 SLA。
