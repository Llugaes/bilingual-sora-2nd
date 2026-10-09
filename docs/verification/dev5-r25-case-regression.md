# DEV5 r25：公共翻译入口修复候选，实机未验收

从 `replacement/dev5-r25` 的 `b4badc9d3234366ae53395cac99cb410bcc6b8e3` 接续旧 writer 的四个生产文件及测试/审计脏改，原文件、未跟踪夹具和原始差分完整保全。没有 reset、重启旧 writer、改运行 r24、附加游戏、替换驻留或公开发布。此候选保存已修公共入口；仍有 **93 个输出缺口与 1 个角色缺证**，书籍和名称的实际 identity 工作继续。

## 已修源码与准入边界

共同三模式入口处理真实资源的 Recovery/Single/Book/Material 分类提示及 Revive、Heal(S)、Shield、Remove Debuff、Self/Hate 完整构造式。type12 空 stat 字段仍保留类型分派；SELF 整个常量缺席兼容旧最小目录，但存在且目标语言缺失仍拒绝。方向与仇恨强度由原生有限参数域、八语字段和实际分组构造，不依赖显示词白名单。图标、控制码、数字、动态参数及顺序保持。

真实独立槽组编译 `native_mixed_effect_sequence`，完整数值加字面效果字段可以越过内部 CP/EP Regen 的参数标签同形冲突；内部标签本身没有获得新角色身份。`member_sequence` 保留旧成功的成员分段；空正文由整个原生槽构造式负责。明确 whole-constructor veto、整数溢出、非法方向、未知控制及畸形 R 仍拒绝。拒绝标题不拖累独立已准入正文，随后行的 whole veto 仍优先整句拒绝。合法原生 R 字节保持，外侧已编译效果只用其自身合同；XYZ reading、无正文、畸形 R、整句冲突均有最终入口反例。

## 独立分母及结果

物理实体 **1797**：835 其他物品、419 装备、128 回路、72 魔法、343 其他技能。保留全部 804 上下文（422 完整、382 未知）、5511 物理输入、3986 独立输入及三模式。原串回放未注入正向 key、scope 或 owner。

| 回放 | 成功 | 原文保留 | 差异 | 宽度等价 | 渲染缺口 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 保全的原始 oracle，旧 stage5 基线 | 5406 | 77 | 27 | 1 | 105 |
| 当前产品，原始 oracle | 5412 | 71 | 27 | 1 | 99 |
| 当前产品，独立 Absorb 顺序校正 oracle | 5417 | 71 | 22 | 1 | 94 |

产品实际修好 **6 个恢复组合**（SkillParam 233/234/237/238/245/246）。5406 个旧成功及 1 个宽度等价输入的三模式完整计划逐字保持，含 annotation 层、offset、semantic ID 和参数。旧 r23 的 91 个完整生产案例也三模式零差异。

另外 5 个 Absorb 是审计 oracle 校正：当前 EXE 的 kind11/12 在 `34d6cf/34d6d9` 跳同一 `34eaf5` 分支，`34eb96` 在最后 stat 后追加 format。原审计器英文颠倒为 `form + joined`，已纠正为各语 `joined + form`。原审计器、5511 原包和首 stage5 receipt 保全。只改变 5 个完整输入及 2 个未完整上下文的 header 文字；所有实体、分类、计数、1851 合同 gap 的 ID/reason/order 不变，零删项。这 5 个校正不能算产品改善。

校正后的实际表面分开核对：list 1631 成功/30 原文/1 宽度；body 1457 成功/23 原文；category header 694 成功；category detail 672 成功/22 差异；effect detail 422 输出成功但其中 1 个 DEF 角色未证；equipment slot 529 成功/18 原文；hint node 12 成功。**1851 合同缺口与渲染缺口重叠，不能相加成另一个分母，也不能删掉。**

## 已运行验证

