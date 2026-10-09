# 综合资源族与显示入口审计（实施中）

最新本地候选`1.0.0-dev5-r12`的结果、保守拒绝与实际入口pending见[安全检查点交接](dev5-r12-handoff.md)。完整综合目标未宣称完成。

最新资源代次、r9失败、r10权限负例阻断及r11修复验证见[本轮证据与边界](dev5-resource-epoch-and-cache.md)。以下历轮记录保留，不把早期通过提升为最新实机验收。

完整输入准入与逐效果单元的正负边界见[渲染合同](dev5-render-contract.md)；它们是两份独立合同，完整语句成功不能覆盖实际控件和注音粒度的缺口。

本轮接续原线程，完整消费综合引导的12类案例，不重建逐例队列。dev4-r2仅为首批正确性门槛，不能替代新增入口验证。当前配置上下文为英文游戏／主日语／副简中；未独立重确认的图片保留此标记。本执行者未看图片像素。

## 证据层与准入

1. 从原PAC物理调用／字段建立每族分母，记录资源版本、语言、稳定ID、函数／called／参数槽、formatter角色。已有目录只作定位，expected直接读取原字段与已证明的构造合同。
2. 修改前以冻结dev3、必要时r2的完整模型和包内解析器重放，记录base→primary→secondary、完整控制串、身份、拒绝／fallback和最终层。资源合同探针与现场raw明确分开。
3. 对生产发现、跨语配对、格式参数和作用域分别建立正／负边界；局部同文必须有资源域或调用身份，不按首条、词语白名单或fuzzy解歧。
4. 控件入口须有实际原生消费／复制／截断／赋值边界的机器码或只读运行证据；缺现场证据的path/hook/变量保持pending。普通setter、内联写入、复制、原生历史和menu/button不能彼此代替。
5. 正确性修复后，同一最终新候选／源码／包哈希回放八种实际base、主副互换、原控制／硬换行／样式、复数／顺序和冷热键；保留1.0既有回归。真实游戏与普通用户首次生命周期由父协调。

## 资源族×入口合同矩阵

| 案例／族 | 首轮资源定位与本轮范围 | 入口边界与当前缺口 |
| --- | --- | --- |
| 1 对白／主动语音／控制变量 | 原script调用身份、finite K及t_active_voice会话；保留r2原调用PC、actor和跨语言回归 | 对话、日志、主动语音分别核对；当前现场frame/var未采，实机pending |
| 2/3 效果单元、HP/CP | SkillEffectHelpData name/stat/turns/value及原生组装合同 | 完整详情头准入与独立效果锚点；短提示／空正文入口不能用有正文结果代替 |
| 4 获得／失去／交付／奖励通知 | system与scena的实际builder调用、item/quantity/currency/quest槽及各locale语法 | 外围模板和动态slot独立核对，通知复制／弹窗／日志不预设同hook |
| 5 料理属性 | 范围／属性／增减／数值模板和颜色槽；与道具通知是否同源待证 | 料理结果提示及属性label；标题正常不能证明正文 |
| 6 范围标签 | SkillRangeHelpData、形状／目标角色、括号／图标controls | 详情头／范围文本，图标opaque；不能全局All替换 |
| 7 同item跨入口 | 原物品ID及名称资源、同名异义候选 | 列表、已装备槽、详情、提示、快捷入口分别核对identity和hook，实际控件路径pending |
| 8 条件复合效果 | critical-health属性组、增量／升降icon／回合共享与原连接表 | 白银之盾等实际槽组合及空／非空正文；不补截图整句 |
| 9 确认action按钮 | t_text真实action key及动态控件key保留／复制 | 合成／购买／出售／装备／退出等按钮族，同名语义与正文分开；现场button路径pending |
| 10 脚本多选菜单 | LP_Terminal及全部同类选择调用、标签槽和locale结构 | 与普通对白／确认button是否同入口待证，不只补三句 |
| 11 战斗即时提示 | 实际资源ID、拼接／截断／control，不能根据裁图认定t_itemhelp | 战斗提示控件与详情表分开；实际调用／path仍pending |
| 12 攻击附加状态／概率效果 | 原状态IDs、程度、共享概率及native角色／slot | 完整外围模板、状态单元与颜色控制同时验证；与Impede同源须证实 |

