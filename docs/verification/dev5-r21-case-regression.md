# r21 局部漏译修复与证据边界

基线为已部署 r20-rev2 `14f281981f2b12e328077736998dfb832ae1a5ea`。r20 的 Tips 与回路槽位已获用户现场确认，本次不改它们的原生入口。游戏 PID42928 已由用户正常退出，未发生工具请求退出或重启；旧 DEV 根目录保留。

## 固定修改

1. 已有 FORMAT8 完整分隔构造器在有已证明详情正文或完整类别标题时，可保留未知完整成员。已证明的效果继续使用各自角色、参数及独立副文。未知成员不会进入全局名称词典。实际同角色冲突、完整原串歧义、整数越界及未知控制继续拒绝；这些硬拒绝传到普通 formatter 回退，防止裸类别后重新翻译非法参数。
2. 从 SkillTextArrayData 各类别完整 format、唯一公共分隔尾部和 FORMAT6 编译完整的紧凑类别标签。只准入完整标签及其正常边界，未给 Physical、HP、状态词添加全局别名。裸标签没有另一个完整字面资源时，不再被无参数域证明的通用方括号模板吞掉。
3. 完整 NPC 设施名只来自原 SCP `chr_set_shop_function`、四个参数的实际类型及 arg2 与当前目录的逐语言完整相等。角色内相同来源出现不同目标或缺语言时不准入。只有精确 `<c990>完整名称</c>` 输出能使用该合同；不注入 map_spot，不借颜色或名称前缀选择资源。未装新的原生钩子。

## 逐项结果

| 用户问题 | 已取得的输入与转绿结果 | 尚未闭环 |
| --- | --- | --- |
| CP 三效果整行副文 | 独立审查者提供的 `STR<I270> (5 turns), CP Regen, Cure Stat Debuff` 原颜色结构，带未知邻居及裸 `[Enhance]` 的两项受控资源夹具，最终 render 均有三个效果语义层。已知全局船名作为未知效果邻居仍原样保留。 | 用户截图对应完整 setter 原串未取得；r21 画面未验收。 |
| HP Regen 原文残留 | `<C3></C>[Enhance] <c698>HP Regen</C>` 受控夹具的最终 render 已译 HP 角色，具有独立效果层。 | 完整现场原串与 r21 画面未验收。 |
| `[Physical]` 原文 | 父线程截图转录 `[Physical]` 通过完整类别合同，独立 render 产生类别副文。`[PhysicalXYZ] HP Regen` 不取得类别或效果角色。 | setter 原串未采集；紧凑类别的原生生成分支尚未独立捕获，画面待验收。 |
| Factory 漏译 | 09:34:52 现有 resident 单所有者串行快照中，实际 `<c990>Arseille - Factory</c>` 无 key、scope、table identity。r20 完整 wire 回放为双语船名加 EN Factory；当前编译 wire 回放为完整 `アルセイユ号・工房` / `埃尔赛尤号·工房`，没有人为授予身份。 | 证明完整构造输出及资源域；没有声称取得现场指针或 caller 资源身份。r21 画面待验收。 |
| 状态描述漏词 | r20 的纯 EN type17 合同保留。本轮独立原 PAC oracle 核对五个家族的最终副文，括号概率、尾空格、颜色包装及完整抗性列表均通过。受控混合串 `「Seal」状態の敵に与えるダメージ+50％` 仍拒绝；截图没有 Seal，不将它当作用户失败。 | 有限离线审计已完成，用户实际失败原串／producer 未取得；现场问题未解决。 |

Factory 的来源资源为 `script/scena/mp8300_01.dat/TK_npc_setting_PAYTON/called/0/arg/2`。英、日、简中原 SCP 皆为 `chr_set_shop_function`；arg1 为 `map.SHOP_PAYTON`，arg2 为各自完整设施名。NPC/shop 中文使用 U+00B7，而 map/place 使用 U+30FB，真实同文差异造成全局完整配对缺失。固定构造器只绑定 NPC 配置角色，不消除地图域歧义。

当前 EXE SHA256 为 `cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`。原生函数 `0x54c2f0..0x54dafa` 在设施配置分支读取 `[rsi+0x258]`，随后复制完整字符串，加入 RVA `0xb16d9c` 的 `<c990>` 和闭标记，于 `0x54d101` 调用当前 SetText `0x5892c0`。包装常量本身不作为资源身份证明；准入还要求上面的完整 SCP 调用关系。

## 检查与交付门槛

