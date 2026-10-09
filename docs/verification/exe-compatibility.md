# EXE 兼容检查与连接失败提示

2026-10-04：本轮候选改为按实际原生依赖定位。DEV4 已获用户实机验收及 0.4.2 发布授权；后续候选仍须独立实机验收。没有正版／破解、DLC 授权、补丁名称或整个 EXE 摘要白名单。

## 检查范围

运行时入口为 `hooks.verified_target_image` → `exe_compatibility.verify_image` → `native_contracts.resolve_native_contracts`。同一次文件读取产生诊断摘要、定位结果和 hook 指令快照。

- 不比较游戏版本、整文件哈希、整个代码／数据段、入口地址、时间戳、资源、证书、调试信息或未使用函数。SHA-256 只用于诊断标识。
- 用 PE 的 x64 异常目录枚举候选函数；无关的坏记录不会阻止已用函数定位。只匹配工具调用、拦截或读取的原生函数及它们的 CHAININFO 续段。无异常目录的叶函数从已验证调用关系定位。
- 模板保留指令、寄存器、字段偏移、业务常量及函数内分支；归一化地址操作数。0.4.3 另归一化四处已审查日志诊断调用的源码行号参数，并显式验证诊断函数及对应 CALL 关系，见下方热修记录。多个调用者共同消除重名函数歧义。函数整体迁址无需新增 EXE 版本名单。
- 所需 manager 指针与两张虚表从对应 RIP 引用恢复；检查实际读取范围、对齐和类型身份。读取操作不要求所在区段必须只读。普通游戏内部调用不扩展为整个传递调用图的校验。
- 字体入口被搬到跳板的变体还校验该入口的续接体、参数／返回合同及必要的路径 helper；不能只 mask 跳转目标后直接接受。只要求当前函数变体使用的延续体，不要求原版具有语音 MOD 的 helper。helper 以“映像基址 + RVA”访问游戏例程、数据表或导入槽时，该 RVA 同样按地址操作数归一化，并分别校验例程自身摘要、与例程读取的表相等、导入目录中的库名和符号名，见下方 issue #1 记录。
- 连接前，仍将上述磁盘快照与进程内原生接管位置的16字节逐一比对（r16在既有67点上增加2个商店copy提交点），在任何适配器、原生调用或hook安装前完成。文件读取器保留磁盘函数合同，但不要求运行时入口保持原始字节：工具自带的松散资源加载器会在该入口安装detour，字体桥应通过这个现有入口调用，而不是拒绝或覆盖它。这项检查防止定位结果与当前进程不符，不是未知EXE的唯一兼容证明。
- 旧文本 Capture 功能有自己的六处调用签名，只有选择 Capture 才验证；它不再成为正常双语连接的前置条件。
- 局部函数确实改写了参数、对象布局或必需语义时，需要扩展该函数合同。不能保证任意修改都兼容，也不以一个“继续连接”开关跳过实际依赖。

`tools/build_native_contracts.py` 是开发期模板编译器，用 Capstone 从经审查样本编译函数摘要、地址掩码及关系。安装端只依赖已有 pefile。内置 `native_contract_data.py` 不含游戏机器码；其中样本摘要和开发期 RVA 是证据出处，不是运行时放行名单。所有合同变化参与 resident revision，新候选须新游戏进程加载。

`tools/build_shop_contracts.py` 另编译r16商店窄边界，三个已审查样本须有相同归一化合同。只增加两个post-copy接管点，复用现有setter。必要printf直接helper、资源key字面量、CRC32常量表、lookup manager及RIP关系参与校验，不递归整个调用图。无PDATA叶的不可恢复常量/IAT失败在加入候选前拒绝，避免固定点反复加入无效叶。独立复审七反例与99磁盘变异见 [r16案例记录](dev5-r16-case-regression.md)。

## 0.4.3 官方更新热修

Steam app 4225980 的 build 25721473 已完整安装；新版 EXE 1.4.0.0，长度 13,470,208，诊断 SHA-256 为 `cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`。0.4.2 的生产预检实际拒绝 `log_write.body.chained[0]`，并传播到对白和日志调用者。热修基于公开 v0.4.2，而不是尚未验收的 1.0 工作树。

对照旧官方与新官方的实际 PDATA 函数，四处非地址差异均为诊断源码行号。记录结构、拷贝长度、flags、寄存器、业务常量及内部跳转未变：

| 函数 | 行号立即数相对函数起点 | 旧值 → 新值 |
|---|---|---|
| `log_write_commit` | 729 | 0x64B → 0x656 |
| `log_record_bind` | 809、1582 | 0x6C4 → 0x6CF |
| `log_rows_build` | 1281 | 0x6C4 → 0x6CF |