## 技术顺序及覆盖缺口

先取得冻结包可失败的回放及原资源族清单，再处理共享的跨语言结构对齐、类型化builder、格式／作用域准入和实际入口身份。按依赖决定实现顺序，不把截图变成字符串patch。

性能随后处理：既有r2新映射45.19–56.22秒／同配置热读1.63–2.10秒仅为模型阶段。按单语言单位复用解析、manifest和历史事实，组合阶段独立校验；新增可观察cache key/hit/miss/rejected及原因。按钮→prepare→publish→wire→resident ack分别记录，离线宿主与真实UI端到端分开。用户未设1–3秒硬指标，不能提前ready或假进度。

旧QA缺口：主要EN主／JA副，部分expected由同一translator生成；缺EN→JA→SC整链、外围模板、逐单元与同资源跨入口。r2的20组合只覆盖第一批合同。本轮每项保留未发现、缺语言、歧义、拒绝、入口未证和实机pending，不声明零遗漏。

## 安全与版本

仅项目workspace-write，approval never，网络未使用，唯一writer，无代理通信。AGENTS已读，项目不存在.agents目录。写探针在唯一项目内目录创建／读回／清理通过。全部旧候选冻结，新标识拟dev5且目录尚未占用；构建时再次核实。dev3当前游戏／配置／缓存／字体／存档不改，不启动第二UI/backend。旧被管理策略拒绝的清理不重试。字体权限仅原dev3指定30对象；新候选不携带私有缓存、不扩大ACL。Fast/priority已请求，当前工具未提供实际effective字段，不能标已生效。

初始证据目录：`generated/dev5-system-audit-20261005`。完整原指导已读取桥接txt；全部12项继续开放，后续逐族证据更新此矩阵。

## 恢复写权限后的实际修复与边界

本次唯一 `.codex-write-probe-8bc22a3f-e165-4294-8376-09444b2ccbb9` 创建／读回／清理通过。实际声明为项目 workspace-write、approval never，网络未使用；未增加目录权限。最新现场 PID 42868／54112／15784 仅由用户递送，本轮没有操控现场或启动第二套 UI。所有旧候选与拒绝清理路径保留。

1. 通知的上游已证明完整 opcode-17 有限物品流，下游数字构造器却统一拒绝超过四槽。修复只允许完整类型化图标流扩至32槽预算，普通数字仍最多四槽；槽数、物品数、三语言物理调用、ASCII图标与printf位置均检查。不满足合同的key/called/reason进入 `producer_numeric_rejections`。`wide-icons-red.log` 保存修复前失败；`wide-icons-green.log` 71项通过。
2. `script-display-before-wide-icons.json`／`script-display-after-wide-icons.json` 独立物理分母为每语言1082个script、938个menu_additem、40个item-panel；978个唯一调用中975个三语言可比，3个动态／未知拒绝。全局成功733→737，四个真实八物品调用恢复，原成功项没有退回；剩余238条均为菜单。不能把这些计数当现场漏译数量。新增报告区分全局与资源指针合同；实际指针是否通过控件复制路径保留仍待采集。
3. 物品详情的原生 `0x347320` 路径从ItemTableData description读取format，经`0x352a80`的有界printf；零参数也会把 `%%` 输出为 `%`。此前索引把零槽format当作字面显示串，混合状态描述因此只剩局部Delay转换。新增编译限定物品description稳定ID及此formatter角色，保留全部控制码、硬换行和各语言原生语法；动态／未知printf字段拒绝，不处理普通脚本、书籍或任意标签。`frozen-r2-item-printf.json`独立原PAC的6条同族描述全部失败；`source-06-item-printf.json`完整工作树生产模型6/6通过。原生literal-copy分支和现场实际raw仍pending，未声称看过截图。
4. 单语言缓存现在存储已经证明的历史marker和静态setter来源，而非每次把全函数调用重新还原／扫描。它不保存目标配对决定；组合仍核对physical called、精确正文、catalog冲突与setter来源，动态／未知调用清空、分支拒绝保持。`provenance-model-equivalence.json`证明完整生产模型的script identities、history contexts、speaker contexts与修改前相同。每个fact记录kind/key/resource/rule SHA、hit/miss/rejected和reason。新规则首轮76.34秒（2609 miss）；暖事实对调40.60秒（2666 hit/0 miss）；同配置暖事实新映射40.34秒。旧同配置54.22秒与新值是离线模型阶段，不能代表按钮→wire→resident ack。跨方向、负载与冷事实限制必须保留。