独审对 `4d848aaa` 找到 P2：`[Support] HP Regen, <X999>Arseille</X>` 的 `unsupported_effect_controls` 未进入旧硬拒绝集合，普通 formatter 重译了拒绝串。修订为完整拒绝原因策略：已记录的失败默认硬拒绝，只有缺原生 LINK 合同、未关联角色及严格路径的部分成员三种情况允许独立资源回退。Python/JS 策略一致，测试枚举所有发出原因，未知新增原因也默认拒绝。未知控制、原生 ruby、空成员、成员上限及分隔控制预算从 fresh final render 起步，在三模式、两种入口顺序均保留完整原串；纯文本未知邻居继续独立分段。此修订后的包放在独立 r21-rev2 根目录，初包未获部署放行。

`tests/check_r21_status_oracle.py` 直接读 EN/JA/SC 原 PAC 的三个表，按物理字段而非 compiler 配对生成 oracle：41 行 ConditionHelpData 中 12 个非空条件枚举、11 个含概率的 format；SkillEffectHelpData 全部状态概率与 type17 格式；51 个非空 ConditionInfo 名称与 effect98 抗性，以及此前 Mute/Freeze、Burn/Confuse/Deathblow 两个完整列表。共196个来源／原资源颜色包装实例，目标来自同资源的原日文／简中字段，已核最终 annotation 的副文。没有扩大到八语64组合，没有通过手工 key/scope 修饰输入。相关记录为 `generated/r21-status-raw-inventory.json`、`r21-status-oracle-inputs.json`、`r21-status-oracle-final.json`；这些是资源 oracle，不是现场原串。

若现场仍漏状态词，下一次只需要停在**仍显示英文状态词的那一件装备／回路的完整说明页**，保留当时语言设置，不要求遍历其它页面。现有单 owner 的完整只读 snapshot 可取得 original、displayed、text_key及拒绝原因、scope、log_identity/kind、presentation/surface、layers、size/flags，并核当前 resident/model/source epoch。diagnostics=false 时该工具不能提供 native pointer、祖先路径或 producer trace，不能承诺这些字段；先用一次完整原串判断是否为混合 formatter、控制分段或入口丢失。当前不启动游戏，不热开诊断、不另 attach。

`tests/check_r21_reported_render.js` 使用实际 schema2 完整 wire，逐项断言效果层、未知成员、完整设施名及相邻反例，最后检查完整歧义和紧凑标题后的 typed 越界。`test_r21_reported_boundaries.py` 检查 Python/JS 最终模式一致、域隔离和硬拒绝；已有 authority 回归继续检查真实 owner 优先与完整目标重建。

证据位于 `generated/r21-existing-owner-snapshot-20261006T093452637602Z.json`、`r21-first-actual-replay.json`、`r21-facility-scp-upstream.json`、`r21-npc-facility-function.txt`、`r21-reported-final-render.json` 和 `r21-complete-production.json`。快照 SHA256 为 `6d08eb3af19d0ad444bcd32f94ab076eda0597bb4163cd7b2a28f9cb1987af67`。

当前源码、实际原串/夹具 render 及完整 wire 的隐藏 Frida V8 检查通过，包括紧凑标题后及单句的 typed 越界拒绝。候选包完成情况由包旁 `candidate-package.json` 确认，包内再运行同一最终 render 检查；部署须待父线程审查放行。尚无 r21 画面验收，公开发布未获授权。单份进度继续写 `generated/r19-execution-handoff.json`。

rev2 独审又取得已保存的真实 Arts 完整 original：`<C3></C>[Arts<I277> - <I297><C3>Fan (M)</C>] <c698>Petrify/Confuse 20%</C><c698>, </C><c698>Delay <c698>(M)</C></C>`。r20 三模式的官方 Delay stat 原来已译；rev2 将包含内层颜色的完整成员当作 opaque，提前成功的效果计划压过旧合法文字段通路，新增 EN 残留。修订只在已证明的详情边界内、完整成员合同未命中且控制合法时，保留颜色／字号独立文字段中原本已准入的效果角色；未知段和 `(M)` 原样，角色冲突及 typed 越界仍硬拒绝。不移除内部控制、不向全局加入 Delay、不为未知参数猜构造器，已知完整 compound 继续优先，CP 三效果保持独立层。`tests/fixtures/r21-r20-captured-baseline.json` 永久保存 Arts、Physical 和此前观察到的 Debilitate 三个真实／已有 buffer 输入及 r20 冻结目标，最终 render 三模式检查不新增 EN；包内 V8 同样从 fresh final entry 检查。rev2 未获部署放行，后续候选使用独立 rev3 根目录；此修订不关闭状态实采缺口。
