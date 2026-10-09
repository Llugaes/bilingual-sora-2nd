# dev4 调查与修复记录（本地门槛通过，实机验收 pending）

dev3 保持冻结。本轮开始的只读桥接快照记录游戏15784、UI37400、backend52848，实际来源en、主ja／副zh-Hans，准备模型runtime-3e9c91d821461e692e73；未重新采集当前进程／场景。静态配置game_language=zh-Hans不是快照中的实际base。截图仅父会话看过，本执行者没有看到像素。

## 修改前生产链失败证据

`generated/dev4-correctness/dev3-failing-production-replay.json` 使用冻结dev3的真实完整模型与随包 RuntimeText/ScriptIdentities，保留模型和解析器SHA、冷／热重复输出。资源证据为 `raw-dialogue.json`、`sample-catalog.json`、`effect-resource-probes.json`。这里的完整控件包装是资源合同探针，不冒充截图原串；实际现场变量与控件raw尚未采集。

- 爱娜：官方 `script/scena/mp0010_05.dat/EV_08_05_00/called/695`，8语均有正文，actor134。表达头后存在var，英文arg5为`Let me see...`，日文`そうね……`、简中`这个嘛……`。旧完整模型没有可接纳callSite，带头／无头字面探针均plain且不转主语言。其它同文记录有不同日中译文，不允许全局短句补配。
- 动态控制拒绝机制：真实定义是局部`<K3>`，距读点超过旧128指令搜索窗口；中间含flag条件的op29及其它对白system-call。旧有限证明只接受很短区域和少量操作，不能覆盖这个真实producer。跨语 `_aligned_call_map` 的早期前缀停止还需独立审计；不能仅扩大窗口后把相同ordinal当可靠映射。
- 效果分段：真实FORMAT8与typed构造模板，在en→ja→zh-Hans完整模型中翻译能完成，但三独立效果被放进一个layer；层内包含全部中文，直接复现整串副文粒度错误。独立效果应各拥有稳定资源／构造器身份、自己的主副配对和注音锚点。
- HP／CP：官方name/stat与turns同英文，但对应日中含义不同。普通全局拒绝合理；作用域里的effect-role对已存在。需检查颜色／字号将单成员与FORMAT8隔开后是否重新落入普通全局拒绝。保留无上下文同文冲突拒绝，不新增词语白名单。

## 授权实施方案与正负边界

1. 按正式VM IR的栈、局部读写和CFG证明控制值，覆盖持久局部值与分支、调用后的栈回收；所有到达读点的路径必须是有限字面控制。动态可见值、地址传递、未知操作、不可证明循环及外部入口拒绝并保存原因。跨语用完整调用／已证明对白序列及原调用身份对齐，不删var或伪造现场值。
2. 保留完整效果串的安全准入；在已证明详情头／说明／稳定资源作用域内编译独立效果单元合同，区分name/stat与turns/value/format。整串匹配用于避免歧义，渲染用每个单元的稳定身份／参数／主副边界；单语、禁用、原控制码、真换行、原注音及未知成员维持保守行为。
3. 分母从原PAC的物理调用／字段建立，输出未关联、缺语言、歧义和拒绝原因；不能把目录条数或coverage缺项数当屏幕漏译数。对8种实际base、主副互换、冷／热键和最终包生产链分层回放，expected取独立资源／参数合同，禁止用生产翻译器生成同一断言预期。
4. 模型／语言事实按解析与规则代码摘要失效，新规则不读写dev3缓存。保留主动语音、Joshua、HP/CP、Swap、快捷、三主题、缓存与安全连接回归。新候选标识占用检查后选择dev4；不会启动第二可附加UI／backend。

旧全量／矩阵缺口：效果重点为英文主／日文副，最终包回放主要验证与先前生成plan一致；没有这次en→ja→zh-Hans的真实完整链、持久控制区域、颜色隔开的effect-role，以及“每独立效果一个注音单元”断言。静态存在、同源parity及热读成功均不能证明现场正确。