当前本地回归：`python-regression-01.log`总运行636项，631通过、5跳过、0失败（在printf修复之前）；printf之后`item-printf-green.log`运行94项通过，包含一个重复指定的class，不能作为94个独立用例计数。曾两次误写不存在的active-voice测试模块导致加载失败，日志保留；随后正确discover整套通过。最后包仍需用正确测试入口再次核实相关变化。

### 必须继续的入口调查

料理11个模板与9个action-key回放正常，不证明用户控件保留key或数值15已经捕获。Back/Side Attack Bonus可定位到两个效果name记录；Impede同时有完整效果name和缺简中的AI调用，不能凭同文把AI来源当真实提示来源。All]、已装备Heal、空正文的白银之盾、HP Regen着色／组合详情均须核实完整原串、角色与消费／复制边界；不按截图补短语或全局选首条。

菜单原资源`menu_additem`实为system group15/command1（不是对白group5）；当前全局同文拒绝与真实携带pointer/option身份是两层。尚未核实现场是否使用直接脚本池指针、复制串、延迟赋值或内联写入。不能把离线手动给定身份的成功算hook覆盖。

若父在安全时点安排只读控件证据，最小输入是现有DEV支持的完整label采集：每个报错控件的original/source、key、scope/path、pointer/复制来源、formatter输入槽、主副输出与resident revision，保留相邻正常控件作对照；不要求退出游戏、重注入或清缓存。本执行者不自行读取控制端口或改变诊断配置。完整12族、普通用户自动准备、真实UI Swap ack和最终实机验收仍开放。

## 完整静态菜单区域与字节码别名

`source-06-script-display-pointer-contracts.json`把975条可比物理调用分为737条全局解析、263条精确资源指针合同；并集962条，225条全局失败可由指针合同解析。后者不是实际控件携带了指针的证明。13条剩余项中，七属性选择和RestShop Yes/No前面的动态通知使整函数对齐中止；另外四条B/C开发菜单仍有真实同文/共享池冲突。

新合同只接受完整静态菜单的create、1–32个不同option ID、open、wait、close。每个调用的实际字节码push参数和literal必须与物理called元数据一致；完整区域的控制码、参数及默认literal保留，重复区域、动态选项、进入区域内部的分支及未知指令拒绝。区域配对仅补菜单，不恢复前序未知对白或通知。七属性菜单八语的原函数均证明11–17物理called对应。

`menu-region-red.log`保存原失败；`menu-region-green-02.log`33项通过。第一次区域修复后`source-07-script-display-pointer-contracts.json`仍为737全局，但指针合同增加至272、并集971。进一步核实called和code两个索引保存的是同一条已证明菜单literal；code的部分语言副本此前仍阻挡全局配对。现以完整区域证明附加物理menu called归属，完整记录只覆盖其自身副本，其他同文来源继续冲突。`menu-code-alias-red.log`保存这一实际拒绝链的最小失败；`menu-code-alias-green.log`64项通过。最终包需重新核对全局/身份结果，不能沿用source-07模型或hash。

