# dev5-r12 本地交接：综合目标仍未实机闭环

`1.0.0-dev5-r12`已完成本轮本地回归、最终包生产回放及逐文件校验。它是下一安全时点的复核/取证候选，**不是12类实际显示入口全部修好、不是用户验收通过、不是正式发布**。当前受保护DEV3/游戏现场未操控，没有第二UI/backend，没有修改游戏、存档或字体ACL。执行者未目视Library截图。

## 身份与位置

- 仓库：`<CHECKOUT>`；分支`main`；HEAD `d62231fec5e11eeed79dfa201c8fe617c82d3587`。未提交修改全部保留；交付时77项status记录（51 tracked、26 untracked），之后仅写本交接及验证文档链接，不改程序。完整清单和每个程序文件SHA见[源码收据](../../generated/dev5-system-audit-20261005/candidate-dev5-r12.json)、[校验收据](../../generated/dev5-system-audit-20261005/final-dev5-r12/delivery-integrity.json)及[最后复核](../../generated/dev5-system-audit-20261005/final-source-and-docs-check.json)。
- 应用明显标识与入口：`dist/comprehensive-1.0.0-dev5-r12/DEV/Start-1.0.0-dev5-r12.cmd`。稳定版本/包协议仍`0.4.2`，避免把候选变成稳定发布；tag/远端未改。
- 便携包：`dist/comprehensive-1.0.0-dev5-r12/bilingual-sora-2nd-1.0.0-dev5-r12-candidate-windows-x64.zip`，112,528,906 bytes，669成员。
- 便携包SHA256：`dd53b38203bdfc171ca6367f0c13adb127cecd15bdd54d8c66d869d33600a7fd`。
- 工作树程序文件汇总SHA256：`5821fbde0763b3b3f69f48d1d39687ab9c5fbf93bc062525d690f1e48505a3de`。标准协议ZIP SHA256：`996ae2d7a64f625396cce18fee47624101f31c70fe9f4d23e40df535979117dd`。
- `docs/ITERATION_PLAN.md`保护SHA保持`fb0c2624e7e1d4463730b3125e4b837343e9b84b9f3bc1dcea07b699e73deb90`。所有旧候选、失败包与证据保留，拒绝清理路径未重试。

新包只含程序、公开资产和新候选配置（EN→JA+简中），不含沙箱生成的font/model/fact/status缓存。普通用户新解压后首次自动准备和健康状态**pending**；旧私有字体目录限制没有解除，既有DEV3指定子树的UAC授权未延伸。

## 本轮真实修复及失败证据

通知身份编译、模型缓存读取、wire就绪/读取以及书籍通知域发现的权限拒绝现在直接传播；不能吞成空索引、缺语言、cache miss或继续重建。损坏/缺失记录的正常失效规则保留。负例只使用自有项目TEMP和内存archive fixture，没有尝试真实受限路径。

[r10阻断](../../generated/dev5-system-audit-20261005/candidate-dev5-r10-blocked.json)保存通知身份权限异常；[r11阻断](../../generated/dev5-system-audit-20261005/candidate-dev5-r11-blocked.json)保存wire/book异常。r11最终包5项测试含子例共6失败→[r12同包5项通过](../../generated/dev5-system-audit-20261005/permission-contracts-r12.json)，生产import路径及SHA均记录。

r12原打包核对器遗漏新增四个“应拒绝”结果，错误要求它们被接受；原日志保留。交付核对器按真实PE测试已经定义的9应接受/6应拒绝、4字体反例严格检查，同时拒绝缺项、重复、未知项和错误布尔结果（9个核对器负例）。隔离Python外置模块加载失败也保留日志，随后固定文件路径加载。只改变交付脚本，应用/配置/标准ZIP/SHA及测试断言未改；[完成门槛](../../generated/dev5-system-audit-20261005/final-dev5-r12/final-pipeline-gates.json)保留原失败入口及exact-SHA复用证据。

## 验证结果与分母

