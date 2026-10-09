# r19 文本失败链：候选检查点，未实机验收

起点为 r18 `30b98715451447a1f82abda9baeb08e8e5cc2829`。原 repo 接管时无未提交修改；唯一 writer 位于 `task-3/sora-bilingual-r19` 的 `replacement/dev5-r19`。执行速度为普通/default。没有新 writer、旧线程重启、公开发布或游戏重启。r18 这批用户案例的实机验收仍失败。

## 首个可证失败

只使用既有 resident，按产品正常 quit、原 backend 退出、同一锁下 reconnect、完整 snapshot、关闭临时 client、重新打开原 r18 的顺序取得一次原文。没有 Frida attach、new resident、load model 或 hook 替换；游戏 PID 31480 与创建身份保持。原 UI 展开状态随后恢复。采样前后的 resident revision 为 `789ae56bd79a9cff6e73ae668dea6b8e14f458f980e1b021dc1505d79ebbe0c2`，diagnostics=false。

`generated/r19-existing-owner-snapshot.json` 的 319 labels 中有一条相关原始输入；它的 key、scope 都为 null，reason 为 `unproven_key_formatter`：

```text
<C3></C>[Physical<I278> - <I295><C3>Target - Circle (S)</C>] <c698>Impede</C><c698>, </C><c698>Blind 30%</C><c698>, Back Attack Bonus</C>
```

实际 r18 schema 2 wire SHA 为 `67be6ff6f721f7d743d67d859d02ddb0d9fef7acf61ecb8f371db49ae066a2e5`。它已有 Impede、Back/Side 和 HP/CP 角色及条件合同，不能归为整体旧模型。具体拒绝点是单体 `Blind %d%%` 没有 typed parameter contract；同族 chance_group 有，单体没有。独立颜色包装的 FORMAT8 也不能按原先裸分隔符正确分段。无正文战斗浮窗另缺完整 SkillTextArray 标题构造入口。

04:15 UTC 的外部只读采样仍看到运行 r18 的 Physical 标题英文，范围和其它效果已双语。该采样读的是 +0x318 的已拥有显示 buffer，包含 `<R>`；没有把它当成 setter original。当前没有 59/89、HP/CP、书籍或终端节点。

04:33 UTC 继续核对 Tips 入口：`generated/r19-readonly-layout-043310.json` 有 189 个布局实例、547 个已验证文字节点、0 个读取错误，布局 ID 中没有 59/89。布局 1 与 14 的 `root/tips/title`、`root/tips/text` 实际是已双语的“解除驱动妨碍行动”和“升级回复”提示；布局 14 的 `root/sub_info/overdrive/name` 则是战斗字段 `Overdrive [%s]`，不是报错的 Tips 标题。五项 Tips 英文来自完整 wire 的入口对照，没有五个现场节点或已证明的路径，不能据此声称其实际 scope 选错。此次未退出工具或进行 owner 读取。

现有 resident 的 `snapshot(False)` 返回完整 original、displayed、key、scope，但 diagnostics=false 时不含节点指针。04:48 外部只读采集实际取得 59/89 布局，04:49 在单一所有权下完整保存 original；四个 EN 左列表均为 `note_help_title`，右侧 Stealing 为 `tips_title` 且采样前已双语。原串、size、flags 有唯一交叉匹配，但 snapshot 无指针，不升级为 resident 内部指针证明。采集没有覆盖旧 Physical 原文，用户已可离开 Tips 页。详细入口、驻留表二进制和候选修复证据见 [Tips 验证](dev5-r19-tips-owner-proposal.md)。

## 最小实现与拒绝边界

- 从当前 PAC 的 SkillEffectHelpData 参数类型 `(1,)`、SkillConnectListData kind 7 和三语完整 name/stat/format，编译全部 11 条 chance_single。没有按 Blind/Mute 等词语增加白名单，也没有把泛 numeric 当作效果身份。
- 编译 SkillTextArray 前缀、opaque 原生图标、资源范围字段及 FORMAT6 的完整构造合同。范围、缺语言或同角色不同译文拒绝；未识别的正文效果拒绝完整构造，不进入碎片回退。标题图标留在主文，不复制到副文。
- FORMAT8 只使用资源的精确分隔符和既有颜色语法；完整分区输出不同仍拒绝，未知成员、未知控制与原生 ruby 不取得完整角色。CP 三段分别携带 role IDs 和参数。
- 完整 condition-mask 单元贯穿最终 annotation，不再在 details.render 中把成员参数退回一般碎片翻译。
- 独立审 P1 已先复现：整串及去样式整串的冲突不能由标题构造语法覆盖。完整 render、translate 与 effect plan 共用冲突门禁；真实已验证 key/scope owner 可另行授权，未知/stale owner 仍拒绝。
- 独立审 P2：编译输出携带 parameter_kinds；`%d/%i` 限有符号 32 位，`%u` 限无符号 32 位。溢出和超长整数不给 effect role。没有未经证明地把概率 clamp 到 0–100；Mute 200% 与 101% 保留，condition-list 的既有 100% 上限独立维持。
- 已证明的 percent_recovery_header 保持 atomic。等价分区的细分不能拆坏该原生一次构造的语义单元；不同分区译文继续拒绝。明确带 resource authority 的 generated 冲突行可 veto，却不能自行授予未证明的角色或参数片段身份。

## 分层证据

