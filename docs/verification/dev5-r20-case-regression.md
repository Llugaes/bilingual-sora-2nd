# dev5-r20：四类修正与验收边界

本候选只用于本地 DEV 实机测试，不是正式发布。r19 的 Tips 修复 `d235d321` 保留，用户已确认 Tips 和大部分此前问题改善；未整版回退。当前四类在 r19 的实机验收失败，不能用离线数量改写这个结论。

| 当前问题 | 代码与证据 | r20 验证等级 |
|---|---|---|
| 菜单技能/魔法描述 | 撤掉 skillHeader 后的整串提前返回。完整 body 的独立资源身份继续走原回退。真实 Arts original 未传入正确 owner，在旧/新 wire 与 renderer 交叉中确认 r19 组合失败、r20 恢复 | 实际原文回放；r20 画面待验 |
| 战斗技能/魔法描述 | 同一正式 resolver，保留新 header/unit 能力。严格分段失败只拒绝分段，未知词保留原文；wholeConflict 与硬分区拒绝继续有效。typed 整数越界拒绝贯穿 fallback | 共享生产路径与整族资源回放；菜单/战斗入口及画面对照待验 |
| 安装中的结晶回路槽位名称 | layout 36 实采七个 `root/orbment_root/orbment/origin/name/name_[0-6]/text`。实际 EXE `0x1a90e0..0x1a9569` 循环七槽；`0x1a92e2` 从 ItemTable 取得记录，`+0xe0` 名称在 `0x1a92fa` 送现有 setter。只给这个完整祖先路径既有 item_name scope | 原生静态 producer、实际节点路径、正式 ownership 函数模拟；Heal/Mute/Confuse/Seal 的该槽原文与 r20 画面待验 |
| 描述嵌入 Seal 等状态名称 | type17 原生 `0x34febb..0x34ff65` 以 `0x256100` 查询 ConditionHelpData，并将 `+0x10` condition 字段与数字传给完整 name formatter。编译时按这张原枚举表绑定整句，不增加全局状态词 | 八语原始字段独立 oracle、64 语言对及生产 wire；r20 画面待验 |

`Heal`、`Seal`、`Mute`、`Confuse` 裸词仍不获得全局译名。列表保持原 item_name 入口；槽位从正式节点识别函数推导 scope，测试没有先将正确 scope 注入未知入口。错误 layout、祖先、节点名和槽号均不获得此归属。状态参数的同名词只能进入已绑定的完整 formatter；未知参数 `UnprovenStatus` 仍保留。

本次先恢复“完整已知描述可以独立翻译”的旧可靠行为。未知效果仍不产生 unit/semantic ID；它保留原文，同时已证资源字段可翻译。旧测试中“出现未知成员就让整个已知句子全 EN”的断言已改成检查未知成员/控制码/原 ruby 保留，另外继续检查完整冲突与越界拒绝。不得把拒绝注解分段误称为整句身份已证。

封包独审在 `e4d4011` 发现：完整 type17 `Damage dealt to enemies with Seal +2147483648%` 的 unit 已拒绝，但普通 numeric fallback 仍翻译。修正只让无完整 pair 的 exact typed 数字拒绝先于普通 formatter 回退；合法 50%、signed32 两端及独立完整描述继续通过。`r20-type17-final-rejection.json` 使用 fresh resolver 直接调用最终 translate/render，覆盖越界正负值、长整数、颜色边缘与不同调用次序；没有先调用 unit 来预置拒绝结果。本反例是资源边界，未声称是实机原文。

验证收据（repo 的 generated，均不附加游戏）：

- `r20-complete-production.json`：真实 Arts 交叉、895 条 resident 原文、旧成功回归、完整描述族、槽位 ancestry 模拟及最终输出。
- `r20-condition-parameter-matrix.json`：原始 ConditionHelpData 41 行，其中 12 个完整名称译句；type17 原生记录 1089；64 语言对，每种引擎合计 2304 次检查。
- `r20-production-frida.json`：自建隐藏宿主使用完整生产 indexed wire、正式 V8 renderer，既有 Physical/HP/CP/抗性回归与新增三例。
- `r20-python-validation.json` 与 Node 合约测试：描述、typed effects、owner、Tips 的相关回归。
- `r20-slot-native-xrefs.json`、`r20-native-0x1a90e0.txt`、`r20-help-parameter-disassembly.txt`：当前已验证 EXE 静态证据。

原生回放辅助器曾在自建宿主报 access violation：小于一页的代码分配与后续数据共用 heap page。辅助器现在给重定位代码独立整页并检查保护成功；r19 原 wire 与 r20 新 wire 的三份 EXE、798 条记录、24 个完整 producer case、9 个算术边界均重新通过。该更改只在测试辅助器，不改 Tips 实现，不是实机崩溃结论。

兼容 raw catalog 和已校验单语 facts 可以复用；新模型按当前 compiler/resource 身份重新生成，没有强灌旧模型。字体 receipts、agent、token 和用户配置不进入构建缓存预种。

用户已授权通过唯一操作者正常重启 DEV 到 r20。仍须在独立审核放行后，确认《空轨2》已退出，正常关闭 r19，再开启独立 r20 ROOT；不能强杀游戏或热替换驻留模块，不操作用户其它游戏。

测试时只需围绕这四类复看：一条含完整第二行的菜单描述、同类战斗描述、已安装槽位与旁边列表的同名结晶回路、包含 Seal 的状态参数。r20 的所有实机项目前均未验收。更早书籍、终端、首次注入等历史证据保留在 r19 交接与旧报告，未因本候选被宣称完成。