- Python完整回归：661总运行，**656通过、5跳过、0失败**，107.564秒。[原日志](../../generated/dev5-system-audit-20261005/python-regression-15.log)。跳过为本机FNT/DDS研究素材不足，不算通过。
- JS：184项/0失败；r12两份JS与原回归精确SHA相同，收据已核对。新增Python异常传播相关34项通过；它们已包含在661内。ruff和diff检查通过。
- 最终发行代码、嵌入Python与同包renderer完成20配置：8种base（en/ja/简繁中/ko/fr/de/es）、主副互换、base与主副不同及重合、冷建/热读；完整模型与同资源代次r9逐字节一致，另一hash seed独立重建一致。完整字节稳定不证明译文或hook全覆盖。
- 独立原PAC主动语音：每组2428可比/0错误目标；26个missing/multiple peer组拒绝，不跨会话借配。不是48,560个独立文本，也不是实际入口采样。
- 独立物理script：978唯一调用、975可比、3动态/未知拒绝；global或精确pointer并集967–975。**EN→JA→简中及反向均971/975**。其余4条为`mp5310_04`的Debug Setting/Council Terminal B/C，原始字节要求未放宽；实际输出与expected的ASCII宽度差异另列，未当通过。
- 效果角色7240探针/7084准入，typed280、组合80、负例396；**80无description独立组仍未有完整身份准入，保持拒绝**。不能因此称现场HP Regen/白银之盾已闭环。
- 有限控制对白496候选：72有限/424未证；320渲染回放与1280负例。六条物品零参数printf描述在20组120/120；oracle读取原字段及独立PE消费合同，不由translator生成expected。
- 24离线入口case×20配置=480/480：terminal3、action key9、cooking11、Handed over1。**不包含Heal/All]/白银之盾/战斗toast的实际控件路径**。
- 水泵`mp3010_01.dat/QS802_08_00/called84`物理literal/newline和20组layer回放通过：中文逗号归第一literal末。实际glyph宽度、frame与像素pending。
- 自有隐藏Python PID18844上的生产V8/wire回放通过，wire 177,748,252 bytes；仅该自建host被使用并清理。没有实际候选GUI startup smoke、游戏启动/附加或普通用户字体准备验收。
- 当前磁盘EXE及旧语音EXE静态依赖：各9无关改动接受、6依赖破坏拒绝，4字体反例拒绝；67个原生点解析。没有读取当前游戏加载映像，没有整体EXE版本/哈希白名单。其他魔改EXE和完整语音资源包未全测，既有用户Mod EXE样本通过不延续成r12验收。

完整机器可审摘要：[handoff-dev5-r12.json](../../generated/dev5-system-audit-20261005/handoff-dev5-r12.json)。全量缺语言/未知/歧义/拒绝原因及稳定ID：[reason ledger](../../generated/dev5-system-audit-20261005/final-dev5-r12/coverage-reason-ledger-index.json)。原始遗漏/未识别pointer不是可见漏译数量。

## 十二族与尚未完成的实际入口

| 族 | 已做的资源/机制边界 | 实机闭环缺口 |
| --- | --- | --- |
| 对白/active voice/Joshua/Aina | 完整body、唯一peer、finite K、physical called与动态负例 | 当前raw/frame/var、base确认与真实消费路径 |
| 效果逐单元/HP/CP | 完整准入与独立semantic ID/主副锚点，角色冲突拒绝 | 实际颜色包装/formatter/无description输入，层位置与重叠 |
| 获得/交付/丢失/数量/货币/奖励 | finite类型槽、物品域、外围模板及调用身份 | slot与外围的真实拼接/复制/截断，不假定与料理共用hook |
| 料理属性 | 范围/属性/数值模板、canonical整数字段key | 是一段rich text还是多个label、key是否保留及真实15 |
| All]/范围/形状 | 原表role与control边界 | 完整原串、icon/颜色identity、入口/路径 |
| Heal跨入口 | 原item3840与item-name域，歧义保留 | 已装备槽与列表/详情/提示/快捷的实际carrier和hook |
| 条件复合/白银之盾 | 原item4330及条件/属性/持续构造族 | 空正文完整constructor、实际输入/消费路径 |
| 确认action按钮 | 9个原table key合同 | Synthesize/Cancel等button实际key/控件类型和hook |
| 脚本多选菜单 | 完整静态region/option/called/code及动态拒绝 | 终端实际指针/复制/setter路径；剩余4–8严格字节项 |
| 战斗即时提示 | 原Back/Side effect name与Impede来源分别登记 | 不能把效果name表当toast入口，真实拼接/控件/hook未证 |
| 攻击附加状态/概率 | 六description的原生printf与外围/状态身份 | literal-copy分支、实际完整原串与角色 |
| 换行/注音排版 | 原hard break、通用CJK/拉丁边界、组合layer机制 | 原生宽度变化、混排/禁则、实际注音/主题像素 |