| 已报案例 | 当前候选证据 | 实机结论 |
| --- | --- | --- |
| Physical / Impede / Blind30% / Back 战斗浮窗 | 真实 resident original，保持 null key/scope；完整生产编译→indexed wire→RuntimeText→Frida V8，5 个语义层，无英文残留 | 候选未实机，仍未解 |
| 菜单裁剪 `[Physical]` | 父提供截图像素，没有完整 setter input；标题独立 constructor fixture 可译 | 原始菜单入口未捕获，未解 |
| 同火龙爆击菜单正常、战斗浮层 EN | 父的成对像素证据；未取得该 Arts 技能两个入口的完整原串 | 不能用菜单成功证明战斗，未解 |
| CP：STR↑5回合、CP逐渐上升、解除能力降低 | 着色 FORMAT8 资源 fixture 最终 3 个独立 role；正文是官方资源，不是用户 CP 控件采样 | 未实机，未解 |
| HP Regen | 完整 Enhance/Self 标题资源 fixture 最终 3 个 role；不是裸标签全局放行 | 用户实际 HP/装载槽入口未捕获，未解 |
| Resist Burn/Confuse/Deathblow、Mute/Freeze | 两个完整资源 constructor fixture 的最终参数已译，各 1 个 role | 未实机，未解 |
| Debilitate / All / Mute200% | 既有外部 owned-buffer 形态回放；原始身份未捕获，5 个 role | 不升级为 setter original 或候选实机，未解 |
| Tips：Tactical Bonus、Stealing、Changing Difficulty、Overdrive | 实际左列表 original/key/scope 和驻留表二进制已捕获；4 个记录经受限 post-load 转换选中完整 owner，三份原生生产路径模拟通过 | 候选未实机，仍未验收 |
| Tips：Orbments | 原拼写确为复数；Help/类别与 Tips 资源译文不同。两个保存内存资源 fixture 可选择各自 owner；现场只采到独立 NoteHelpCategory 身份 | 报错列表原始承载未知，未解 |
| Quartz/Heal 列表正常、装载槽异常 | 父的不同承载证据；本次没有各自原始身份 | 逐承载未解 |
| 书籍类别、hint、正文 | 继承完整类别资源及 owner342/372 英文同文异译证据；没有安全的新 owner 传播实现 | hint 分段和真实正文 owner 未知，未解 |
| 终端 group15 五个带括号选项 | 完整原字符串在当前 wire 可译，已知静态调用经过当前 setter 5892c0 | 首个现场失败未知，未解 |

资源 fixture、保存内存回放和自建宿主不是候选游戏像素验收。没有新增逐图导航队列；用户已释放 Tips 停留要求。

## 完整生产产物

`tools/compile_r19_production.py` 将 r18 原始 catalog 的完整 resources/catalog_code 签名与当前 PAC、当前解析器核对后，只复用这个 raw 层。随后真正调用 production load_entries、load_model 和 prepare_wire；没有复制旧模型、font receipt、native-agent/token、配置或缓存规则实现。

最新模型为 `generated/r19-production/runtime-bad2b436720247031769.json`。完整 indexed wire 为同名 `.wire.bin`，178690472 bytes，SHA256 `ed829cab814b64c57de34aeea27d6192b25c039d55a0378a94a9db19e0586088`。有 7 个标题 format、2324 个效果单元、2212 个 typed 参数单元及 2 个 atomic 单元；新增精确 Tips 转换元数据。最终 code/resources 签名已重新核对相符。

`generated/r19-complete-production.json` 不 spread model、不追加 role、不注入 owner；直接读完整新 wire。`generated/r19-production-frida.json` 在自建隐藏 Python 宿主的真实 Frida V8 读取同一 wire，与 Node 的主文、副文和最终 annotation 逐项一致，并复核整串冲突与整数越界。宿主正常退出，未 attach 游戏。早期 r18+delta 回放仅作定位，不能替代这些完整产物。

实际 resident source_language=en；磁盘 control 的 game_language=zh-Hans 是另一个状态，生产回放按 resident EN 编译，没有用磁盘字段掩盖实际 wire 来源。

## 验证与剩余门槛

定向 Python、RuntimeText JS、生产 native-agent 模拟回归和 diff whitespace 均通过。正文重排回归改为验证两个独立效果语义层，并禁止正文借用任何效果文本；没有把失败断言删除。生产资源 authority 冲突拒绝仍按原断言通过。独立审核的红绿日志及完整回放产物保存在 generated。

尚未封 ZIP、部署或修改 r18 包。不能把这一检查点叫作全批修好。缓存/UI/兼容工作保持暂停；原 cache 方案补丁只在 generated 保存。

若当前游戏正常活动中恰好出现 CP/HP/Tips/书籍/终端，可以由父协调一次现有 backend 所有权串行读取完整 original；没有第二 RPC owner 或 attach fallback。若必须取得 setter caller/身份拒绝阶段，当前 resident 的 diagnostics=false 在初始化固定：具体门槛是用户正常退出游戏后，在新 resident 初始化前开启已有诊断，随后仍只用现有单 backend 取有界记录。不能热开、重装 hook 或替换现 resident。r19 代码验收也须新正常游戏进程；父在剩余入口闭合后再安排一次候选包及必要实机验收。

冷构建耗时证据继续指向原任务的 `replacement-r19-cache-layer-initial.json` 和 `replacement-r19-fact-miss-evidence.json`。本次完整冷 model 约71.95秒，其中 script_identity_history 51.29秒、facts 57 hits/2664 misses；第二次实际 model 40.35秒，facts2721 hits/0 misses，history18.47秒。完整生成连同 wire 分别87.71秒和53.48秒。raw catalog 复用不等于模型/历史映射全部复用；没有实施暂停的 cache 导入/新 fingerprint 方案。
