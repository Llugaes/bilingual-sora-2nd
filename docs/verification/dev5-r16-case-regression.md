# r16 逐案例证据对照

本表记录用户已报告的案例，不能由总通过数替代。资源、模型、模拟原生回调、实机像素是四个独立层级。r14 源为 `d7d98f057470dab766333f4fbe719749e24b2f38`，本轮继承 r15 `96d546fbaa482f28a3e5ca57d5fe55e0709ced7e`；未重跑无关大模型矩阵。截图像素由父线程看过，本执行者只记录父提供的现象。

| 案例 | 实际入口／首个已知失败 | 本轮改动与证据 | 尚缺的实机证据 |
| --- | --- | --- | --- |
| 1 对白／主动语音／Joshua／Aina | script 调用身份、ActiveVoice、日志分别有合同；现场变量帧未知 | 继承 r14；本轮未改 | 🔴 每个实际入口的原串、调用帧和像素 |
| 2 独立效果单元 | description 头准入与无正文成员分段是两条链 | 继承 r14 细分方案与冲突拒绝；本轮未改 | 🔴 无正文／有正文实际控件分母 |
| 3 HP／CP 效果 | name/stat/turns/value 的角色、着色与共享参数 | 继承 r14；本轮未改 | 🔴 组合行、颜色、注音锚点 |
| 4 获得／失去／交付／奖励通知 | ITEM_SUB_MESSAGE helper 家族提取遗漏已证；VM 输出→label 身份未知 | r15 `a10c025`；29 producer、261 实例离线通过 | 🔴 Monster Bird Meat 等实际 producer 与最终 buffer |
| 5 料理属性／数值 | 类型化 formatter 已编译；不能用标题成功推正文 | 继承 r14；本轮未改 | 🔴 实际数值／槽／label 路径 |
| 6 All]／范围／图标 | SkillRangeHelpData，完整 controls 与 opaque 图标 | 继承 r14；本轮未改 | 🔴 裁图之外的完整原串 |
| 7 Heal 同物品跨入口 | 同名跨 item；必须有各控件的 item identity | 继承 r14；本轮未改 | 🔴 列表、装备、详情、提示、快捷槽分别验证 |
| 8 白银之盾／条件复合 | 完整准入与独立成员不同；条件槽／增量 icon | 继承 r14；本轮未改 | 🔴 空正文入口和实际条件组 |
| 9 Enhance／Synthesize／Cancel | resource YES/NO key→栈 printf→现有 copy setter；原资源指针与动态 key 未随栈字符串进入 label identity | 整族7原始 key、八语 payload、65小配置455最终render通过；两个已验证 caller 暂缓即时翻译，owned copy 校验后带实际 key；生产 VM、真实隔离 Frida 和三 EXE 负例通过 | 🔴 新候选正常游戏进程中的两按钮、排版与模式复用切换 |
| 10 Check new recipes／Verify Crystals／Quit | script group15/menu_additem，非对白 group5；实际 label 载体未证 | 原资源完整字符串包含方括号：`[Check new recipes]`、`[Verify Crystals]`、`[Quit using terminal]`，同菜单另有`[Yes]`／`[No]`。五项在精确r14已缓存模型与本轮完整模型均正确；首个现场失败尚未定位，不凭脱括号截图改模型 | 🔴 实际完整原串（含缩进/控制码）、physical option/region、复制来源与实际加载模型版本 |
| 11 Back／Side Attack Bonus／Impede | 即时战斗提示消费边界未知；同文效果表不能证明 toast 来源 | 继承 r14；本轮未改 | 🔴 实际即时入口的调用与原串 |
| 12 附加状态／概率／Resist | effect98/type10 的 ConditionInfo 列表角色；全局同名拒绝使参数仍英文 | r15 `a10c025`；51 名称、64 小模型、57,600 render 与 384 负例 | 🔴 完整输入及逐状态输出像素 |
| 13 换行／长注音／水泵对白 | 完整句准入、native wrap 与注音几何分别验证 | 继承 r14；本轮未改 | 🔴 实际宽度、热切换与长句 |
| Balstar Channel／Saint-Croix Forest／Le Locle 地图 | map_spot scope 只选 SpotData，AreaData 漏入；资源齐全 | r15 `a10c025` 全 mapjump name 族；八语 572 物理名称与模拟入口 | 🔴 地图列表实际 scope/path；Le Locle 对照 |
| Tips 8 标题及正常对照 | Tips 全局与演员／地图／物品冲突；原始 ID、catalog 与 table 模型均齐全；原生消费后拥有字符串，现场 table identity 未命中原因未知 | `4e9dc06` 完整 Tips＋HelpTitle title scope；344 物理标题、65 小组合、39,149 render、108 同族冲突拒绝；复制回调／ownership 移出恢复模拟通过 | 🔴 Tips 列表、详情的实际 label ancestry、setter identity 与像素 |
| 地图登录 Zeiss Central Factory | TXT_HUD_ADD_MAPJUMP_SPOT 参数来自 MapJumpSpotData+16；既有确认派生器漏掉 HUD 模板，通用%s保留英文名 | 本轮共享 formatter 派生器涵盖确认与通知；540 物理 destination、65 小组合、20,930 render；65 未知名称拒绝及缺语言／同族冲突负例 | 🔴 notification 最终 label 路径／副文参数 |
| 书籍青色 Book List 提示 | 完整有色字段可解析；裸提示分段无身份准入 | 🔴 r15 只提供有界诊断，没有按句放行 | 🔴 setter 的完整原串与实际分段 |
| 书籍 Volume 1 正文 | 原始正文有两个不同 item owner；各 owner 模型正确，无 owner 拒绝 | 🔴 r15 维持 item 歧义门禁 | 🔴 真实物品 ID／description→label 身份 |
| 用户主副语言偏好 | 每游戏会话默认同步覆盖选择；旧快照并发覆盖 | r15 `9c13fc9`＋`a10c025`；全八 base、旧持久化、重连与共享锁交错离线回归 | 🔴 正常 UI/game 重开、换 base、重连 |
| 044 更新通道／首次闪退 | DEV 稳定升级门禁与首次 frida-agent.dll 崩溃是不同问题 | r15 精确合入 044；DEV 下载／安装前拒绝稳定覆盖 | 🔴 首次注入崩溃根因仍未知 |

