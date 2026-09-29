# 通用说话人名遗漏：女子的声音

## 现场证据

`generated/diagnostic-134-history-live.json` 的历史槽位 1460–1462 都保留了
`女子的声音` 和独立 marker：31577、34258、31579。正文分别是：

| marker | 原文 | 英文官方文本 | 日文官方文本 |
| --- | --- | --- | --- |
| 31577 | `……让各位久等了。` | `Your attention, please.` | `……お待たせしました。` |
| 34258 | `本船即将抵达\n王都格兰赛尔。` | `We will shortly be arriving in Grancel.` | `まもなく本船は\n王都グランセルに到着いたします。` |
| 31579 | `降落时多少会有些颠簸，\n请各位尽快回到座位上。` | `There may be some bumps as we come in to land,\nso please return to your seat without delay.` | `着陸の際、多少揺れますので\nお早目に座席にお戻りください。` |

这些正文对应的原始 `assembled_dialogue` 调用包含：
`script/scena/mp8010_01.dat/EV_03_09_00/called/12`、`14`、`16`。同一函数中，
`called/11` 是 `chr_set_display_name(21000, "女子的声音")`；`called/12`、`14`、
`16` 分别将三个 marker 作为 builder op 11 的后继操作数。调用之间只有
`wait_prompt`。setter 的三语资源为 `女子的声音` / `Woman's Voice` / `女性の声`。

## 根因与修复合同

`t_name.tbl` 没有 actor ID `21000` 的名称，因此旧的历史名称索引无法处理这类
直接 setter 的通用显示名；这与正文的 marker 身份恢复是两条独立路径。

`speaker_context.py` 现在系统扫描目录中的 `display_role=speaker` 且键精确为
`.../called/<id>/arg/1` 的物理 setter。每个来源标签仅在所有不同物理 setter
的主、副语言完整配对完全一致时进入历史名称索引。相同 setter 的不完整 alignment
片段由完整行支配；不同 setter 的不同译文或缺项仍写成歧义，运行时不会猜测。

完整目录证明 `女子的声音` 有两套官方日文配对：`Woman's Voice / 女性の声` 与
`Woman's Voice / 女の声`。因此这个安全的全局索引正确把它记为歧义，不能修复本次
带 marker 的现场记录。

`script_identities.history_speaker_setters` 现在按稳定 dialogue `recordKey` 输出
`[sourceLocale, expectedSpeaker, primaryLabel, secondaryLabel]`。编译器只接受完整
官方 setter 配对、无 branch 的函数、同 actor 的后续 marker dialogue，以及其间唯一的
无参 `wait_prompt`；改名、未知 callee、动态 setter 或分支都会清除／拒绝该状态。目录中
call 12、14、16 都有完整的 setter 行；运行时必须先由 marker identity 选中一个实际
`recordKey`，再消费本字段，不能以名称白名单或旧 diagnostic-133 已否定的“跳过中间 VM
调用的相邻扫描”替代。

本次真实旧历史回放区分两种结果：marker `34258` 唯一恢复到其实际调用 ID，并显示
`Woman's Voice / 女性の声`；`31577` 和 `31579` 的 marker 在原生记录中重复，
`historyMarkerIdentity` 明确返回空值。这两行没有伪造调用 ID，而是在缺少真实身份的
旧历史路径按用户授权的稳定 fallback 选择完整官方候选 `Woman's Voice / 女の声`。
fallback 只索引完整配对，优先同说话人，并以规范化配对稳定排序；它不改精确 map 的
`-1` 歧义语义，也不向普通对话身份路径扩散。

### 多槽历史姓名的原生时序（已有回归）

对 `sora_2nd.exe` 的只读反汇编显示，MessageLog 在 `0x35f930` 至
`0x35f9b4` 循环收集追加槽位；`log_present_single` 的钩点在
`0x35f98e`，随后才从 `0x35f9ba` 开始读取姓名，并在 `0x35fd6c` 调用
`SetText`（返回点 `0x35fd71`）。因此姓名 setter 运行时，当前
`logPresentFrames` 已拥有整条记录的所有 `parts`。

原实现只从 `present.slot` 重新读取一个 body 片段来为可见姓名恢复身份。
多槽对话的记录身份却以完整拼接正文为条件；单片段不能等于原始
`assembled_dialogue`，所以 `history_speaker_setters` 不会命中。这是可见姓名
路径的遗漏，量测路径已使用整行 `logRows`。生产修复复用完整
`present.parts`，先验证共同 speaker 和完整正文，再将该 identity 交给姓名标签；
不得以单槽或相同名称放宽匹配。已有两个槽、完整 marker、同一 generic
setter 的可见姓名回归，同时断言量测和可见路径选择同一官方名称。

