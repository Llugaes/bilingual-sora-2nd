# dev5 同资源代次回放与缓存边界

最新完成的本地r12交付、准确计数、12入口未测边界与父协调动作见[交接摘要](dev5-r12-handoff.md)。以下失败/修复历史保留，不提升为实机验收。

2026-10-05，唯一执行者在项目写权限恢复后持续修复。冻结DEV3及当前游戏未操控，没有第二套UI/backend、字体ACL变更、push、CI、tag或发布。此页不是实机验收记录。

r8矩阵中16份PAC大小/mtime变化，磁盘EXE也有新mtime，来源未确认。新增资源代次检查已覆盖catalog build/read、model input/read和publication前后，变化报`resource_changed_during_preparation`、phase及changed_files，不确认ready。旧r8失败证据保留，不把混合代次矩阵算通过。元数据检查不能检测恢复原大小/mtime的外部改写；单语言facts另以完整资源SHA和生成规则SHA校验。

r9同一新资源代次下20模型冷建/热读及独立原PAC主动语音通过。每组975条可比脚本调用中，全局或精确指针合同的并集为967–975条；EN→JA→简中是971条，不能提升为所有base均975。另3条未知/动态拒绝；全局与指针计数有重叠。拒绝的稳定ID和原因保留在各组script-display报告。它们不是实际控件保留该指针的证明。后续物品printf的独立PE oracle因固定开发期RVA失效，门槛停止；当前磁盘EXE还被原native合同拒绝。r9包和失败日志保留，不交付、不沿用其hash称新候选。

原/新EXE只读指令审查见[EXE合同](exe-compatibility.md)。四份MessageLog精确变体保留所有旧掩码、字段、分支、CHAININFO与必要链接；没有扩大成版本/哈希白名单。当前磁盘EXE与此前语音EXE各接受9个无关改动、拒绝6个依赖破坏，4个字体跳板负例仍拒绝。物品printf改为定位局部函数再检查字段、参数及callee，原/当前样本及8个独立破坏负例通过。执行者没有读当前游戏内存来确认加载映像，因此新游戏/原生入口仍pending。

Swap剖析`identity-profile-r9-02.txt/json`读取已有暖facts，不写旧缓存，编译输出与原模型经正常JSON元组序列化后完全一致。剖析包含计时开销，不能当真实按钮耗时。其中52次完整SCP parse占约5.2秒剖析时间，来自通知身份编译重复读取全函数元数据。新增`notification_metadata`只缓存单语言的声明参数类型与按序调用目标；它不是Function，不提供called/code_shape，不能充当动态参数或分支证据。原始字节码、helper转发、调用序号、栈槽与所有主副配对仍每次核验。资源/语言/生成规则SHA、校验和及权限拒绝沿用facts合同；PermissionError直接传播，不换路径重建。

`notification-cache-red.log`保留新回归的失败；green中6项语言缓存、4项动态/栈槽回归通过。另将每个call的完整候选按原family分桶，减少同一family字符串的重复计算；仍检查全部locale字节和原best选择规则，没有放宽身份。`python-regression-12.log`完整656项总运行，651通过、5跳过、0失败，100.452秒；JS程序未改，184项同源码证据保留。跳过是缺少本机FNT/DDS研究材料，不能算通过。

### r10生产回放通过，但权限负例阻止交付

r10的20组合已由实际包内Python完成冷建、热读，并与同资源代次r9完整模型逐字节相同；另一个hash seed的独立重建也相同。冷模型阶段30.53–67.15秒，热读1.69–2.30秒。67.15秒的首组包含规则变化后的事实miss，不能称暖缓存。EN主日副简中对调主简中副日的新模型32.22秒，2718 fact hit/0 miss，script身份阶段13.02秒。以上均为离线模型阶段，不是按钮→wire→resident ack，也不是受控负载下优化前后的因果对比。

独立原PAC主动语音、script与控制对白、物品printf、效果/入口合同、水泵硬换行、隐藏自有V8及当前磁盘EXE原生依赖检查完成。最终新增权限负例发现：通知编译器把缓存`PermissionError`当`invalid_archive`吞掉，返回空通知索引。这个失败来自自有内存archive fixture，没有尝试访问受限目录或修改ACL。`notification-denial-r10.json/log`保存结果，`final-validation-r10.log`在portable bundle门槛停止；r10未生成最终便携候选，不交付。

### r11权限传播修复与同包验证

通知编译器现直接传播`PermissionError`，不重试或换路径。继续检查发现完整模型缓存读取也会把此异常当miss：已改为传播，不重建、不写ready收据。`notification-consumer-denial-red.log`与`model-cache-denial-red.log`分别保存修复前失败；green保留真正调用方的负例。`python-regression-14.log`完整658项总运行：653通过、5跳过、0失败，103.841秒。五项材料不足的研究测试不是通过。

新标识`1.0.0-dev5-r11`，稳定/包协议仍`0.4.2`。全部旧候选和未提交修改保留。r11实际生产pipeline正在以单一资源代次冷建/热读20组合并与r9完整输出核对，再运行独立原资源oracle、正负合同、拒绝清单、owned V8、当前EXE依赖及权限传播门槛。任何失败保留包与日志并阻止交付。新包不携带沙箱私有字体、模型或facts缓存；没有启动候选UI、backend或游戏。

r11继续审计时新增实际包内负例：wire就绪检查、wire读取（schema1/2的stamp与payload）以及书籍通知域发现仍吞`PermissionError`。`permission-contracts-r11.json/log`核实所有import来自冻结r11，5项测试含子例共6失败；其中此前修复的模型读取和通知身份两项已通过。fixture只模拟拒绝，没有访问受限目录、扩大ACL或写游戏。r11便携打包已在此失败证据处停止，不交付；`candidate-dev5-r11-blocked.json`保存完整阶段结果。

当前冻结包回放命令已正常结束后，才修复剩余三处源码边界：wire两个入口与book资源域的`PermissionError`直接传播，其它缺失/损坏记录的正常失效规则不变。`wire-book-denial-green.log`34项相关测试通过，含两个wire协议正常复用/失效，ruff与diff检查通过。r12完整Python661总运行（656通过/5跳过/0失败），最终包20配置和14本地门槛完成。打包核对器的旧期待与隔离import错误保留，修复仅交付脚本，候选程序/配置/SHA未变。详见最新交接；保留r11全套回放与日志，没有第二UI/backend或新游戏进程，实际12入口目标仍未闭环。

全部12族继续按`dev5-system-coverage.md`的入口合同报告。All]、已装备Heal、白银之盾完整constructor、战斗toast与当前HP Regen着色组合等缺现场source/key/scope/formatter及真实hook证据；24个离线入口case不能代表这些屏幕入口覆盖。普通用户首次自动准备、真实按钮→prepare→publish→wire→resident ack、glyph宽度/视觉禁则及最终游戏验收待父协调安全时点。未设1–3秒门槛，不以静态资源存在、同包矩阵或隐藏V8通过宣称无遗漏。