缓存阶段另将历史正文及主副pair的纯规范化限定为单次编译内的有界memo；不存跨语言配对或歧义决定。`source-preview-07`整轮171.61秒包含资源规则变更后的重新提取/新事实，不能当暖Swap耗时。最后候选只发布公开程序/资产及新候选配置，测试模型留在项目证据目录，不携带沙箱生成的font/model/fact/status缓存。

`python-regression-02.log`总637项，632通过、5跳过、0失败。增加菜单边界后`python-regression-03.log`总640项，634通过、5跳过、1失败；失败为独立离线单实例进程quit IPC在2秒内未关闭端点。该测试在`ipc-rerun-01.log`原断言单独复跑通过，未放宽timeout或删除断言，未修改IPC实现；原失败保留，全套复跑仍作为打包门槛。这些Qt子进程仅使用项目临时root和`--no-auto-connect`，不启动后端，不属于真实候选或DEV3验收。

## 最终包回放发现的新问题与后续候选

完整效果模板准入和注音粒度是两份合同。渲染器原先只在存在物品description边界时进入效果分段，且最长完整复合模板会吞掉本可独立的效果成员。现保持完整句身份准入，比较所有有界的原生连接符分段：只有所有完整方案的主副输出一致，才选择更细的独立单元；不同目标、未知控件、原生ruby、硬换行、超过32成员或128方案预算继续拒绝。`effectUnitFailures`保存分段拒绝原因。效果候选采用现有无损字面索引，避免普通对白扫描全部2,313规则；未被索引证明的正则仍保留fallback与冲突检查。新增JS用例含同目标的复合/独立规则、冲突方案、完整句与角色不一致、控制和动态负例，属于机制回归，不能当真实截图已复现通过。真实资源的无description行若没有完整准入仍保持拒绝。

`python-regression-04.log`总640项，635通过、5跳过、0失败。`js-regression-05.log`181项通过、0失败。随后dev5-r4同包生产重建发现与r2同规则的模型SHA不同：不是目标值变化，而是`MenuTranslator`从set迭代源变体及拒绝模板，导致numeric数组和嵌套模型顺序随Python hash seed变化。`r4-model-difference.json`只对明确无序的规则字段做诊断，证明其余字段完全相同；原byte-identity门槛仍为失败，没有覆盖旧证据或放宽门槛。最初指纹比较脚本还因tuple/list未规范化而失败，原日志同样保留。

已在源变体和拒绝模板生成处固定顺序，不改变配对、动态拒绝或缓存身份范围。`model-order-red-02.log`记录跨10种hash seed的失败；新增回归在`python-regression-05.log`全套通过：总641项，636通过、5跳过、0失败，107.101秒。一次针对性命令误写不存在的`tests.test_native_catalog`导致加载错误，保留`model-order-green.log`；本次全套discover使用实际模块。所有历史候选r1/r2/r3/r4保留，最新候选为`comprehensive-1.0.0-dev5-r5`，显示1.0.0-dev5-r5，package协议仍0.4.2；正式版本、tag、远端未变。

r5正在从包内嵌Python为20组合逐一重新构建完整模型，再热读核对；不再沿用r2运行模型。已有我们自己生成的单语言事实和catalog由生产签名检查决定复用，不读取DEV3、受限字体或游戏缓存。所有资源渲染回放需在r5同一包与模型上完成，实际控件、普通用户自动准备和用户验收仍pending。

### r5同包结果及新增失败：不能交付验收

r5的20生产组合均完成：模型冷（单语言事实暖）32.28–39.14秒，同配置热读1.79–2.33秒；2666 fact hit/0 miss，各阶段保留日志，未测真实按钮→wire→resident ack。全20效果回放没有失败：物理字段1025，累计角色字段探针7240/准入7084，typed280、mixed80、负例396；无description的80个整串未有完整身份准入，明确拒绝。控制对白独立分母496候选，分类finite72/unproven424；128个语言证明变体，320个渲染回放及1280负例通过，Aina/Joshua现场raw未采。六条零参数printf原描述在20组合共120/120通过；此原生反汇编oracle使用已有分析Python的capstone/pefile，模型来自候选内嵌Python、渲染器来自同一候选。公开运行时不包含分析依赖；第一次用公开Python执行反汇编的ModuleNotFoundError日志保留，并非产品依赖错误。

