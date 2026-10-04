# EXE 兼容检查与连接失败提示

2026-10-04：本轮候选改为按实际原生依赖定位。公开稳定版仍为 0.4.1，后续发布须取得用户对新候选的实机验收。没有正版／破解、DLC 授权、补丁名称或整个 EXE 摘要白名单。

## 检查范围

运行时入口为 `hooks.verified_target_image` → `exe_compatibility.verify_image` → `native_contracts.resolve_native_contracts`。同一次文件读取产生诊断摘要、定位结果和 hook 指令快照。

- 不比较游戏版本、整文件哈希、整个代码／数据段、入口地址、时间戳、资源、证书、调试信息或未使用函数。SHA-256 只用于诊断标识。
- 用 PE 的 x64 异常目录枚举候选函数；无关的坏记录不会阻止已用函数定位。只匹配工具调用、拦截或读取的原生函数及它们的 CHAININFO 续段。无异常目录的叶函数从已验证调用关系定位。
- 模板保留指令、寄存器、字段偏移、常量及函数内分支；仅归一化地址操作数。工具依赖的调用关系必须相符，多个调用者共同消除重名函数歧义。函数整体迁址无需新增 EXE 版本名单。
- 所需 manager 指针与两张虚表从对应 RIP 引用恢复；检查实际读取范围、对齐和类型身份。读取操作不要求所在区段必须只读。普通游戏内部调用不扩展为整个传递调用图的校验。
- 字体入口被搬到跳板的变体还校验该入口的续接体、参数／返回合同及必要的路径 helper；不能只 mask 跳转目标后直接接受。只要求当前函数变体使用的延续体，不要求原版具有语音 MOD 的 helper。
- 连接前，仍将上述磁盘快照与进程内 67 个原生接管位置的 16 字节逐一比对，在任何适配器、原生调用或 hook 安装前完成。文件读取器保留磁盘函数合同，但不要求运行时入口保持原始字节：工具自带的松散资源加载器会在该入口安装 detour，字体桥应通过这个现有入口调用，而不是拒绝或覆盖它。这项检查防止定位结果与当前进程不符，不是未知 EXE 的唯一兼容证明。
- 旧文本 Capture 功能有自己的六处调用签名，只有选择 Capture 才验证；它不再成为正常双语连接的前置条件。
- 局部函数确实改写了参数、对象布局或必需语义时，需要扩展该函数合同。不能保证任意修改都兼容，也不以一个“继续连接”开关跳过实际依赖。

`tools/build_native_contracts.py` 是开发期模板编译器，用 Capstone 从经审查样本编译函数摘要、地址掩码及关系。安装端只依赖已有 pefile。内置 `native_contract_data.py` 不含游戏机器码；其中样本摘要和开发期 RVA 是证据出处，不是运行时放行名单。所有合同变化参与 resident revision，新候选须新游戏进程加载。

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

实机记录保存在本地 `generated/voice-live-test-dev4-20261004`，包括两次脱敏状态、原 EXE 备份、恢复校验及补丁 EXE 的双语 HUD 截图。该结果证明此 EXE 的连接和实际双语渲染已通过，不等于完整语音包或其他用户的所有补丁组合已验收。稳定版仍为 0.4.1，DEV4 的正式发布仍等待用户对完整候选的明确验收。

静态审查发现 68 个使用位置可对应（67 native 点加文件读取器），但两个字体函数有实质跳板变化。153 组 RIP 目标已分类；普通内部调用不作为新增全部校验要求。审查还构造三个实际反例：字体读取跳到错误出口、reader 入口跳到 RET、acquire 的 CHAININFO 续段常量被改；新合同必须全部拒绝。记录：
- `generated/patch-inspection/standards-function-complete.json`
- `generated/patch-inspection/voice-rip-target-audit.json`
- `generated/patch-inspection/native-contract-review-counterexamples.json`
- `generated/patch-inspection/voice-font-contract-review.json`
- `generated/voice-live-test-20261004`

这些公开包不等于反馈用户的最终补丁组合。完整语音包还会修改松散场景脚本和表资源；成功连接不证明所有对白身份、字幕配对和组合 MOD 已验收。

只读用户诊断命令：

```powershell
python -m sora_bilingual.game.exe_compatibility --exe "游戏目录/sora_2nd.exe" --output compatibility.json
```

输出文件名、诊断摘要、合同标识及具体缺失依赖，不采集账号、存档或游戏文本。