`log_write` 还完整验证 `log_write_commit` 所在的 CHAININFO 续段，因此行号 729 的同一参数在两个模板中各有一份掩码。实际新增掩码共五份，覆盖四个调用点；没有删除旧掩码或放宽整段。

开发期仅在这三个已审查函数中识别连续的 `LEA R9`、`MOV R8D`、`LEA RDX`、`MOV ECX,3`、`CALL diagnostic_report`。只有 R8D 的四字节立即数可归一化；操作码和寄存器仍参与函数摘要。新加入的 140 字节诊断函数依赖必须在 PDATA 中定位、通过自身摘要及 caller 关系校验。该函数在 ECX=3 路径使用原行号前先以 0x7FE 覆盖 R8D，并清零 RDX，因此这四处行号不参与双语业务。新旧官方与已支持语音样本的诊断函数归一化合同一致。

这降低了诊断源码行号调整造成的更新敏感度；诊断函数自身改写仍可能要求重新审查。没有新游戏版本或整 EXE 哈希白名单，没有关闭未知、歧义、字段、控制流或进程指令校验，也没有扩展为整个传递调用图。

本地只读回归以新官方、旧官方、旧语音 EXE 为输入，允许四处行号变化；拒绝错误 CALL 目标、诊断函数改写、日志记录步长改写、内部跳转改写、severity 改写及行号寄存器变更。旧字体跳板的四个反例仍需全部拒绝。模型检查从新版 16 个脚本／表 PAC 的指纹开始，在空的隔离目录重建，不使用旧生成缓存。静态兼容、隐藏宿主执行、实际游戏连接和公开发布分别记录，不把静态通过写成实机验收。

2026-10-05 本地候选检查通过：`tools.dev check` 的 582 项 Python（9 项跳过）、177 项 JavaScript 及标准隐藏宿主检查；新旧官方和旧语音 EXE 各 21 项允许／拒绝变异、旧语音四项字体反例；新旧官方日志复制分支的隐藏原生执行，以及新版实际书籍查询。语音样本仅做本轮静态验证，没有运行第三方 MOD 程序。首次标准检查发现书籍检查仍固定旧 RVA，已改为按生产合同解析后重新通过完整检查。

新版 16 个脚本／表 PAC 均记录内容摘要。空目录重建 984,564 条资源记录，编译简中来源和英文来源的中日模型，分别含 204,017 和 207,918 条明确配对。隔离候选包 660 个受管文件逐项校验通过，组件与安装包摘要通过，包内 CPython 的生产兼容预检定位到全部 67 个接管位置。证据保存在本地 `generated/p0-*.json` 和 `generated/p0-dev-check-final.log`；游戏文本、EXE 样本、用户状态和生成缓存不提交或分发。

## 语音 MOD 随 1.04 重链接的 EXE（issue #1）

反馈样本为 issue #1 附件中的 `sora_2nd.exe`：长度 13,478,912，诊断 SHA-256 `ae79759703f26ea750b46deadb3ed0ed11377c25950b8f9454e9d89f3020d966`，加载器所在的 `.rootio` 段位于 RVA 0xCF0000（1.0.7 样本为 0xCEF000）。0.4.4 的生产预检实际拒绝 `font_image_read_call.body.continuation[cache_hash_wrapper]`，与反馈截图一致；该错误只是第一处，逐段走查还发现 `cache_hash_helper` 与 `file_reader_helper` 不匹配。

其余函数未变：用开发期编译器从该样本重新编译全部合同函数，除 `font_image_read_call` 和 `font_file_read` 外，每个模板都与已提交变体逐项相等，包括另外三个 wrapper、三个 helper 和 `absolute_path_predicate`。两个函数的主体也与 1.0.7 变体相同，差异只在下表四个字段。把新字节按旧形状写回后，三段续接体的摘要与已审计的 1.0.7 摘要完全相等，因此表中列出的就是全部差异。

| 续接体 | 相对偏移 | 1.0.7 | 新样本 | 含义 |
|---|---|---|---|---|
| `cache_hash_wrapper` | 71–84 | `SUB R11,段基址`、`ADD R11,恢复 RVA` | `LEA R11,[RIP+恢复地址]` 加 7 个 NOP | 恢复点仍是 `font_image_read_call+223` |
| `cache_hash_helper` | 831 | 0xA92640 | 0xA93640 | CRC-32 表的 RVA |
| `cache_hash_helper` | 837 | 0x5B180 | 0x5B3C0 | 游戏路径哈希例程的 RVA |
| `file_reader_helper` | 181 | 0x8BA098 | 0x8BB098 | `KERNEL32.dll!GetCurrentThreadId` 的导入槽 RVA |