物理script每base的938菜单/40物品panel保持978唯一调用，975可比/3动态或未知拒绝。EN→JA→SC为744全局、265指针合同、并集971；其他base并集967–975。剩余只有`mp5310_04`的开发/议会设置A/B/C/E同文与池冲突（不同base具体拒绝数不同），不选首条或全局字母替换。LP_Terminal等指针合同成功不是实际复制链保存pointer的证据。控制回放初次沿用`full/`目录而非本轮`models/`失败；已增加显式catalog-dir，旧日志保留，source/hash相同的parser audit仅复用我们自己的合法数据。

24个冻结独立资源expected在20组合的全局/静态key回放仅404/480。JP/SC料理五模板的%d展开后，不再等于资源模板，可信key被现有严格字面条件丢弃；部分终端同文需要精确资源身份，不能凭全局结果称该场景通过。另新增的完全独立ActiveVoice oracle直接读scalar、说话者、条件、voice数组及body，以唯一原始metadata peer建立expected，不调用生产aligner或translator。每组合2428条可比、26组missing/multiple peer拒绝；繁中5073/5074等完整body有不同JP语气，global却在失去整句后借译另一条的片段，独立oracle真实失败，尽管精确pointer合同仍正确。因此r5门槛失败，保留候选、模型与`voice-independent-summary.json`，不把pass计数或pointer成功覆盖这个错误。

### r6授权修复与严格边界（验证中）

1. 已知完整ActiveVoice body和script-menu source若没有自己的唯一完整配对，加入整串拒绝，避免generic wrapper及逐行借译。精确VM/pointer/key局部模型仍可准入；菜单的partial alias仅能被同physical record证明覆盖，外国同文缺语言仍拒绝。新增`display_rejections`保存source、稳定keys、conflicting/missing reason。`whole-display-refusal-red.log`记录失败；最初把menu当成display authority破坏两条异义负例，已纠正为只加整串拒绝、不提高菜单的authority，`whole-display-refusal-green-02.log`71项通过。
2.可信text key只扩展到已编译、完整命中的1–4个canonical %d/%i/%u实例：source及双目标kind相同、整数表示和32位范围准确，不接受%s、float、宽度/precision、positional、未知控制、陈旧key或片段。`keyedMatch`返回可观察reason，native snapshot附加text_key_reason；旧resident无此接口仍保留字面条件。本轮不会加载到DEV3。`keyed-integer-red.log`、green及native mock证明正常格式化和陈旧widget拒绝；这是控件合同回归，现场cooking是否同label含数字/保留hash未采，不冒充实际入口通过。
3.完整回归`python-regression-06.log`总643项，638通过/5跳过/0失败；`js-regression-06.log`184通过。五跳过均为实际FNT/DDS研究素材不齐，详见`python-skipped-tests.json`；不计为通过。新候选标识dev5-r6，所有旧候选冻结。仍需最终同包、八base、独立oracle及owned V8验证，真实UI与普通用户准备pending。

### r6完整字节门槛失败及r7修复

r6的20组合生成/热读全部完成，暖单语言事实下的新组合32.39–41.17秒、同配置热读1.80–2.22秒。另一个独立进程、hash seed 11重新生成同EN→JA→SC完整模型时，字节SHA仍不一致。`final-dev5-r6/model-determinism-report.json`和`model-order-diagnosis.json`保留原失败：完整模型语义相同，只有`history_contexts.names`和`fallback_names`的字典写入顺序不同；不能因此覆盖byte gate或沿用验收。

根因是静态speaker setter从跨语言集合遍历source label，传递到历史名字索引的顺序随hash seed变化。现只把此集合遍历排序，保留全部候选、歧义及fallback选择规则。`history-order-red.log`记录新增10个seed的未排序字节测试失败；`history-order-green.log`43项相关回归通过。原菜单hash-seed测试的`sort_keys=True`也已移除，它曾掩盖字典顺序；expected不再进行排序归一化。正式规则fingerprint包含speaker_context.py，因此必须生成新运行模型，不能复用r6 runtime文件。