追加槽位也不能从 hook 时的 `RBX` 推断：`0x35f948` 以实际槽位 `RAX` 乘
`0x18c`，再在 `0x35f956` 形成 `RDX = owner + 0x160550 + slot * 0x18c`；
`log_row_append` 则从 `0x3623f4` 的 `mov eax, ebx`、`0x3623f6` 的乘法、
`0x3623fd` 的基址相加，到 `0x362404` 的 `add rdx, rcx` 形成相同 body 指针，
然后才到 `0x36240b`。因此所有 append 采集必须由输入 body 指针相对
`owner + 0x160550` 的对齐偏移恢复槽位，并保留已有的范围、owner、epoch 和 stamp
验证。代码回归以 1599→0 的双槽行、故意错误 marker 和用于误导旧实现的相对 `RBX`
覆盖可见与量测姓名路径；原生 clone 检查也验证两个 append 分支的 `RDX` body 指令。

## 验证

`tests/test_speaker_context.py` 覆盖完整通用 setter、同一物理 setter 的不完整
alignment、跨 setter 冲突、非 `arg/1` 条目不会进入索引，以及旧历史 fallback 的稳定性
与不完整配对拒绝。完整目录回放确认 `女子的声音` 为歧义，并确认三个 marker recordKey
各自有完整官方名称对；实际回放只将 `34258` 标为精确 ID 恢复，另外两项明确标为 fallback。
`tests/test_native_agent.js` 的双槽姓名回归确认可见和量测都使用同一精确 setter，且错误
marker 不会继承身份；实机加载验证仍待进行。

## 0.3.19 全部名称及“声音”族反查

上一版的 `actor_name_set` 钩子保留真实脚本 setter 身份：原生函数将脚本文字复制到
`actor+0x2c0` 后，UI 通过 `actor_name_get` 取得该缓冲，再交给 `SetText`。缺少复制来源时，
有多种官方配对的普通名称无法准确选择；旧日志另有经授权的完整官方候选索引，所以会出现
普通对话漏译、日志有副文的差异。现有 Node 回归覆盖同一源文不同调用、角色缓冲复用、
失效旧指针、空指针只改标志及模式切换。不是按某个中文名称特判。

本轮反向检查还发现资源层缺口：完整函数分组会因为后面的无关调用不同，拒绝前面
可以严格对应的 `chr_set_display_name`。例如 `mp3010_01.dat/QS802_08_00` 的第 125
调用，简中 `男子的声音` 与日文 `男性の声` 的 actor 都是 133；两语首个不同调用却在
349，是不同语言的物品获得模板。老婆婆、青年、怀斯曼的声音也有同类缺项。

修复将既有物理调用对齐逻辑共用到名称记录。完整一致前缀、已验证唯一非显示插入段
均保留各语言真实 called ID；不跨越无法证明的差异猜测，也不放宽 actor、函数签名或
参数结构。完整名称记录支配同一物理调用的不完整 alignment 片段。此逻辑只在建库运行。

`tests/check_speaker_setters.py` 从完整目录枚举所有静态名称 setter，并从安装包读取实际
脚本指针、文件内容与偏移，通过生产 `pointerSelect`、`translate`、`render` 检查最终副文。
“声音”只是报告子集，不参与生产准入。另核对当前 EXE 的 18 条机器指令，确认 getter、
复制及四处 UI 的 getter→SetText 参数链。该检查只读磁盘，不附加游戏。

修复前简中/日文只有 216 个声音 setter 可形成完整配对；新增检查把另外 4 个缺日文的
调用明确列出，修复后这 4 个也加入完整配对。所有声音类别共 22 种，包括女子、男子、
女孩、少女、少年、男孩、老人、老妇人、老婆婆等。其他未能证明配对的名称逐项保存在
报告的 `unpaired_resource_setters`，不伪称全部资源均已配齐。

最终完整模型回放：简中/日文 617 个、简中/英文 622 个、英文/日文 617 个静态名称
setter 全部通过；每组均包含上述 220 个声音 setter。剩余未完整配对的物理名称调用
分别为 9、4、9 个，涉及其他名称，继续单列；未配对不等同于已证明实机漏译。

重跑：先执行 `check_status_omissions.py` 生成最新完整模型，再执行
`python tests/check_speaker_setters.py --game-dir <game> --status-audit <report> --output <output>`。
模型回放、原生参数合同、复制生命周期回归和实际游戏画面属于不同证据；本轮没有在玩家
运行中的游戏替换钩子，新增资源配对及实际画面仍需新版正常启动后加载。
