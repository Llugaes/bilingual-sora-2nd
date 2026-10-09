# DEV5 r23 固定候选验收边界

r23 首次固定包独审结论为 NEEDS_REVISION；本次 rev2 在独立 `dist/comprehensive-1.0.0-dev5-r23-rev2/DEV` 封存，必须重新独审后才可部署。旧 r23 包和当前 r22-rev4 部署保留。

独审反例 `Recover 10.5% HP & EP/CP+10 before KO` 和 `mystery` 未匹配整数角色，却被旧 `%s` formatter 局部改写。rev2 从同一批已准入角色的 printf 字段派生整数参数形状检查，在完整严格角色匹配失败后记录 `unproven_effect_parameter`，并沿分段、普通 formatter 与最终渲染传播拒绝。参数捕获不能跨 native join、属性组或装备围栏；合法角色旁的独立未知纯文本仍保留。未知/空/畸形参数的标题完整保留，已知正文独立渲染；整数越界继续沿原硬拒绝合同保留原文。没有单词特判、强制 owner 或替换生产模型。

两槽位、着色/无色、三个最终模式的定向正负例见 `tests/test_r23_feedback_contract.py`；完整当前生产 wire 的 Node/V8 与包内复验见 `generated/r23-rev2-complete-production*.json`、`generated/r23-rev2-production-frida*.json`。候选 native revision 必须从实际 rev2 包的 CONTRACT 与 attach 脚本清单重算；它与最近现场 r22-rev4 resident revision 分开记录。真实 glyph/像素仍未验收。

r23 是独立候选，尚未部署，尚未通过独立候选审计。当前部署保留 r22-rev4，r18 与既有候选目录均未覆盖。此批新增截图没有取得完整 setter 原始字节、真实 glyph 或像素验收；下表中的资源回放与回调模拟不得作为实机修好的结论。

## 已确认的首失败与共享修复

| 反馈 | 原失败入口 | 候选实现 | 已验证等级 | 未完成 |
| --- | --- | --- | --- | --- |
| DEF/ADF↑、↑↑ 的 5 turns | kind4 双成员用原始 stat + LINK + icon + turns；原模板只覆盖单成员或带空格的 name | 按原始等参 forward scan 编译完整单／多成员构造，保留当前 EXE 的 I270/271/272 和无空格时长边界 | 实际 PAC 字段、当前 EXE 静态构造、完整三模式回放 | 实际 setter／画面 |
| All Stats↓↓ | type10／kind6 的方向参数未绑定 | 编译整个 kind6 家族，按当前 EXE 绑定 I267/268/269，未知图标不授予角色 | 实际资源＋完整三模式 | 实际箭头字节／画面 |
| Immunity | effect97.format 被当作孤立参数；相同颜色分段挡住完整 DEBUFF_CANCEL + LINK 构造 | 已验证免疫 modifier 和完整构造进入详情角色；只合并相邻同色 span，不剥不同颜色、字号、ruby 或图标 | PAC 精确 `Remove Debuff/Immunity`，整段与分色回放 | 截图的实际原串；`Cure Stat Debuff/Immunity` 不能冒充 native 拼接证明 |
| Upon Action / CP+25 | 已有 type1 数值角色，被装备括号、横线与分色遮挡；截图的 LINK 显示不同于资源 FORMAT8 | 外层装饰走同一完整角色解析；effect1016 整个数值模板绑定 LINK 显示变体，不拆任意逗号或翻译事件前缀 | 实际 type1 资源、精确逗号分色构造、截图 LINK 转录回放 | LINK 变体仍非实际 setter 采集 |
| Male Only／Female Only | 资源字段含尾空格；完整装备头未提取资格角色 | 资源前缀作为详情资格角色，覆盖括号内、括号后及括号前；保留原有冲突拒绝 | 完整详情三模式 | 实际 setter／画面 |
| 替身木偶 S/M/L | effect1046 type6 双数值合同缺失；正文尾空格变化使详情边界失效；无色头进入错误局部 recovery fallback | 完整 type6 单位独立绑定 HP/EP 百分比与 CP；描述的完整尾部 ASCII 排版空白别名只进入详情范围 | S/M/L/G 全族，10/30/90/100% 与 CP10/30/90/200，分色／无色头、原始／去排版空白正文、三模式 | 实际 setter／画面 |
| 所有已识别详情首行过低 | 原有 newline spacing 只改间距，不能证明 header 上移 | 对有完整已知正文的 layered 详情，在现有 layout_ready 中读取 quad 边界；只按实际碰撞＋用户间隔上提 header，正文基线不动 | 同一输入的 r22-rev4／r23 生产回调模拟对比；81 个字号／缩放／ruby／间隔组合；重复解析与关闭恢复检查 | 真实 glyph、窗口裁切与像素；多行 header、分离 widget 的未识别入口不据此宣称通过 |
| 英文存档章节、难度、`-角色` | 实际 save scope 使用严格子 translator；独立章节／姓名命中并不覆盖完整拼接 | 仅在已有 save ancestry 范围编译章节＋资源难度枚举、party prefix＋名字；允许存档写入语言与当前前缀语言的资源组合；保留等级与未知输入 | 严格子 translator 完整三模式；已存在原生 scope 回调回归保留 | 实际 save setter／像素 |

