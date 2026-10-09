# Tips 实际入口：已实现最小候选，未实机验收

在已保留的 `46d210d` 上合并 Tips 表加载转换修复。仅扩展现有 TableIdentities 的精确记录身份与原生能力合同；没有新增 hook、scope 或词语白名单，没有部署或修改正在运行的 r18。

## 实际失败证据

`generated/r19-tips-input-red.json` 使用 04:49 的既有 resident 完整 original、真实 key/scope 和原 r18 wire `67be6ff6…066a2e5`，没有注入 owner。四个实际左列表输入均保持英文。`note_help_title` 精确 pair 缺失；其 `ambiguous_display` 标志没有置位。Help 与 Tips 资源目标不同，已在完整 wire 中逐个保存，不按词语放行。

04:48 的外部只读节点记录与 snapshot 的原串、size、flags 交叉核对，各左列表项有唯一属性匹配。snapshot 不含指针，不能升级成 resident 内部指针身份。右侧 `Stealing AT Bonuses` 的实际 scope 为 `tips_title`，采样前的 owned buffer 已是双语。

## 新发现：现有表身份入口已有可证拒绝

通过既有原生合同验证的 `shop_text_owner_global` 数据管理器，只读已加载 Help/Tips 表，不需要页面停留、RPC 或 attach。`generated/r19-tips-existing-table-readonly.json` 保存实际 `Stealing AT Bonuses` 两个资源 owner 的验证结果：Help 表 header、完整 pool hash、field pointer、去指针 record 均匹配；Tips 表 header、完整 pool hash、field pointer 均匹配，只有 record 的 +2 两字节不同。

Tips 该行原始 record +2 为 122，驻留值为 7522。全 266 条记录对照只在 +2 两字节发生非指针变化。`generated/r19-tips-all-record-diff.json` 保存逐行关系；header 与完整不可变 pool 保持一致。

## 完整原生转换证明与产品边界

新 official 的加载函数为 `259d20..259eca`，全长 426 字节。旧 official 与认可 voice 样本的相应完整函数具有同一规范化合同。实际代码是 `mov eax,0x1ce8; add ax,word [rbx+2]; mov word [rbx+2],ax; cmp ax,bp`，其中 bp 为 `0x1e77`，无符号 JBE 后超界路径写回 bp。因此语义精确为 `min((serialized_u16 + 7400) & 0xffff, 7799)`；不是以 ID 推算，也不忽略该字段。399→7799，400→7799 并报告越界，65535→7399 体现 AX 回绕。

`tips_contract_data.py` 校验完整函数及 103 字节 descriptor compare，约束 CALL 目标、RTTI vtable、TipsTableData 字符串、诊断数据与 RIP 依赖。该点仅提供已验证能力，未安装任何新拦截器。当前 native report 无该能力时不接受转换记录。

编译器只给 TipsTableData、56 字节 stride、title/text 的 +40/+48 字段以及原指针布局 `(8,24,40,48)` 标记该转换。运行时只接受原始整条记录或该精确转换后的整条记录。ID、+4、+16/+20、+32/+36、资源 key、pool/hash、字段指针和共享指针异译冲突的原有拒绝继续维持。原 loader 将 +24 selector 转成标志，沿用现有指针掩码；完整 pool 仍约束原 selector 和条件资源，没有扩大掩码。

## 分层验证与交付

| 证据 | 结果 | 等级 |
| --- | --- | --- |
| 原 r18 完整 wire + 04:49 实际 key/scope/original | 四个左标题保持 EN，未注入 owner | 真实输入离线红例 |
| 保存的实际 Help/Tips 驻留二进制 + 新完整 wire | 4 个 Tips 由 record_mismatch 转为完整 owner；4 个 Help 保持原 owner，不猜 key | 实际内存离线指针回放 |
| 三份 EXE 原始完整加载与 ListItem 构造函数在自建隐藏宿主执行 | 798 条转换记录、24 个生产参数入口、9 个算术边界通过；关闭能力时 Tips 仍拒绝 | 隔离原生参数路径模拟 |
| 三份 EXE 危险变体 | 60 个字段、宽度、cap、CALL、数据依赖变体全部拒绝 | 原生合同负例 |
| 新 wire 的 Physical、HP/CP、条件与 atomic 回归 | Node 与 Frida V8 的 7 个最终 render 一致，整串冲突和整数越界仍拒绝 | 实际输入/资源 fixture 离线 |

保存证据分别为 `r19-tips-resident-replay.json`、`r19-tips-native-path.json`、`r19-tips-contract-mutations.json` 和 `r19-production-frida.json`。当前完整 wire SHA256 为 `ed829cab814b64c57de34aeea27d6192b25c039d55a0378a94a9db19e0586088`，178690472 字节；最终编译 code/resources 签名与当前代码及 PAC 相符。

四个实际左标题为 Tactical Bonus、Stealing AT Bonuses、Changing Battle Difficulty、Overdrive。右侧 Stealing 的采样前显示已双语。

Orbments 的原拼写确为复数，不是漏了另一种拼写。单数 Orbment 是独立已有完整 pair，不能拿它替代复数入口。复数的 Help/NoteHelpCategory 目标是 `オーブメント／导力器`，Tips 目标是 `【導力器】／【导力器】`；完整 global 与 note_help_title 精确 pair 因资源族异译而缺失，`ambiguous_display` 未置位。采到的复数仅有独立 NoteHelpCategory/title 身份，snapshot 在 disable 后显示原文，不能据此判断采样前该类别控件失败。新转换已覆盖实际驻留 Tips 表中 Orbments 的资源记录；额外 2 个 Help/Tips 保存内存 fixture 可选择各自译文，但没有该报错 UI 列表的真实 setter 参数和节点关联。因此它保留“资源/保存内存 fixture 通过，实际失败承载与候选像素未验证”，不并入四项实际输入。

候选尚未实机验收或打包部署。HP/CP 原入口、菜单/Arts 差异、装载槽、书籍 owner342/372、终端首次失败与崩溃仍未解。用户可以离开 Tips 页；已保存证据足够继续独立审核，下一步实机必须在用户正常退出后的新进程中进行，不热换当前 resident。
