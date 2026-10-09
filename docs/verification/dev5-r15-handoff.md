# r15 独立 DEV 候选交接

本轮从精确已验收源 `d7d98f057470dab766333f4fbe719749e24b2f38` 建立 `--no-hardlinks --no-checkout` 独立 clone，分支 `replacement/dev5-r15`。原 HEAD 与该源相同；原树两份未提交验证文档没有复制，未使用任何旧脏实现或运行状态。原工作树、运行中的 r14 ROOT、游戏、字体安装、用户配置、存档、旧线程／DB／writer 锁均未修改。没有启动 UI/game、attach、第二 RPC、诊断开关、resident 替换、push、CI 或 1.0 发布。

## 源与身份

044 原提交 `9f3726e6d963a722438c76d5597941d3edbb7cce` 精确 `cherry-pick -x`，本地映射 `9c13fc9f16467bff205949abcb7220bb3cee7dee`。README 冲突保留 r14 内容；程序／分发基础版本仍为 `0.4.2`，候选显示 `DEV 1.0.0-dev5-r15`。044 静态索引与回退实现已包含；沿用既有 DEV 标记，在下载／安装前拒绝稳定升级和回退覆盖，包括带 installed receipt 的 DEV 包。该更新通道修复不代表 frida-agent.dll 闪退修复。

最终源提交与 ZIP SHA 以候选收据为准：独立 clone 的 `dist/comprehensive-1.0.0-dev5-r15/packages/candidate-package.json`，以及 `generated/replacement-r15/candidate-delivery.json`。入口是同一候选的 `DEV/BilingualSora2nd.exe`。程序来自已提交 clone；只按 r14 完整 DEV 包清单逐文件校验并复用公开 runtime／launcher 字节（r14 没有稳定安装收据），不带 r14 程序、配置、缓存、model、agent token、游戏路径或字体安装状态。字体及加载器资产来自提交，仍需新候选首次正常准备。

## 实现与首个离线失败

| 家族 | 证据与修复 | 边界 |
| --- | --- | --- |
| 语言偏好 | 旧每新游戏会话同步主语言的逻辑移除；仅全新配置 pending 初始化主 gamebase、副 JA，JA base 副 EN；手选（包括选择当前值）取消 pending。复用现有 OS 文件锁，UI 和后端启动／默认／手柄窄更新在同一短事务内读取最新值，消除整份旧快照覆盖 | 全八 base、旧持久化、再次读取、重连路径和真实线程交错离线通过；实际 UI 生命周期待用户验收 |
| 地图复制名称 | 资源与 catalog 译文齐全，首次模型失败是 `map_spot` 只选 SpotData，遗漏 AreaData。改为整个 mapjump `/name` 家族，保留 LF 删除、同族冲突拒绝和 Viewer 隔离。EN→简中＋JA 回放两条 plain 变为正确双语，Le Locle 保持正确 | 截图实际 native carrier／node path 未捕获，不宣称实机闭环 |
| 书籍提示／正文 | 八语原字段可关联；完整有色 Book List 提示可正确渲染，单独提示不入词典。正文有两个不同物品 owner，局部模型各正确，无 owner 仍拒绝 | 实际 setter 分段与物品身份未知，未添加句子例外或放宽身份门禁；本轮交付诊断设计而不是假定修复 |
| 交付／获得通知 | 原 SCP 的 ITEM_SUB_MESSAGE 单段／双段、EV／TK 家族被提取门禁遗漏；与历史 data crystal 资源调用同属被漏 SUB 家族。已验证 helper 的既有精确转发程序，扩展整个 helper 家族；alignment 保留 add/remove 区别，VM hash／tokens／PC 与多 owner 冲突拒绝不变 | 新 Monster Bird Meat 截图实际调用和输出 buffer→label 生命周期未知；静态缺失是已证实的离线失败，不把截图未知归于已知运行路径 |
| 状态枚举参数 | r14 模型复现 Resist Mute/Freeze、Burn/Confuse/Deathblow 两侧仅标题变译。状态名与同名物品冲突使 `%s` 参数走通用拒绝。按原始 effect98/type10、name/stat/format 及 LINK/PERSENT 字段编译完整状态列表角色；只取 ConditionInfo 名称，逐成员翻译并使用各目标资源分隔符／百分号 | 状态名、列表、数值与外层颜色／字号都校验；未知成员、角色内冲突、完整句歧义及不完整资源继续拒绝。实际标签入口仍待验收 |

## 回归与证据

`generated/replacement-r15/` 保留可复查 JSON 与日志；命令实现存于本次提交的 tests/tools 中。196 项针对性 Python 回归通过，包含新增状态角色歧义负例，见 `targeted-python-final.log`。JS resolver／identity 35 项及必要 native 模拟 5 项通过，见 `targeted-js-final.log`、`targeted-native-js-final.log`。

- `raw-map-book-coverage.json`：独立物理字段分母，八语 26,168 个非空字段，catalog 缺失／错配为 0。仅原始字段覆盖，不是 UI 覆盖；association key 仍复用生产 identity，报告明确该限制。
- `map-families.json`：572 个实际 mapjump 名称记录，64 个家族语言组合，10,985 次最终 render；目标原文来自另一语 PAC 的同物理 family／occurrence／row，错配、漏项、render 失败为 0。仅一份完整 catalog 模型用于跨表冲突隔离，没有重跑无关大模型矩阵。
- `model-path-replay.json`：原 EN base／主简中／副 JA 的三张地图和两条书籍字符串；完整字段与裸分段路径分别记录，物品身份未知未混成 pass。
- `item-transfer-family.json`：五个案例 seed 脚本内所有 item-message 操作，29 个 producer（含 12 个新增交付记录）；EN／简中／JA 的原始 SHA、helper、VM token 与 PC→slot provenance→local resolver→完整主副文，261 个实例通过。此有界脚本集合不是整个游戏事件分母。
- `condition-lists.json`：八语原始 ConditionInfo 字段及去指针 scalar peer 独立核对 51 个名称；64 个状态专属小模型、57,600 次完整参数／最终副文检查、384 个未知或畸形负例，失败 0。截图两条逐成员得到 `封魔･冻结`／`封魔･凍結` 与 `炎伤･混乱･即死`／`炎傷･混乱･即死`，数字 100 和各语资源百分号正确。不是只看有双语两行。

## 有界诊断与切换门槛

诊断默认关闭。本轮未在当前 r14 配置中启用。新 agent 复用现有 setter／snapshot；只由一个最多 64 条的 Map 保存最近输入身份，label 不另持有诊断对象。原串最多 2,048 字符、node path 最多 12×256 字符；table 事件最多 12 个，每个 key 最多 512 字符。记录事件总数／丢弃数、截断标志、最终阶段，因此晚于第 12 个事件的歧义不会被隐藏。附 input/caller、scope、global pair、table key、script frame／origin／record／rejection／source locale 和实际 presentation；没有新增 hook 或后台 native 指针采集。

root 之后协调切换与新的正常游戏进程。当前游戏继续测试时，本候选不替换 resident；启用诊断／采集需要另行授权与安全时点。需要补地图实际路径、书籍 setter 分段与确切物品 owner、通知 VM 输出 buffer 的身份传递、状态列表实际完整输入以及语言偏好真实生命周期。首次注入 frida-agent.dll 闪退原因仍未知；复用同一公开 runtime 不能消除该风险。上述实机门槛通过前，候选不是 1.0 稳定发布。
