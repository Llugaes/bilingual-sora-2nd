# 1.0 综合阶段 9935：源码修正与 Git 合入阻塞

本轮已消费父提供的完整 canonical SHA `9935b79b3af0bd5b4b2fcf37291650800299423218a6902a89fe85483b48c925`，包括全部 13 类入口、P1 D1/D2、P2 D3、MOD/Physical、11:06 热修合入及 11:58 条件 DEV 切换授权。该 SHA 是父提供的消息身份；执行者没有把“阅读消息”记为“合入完成”。

## 当前可交接状态

- 仓库 `<CHECKOUT>`，分支 `main`，HEAD 仍为 `d62231fec5e11eeed79dfa201c8fe617c82d3587`。
- 实际可见策略为项目 `workspace-write`、网络受限/off、审批 `never`，并且 `.git` 有单独的 **read-only** 管理项。项目内唯一临时写入探针通过并清理。未修改全局设置、ACL、锁或 Git 数据库。
- 全部进入本轮时的脏改与未跟踪源码已封存到 `generated/dev5-system-audit-20261005/checkpoint-9935/`。初始 78 个文件，原始 binary diff SHA `20875b36c439e51235b4905dc147b06c052bc9c1b7f6e0f351252587134e5ab0`。历史候选和生成证据在原位保留；受限字体缓存未遍历、读取、复制或改权限。
- 已实际 `git bundle verify` 验证父交付的 bundle，阅读并保存三份精确 patch 及 SHA/hunk/脏文件交叠清单。**未 import、stash、cherry-pick 或创建 commit**：`.git` 只读阻止该路线开始。没有实际冲突；交叠文件只是将来可能的冲突点。
- 要合入的顺序仍是 `1a9c126e4e66f453fb18050077f5ed29fb96d45a` → `ffdc7c0ba2a9755bff72865a65a3c71a38cb1441` → `45666d4a823e87f79755b4bc77e523f923c8446c`。原 commit 到 1.0 commit 的映射目前均为 `null`，详见 `stage-9935/hotfix-integration-status.json`。
- 本轮没有新最终候选/ZIP，没有启动候选 UI、backend 或游戏，也没有操作用户当前 0.4.3 工具/偏好/存档。旧 r12 与 DEV3 均保持。条件切换前提未达到，**不能切旧 r12 或 DEV3 代替新候选**。

## 本轮实际源码修正

### 拒绝传播、owner 和有类型缓存

`runtime_text.js` 与 `menu_text.py` 统一检查完整效果分区。不同分区产生不同主/副完整目标时，或预算/空成员违反合同，拒绝须传播到 `component`、带 description 的 `translate` 以及最终 `render`，旧贪心 fallback 不能复活它。具有独立准入的完整资源配对仍可保留。只有部分成员被识别不等于整串已属于效果语法：它不会被扩大为全局硬拒绝；未知片段继续保留，无关标题及合法颜色分隔保持原行为。

`render` 先通过原有 key/scope 匹配取得合法 owner 完整配对；只有分段重构在主文与副文两侧均与 owner 完整目标一致时，才采用逐效果单元。否则沿用 owner 的完整排版，保留颜色、原生 ruby 和真实硬换行。整数 format key 仍用既有 canonical 验证，陈旧/错误 key 不授予 owner。

翻译与 render 缓存键改为有类型的 JSON tuple，避免无上下文 `null` 与合法字符串上下文 `"null"` 碰撞。

先在冻结 r12 的真实 JS 上，用正式 Python 编译器生成的合法独立反例复现三个失败；修正后 Node 及自建隐藏宿主的真实 Frida V8/indexed wire 均通过。V8 宿主正常退出，仅附加本轮自行创建的 PID，未枚举/附加游戏。反例是独立解析器/编译器证据，不是游戏画面或现场 source/key 证据。

### MOD 字体间接依赖

静态逐指令比较后发现，MOD 的 font hash helper 与既有语音样本仅有 CRC 常量表 RVA、CRC 尾函数 RVA 差异；reader helper 另有 `GetCurrentThreadId` IAT 槽 RVA 差异。寄存器、对象字段、控制流与缓冲合同不变。新增两个精确函数变体，保留原掩码，没有扩大掩码覆盖寄存器、常量、字段或分支。

新增间接依赖校验：CRC 表必须处于完整可读、不可写区间，1024 字节内容摘要一致；间接尾函数按审查的 41 字节边界、原 RIP 操作数掩码及同一 CRC 表关系校验；reader IAT 必须唯一绑定 `KERNEL32.dll/GetCurrentThreadId`。历史语音变体也保留同样的数据/IAT依赖，防止旧精确 helper fallback 接纳非法地址。数据/导入依赖参加同址变体语义比较，无/多候选与不同语义仍拒绝。没有整 EXE/hash/版本/section 放行名单。

