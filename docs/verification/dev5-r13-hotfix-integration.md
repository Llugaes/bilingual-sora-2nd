# 1.0 DEV5-r13：真实热修合入与候选验证

本阶段实际消费用户给出的 canonical `2399896c`（只提供前缀），延续全部 13 类、D1/D2/D3、MOD/Physical、八种 base、三语言链及 Swap 目标。此文只记录本阶段的实际证据，不把 0.4.3 验收迁移为 1.0 验收。

## Git 合入已完成

工作树 `main` 的原 HEAD 为 `d62231fec5e11eeed79dfa201c8fe617c82d3587`。83 个脏改/未跟踪源文件逐一核对已有 SHA 后，正常 Git checkpoint 为 `dcea41acb1b84d6bd799e2b9812d7ea8f3cf38e2`。历史候选和生成证据保留在原位。

通过本回合可见的 `auto_review` 对限定本地 Git 的正常 `require_escalated` 审核，导入已验证的本地 bundle 并顺序执行真正的 `git cherry-pick -x`：

| 上游 0.4.3 commit | 对应本地 1.0 commit |
| --- | --- |
| `1a9c126e4e66f453fb18050077f5ed29fb96d45a` | `6708e20c367274726f799a197c056efacd20f0c9` |
| `ffdc7c0ba2a9755bff72865a65a3c71a38cb1441` | `ffe1ae35afac83a64d770a9dc82b77517f5c13aa` |
| `45666d4a823e87f79755b4bc77e523f923c8446c` | `163c3237a8e17c814ddd3fe83520920fa80692a9` |

第一条有测试导入冲突，并实际复现旧 r12 精确诊断行号变体与 P0 合同的同址冲突。删除四份被 P0 替代的重复变体，保留固定 ABI、severity、栈槽及 `diagnostic_report` 依赖校验。诊断行号值变化按已审 P0 合同允许；寄存器、偏移、stride、分支及依赖危险变化仍拒绝。保留 MOD 的 CRC 数据与 IAT 语义保护，没有扩大整个 EXE/版本/section 白名单。

第二条无冲突。第三条融合三份 README、overlay 与测试，保留简洁文档、三主题真实状态及 D1/D2/D3；默认字体改为只准备外置缓存、完整校验、运行时加载，不自动写游戏文件或认领未知字体。

Git 映射、最终差异、83 文件前后摘要和冲突记录见 [integration-receipt.json](../../generated/dev5-hotfix-integration-2399896c/integration-receipt.json) 与同目录 `hotfix-merged-final.diff`。没有引入 0.4.4，没有网络操作、push、tag 或公开发布。

## 候选身份和验证边界

独立候选为 `dist/comprehensive-1.0.0-dev5-r13/DEV`。显示 `DEV 1.0.0-dev5-r13`，overlay 与更新页共用同一校验过的 DEV manifest 标签。目标仍为 `1.0.0`；构建器原有 metadata 版本保持 `0.4.2`、包格式协议仍为 1，未改稳定发布版本。新候选使用新包及新 hash，不沿用 r12 ZIP/hash。

没有携带字体、模型、语言事实、状态或用户缓存；只复用经摘要核对的通用 runtime 与 launcher。没有读取受限旧字体目录、修改 ACL、启动第二 UI/backend、接管或改写当前游戏。用户普通权限的首次自动字体准备、真实 GPU 加载仍待实机时点验证。

第一条合入的 26 项单测、第三条合入的 133 项相关回归均为全部通过、0 跳过、0 失败。最终包的生产 PE 管线检查当前官方（磁盘 EXE SHA `cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`）、旧官方、语音 MOD 各 67 入口，接受有界诊断行号变化并拒绝危险负例；MOD/语音依赖 34 个危险负例拒绝。最终包 D1/D2/D3 的正式编译模型和自建隐藏 V8 宿主 3/3 通过。宿主不是真实游戏。

新包的真实资源生产编译及独立 oracle 在 `generated/dev5-hotfix-integration-2399896c/final/` 保存输入/规则/模型摘要、逐阶段日志、主副互换冷热结果和拒绝原因。本阶段只补与融合/纠偏相关的必要回放，不把旧 20 组合完整重跑当新目标。此前全八 base 的证据保留其原规则/输入身份；新生成模型才标记为 r13 正式 pipeline 结果。

## 当前开放项与现场保护

13 类入口的细分合同和剩余原因沿用 [系统覆盖](dev5-system-coverage.md)、[渲染合同](dev5-render-contract.md) 与 [9935 阶段](dev5-9935-stage.md)。资源可配对不证明真实 hook、pointer/key 载体、截断输入或动态现场值正确；短标签 Physical、同 item 不同入口、按钮/菜单、战斗提示仍需真实控件核对。MOD 只验证静态样本合同，未安装、执行或验证其完整资源/界面。

历史 44.914 秒现场记录不是最后按钮端到端耗时。r13 离线冷热结果只能说明生产建模/缓存复用，按钮→prepare→publish→wire→resident ACK 与真实帧时仍 pending，没有虚构 1–3 秒硬指标。

本回合只读 `Get-CimInstance Win32_Process` 被管理权限拒绝，已停止该路线，无升级、无重试、无替代注入。无法凭历史 PID 判断当前 resident 是否兼容，因此没有执行条件 DEV 切换，也没有备份/覆盖用户当前设置。切换前须从受支持的只读状态确认当前单连接及 revision，并备份用户当时最新的 0.4.3 偏好。驻留代码变更按 AGENTS 要求通过新游戏进程加载；如 revision 不同，只需用户正常退出/重开游戏，再按已经授权的正常单工具切换执行，禁止热卸/叠加/强杀。

## 最终效果红项与后续候选

r13 的最终资源回放发现三组配置各 7 个 native type16 控制码不一致，门槛失败，未分发/启动。诊断确认它不是 oracle 简单漏掉颜色：同一正式模型中，`translate` 输出额外 `<c698>…</C>`，而 `render` 采用独立语义单元并保持原输入颜色，两者不一致。上游原始 name 模板并不含该包装；无 key/scope 的通用构造器模板抢先于已绑定 description 的效果角色。

修复只限定未拥有 key/scope 的早期完整配对优先级：已有 description 绑定时先使用经过准入的独立角色；硬拒绝仍传播，独立完整配对的回退仍保留，明确 owner 仍先于分段。Python/JS 同步，新通用正负测试先红后绿，JS 169、Python 59 全通过。保留 r13 文件/包/hash/失败日志，不热替换。后续使用新候选 `1.0.0-dev5-r14` 再回放同一独立 raw oracle。

1.0 用户实机验收、普通用户首次生命周期和公开发布均未完成。