新标识为r7，所有旧目录、模型和日志冻结。先完成一个正式生产模型与另一独立hash seed的完整byte gate，再生成其余组合并做最终同包资源、拒绝清单和owned V8回放。r6不是最终验收候选；未操控DEV3，普通用户字体生命周期和实际控件入口继续pending。

r7全套Python回归总运行644项，639通过、5跳过、0失败（107.523秒）；JavaScript程序与r6相同，184项同源码回归证据保留。r7完整EN→JA→SC生产模型以seed 1和seed 11在两个独立进程重建，完整SHA均为`8f034d316ff069c43d6b1343bec0ff832e7c1401e833f8ee7fa4af33f66cf227`；未排序／改写模型，`model-determinism-report.json`门槛通过。其余组合正在重建，不把首组通过代替全矩阵。

## 后续最小入口补采（本轮未执行）

已核对现有`tools/read_native_layout.py`只申请`PROCESS_VM_READ|PROCESS_QUERY_INFORMATION`，没有写内存、暂停、输入或注入。新增可选`--include-node-inventory`，只记录已遍历基类节点的vtable原值／模块基址差值、路径和有界实例；未分类节点绝不读取TextLabel字段，也不算可见未译文本。已证明TextLabel新增原始`0x2ec` key hash，陈旧hash仍不当身份。`layout-inventory-offline-02.log`3个离线负边界通过；此诊断工具未进入候选包，候选源码摘要没有因此变化。这三项在全套644运行之后新增，单独计数，不声称全套647已跑。

父需要先协调只读补采授权与安全时点；本执行者没有执行采集。当前PID必须重新只读核实，禁止直接沿用旧PID、猜EXE路径或广泛进程匹配。若已有`generated/native-labels.json`，可先复制其现成快照与同时间status/live/model/revision；不启用当前DEV3 diagnostics、不改它的配置或缓存。没有该快照时，布局采集只能获得当前内存display，不保证取得resident保留的original／script／table identity。`native_runtime.snapshot()`是现有backend持有的接口，不假称外部CLI可以无附加访问；不为取原串重attach或加脚本。

下一安全新游戏进程的候选验收，可由父明确安排新候选的既有diagnostics生命周期与布局采集。所需对照为：完整original/displayed、text_key及reason、控件path/surface、实际source/key/scope/script/table/pointer身份、动态参数、formatter角色、渲染layers、模型SHA与resident revision，保留相邻正常label。先采不需移动当前场景；若场景已变，再由父安排最小复现操作。普通用户从候选ZIP新解压并首次自动准备，另记录按钮→prepare→publish→wire→resident ack，不能用`--no-auto-connect`替代。此安排尚未执行或批准，不向运行中的DEV3施加任何变更。

## r7独立主动语音失败：归类没有覆盖正式身份

`voice-independent-r7.log`／`final-dev5-r7/voice-independent-summary.json`完整20组合仍有8组合共40条错误global输出，尽管每组2428条精确pointer合同仍正确。完整byte gate通过只能证明重复生成稳定，不能证明译文正确。r7冻结，`candidate-dev5-r7-blocked.json`明确阻止交付。

已从正式catalog取到导致失败的完整记录，稳定ID形如`table/t_active_voice.tbl/group:5073/sequence:<sha256>/record:0/body`，带全部`table_rows`与`table_record_identities`。r6/r7拒绝规则只认`.../ActiveVoiceTableData/.../body`原始class前缀，而正式ordered producer已经换成group/sequence/record；模拟class key单测漏掉生产归类。修复按同一真实表资源族和完整body字段识别，保持segments/line片段不取得整句authority；不新增台词、词语、群组号或语言名单。

