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

### 多槽历史姓名的原生时序（回归待补）

对 `sora_2nd.exe` 的只读反汇编显示，MessageLog 在 `0x35f930` 至
`0x35f9b4` 循环收集追加槽位；`log_present_single` 的钩点在
`0x35f98e`，随后才从 `0x35f9ba` 开始读取姓名，并在 `0x35fd6c` 调用
`SetText`（返回点 `0x35fd71`）。因此姓名 setter 运行时，当前
`logPresentFrames` 已拥有整条记录的所有 `parts`。

原实现只从 `present.slot` 重新读取一个 body 片段来为可见姓名恢复身份。
多槽对话的记录身份却以完整拼接正文为条件；单片段不能等于原始
`assembled_dialogue`，所以 `history_speaker_setters` 不会命中。这是可见姓名
路径的遗漏，量测路径已使用整行 `logRows`。生产修复应复用完整
`present.parts`，先验证共同 speaker 和完整正文，再将该 identity 交给姓名标签；
不得以单槽或相同名称放宽匹配。需要新增一个两个槽、完整 marker、同一 generic
setter 的可见姓名回归，并同时断言量测和可见路径选择同一官方名称。

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
