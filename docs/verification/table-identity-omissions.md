# 表资源身份审计：地图、历史、泛称与帮助条目

`generated/diagnostic-136-resource-inventory.json` 曾把以下原始显示字段列为
`ambiguous_duplicate_identity`。本轮逐项读取八语 `table*.pac` 的行字节、字符串池和
非显示资源字段；没有用各语种本地 ordinal 猜测对应关系。

| 表／字段 | 原因 | 结果 |
| --- | --- | --- |
| `t_place.tbl/name`（4 行） | `PlaceTableData` 的 map/script/resource selector 指针此前都被地址掩码。 | 身份保留 `+8,+16,+24,+48,+64,+88,+120` 指向的 UTF-8 内容，地址仍不参与哈希。玛鲁加矿山／户外、Axis 6F／电梯已各有独立稳定键。 |
| `t_quest_fc.tbl/NoteMainHistory/body`（2 行） | 16-byte 行只有正文指针。八语都有相同 11 行和相同 16-byte layout，但尚无原生消费者按文档索引取行的证据。 | 保留歧义；不能仅由同序推断 `row:N` 是资源 ID。 |
| `t_name.tbl/name`（5 行） | 两组泛称分别共享全部非显示字段：`0xffff` 加 `chr0714/chrf000_face/chr0701` 的两行，以及 `0xffff` 加 `chr5112/...` 的三行。 | 保留歧义。文本是唯一不同字段，不能以本地行号或首个候选建立跨语身份。 |
| `t_help.tbl/HelpIconList`（ja/zh-Hans 等各 94 个字段） | 重复组只有相同标量（例如 `0x1003f`）与文字指针；`+48` 是空字符串池边界。西语／法语等的换行又会改变记录切分。 | 保留歧义。既没有跨语稳定主键，也不能用相同 ordinal 假设同一帮助条目。 |

验证：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_tables
```

单测共 19 项通过。另以 `build_table_entries` 重建八语索引，再调用 `audit_tables` 回放
原始字段；当前安装目录构建 18,350 项、0 个解析诊断。以该新构建作为
索引重放全部八语原始字段时，`t_place` 的遗漏为 0。`t_name` 的 40 个字段、`t_help` 的
826 个歧义字段及 272 个不具完整语言 pair 的字段、`t_quest_fc` 的 16 个字段仍明确保留，
不计为已翻译。