- 9 组当前源码回归 **72/72**，Python 模块和 JS 子进程均核真实 repo 绝对路径与 SHA，未误用 embedded r24 源码。
- 原生回调模拟 **149/149**；首行相对 r24 约下调 4.58 px，正文 baseline 保持。模拟不证明实际 glyph/clip/像素。
- 当前完整模型重新编译；只复用已验证兼容的 raw catalog 与 3135 个语言事实（0 miss/0 reject），未拿旧模型为新源码背书。
- 当前 Node 5511×3 及自建隐藏 Python 宿主的原生 **V8 5511×3 完整计划一致**；正确 Hate 字段非法强度、溢出、畸形 R、未知控制反例通过。只附加自建宿主，game_attached=false。
- wire 183705912 bytes，SHA-256 `f4b3c81bebd7754eb33dfedcc38cb77e2887ce4793410c41d27c060f332b2666`；RuntimeText SHA-256 `1c68a0e598d7b528cde83971562a6b014312fb930768fe7b4b5f4146693b3164`。

关键证据：`generated/r25-stage5-final-verified-source-guards.json`、`r25-stage5-qualified-{original,corrected}-producers-final.json`、`r25-stage5-qualified-prior-success-differential.json`、`r25-stage5-legacy-complete-production.json`、`r25-stage5-production-receipt.json`、`r25-stage5-production-frida.json`、`r25-stage5-oracle-order-correction.json`、`r25-stage5-reviewed-production.diff`。所有结果均非游戏实机成功。

## 剩余 identity 与最小下一步

93 输出为 **44 书籍 + 48 名称 + 1 Move 正文**；另 1 个 DEF 角色证据未闭合。22 本书各有 description 和 category_body 两个输出；11 个英文正文组每组两条真实记录的 JA/SC 不同。实际 model 的两个 description 候选拥有不同资源池偏移，既有 `TableIdentities.select(input_pointer, source)` 可在实际 setter 直接传字段指针时，通过文件 header/pool、完整 masked record、field pointer 和原串验证区分。**未观察到对应实际 setter 输入，不能把存在候选算 44 输出已解决。**

22 个拼接 category 输入全部没有直接 table-field 候选。缺环是：物品详情 producer 选中的真实 ItemTableData record/field → 共享分类与正文拼接/复制 buffer → setter 入参这一链中，选中记录身份在复制后如何仍被证明。下一步由同一 Sol 继续现有 setter/caller 静态链，证明实际 caller、记录来源及生命周期；只接受完整原串和该记录关联，不能按书名猜正文 owner、按共享 selector 猜记录或另加游戏 hook。

48 名称为 list 30 与 equipment slot 18。既有 `item_name` scope 仅从完整 `t_item.tbl/name` 编译；native 结构入口包括 `name` 节点的 `item_template` 祖先及既定 layout36/quartz 名称链。资料中的唯一物品目标不证明这些 48 个实际控件走了该结构入口；普通 skill 列表与装备槽实际 node/path/layout、输入 source 和记录关联仍需证据。分母继续无正向 scope；不能把 body 成功当 list/战斗/槽位成功。

## 候选与验收

独立标签 `1.0.0-dev5-r25`，目标 1.0.0。正常只读验证历史 r14 真实 `dev-manifest`：source `d7d98f...`、runtime `bac6e42e94e62356`，552 个运行时文件全部摘要一致，aggregate `abf98b97e7ae210ea8f930cb7727caca4e7aaa0cfb8987e9b3b227d1e09d2f55`；未写旧树、用户配置、存档、字体 receipts 或 agent token。精确 commit/ZIP/包内核验以独立目录的 `packages/candidate-package.json` 和 package V8 receipt 为准。

父线程先审固定候选与剩余清单，再决定切换时点。未审不部署；新正常游戏进程实际 setter、菜单/战斗/装备槽/列表，以及首行 glyph/clip/像素仍待验证。新字体调查和远端 hotfix 合并另行处理。本页是已修公共入口的候选记录，不是全部文本修完或正式实机验收。