既有Swap互斥、快捷operation/手柄名机制与按钮布局、三主题真实状态文字/图标+颜色、safe attach、三语README和缓存代码保留并包含必要源码回归。真实UI、手柄、三主题可读性与自动准备仍未验收；本轮不扩展新功能。

## 性能：只报告实测层级

除首次catalog规则失效外，新组合（parsed facts暖）29.74–36.86秒；同配置热读1.78–2.23秒。EN主日副中→主中副日29.737秒/热读1.844秒，2718 fact hit/0 miss；身份10.112、组合10.993、speaker/history4.577、发布1.304秒。首次catalog规则失效总152.8秒仍复用2718facts，不是空缓存普通用户首次启动；后者pending。

这些是离线模型阶段，负载非受控前后对比。没有按钮→prepare→publish→wire→resident ack的端到端测量，没有1–3秒硬目标，也没有提前ready。组合/历史语义与方向相关，未无条件翻转整个模型。单语言事实、真实规则/资源失效及权限拒绝已验证；实际Swap与base变化性能仍由父协调测量。

## 父线程最短安全下一步与待批准动作

当前现场按用户最新信息为DEV3 UI42868/backend54112/game15784；本轮未重新枚举或操控。未知入口缺完整source/key/scope/formatter及运行身份，禁止根据截图短词猜配；现有日志不足以决定上述实际carrier。请父先使用已有label快照；没有时，在另行协调的安全时点采相邻正常/异常控件的完整original/display、key及reason、path/surface、script/table/pointer、动态槽、formatter/layers和model/resident revision。新候选既有diagnostics需在新游戏生命周期安排，不热装当前现场。

最短候选入口是上述`Start-1.0.0-dev5-r12.cmd`，**当前不要运行**。父协调正常退出旧游戏/DEV后，使用普通非管理员用户从ZIP新解压并普通自动连接启动；不以`--no-auto-connect`代替自动准备。先验证EN游戏→JA+简中及同一异常/相邻正常，然后主副对调和base变化记录各阶段/ack；再覆盖全部12入口及注音/主题/快捷操作。原截图/资源与新窗口逐项核对，失败继续保留现场→修复→新候选，不标完整验收。

项目外安装未获本线程写权限。具体建议待父批准：确认`E:\Bilingual Sora 2nd DEV\candidate-1.0.0-dev5-r12`不存在后，由普通用户新建并解压669成员，核对ZIP SHA；不覆盖旧安装、当前DEV3、配置或存档，不复制任何受限font/model缓存。旧目录原位保留作为恢复点。若需原位替换，另列/批准关闭步骤与配置备份；本轮未执行。回退也由父协调正常退出新进程后用原目录启动，禁止强杀或向当前游戏热替换resident。

项目权限保持workspace-write/approval never，仅项目写入，未使用网络、未增加ACL或全局权限。gpt-6.1-sol/xhigh/priority为请求；工具未暴露effective字段。无push、CI、tag、release、外部公告或付款。用户对新候选明确实机通过前不允许晋升发布。