恢复点处的原始指令是 `JS`，使用被搬走的 `TEST R13B,R13B` 的标志位。1.0.7 的 `SUB`／`ADD` 在 `TEST` 之后改写标志位，新样本改用 `LEA` 后不再改写；这是 MOD 自身的修正，恢复地址、寄存器和栈合同未变。后三个字段是 helper 写死的“映像基址 + RVA”，随 1.04 的布局平移；0x5B3C0 处是 41 字节的无 PDATA 叶函数，它用 RIP 读取的表正是 0xA93640，内容为标准 CRC-32 表。

0.4.5 只扩展两个字体入口所需的局部合同，不加入 EXE 版本／哈希准入名单：

- 新旧 wrapper 分别保留完整的已审查指令形状；新 LEA 恢复的 `links` 必须指向独立定位的 `font_image_read_call+223`。不把 71–84 字节整体 mask，也不将 SUB/ADD 与 LEA 宣称为任意语义等价。
- 哈希 helper 的 `rva32` 调用必须落到完整匹配的 41 字节 `path_hash_update`，包括其内部循环、参数寄存器和返回合同；不能落入函数中部或任意同名函数。
- 两条表引用须相等；`data_refs` 同时要求该地址按 4 字节对齐、映射的 1024 字节可读，并匹配标准 IEEE CRC-32 表摘要 `12f3e0576d447eb37b36d82ba0c1c5481b8f0d12fdc70347ce4a076b229d4c86`。该摘要由固定多项式生成，校验实际消费的数据，不是每版 EXE／数据段白名单。
- 文件 reader helper 的导入槽须在唯一、正确终止的导入描述符／thunk 列表中声明为 `KERNEL32.dll!GetCurrentThreadId`。错 DLL／符号、相邻槽、ordinal、冲突描述符或畸形映射均拒绝。
- 旧 voice 的固定 RVA 模板替换为同样的叶函数／CRC／IAT 目标合同，不能在较强模板失败后退回较弱旧模板。官方变体不使用这些 helper，继续只要求其实际依赖。
- 同地址变体的嵌套合同不同仍拒绝，比较包含数据和导入要求的完整嵌套模板。错误诊断优先保留真正失败的局部依赖，不能把 caller 被传播淘汰误报为首根因。

issue 的唯一评论提供第三方 patch；其“修复了兼容”的说法不能当作验证结论。对该 patch 的生产静态预检独立复现了三个错误接受：新 voice CRC 表损坏、旧 voice CRC 表损坏、旧 voice 所需 IAT 符号改名。0.4.5 必须从生产入口拒绝这三种反例，附件没有运行。

兼容边界：PE 元数据、未用代码／资源、完整函数迁址和这些已审查引用的重链接可自动适配；CRC 表／叶函数整体迁址后，只要内容与引用关系保持合同，无需新增变体。不同但可证明安全的指令形状需要单独审查并加入局部 adapter／变体；字段布局、调用约定、参数／返回职责、必要控制流、语义常量、CHAININFO 或接管位置冲突不能由地址归一化解决，继续拒绝。任意 MOD 的整体正确性、运行态 IAT／helper 被另一个 MOD 改写、图形驱动与资源包内容不由磁盘静态合同证明。原有 67 个进程接管点快照仍在任何工厂／原生调用／hook 前统一核验；已有文件 reader 的生产 call-through 例外不扩大到其他接管点。

编译器增加有界 image-relative 引用、跨续接体同表、固定 CRC 数据和导入身份表达。`--extend` 仅在完整生产合同已通过时重编译并要求模板已存在；不删除 continuation 来定位，不学习未知字节，不自动写入新变体。未来普通迁址由生产解析器直接处理；未知代码仍需要可审查的新合同证据：

```powershell
python -m tools.build_native_contracts --extend "语音 MOD/sora_2nd.exe" --output generated/recompiled-contract.py
python -X utf8 tests/check_exe_compatibility.py --exe "新官方/sora_2nd.exe" --old-exe "旧官方/sora_2nd.exe" --voice-exe "旧语音/sora_2nd.exe" --relinked-voice-exe "issue语音/sora_2nd.exe"
```

证据分层：四个真实 PE 的静态生产预检及允许／拒绝变异、自建隐藏原生宿主、包内解释器和清单校验分别记录在隔离任务 `evidence` 目录。隐藏宿主包含独立手写 TEST/LEA 与 TEST/SUB/ADD 夹具，证明 JS 消费 SF 时的差异；不提取或执行附件机器码。真实游戏连接、真实语音资源包与 GPU 字体加载未验证；静态接受不能写成实机连接通过。合同改变包含在 `native_revision` 中，新候选须由新游戏进程加载。

