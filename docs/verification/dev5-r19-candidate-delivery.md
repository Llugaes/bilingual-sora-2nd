# r19 本地候选交付与回退

核心文本修复来自 `d235d321227fd10369f50f0c990b2512659220b9`，其父检查点 `46d210d` 保留。后续提交只补齐 Tips 合同模块的分发/组件清单、私有候选缓存预置、包内验证和 Orbments 证据说明；不改变已审的 compiler、renderer 或原生身份算法。包清单的 source_head 指向最终干净提交。

目标为 `dist/comprehensive-1.0.0-dev5-r19/DEV`，marker 为 `DEV 1.0.0-dev5-r19`。包 SHA、最终提交、完整文件清单和运行库摘要以相邻 `packages/candidate-package.json`、`candidate-final-verification.json` 为准。当前运行 r18 目录不覆盖。本候选只在本地分发，不是稳定更新资产或公开发布。

## 精确运行库与模型身份

复用已审 r14 的 552 个 launcher/runtime 文件，逐文件校验原清单；runtime_id 为 `bac6e42e94e62356`，整个复用清单摘要为 `abf98b97e7ae210ea8f930cb7727caca4e7aaa0cfb8987e9b3b227d1e09d2f55`，与 r18 沿用内容相同。没有下载运行库或更换 Frida。

私有候选带入本次已经完成的 production 编译，配置为 source EN、primary JA、secondary zh-Hans、scope all。完整 wire SHA 为 `ed829cab814b64c57de34aeea27d6192b25c039d55a0378a94a9db19e0586088`，178690472 字节；含 Physical/完整标题、CP 独立语义层、条件参数和精确 Tips 表加载转换。源码身份、PAC 内容/大小/mtime、模型文件名、wire stamp 与已验证 renderer SHA 必须一致，才能带入；没有拼接旧模型或临时编辑 wire。

预置范围仅为 raw catalog/signature、这一个模型/wire/stamp，以及按现有格式校验 identity、规则 SHA 和值摘要的 2664 份兼容单语 facts。2609 份旧规则记录排除。没有新增缓存层；用户配置、字体 receipts、驻留 agent/token、backend 状态和更新状态不随包复制。

独立 ROOT 的准备成本明确区分：本次编译已经在候选中完成，包含生成 wire 共 86.82 秒，不声称算法提速。交付的本地 DEV 根用 copy2 保留源模型 mtime，使现有 stamp 命中；验证器在禁止 catalog/model/wire 冷构建的条件下执行包内真实 model_worker 路径。普通 ZIP 工具解压到另一个 ROOT 会改变模型 mtime，可能触发一次 wire 序列化；模型、raw 和 facts 的现有缓存身份仍可复用，不能把这一次刷新叫完整冷模型重建。不同语言组合、资源/PAC mtime 或 compiler 身份变化会按现有门禁失效，仍可能需要重算相应模型。字体准备不预置身份 receipt，首次候选字体成本保留独立测量。

## 切换与可逆回退

1. 保留当前 r18 和游戏。原生 revision 已因完整 Tips 合同、identity/renderer/agent 代码改变；准确旧/新值由包内验证记录给出。本候选不得向现游戏热换或重装 hook。
2. 独立审核通过后，由父协调用户正常退出当前游戏，再正常退出旧工具。不要强杀游戏。
3. 在停用旧工具后，只向新根迁移允许的设置 `generated/native-control.json` 与 `generated/overlay-window.ini`；不复制旧模型、程序、token、font receipt 或运行状态。迁移前后保留原 r18 设置。此交付阶段没有执行迁移或启动候选 UI/游戏。
4. 正常启动新游戏和 r19 工具，确认 marker、实际来源语言、native revision 和 model/wire 身份，再按已报入口进行必要实机验收。若要已有有界诊断，必须在新 resident 初始化之前设置，不热开当前 resident。
5. 回退时正常退出候选游戏和工具，沿保留的 r18 原目录及设置启动新进程。旧目录没有被改写；不经自动更新安装本地 DEV ZIP。候选状态与旧根隔离。

## 尚未实机接受

包内 `candidate-case-status.md` 和 `candidate-tips-evidence.md` 保留逐案例的资源、保存内存、原生宿主与实机等级。四个 Tips 实际输入通过离线链路；Orbments 只有资源/保存内存 fixture，Help/类别与 Tips 的同文异译仍保持区分。菜单/Arts 差异、HP/CP 实际原入口、装载槽、书籍 owner342/372、终端首次失败与崩溃均未以候选游戏像素验收。没有把测试数量当作全批修好。