## 当前已实施与进一步失败闭环

- 有限控制证明扩展为有界栈与到达读点的 CFG；未知到达操作、可见动态值、外部入口和回边仍拒绝。helper 的字面参数与正式可选参数声明须一致。重复对白元数据仅在完整 leaf 对白 producer 的命令、actor、参数与原生回收序列全部一致时按 PC 区分；其它 producer 不采用过滤后的 ordinal 猜测。
- `sample-contracts-after.json` 核对 8 语真实资源：爱娜 695（K3）、另一处爱娜 597、Joshua 501 各保留原 called ID，均有正式字节码 PC。原始 var、控制值与调用上下文未删除；现场实际变量仍未采到。
- 作用域里的效果配对按 name/stat／已证明 typed constructor 的角色归类，与其它物品或技能同文冲突分开。角色内缺语言、歧义、未知参数继续拒绝。独立效果层携带 `semantic_ids`、`parameters` 与 UTF-8 锚点偏移，完整原生聚合构造器保持原子性，真正换行保留。
- dev4 第一版实际发行包的 `ready_model` 冷构建失败（`final-model-build.log`）：新增 helper 读取错把 +5 flags 当参数数。已修正为正式 +4 byte，并补 flags／缺身份拒绝回归。失败包及缓存原样保留；下一修正候选为独立 `1.0.0-dev4-r1`，不沿用旧包哈希。
- 修正后的独立原 PAC manifest 审计：8 语各 1082 个逻辑脚本均可接受，见 `manifest-resource-audit.json`。此处证明发现／身份解析可执行，不等于所有文本配对或可见场景均已通过。
- 第一版全量门槛：Python 625 总运行／620 通过／5 跳过／0 失败。最终源码为 Python **629 总运行／624 通过／5 跳过／0 失败**，JS **180 通过／0 失败**；候选标识另有 2 项最小回归。所有单元日志中的上传、发布或连接字样属于 mock，不是本轮操作真实游戏或发布。

## 最终候选及修复失败闭环

最终交付是 `dist/comprehensive-1.0.0-dev4-r2/DEV`，显示 `DEV 1.0.0-dev4-r2`，入口 `Start-1.0.0-dev4-r2.cmd`。package schema 1、内部发布协议版本 `0.4.2` 保持，目标仍为 1.0.0 候选；稳定版、tag 和远端均未修改。显示 helper 已在包内导入核对，未启动或目视真实窗口。

第一版 dev4 的参数头错误以及 r1 的独立效果审计失败均保留。r1 暴露两类进一步缺口：原字段拥有的前后空白被展示 padding 先处理，以及派生片段／前缀和无参数身份的格式标签混入效果成员角色。r2 先匹配资源拥有的完整字面，再处理边缘展示；角色只接纳原始 name/stat、正式 typed 构造合同及已证明的原生 flag 枚举。没有 HP 单词补丁、短句补丁或全局模糊匹配。

源码发行文件集合 SHA-256（文件名→摘要，排序 JSON 聚合）：
`b7107a802f7d05518f31d861afd02966dab7dfaa8d497dec97a721aa25493c66`。
完整程序 ZIP SHA-256：
`5de4469af0e279d2f6efba2d1b5b67cdf4b87eb2296a2e242a947ccb64ddf139`。
DEV 逐文件清单 SHA-256：
`1aac15ddfada45316fe8c4f66242fbafaba34c13e71532a73afb2ff0979c8403`。
详细文件摘要与所有状态见 `generated/dev4-correctness/candidate-r2-final.json`、`final-r2/candidate-files-sha256.json`。664 个程序文件校验通过；加入 6 个已验证常用模型和单语言事实后共 10,467 文件。源码无漂移，dev3 管理的源码摘要未变，迭代计划原有修改未动。

## 最终包生产链覆盖