难度标题的官方 JA／中文资源仍使用英语，因此 r23 明确为六个资源枚举（Very Easy／Easy／Normal／Advanced／Hard／Nightmare）增加局限于存档显示的 JA／简繁中文标题。没有读写存档，没有改变游戏保存语言，也没有将这些英语短词加入全局替换。

## 原生与渲染证据

- 当前 EXE SHA256：`cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`。有边界的静态读取从已核对的 `0x34c454 / 488b5330` 开始，不把旧地址整体平移当证明。
- type6：当前 `0x34fa91` 先调用参数一 getter、再调用参数二 getter；effect1046 的 jump-table 指向 `0x352c44`（slot1），第二 getter `0x3531b9` 读取 slot3。G 档原始 slots `[1046,100,100,200]` 证明两参数不能合并。
- 资源 fixture：`tests/fixtures/r23-resource-constructors.json`。完整构造门槛：`tests/test_r23_feedback_contract.py`、`tests/check_r23_feedback.js`。正例没有预注入 item owner／key／scope；save 明确选择生产的严格子入口。
- 旧 17 个完整生产基线（含原始 null identity、native R、malformed R 与复合拒绝）保持三模式最终 plan 相同。外层新解析若与既有解析重建相同目标，保留已有锚点与分色位置。
- 完整新门槛包含 S/M/L/G 的两种分色和两种正文空白，以及严格存档资源混合语言；最终报告：`generated/r23-complete-production.json`。同一全量 wire 的 V8 报告：`generated/r23-production-frida.json`。
- glyph 模拟：`generated/r23-geometry-evidence.json`。它使用生产 callbacks 和模拟 quads，与已审 r22-rev4 原生代码逐场景比较；不是真实游戏 glyph。
- 未知图标、未知整数／CP字段、溢出、模糊复合角色、malformed ruby、同文异译仍保留拒绝或原文；不靠补充较短词条逃过完整合同的 veto。

## 缓存、封包与部署边界

r23 在独立输出根验证并复用兼容 raw catalog 与单语 facts。实际命中 3,135、miss 0、rejected 0；没有复制字体 receipts、agent／token 或强灌旧模型。最终目标模型为 JA 主／SC 次、EN 源、annotation，重新计算当前源码影响的模型，层次耗时留在 `generated/r23-production-receipt.json`。已有运行目录与用户缓存没有被打断。

候选目录固定为 `dist/comprehensive-1.0.0-dev5-r23/DEV`，与旧包分离；完整源、renderer、wire、native-agent、ZIP 的身份记录在构建报告和唯一原位交接 `generated/r19-execution-handoff.json`。封包 allowlist、模型 fingerprint 和 catalog 更新组均包含新增 `save_summary.py`，并使用包内解释器验证依赖闭包。

独立审计必须核对固定 diff、完整三模式、装饰边界、硬拒绝与 glyph 模拟依据后才可部署。没有启动／退出游戏、没有游戏 RPC／attach／第二 resident、没有热替换。V8 验证只使用自建隐藏 Python host。公开发布未授权。后续实机只需导航到仍失败的具体场景，不要求用户从头遍历全部页面。