标题原始布局采用该资源的真实 serialization keys 103/342：`list_root/item_template/text`、`list_root/tab_root/item_template/text`、`tips_contents/title`。tab_root、不同 layout、错误父节点、HelpPage、同族缺语言／不同目标皆拒绝。ownership 检查仅限最多12祖先的父指针、name pointer 和登记 layout ID；移出登记树即取消 scope，移回恢复。dirty-owned 写会更新原串并清除旧 script/table/book identity，清洁帧没有新增 UTF-8 读取。

本轮可复查证据在独立 clone `generated/replacement-r16`：`title-name-audit.json` 的 51,062 非空原始字段仅证明有界20族 literal 覆盖，不证明跨语配对或实机入口；Tips 的全 metadata／resource selector／condition array 独立 oracle 与所有语言 payload multiplicity 已单独验证。`help-titles.json`、`tips-node-paths.json`、`map-notifications.json` 保存更强的各自族合同；不能将这些层级合并为“全部已修”。

静态解释更正：开发期旧官方 `set_text` RVA 为 `588a40`，生产合同在当前官方恢复为 `5892c0`，语音样本为 `588720`。当前 `5892c0` 并非遗漏的新 setter。商店确认的确定失败是原始资源 key 经过栈 printf 后没有传给该 setter 的身份链；Tips 不能据此归因为 hook 缺失。dirty-owned 回归测试的是未观察的原生／内联写入机制，不声称当前某条 Tips 路径必然绕过 setter。

## 商店动态资源身份合同

原生 owner 的596字节函数体保留模式0..5、trade/create谓词、实际资源hash、YES/NO label字段、内部控制流与目标关系。整族包括 Buy、Sell、Generate、Trade、Customize、Create 与 SelectNo；Create/Generate 虽同为英文 `Synthesize`，目标语言不同，必须以实际动态 key 区分。运行时不按这些显示词匹配入口。

两个 post-copy 点复用现有生产 `set_text` 合同；仅两个精确返回 caller 使用 sourceOnly，复制完成后从 RDI 取 label、RSI 或 R15 的无符号低32位取 hash，核对当前原资源与 owned 字符串、无动态printf参数且UTF-8不超255字节。保留字符串身份，不保留栈指针；翻译仍由现有 Update 负责。未知hash、转换参数、截断、source不符都拒绝。动态身份域在拒绝、外部重交display或owned写变化后仍禁止旧`+2ec`布局key回退；新的有效原生证据可恢复身份，Destroy结束该域。

地址掩码带明确约束：YES/NO lookup manager恢复同一个具名全局地址并验证唯一性、对齐和映像区间；bounded formatter的strlen、copy、options及printf engine是有界直接函数合同，CPU flags和options的RIP读数有全局关系。CRC32表是1024字节必需只读常量，正文匹配不替代数据验证。共享解析器在导入无PDATA叶候选前拒绝不可恢复的常量/IAT失败，防止固定点重复加入已拒绝叶候选；拒绝仍报告根依赖。

独立复审的四个身份反例和三个PE单字节反例均先红后绿，证据为`independent-identity-red.log`／`independent-identity-green.log`、`independent-contract-red.json`／`independent-contract-green.json`。常量叶循环另有`leaf-data-red.log`／`leaf-data-green.log`。最终169项定向Python回归通过（4项既有跳过）、173项生产JS回归通过，三份EXE的99危险变异全部拒绝。真实Frida V8只附加本任务新建隐藏宿主，7项执行实际Win64寄存器、原生printf、owned copy及生产renderer，未执行游戏控制器或游戏排版。

完整EN→SC/JA MenuTranslator另回放35个实际原资源案例：精确r14缓存21项失败，本轮完整新模型0项失败；其中终端五项在两者均通过。该结果是模型层，不能视为终端、Tips或书籍的现场身份已经证明。整族标题和地图的小配置检查只围绕本轮改动，没有重跑无关全量矩阵。

后续由父线程安排候选切换后，在新游戏进程使用既有默认关闭、最多64label／每label12table事件的诊断。对Tips与终端记录同一次setter的完整source、input/caller、table候选拒绝原因、最终key/scope/node路径，并连同resident revision和模型SHA保存；若只有owned_update，明确缺失setter provenance。书籍另须真实item owner与分段，不借其它同文条目放行。当前游玩进程未开启诊断、未attach、未替换resident。首次044 frida-agent.dll崩溃根因仍未知。

## 候选包校验

第一轮`b28438f`包的最终包内预检发现显式发行清单漏了新增`shop_contract_data.py`，该失败包已经隔离，未交付或运行。发行清单与UI/resident更新归属已补齐；既有架构覆盖检查先红后绿，相关打包／更新18项回归通过。DEV打包器另使用候选内置Python直接导入完整生产合同，避免文件SHA正确却缺导入依赖的包被报告成功。最终包以`packages/candidate-package.json`的精确source_head、ZIP SHA、ROOT及运行库关联为准；历史失败包不可使用。r15历史ZIP保持原SHA。
