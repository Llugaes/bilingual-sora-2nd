# 剩余表文本身份：只读审计

本报告只读取 `D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter` 的八语
`table*.pac`、当前 catalog 和磁盘 `sora_2nd.exe`；没有启动或附加游戏，也没有修改
提取器、运行时或原始资源。它复核了 `generated/diagnostic-136-resource-inventory.json`
中的三类未对齐字段，目标是找真实稳定键，而不是按译文或本地行号配对。

## `t_name.tbl`：40 个实际名称字段继续拒绝

`NameTableData` 的 `+8` 是显示名，五个冲突行在八语都有相同的 104-byte 行布局和
1,583 行总数；它们是两组完全相同的非显示数据：

| 行号 | `+0` actor | 资源字段 | 各组成员 |
| ---: | ---: | --- | --- |
| 374、789 | `0xffff` | `chr0714`, `chrf000_face`, `chr0701`, `F`, `npc` | 不良少年（青年男性01）※レイブン／ベルフ |
| 427、428、429 | `0xffff` | `chr5112`, `chr5112_face`, `chr5112`, `F`, `npc` | NPCフィー0／フィー／NPCフィー2 |

各组只有 `+8` 显示名不同。`0xffff` 是无 actor 的哨兵而非可细分的角色 ID：原始对白
目录确有 656 个 `speaker_ids` 为该值的 dialogue 调用，但其中没有一条把该值关联到上述
某个 `t_name` 行。历史名称读取也只接受非 `0xffff` 的显式 actor ID。

磁盘 EXE 的类注册数据包含 `NameTableData`，但未找到以这五行的本地序号为参数的消费
合同；表打包时八语行号相同不能证明运行时使用该序号。这里的名称是实际显示字段，不能
归为内部数据；缺少的只是能区分同模型多显示名的稳定主键。继续保持 40 个
`ambiguous_duplicate_identity`，不建立全局名称词典。

## `t_help.tbl`：文本字段实际存在，元数据不能对齐

`HelpIconList` 的 `+8` title、`+24` description、`+40` detail 都是非空 UTF-8 显示文本；
`+48` 在重复组中是空字符串。`+0` 的标量和其余非显示布局值会重复，例如 ja/zh-Hans
的第 12--23 行均为同一 `0x0001003f` 形状，却分别显示 HP、EP、CP、STR 等不同标题。
这证明该标量不是每条帮助文本的 ID。

| 语种 | `HelpIconList` 行数 | 冲突组／行 | 冲突中的非空显示字段 |
| --- | ---: | ---: | ---: |
| ja、zh-Hans、zh-Hant、ko | 131 | 4／34 | 94 |
| en | 131 | 5／36 | 96 |
| fr | 143 | 8／55 | 108 |
| de | 166 | 11／82 | 127 |
| es | 157 | 11／59 | 119 |

西语的行数和拆分都不同，所以同 ordinal 既不是跨语主键也不是安全候选。诊断中的另外
272 个 `table_field_not_in_catalog` 是 en 82、fr 59、de 61、es 70 个实际 title/description
等文本，它们缺完整语言 pair，并非空字段或内部指针。

已有 `SkillItemStatusData` 到终止加号 title 的窄映射仍是唯一已证明的例外：它由状态 ID
和格式前缀约束，只覆盖同一状态的字形变体，不能推广到这些帮助行。没有发现
`HelpIconList` 自身的跨语 ID 或原生 consumer 给出的行键，故 826 个冲突字段和 272 个
不完整 pair 保留拒绝。

## `t_quest_fc.tbl`：最后两条无独立资源键

这个文件的 `NoteMainHistory` 记录是 16 bytes：`+0` 为正文指针，`+8` 为未被文本 schema
解释的原始 64-bit 值。后者在八语完全一致，且落在同文件 `QuestText` section 的内部位置；
它已作为未掩码原始 payload 参与现有 identity，因此前九条历史记录有不同 identity。

最后两行的 `+8` 都是 `0x376b`，八语均相同，分别为“正游击士推荐状授予（格兰赛尔）”
与“取得正游击士资格”。这正是剩余的 16 个 `ambiguous_duplicate_identity` 字段。
其余可见字段、行尺寸和八语顺序也相同，不能消除这个冲突。`0x376b` 指向 `QuestText`
记录的内部字节而非经验证的文本 ID；例如前几行的目标在该 section 内的余数分别为
8、18、26、25，不能从地址形状推导语义。

EXE 的表类注册仅能证明 `NoteMainHistory` 被加载，尚无机器码或运行态证据表明消费者用
第 9／10 ordinal 作为文档主键。因而不能以“八语顺序目前相同”添加 `row:N`。若以后取得
consumer 中由游戏状态导出的索引及 `base + index * 16` 读取链，且证实索引在八语不变，才
可将该索引作为独立 ID；在此之前两条仍需拒绝。

## 结论

三类字段均可能显示给玩家，不能按内部垃圾文本排除。当前没有新增安全对齐方案：
`t_name` 缺非哨兵 actor ID，`t_help` 缺跨语记录键且行数不同，`t_quest_fc` 的最后两行共享
全部可验证的原始 payload。保留拒绝项比猜测译文对应更符合资源身份合同。