MOD SHA `9676f7cf63ededd1e37bb86b0d0a4dbf37539ff577ff2d6d38baa0453aefa871` 仅作证据身份。实际生产静态链对 MOD 和既有语音样本各接纳 67 native 点；17 种危险变异各在两个样本上拒绝，合计 34 次拒绝。当前官方与历史原版 EXE 也通过原关键合同正负回归。没有安装或运行 MOD；EXE 静态接纳不等于完整资源兼容。

### 内容身份与缓存失效

目录顶层资源身份原先只有名称/大小/mtime，同大小且恢复 mtime 的内容变化能复用旧身份。本轮先保存失败测试，再把 script/table PAC 内容 SHA 加入 snapshot；读取前后 stat 变化拒绝，读权限拒绝不会当缺失或 ready。所有原有 catalog/model 输入、读取及发布 guard 使用这一身份。单语言事实仍按本语言原资源内容 SHA 与实际规则代码身份缓存，不缓存主副配对决定。

这是内容校验与前后 guard，**不是原子文件系统快照**。更改发生在构建/发布边界时必须拒绝并从一致输入重新生成，不能用 mtime 或旧缓存命中证明新版验证。

当前 16 个 PAC、11176 个成员保存了逐内容 SHA，采集期间每个 archive 前后校验一致。集合 SHA `2f4352f5c21448c226f644c29a6599e25a4676721c099dd49d572ea06535ffe9`；官方 EXE 实际重读 SHA `cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`。版本 1.4.0.0/build25721473 引用父的静态版本观察，不冒称本轮进程内重读。

离线 content snapshot 的三个测量为 0.370/0.378/0.370 秒（741162143 字节）；OS 页缓存未清，不能称冷磁盘、完整 Swap 或按钮→resident ACK 耗时。热模型 guard 有 fingerprint 和复验两次读取。r12 的冷/热模型指标是旧源码测量，不能作为本轮最终包/真实 Swap 达标证明。

## 13 类范围与证据缺口

下列 1–12 类旧生产包/资源回放在 r12 留存。本轮没有把旧矩阵重跑计为新增成果，也没有把源码单测或同源 expected 当现场验证。最终同包、同源码 hash、当前内容身份的三语言及八 base 回放须在热修真实融合后更新；现场 raw input/key/scope、动态值和控件 hook 尚未采集的地方继续 pending。

| 类别 | 已有/本轮依据 | 仍缺的显示入口证据 |
|---|---|---|
| 1 对白、active voice、Joshua、爱娜 | 保留 r12 正式资源与控制/动态拒绝；本轮未改此链 | 实际 source/key/控制变量值；新候选现场复验 |
| 2 效果独立语义单元 | 本轮 D1/D2 修正拒绝传播及 owner 优先；等价完整目标才能拆分 | 真实原生 formatter 输入、各单元锚点/宽度和画面 |
| 3 HP/CP Regen | 保留资源角色/颜色包装与完整模板边界；既有相关 JS 回归通过 | 用户所报真实入口的新包回放与现场 |
| 4 获得/交付等通知族 | 保留 r12 opcode/参数槽/完整模板准入，不补动词 | 原生复制/图标/format key 及真实动态物品值 |
| 5 料理属性增减 | 保留目标/属性/数值/颜色槽模板合同 | 对应控件是否通过已审 formatter |
| 6 范围、分类、Physical | 当前八语言正式 table 重新解析；找到两条完整 `SkillTextArrayData/format`：EN `[Physical%s - ` 对应 JA `【物理攻撃%s／`、SC `【物理攻击%s／` | 截图 `[Physical]` 不等于这两条 formatter 的已确认输入；截断/复制/控件未定位，不作词补丁 |
| 7 同 item 多入口 | 保留稳定 item 资源身份及列表/owned 配对边界 | 已装备槽/列表等真实控件 carrier 差异 |
| 8 条件复合效果 | 保留条件/增量/回合构造器；本轮拒绝传播不再任挑分区 | 真实条件值、formatter 与画面 |
| 9 action/确认按钮 | 保留固定按钮资源及同名异义拒绝 | 真实按钮控件 hook/key |
| 10 脚本交互菜单 | 保留完整生命周期、分支/字节码/重复区域拒绝 | 真实菜单复制/截断与动态值 |
| 11 战斗即时提示 | 保留即时文本/颜色/图标片段资源回放 | 实际控件输入与实时入口 |
| 12 概率/大小/状态混合效果 | 保留 slot/状态角色；本轮 D1/D2 完整身份和分段合同 | 实际概率/大小槽及最终主副单元 |
| 13 MOD | 本轮静态 EXE 67 点接纳、34 危险变异拒绝；松散资源比对留存 | 未安装/执行，modified/extra 松散资源配对及所有真实入口未验 |