`final-r2/matrix-build-receipt.json` 和 `full-model-builds.json` 由 **r2 包内嵌入 Python + ready_model** 产生。八种真实 base（en/ja/zh-Hans/zh-Hant/ko/fr/de/es）各两组 base、主、副全不相同配置及主副互换，另加 ja/zh-Hans 的 base 等于主／副共四组，总计 20 组。这里不是所有 8×7×6 组合，也不是全游戏逐条实机验收。

| 检查 | 实际结果 | 证据（均在 generated/dev4-correctness） |
| --- | --- | --- |
| 修改前冻结 dev3 完整模型／包内 JS | 爱娜无准入身份、三效果整串 layer、样式后的 HP 角色退化；失败保存 | dev3-failing-production-replay.json |
| 原 PAC 独立分母 | 八语各 1082 脚本可解析，315 table 文件；未知与遗漏槽分别留存，不当作屏幕漏译 | resource-inventory.json、resource-inventory.summary.json、manifest-resource-audit.json |
| 最终控制对白 | 496 原始候选，72 调用证明有限控制、424 拒绝；128 locale/control 变体；320 渲染和 1280 反例，0 失败 | final-r2/control-dialogue-resources.json |
| 独立效果字段／构造器 | 1025 物理字段、7 个已证 type16；20 模型共 7240 字段／样式探针，7084 准入、156 明确拒绝；80 组合、396 拒绝／未知反例，0 失败 | final-r2/effect-resource-summary.json、effects-BASE-PRIMARY-SECONDARY.json |
| 主动语音全部原行 | 八语 19,848 原行强制指针检查；20 正式模型 49,620 次回放（4052 走指针），0 失败；540／541 保留独立会话身份 | final-r2/active-matrix-summary.json、active-BASE-PRIMARY-SECONDARY.json |
| 保留对白身份后重载 | 20 模型共 2560 次解析、5120 反例，0 失败 | final-r2/retained-identity-summary.json |
| 包内完整索引 V8 | 175,747,868 字节 wire；3 个独立效果层、16 英文控制对白及动态反例通过；仅本轮自建隐藏宿主 PID，已正常完成 detach／自身宿主清理 | final-r2/owned-v8-report.json、owned-v8-r2.log |

字段／样式数量包含重复展示变体；plain-equal 及 typed 是准入数量的子集，不再重复累计。全量 Python 保留主动语音、Joshua、HP/CP、Swap、快捷操作、三主题、缓存和安全连接回归；几何 fixture 覆盖不同宽度、原生 flags 和重复帧，但不等同于游戏真实 renderer。

效果 expected 直接来自物理 table descriptor、字段偏移、FORMAT8 和已证 type16 参数绑定，不调用生产效果 grammar／翻译器生成。控制对白正文 expected 从物理 called 参数和字符串读取，有限控制值另由 VM 证明核对；实际 PC、token 和资源身份由正式 manifest 验证。负例包含真实未证明调用和真实 producer 的离线 IR 可见动态变体，不冒称改过游戏字节码。

爱娜 695 的英文正式 PC 为 488482，控制原串为 `<#E[1]#M_2#B_0><K3>Let me see...`；包内主日文为 `そうね……`，副简中为 `这个嘛……`。这是原资源合同回放的值，当前用户现场实际 var/frame 尚未采到。其它同文爱娜记录仍按各自调用与 actor 分开，Joshua 501 的有限控制身份回归保留。

## 渲染粒度与拒绝合同

- 完整详情头／正文资源边界负责准入，不能拿逗号分割任意文本后全局猜译。
- 每个独立效果成员携带稳定 `semantic_ids`、受约束参数、主／副文和 UTF-8 锚点。原生组合构造器共享参数的部分仍作为一个语义单元；相邻独立效果各自一层，分隔符不拥有注音。
- 仅剥离边缘展示颜色／字号；内部控制、图标、原生注音、真实硬换行不抹平。未知成员不得授权整串的效果单元；无上下文 HP/CP 同文冲突继续拒绝。
- 宽度、禁则、拉丁词边界与主副分段沿用既有通用规则；原生布局 fixture 通过不证明用户三图的真实字形坐标。