## 连接与字体提示

0.4.1 之前，离线字体准备和连接共用整文件版本门禁，拒绝会被显示成字体失败，连接错误还可能被黄色字体就绪通知覆盖。现有修正保留 EXE、权限、语言资源和进程读取的具体错误，只有文本表尚未初始化才等待重试；字体通知不覆盖连接失败。离线拒绝不写字体或安装收据。

语言识别从四个独立样本中至少取得三个一致结果；缺失的一个可以等待或容忍，但已识别的其他语言冲突不能被多数票掩盖。

## 回归入口与证据边界

`test_native_contracts.py` 使用有效合成 PE 验证迁址、无关代码／数据变化、caller 消歧、叶函数、global／RTTI、BSS、CHAININFO 和局部跳板。错误返回目标或被修改的必要函数体必须被拒绝。

`test_exe_compatibility.py` 经生产连接预检入口验证单快照、诊断错误、Capture 能力隔离和驻留 revision。`tests/check_exe_compatibility.py` 对真实原版和语音 EXE 的临时副本做允许／拒绝变异，不启动游戏：

```powershell
.venv/Scripts/python.exe -X utf8 tests/check_exe_compatibility.py --exe "游戏目录/sora_2nd.exe" --voice-exe generated/patch-inspection/add-sora_2nd.exe.inspect --output generated/native-contract-regression.json
```

`tests/check_native_fonts.py` 在隐藏自建进程中执行实际形状的 CALL、JMP、reader wrapper 和生产字体桥，包含原有 8 项及新增 18 项跳板检查：绝对路径、别名、普通资源、五个参数、cache hit/miss、失败分配和返回值。可选 `--voice-exe` 额外对照样本机器码。该检查已在 `tools.dev check` 中执行。

源码检查、隐藏原生宿主、安装到 DEV、真实游戏连接及画面验收是不同证据，不能互相替代。最新完整检查与实机结果见下方记录。

本轮 `tools.dev check` 通过：578 项 Python（5 项既有跳过）、177 项 JS、20 个隐藏原生检查入口；其中字体检查覆盖 26 项。两个真实 PE 均通过定位，并各自通过 9 个无关改动变体、拒绝 2 个实际依赖破坏变体；另 4 个字体跳板／续段反例全部拒绝。末次撤回 reader 的原始运行时字节要求后，8 项连接入口回归及两份 PE 变异检查再次通过。112 文件测试更新包构建及 manifest 校验通过。详见本地 `generated/minimal-contract-dev-check.log` 与 `generated/native-contract-regression.json`。提交 `fa83dd9` 的 CI 37202825987 通过；DEV4 的真实连接复验见下节。

## 补丁样本和真实复现

