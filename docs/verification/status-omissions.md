# 状态与详情漏译核对

tests/check_status_omissions.py 从本机八语 PAC 读取全部 SkillItemStatusData 与
SkillEffectHelpData 字段，并以生产 load_model 与 runtime_text.js 回放。它只读游戏目录，
复用 generated/catalog.json；不启动、不附加游戏。结果写入
generated/status-family-audit.json。

运行：

    python tests/check_status_omissions.py --game-dir 'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter' --existing-catalog generated\catalog.json

审计固定源语言 zh-Hans，覆盖三组目标配置：zh-Hans/ja、zh-Hans/en、en/ja。每个结果保存
完整资源 key、record ID、原始 parameter_types、原串、预期两侧文本、生产模型输出及失败原因。

分母分为三类。原始资源字段保持格式符原样回放，不为 %d、%g 或 %s 编造参数。已证明构造器
仅使用实际 item/skill 槽位和 production grammar 生成的完整字符串。无法证明 native 参数如何
绑定到格式符的字段单列为合同缺口，并列出 effect ID、原始槽位和参数类型；它们不能算通过。

原始槽位由审计独立读取：SkillParam 从 +0x30 取五个 16-byte 槽，ItemTableData 从 +0x3c
取五个槽。后者的机器码证据是 0x23ef20 查得原始 ItemTableData row，0x23f010 复制
+0x3c..+0x7c。现场 ID 4050 与 PAC 一致，前两槽为 (1092,30,0,0) 和
(1033,10,0,0)。旧的 ItemTableData +0x6c 三槽分母会遗漏前段，不能使用。

0x34de3f 的详情分支按首项 name、后续项 stat 加 format 构造，并为每项读取独立数值。ID
1092 与 1033 的组合因此由 ID 4050 的 source slots 证明；审计只接受 production grammar
按此合同生成的构造器，不能把截图或裸标签作为组合通过。

状态面板的四个报告标签经只读节点图确认是 fdk::ui::Sprite（vtable RVA 0xb18658），不是
Text（0xb18490）。图片路径不在本轮要求；同名 HelpIconList 纯文本仍纳入全量资源配对和
纯文本 resolver 回放。该结果不把文本回放写成 Sprite 绘制验证。

此前 generated/diagnostic-134-model-ja.json 对 危机时2回合“心眼” 和道具效果加射程的实际
模型输入仍返回原串；截图中的 HP吸收 也不同于表字段 吸收HP。生产模型回放、驻留模型和
实际 Sprite 绘制必须分别报告，不可用其中任一项代替另两项。


## 2026-09-29 最终生产模型回放

最终报告为 `generated/status-family-audit.json`。它复用 `generated/catalog.json`，重建三种生产
模型并调用顶层 `runtime.render(source, "annotation")`。每条同时检查 primary、secondary 和
annotation：需要副文的 layered/ruby 计划必须包含完整 secondary；同文的 plain 计划必须保持
primary 文本。报告中的 `all_known_inputs_passed` 为 true，但 `all_parameter_contracts_proven` 为
false，二者不能混为“全覆盖”。

每种配置的基础检查分母为：249 条无格式符的完整 raw field（检查顶层解析；孤立全局查找有
歧义时，另检查 production `table_identities.models` 的真实 resource key 上下文）、4 条状态同名纯文本、4
条截图可见字符串、14 条实际 source slot 能证明取值的 typed bare 构造器、6 条带 description
anchor 的构造器、ID 4050 的真实 `ItemKindHelpData` header + native icon/count + 组合效果，及纯
数值格式探针。结果如下：

| 配置 | 总检查条数（含诊断） | 数值 probe | 未通过的全局 probe 诊断 | 基础检查失败 |
| --- | ---: | ---: | ---: | ---: |
| zh-Hans → zh-Hans / ja | 507 | 229 | 12 | 0 |
| zh-Hans → zh-Hans / en | 493 | 215 | 33 | 0 |
| zh-Hans → en / ja | 493 | 215 | 45 | 0 |

纯数值 probe 只覆盖完整 raw 模板中的 `%d`、`%u`、`%g`，以 `2` 或 `0.7` 实例化；它不证明
native argument binding。12/33/45 条诊断都没有对应的 `table_identities.models` 局部模型，因而
记录为 `formatting_probe_global_ambiguous`，保留原串、官方目标、实际全局输出和 resource key。
它们包括孤立 `2 → ２` 等真实全局 pair 冲突，不被写成局部控件漏译，也不据此修改生产词典。没有
局部身份已解析后仍错误的格式 probe。

四个用户截图可见字符串仍单列为 `reported_visible_text`：`魔法驱动时间0.7倍`、
`消耗EP0.8倍`、`危机时2回合“心眼”`、`HP吸收`；均在三种模型的顶层 annotation 通过。四个
状态 Sprite 标签的图片绘制不在本轮要求，文本审计结果不等同于 Sprite 绘制验证。

786 个实际 source slot group 的可信分类为 678 个 `contains_unrecognized_union_slots`、98 个
`known_effects_non_display_connection_kind`、10 个 `known_effects_but_full_group_not_constructed`。
最后一类的 native kind 分布为 `[12]` 4 个、`[4,13]` 3 个、`[6,7]`、`[4]`、`[11]` 各 1 个。仍有
303 个带格式符 raw field 没有 native 参数绑定、15 个 typed constructor 的 native value projection
未证明、11 个 constructor 缺 description anchor；这些均保留为 contract gap。生产 table identity
能解析的离线模型结果也不证明驻留游戏已加载该模型，更不证明 Sprite texture 路径或实机 pointer
消费已验证。