MOD 松散 `script_sc/table_sc` 共 889 文件：4 同路径同内容，238 同路径内容不同，647 当前官方 PAC 没有同路径。此分类不推断 MOD 何时覆盖，也不将额外 AI/动画文件误称显示文本。逐文件身份见 `mod-resource-comparison.json`。本轮普通用户新缓存首次自动准备、三主题真实窗口、UI→prepare→publish→wire→resident ACK 与实机帧时均未测试。

此前 QA 的缺口仍成立：EN 主/JA 副和同 translator 生成的部分 expected，不能覆盖 EN base→JA 主→SC 副、逐效果单元、owner/拒绝 fallback 与多显示入口；静态词库完整不能证明 hook、参数或截断入口覆盖。

## 本轮验证结果与证据

证据根：`generated/dev5-system-audit-20261005/stage-9935/`。

- `authority-frozen-r12-red.json` → `authority-worktree-final.json`：D1/D2/D3 失败→通过；`authority-owned-v8.json` 为真实 V8/indexed wire 三例通过，宿主退出码 0。
- `python-scoped-final.log`：92 运行、92 通过、0 跳过、0 失败（配对/效果/内容 cache/native contract/language facts）。
- `python-preserved-features-isolated.log`：108 运行、108 通过、0 跳过、0 失败（EXE/config/settings/overlay/update）。先前两失败由测试全局 UI 语言泄漏造成，新增 setUp 保存/恢复，不修改生产行为或用户配置；原失败日志保留。
- `js-scoped-full.log`：192 通过、0 失败，包括八个新增 authority 用例。
- `mod-font-production-negatives-v2.json`、`official-voice-negative-regression.json`、`old-original-negative-regression.json`：纯静态真实 PE 生产链，不执行二进制。
- `content-cache-red.log`、`content-resource-epoch-after.json`、`content-guard-cost.json`：内容身份失败→修复、实际输入及规则文件 SHA、离线 guard 成本。
- `physical-table-identities.json`、`mod-resource-comparison.json`：稳定资源/语言字段及 MOD 差异，显示入口 pending。
- Ruff 已检查本轮相关 Python 源码/测试并通过；最终 read-only Git diff-check 和源码/证据 checkpoint 另存交接收据。

这些是源码、离线资源和隐藏自建宿主层级。没有新最终包验证、普通用户自动启动或用户实机通过；不能标“完整 1.0 候选可验收/已发布”。

## 下轮最小恢复步骤

1. 父通过正式 workspace 权限设置恢复**仅本仓库 `.git` 的所需写权限**，沿用网络 off/审批 never/唯一 writer；不改 ACL、不绕锁、不新增 Git DB。此前保存的 bundle 无需联网。
2. 原线程再次核实策略，保存本轮最新 source/evidence checkpoint；按三 commit 顺序 import/pick，自行融合已列交叠，保存实际原 commit→1.0 commit 映射/冲突与最终 diff。保留本轮效果/owner/cache/MOD修正与全部 1.0 UI 功能；不能取 0.4.3 整包覆盖。
3. 真正融合 owned font 完整性/完整 runtime 字体链及默认 external no-gamewrite；当前旧 `auto_connect.py` 尚有 apply/install 路线，**未声明默认零写入已完成**。版本/UI/update/manifest 保留真实 1.0 DEV 身份，协议版本另记，不降成稳定 0.4.3。做与合入冲突相称的 67 点/诊断行号正负例、游戏有/无/退出/重连与无 ownership receipt 写入回归。
4. 使用未占用的新候选 ID；保留 r12/历史包，逐文件验证并记录新源码/包 hash、当前内容集合与 cache 规则身份，做最终同包独立 oracle 回放。普通用户缓存由普通用户正常生成，不能携带受限 sandbox 私有字体缓存或改 ACL。
5. 前置条件均真通过后，已有授权允许正常单连接切新 DEV1.0，无需再问一次正常切工具许可；先备份**切换当时最新** 0.4.3 语言/显示/热键偏好。旧 UI/backend 正常退场，保留游戏优先，不安装字体/写 game。resident revision/immutable 不兼容时只报告需要正常退出重开游戏的最小步骤，不热卸、叠加、强杀或静默重启。
6. 用户对这一精确新候选亲验之前，1.0 不 push/CI/tag/公开发布。MOD 真实进程另需父给出明确样本与安全窗口授权；不能把 P0 0.4.3 用户 OK 转移到 1.0。