| 来源 | 已取得证据 | 边界 |
|---|---|---|
| [全语音 MOD 1.0.7，杏雨浩](https://www.bilibili.com/video/BV1wAeg6DEEJ/) | 公开更新清单，纯追加／去羊／全替换三个 ZIP 目录及同一 EXE | 本轮用 EXE 单独替换做连接复现；未安装完整语音／场景资源包 |
| [科洛丝战斗／主动语音替换，春落木祈雨](https://www.bilibili.com/video/BV1Teeg68Exq/) | 作者说明和网盘链接 | 未取得文件，不能宣称实测兼容 |
| 用户截图中的 DLC 补丁站 | 域名访问失败 | 未取得文件，不能归因或宣称实测兼容 |

全语音 EXE 长度 13,472,768，SHA-256 `b9bfd04877277ea0a4512da2e5fd7d7ec6d8e7c86227e5c16c2c12c3a7b13414`。原版摘要为 `d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf`。样本仅留本机 `generated/patch-inspection`，不提交或分发。

用户授权替换后，语音 EXE 成功进入标题界面，显示 Ver.1.03.2；DEV3（组件 `b94347e944a4c1a2`）报 AddressOfEntryPoint 等 18 项布局差异，尚未安装 hook。随后从菜单正常退出，原 EXE 恢复并校验，56 个存档文件摘要不变。同一 DEV3 对原版则达到 ready、resident 和 runtimeFonts ready。这证明旧门禁造成的真实失败，而不是由字体资源不足推测连接失败。

DEV4 复验（2026-10-04）：从 `fa83dd9` 安装候选 `source-language-dev4`，组件 `d187887a1a6f01f4`，660 个受管文件逐一校验。只替换语音补丁的 EXE 后，新游戏进程 49584 达到 `phase=ready`、`resident=true`、`failed=false`、`runtimeFonts.ready=true`；语言映射完成后记录到 `matched=8`、`modified=8`。用户随后进入地图，截图可见任务提示和 EP 回复的中日双语 HUD。游戏正常退出后恢复原 EXE，摘要与备份一致，56 个存档文件摘要仍不变。重新启动原版进程 32320，同一 DEV4 再次达到连接与字体 ready。两次进程的驻留 revision 均核对为 `3a056ff70e1d3103371f678998db863d3a14994cc1089f8692a1778b905c5120`。

实机记录保存在本地 `generated/voice-live-test-dev4-20261004`，包括两次脱敏状态、原 EXE 备份、恢复校验及补丁 EXE 的双语 HUD 截图。该结果证明此 EXE 的连接和实际双语渲染已通过，不等于完整语音包或其他用户的所有补丁组合已验收。2026-10-04 用户确认此前反馈的问题已修复，并明确授权以该完整 DEV4 候选发布 0.4.2；新发现的动态效果遗漏登记到 0.4.3，不阻塞本版。

静态审查发现 68 个使用位置可对应（67 native 点加文件读取器），但两个字体函数有实质跳板变化。153 组 RIP 目标已分类；普通内部调用不作为新增全部校验要求。审查还构造三个实际反例：字体读取跳到错误出口、reader 入口跳到 RET、acquire 的 CHAININFO 续段常量被改；新合同必须全部拒绝。记录：
- `generated/patch-inspection/standards-function-complete.json`
- `generated/patch-inspection/voice-rip-target-audit.json`
- `generated/patch-inspection/native-contract-review-counterexamples.json`
- `generated/patch-inspection/voice-font-contract-review.json`
- `generated/voice-live-test-20261004`

这些公开包不等于反馈用户的最终补丁组合。完整语音包还会修改松散场景脚本和表资源；成功连接不证明所有对白身份、字幕配对和组合 MOD 已验收。

## 2026-10-05 磁盘映像变化后的精确合同

dev5-r8回放期间16个PAC的资源代次改变，当前磁盘EXE的mtime亦改变；变化来源未确认，执行者未写游戏文件。当前只读样本摘要为`cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`，仅作证据身份，不作放行名单。当前游戏进程加载的是哪份磁盘样本尚未采集，不能从mtime推断。

r9原生产合同拒绝`log_write/body.chained[0]`。以合法保留的原EXE逐指令比较，四份MessageLog模板的未掩码差异仅为断言报告的`R8D`行号参数：writer及commit共享片段`0x64b→0x656`，bind的两处与rows的一处`0x6c4→0x6cf`。它们仍走相同错误报告分支；记录复制、字段偏移、调用点、CHAININFO片段位置及必要函数链接保持原合同。新增四份精确摘要变体，保留旧变体、全部原掩码、相对点位及链接；没有把行号加入通用掩码，也没有加EXE版本或哈希门禁。

`generated/dev5-system-audit-20261005/exe-epoch2-reviewed-draft.json`保存差异指令、报错分支上下文、变体及全部恢复位置。`tests/check_exe_compatibility.py`新增四个行号常量破坏负例，连同原有函数体破坏与字体跳板负例检查拒绝边界。真实PE回放只改项目临时副本，不启动或附加游戏。当前磁盘EXE和此前语音EXE的源码回放通过；这不是新游戏连接或画面验收。

物品description的独立PE oracle原来固定使用开发期RVA，本次迁址后失效。现在以`tests/fixtures/item_description_printf_contract.json`中的原样本局部函数合同恢复builder前缀、bounded printf及CRT消费函数，并核对实际调用链接、`ItemTableData+0xe8`来源、format参数槽及`0x800`容量。builder合同只覆盖连续前缀至该format调用，不冒称其后所有分支已经验证。原/当前映像均通过；错误字段、容量、CRT指令及地址已掩码但指向错误callee偏移的八个负例均拒绝。独立fixture不由当前translator或译文expected生成，不意味着现场必然经过此入口。

驻留revision因合同变化而改变；r9包保留并阻止交付，后续必须用新候选标识打包，在父协调的新游戏进程验证。运行中的DEV3未更新、未附加、未热替换。

只读用户诊断命令：

```powershell
python -m sora_bilingual.game.exe_compatibility --exe "游戏目录/sora_2nd.exe" --output compatibility.json
```

输出文件名、诊断摘要、合同标识及具体缺失依赖，不采集账号、存档或游戏文本。