资源级清单在 `final-r2/resource-coverage-ledger.json`。当前 en→ja/zh-Hans 有 53,251 个目录记录缺目标或为空、2028 个全局显示串冲突；这些是发现／配对分类，可能含非显示参数、重复源和可由作用域解析的记录，不能称为可见漏译。134 个详情效果拒绝记录保留原编译理由（125 参数合同未证实、9 成员准入未通过）；`effect-role-rejection-context-en-ja-zh-Hans.json` 补原字段、目标是否缺失、参数及合同身份。混合编译理由不擅自改称全部歧义。其它 base 的角色拒绝见各效果报告，八语缺项／未知字段见独立 inventory。第一次清单的 metadata 子模型位置和列名误写已纠正，原 metadata 文件留存，不改变模型或包。

## 缓存、字体与实机边界

R2 映射代码键为 `0c503685ea64108407c85b8304b745078074723984171b74af35115c15f66b7d`，解析目录键为 `3c60feabd890c57516f6e944d2b2a4fb6edf3bbc0256c9143cbaf185524ad2fe`。每个新模型都是冷映射键，复用本轮 r1 已验证且键／内容摘要相同的解析目录和单语言事实；没有读写 dev3 模型缓存。20 组冷映射 45.194–56.223 秒，中位 48.827；热读 1.632–2.101 秒，中位 1.854。r1 完全冷 parser 首例 78.280 秒是独立前批基准，不能和 R2 暖事实比较冒称零重建。

候选只预置 en/ja/zh-Hans base 下主日副简中及对调共 6 个模型；其余完整回放模型保留在证据目录。未复制 preparation/live/status 的陈旧运行记录。没有字体缓存、旧受限 manifest、游戏文件或存档进入候选；仅普通用户首次自动生成字体。新目录及一个模型文件只读 ACL 核查有继承的 Authenticated Users Modify／Users ReadAndExecute，无 ACL 修改；实际普通用户启动、font health 和自动连接仍 pending，不能靠 ACL 文本替代。

当前 dev3 场景、正式安装和旧候选均未关闭、附加或覆盖。需要父线程协调安全时点：用户正常结束当前游戏并从托盘退出 dev3 后，自动启动 r2 的现有入口，再用新游戏进程测试英文 base／主日／副简中。先核对路径、候选标题、来源 matched、字体 health、ready；复测爱娜、HP/CP、三效果独立对齐、主动语音／Joshua，并做主副对调、宽度／日志检查。失败时只读采集 raw/frame/key/scope/参数和调用身份，不清缓存。恢复则正常退出 r2／新游戏，再使用保留 dev3 入口和新游戏进程；不覆盖安装或存档。项目外安装仍未执行。

**未测**：本执行者未看三图像素；三图控件的现场原串／变量／scope/frame 未采；普通用户实际首次字体生命周期、新游戏 resident revision、所有场景／语言组合／全部修改版 EXE 和完整语音资源包。新候选用户实机明确通过前禁止 push／CI／tag／公开发布，dev3 失败及旧候选验收不延续到 r2。

## 冻结与权限

原dev2/dev3、证据与未提交修改保留。初次命令误在dev3下创建空 `generated/dev4-correctness` 目录，未写任何源码／配置／缓存文件；移除空目录被管理策略拒绝，留存且不重试。后续输出只在项目根generated/dev4-correctness。旧字体ACL授权仅属于用户指定dev3子树；不会改新旧ACL或复制受限manifest。新交付不携带sandbox生成的私有字体缓存，普通用户的正常自动准备与新游戏验证待父协调安全时点，不能用离线UI代替。