`voice-production-role-red.log`记录真实生产key形状的最小失败，green中38项相关回归通过。新增断言既覆盖冲突完整目标，也覆盖缺目标不能借片段；正式原PAC独立oracle仍必须通过。新标识r8，先从失败的繁中base建立完整生产模型、做独立原资源oracle，再扩到其余base/互换组合，防止首个EN组合正确再次掩盖本类失败。所有旧目录、模型与日志保留，DEV3现场没有改动。

新增缺语言负例还证明“另一条同文完整voice可用”不能填补当前identity缺失的目标。`voice-missing-peer-red.log`失败后，未知整条资源的source保留拒绝；`voice-missing-peer-green.log`38项相关回归通过。最终`python-regression-09.log`总648项、643通过、5跳过、0失败（104.970秒），其中已包括采集器3项。

r8正式包第一组改为繁中base、主日副简中。`final-dev5-r8/early-independent-zh-Hant/voice-independent-summary.json`直接读取原PAC的唯一scalar/actor/condition/voice peer：2428/2428资源或pointer合同成功，错误输出0（r7同配置3错误）；26个missing/multiple peer组仍拒绝，不猜配。global2224、pointer205有重叠，不能相加当分母；actual carrier／控件hook仍pending。这是第一组独立门槛，不代表剩余19组合或12入口完成。新组合（暖单语言事实）42.23秒、热读2.07秒；时间包含完整文件核对，仍不是UI→wire→resident ack。

### r8全矩阵门槛的新失败（候选冻结）

r8前14个组合构建/热读完成，首个繁中独立voice门槛和独立seed完整字节门槛通过。但西语base、主日副简中在生产script pointer编译中触发`Script pointer/catalog disagreement`，后续gate未运行。`candidate-dev5-r8-blocked.json`与`final-r8-remaining_models.log`保留精确失败；不以已有组合、首个voice或字节门槛替代全矩阵。仅在项目新诊断目录重放冻结包定位记录，未修改r8或运行中DEV3。

水泵旧截图描述对应原资源`script/scena/mp3010_01.dat/QS802_08_00/called84`。独立原SCP descriptor读取显示简中逗号属于第一行末，不是下一literal开头。r8 EN→JA→SC全模型渲染层也把逗号留在第一段末，第二段从“并询问”开始；此为离线模型观察，原生glyph宽度和当前frame未测，本执行者未见截图像素。

### 原资源代次改变的诊断与r9安全边界

`resource-epoch-change-r8.json`保存旧/新16个PAC的大小与mtime，旧catalog SHA为66755c3f…，新catalog为d852deee…。本执行者没有写游戏文件；变化来源未确认。冻结r8的独立重放经正常签名失效重建新catalog后成功，因此`r8-pointer-diagnosis.log`记录原失败未复现；不能把此当旧代次通过或臆断某条永久catalog错配。旧raw资源与当时catalog的差异也不计为当前可见漏译数量。r8全部既有包、模型、失败日志冻结，混合代次的矩阵不能验收。

新增通用resource_changed_during_preparation检查：catalog build/read、model input/read以及publication前后都核对实际PAC文件快照；严格raw/pointer错配仍拒绝，若资源已经改变则给出phase、changed_files及前后快照，并保留原异常上下文。不会清旧缓存、向运行中工具推模型或提前ready。此检查依赖现有大小/mtime资源版本；不能声称检测保留同大小和同mtime的外部篡改。新资源自身的单语言facts继续按完整文件SHA及生成规则SHA校验。

`resource-drift-red.log`保存4个新负例失败；`resource-drift-green-03.log`16项相关回归通过，含catalog、冷model、热读、写入中换代及严格pointer异常的归因。`python-regression-10.log`完整总654项：649通过、5跳过、0失败，107.819秒。JS与r6-r8完全同源码，184项回归证据沿用其精确SHA，不扩为实际窗口验证。新候选r9需重新打包并以一个明确资源代次完整回放；矩阵和每个独立oracle阶段前后再次核对同一输入签名。r9用户验收仍pending。
