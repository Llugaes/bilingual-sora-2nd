# r18 诊断隔离修复

r18承接r17 `f38c957a07753ba173e5eedb87363eecadb05180`，只修复诊断自身的类型、预算和异常隔离。父线程独立审查发现r17三个阻断，r17未部署；当前运行r16及配置未改。r15／r16的044、语言偏好和已证明的同族修复继承。书籍实际owner／输入分段、终端现场首个失败及首次注入闪退仍未知。

## 反例与修复边界

独立反例源为父任务的`r17-diagnostics-independent-review.json`。本任务先在r17源码复现失败回归，再应用最小修复；红绿证据位于独立clone的`generated/replacement-r18-{js,python}-{red,green}.log`。

| 独立审反例 | r18行为 | 回归证据 |
| --- | --- | --- |
| 非法candidate key为42；诊断off正常拒绝，on的`.slice`抛异常使agent failed | 两种开关保持相同业务拒绝；诊断只接受原始string，错类型记null，不做隐式转换 | 实际table／script生产选择器；key为数字／对象／数组／null，off／on健康状态及显示一致 |
| 拒绝项file或sha256各150000字符可进入遥测 | 固定字段白名单、逐字段长度上限、截断标记；不复制未知字段，不保留对象／数组 | 实际生产拒绝路径与两层trace边界，另测错误数值、超长stage／key及未知字段 |
| snapshot RPC错误逃逸主loop，进入cleanup并可能park健康resident | 仅可选snapshot／export及诊断错误日志有局部异常边界；下一次输入和快照继续处理 | 运行真实`probe.run`循环的两tick替身：首个RPC失败后执行下一次主文切换；失败时无disable／park，替身正常退出才cleanup |

身份选择器包装的仅是记录回调，不包装身份验证和业务选择。throwing callback／metadata getter不能改变selected、rejected或ambiguous结果；实际身份实现错误在诊断off／on都触发原业务错误处理。后端实际mode RPC错误同样继续抛出，不能用诊断catch隐藏连接／业务故障。

每事件限定stage／key／file／sha256为64／512／256／64个JS字符；offset／size／record_at／field_at必须是非负safe integer，否则null。原有64输入、每类12事件及原串／显示各2048字符上限保留。超限后最终阶段仍受64字符预算，截断标记在二次收集时保留。附属身份key最多512、reason128、scope64；provenance格式32、路径1024、非负safe integer长度，不调用自定义`toString`。成功加载业务模型后，坏provenance只失去诊断元数据。

snapshot RPC、序列化、写文件失败返回限定的stage／error_type／message；message最多256字符，坏异常`__str__`也隔离。错误状态进入下一次heartbeat，错误变化时写日志；写诊断错误日志本身失败不能终止健康循环。原显式完整snapshot接口与实际业务RPC错误处理不变。

默认diagnostics仍关闭。关闭时仍有少量note调用／分支和status元数据开销，不声称零开销。没有新增hook、stack walk、控制连接或背景native读取；诊断开启与候选切换仍由父线程协调新游戏初始化。本轮未量测游戏帧时间或现场稳定性。

## 定向验证

- 170项JS：生产agent、runtime identity、transport全部通过；包含错误类型、150000字符、回调／getter异常、歧义拒绝和off／on业务等价。
- 41项Python：native lifecycle、loading、snapshot、model wire、portable build、DEV update、architecture及新增诊断隔离全部通过。新增五项包括真实后端循环RPC／导出失败、业务RPC反例、导出不可用和异常消息不可用。
- `tests/check_native_input_diagnostics.py`实际Frida V8：完整agent语法、真实NativePointer SHA拒绝、throwing callback、标量白名单／字段预算／getter隔离、64记录／2048字符和关闭状态通过。只附加本任务新建的隐藏Python宿主，宿主正常退出；不附加游戏。
- Ruff定向检查与diff whitespace通过。未重跑无关大模型矩阵；未以离线测试替代游戏字体／画面／控制器验收。

独立候选构建receipt和最终核对保存在`dist/comprehensive-1.0.0-dev5-r18/packages`，包含精确提交、DEV标识、包SHA、逐文件核对及复用已验收runtime证据；机器交接位于任务目录`replacement-dev5-r18-handoff.json`。打包后再次用候选脚本执行上述Frida检查，结果位于`generated/replacement-r18-package-frida.json`。

## 剩余门槛

父线程先独立审查r18，再安排候选切换。本执行者未改r16运行ROOT、用户配置、存档或字体；未启动／关闭UI或游戏，未替换resident，未发布稳定1.0、push、tag或CI。

书籍／终端的静态资源、模型和当前磁盘路径证据继续引用[r17遗漏链](dev5-r17-omission-paths.md)，其r17诊断实现已被本轮修复替代。只有现场允许时取得实际resident／模型、完整SetText输入、owner和后续owned-copy生命周期，才可确定首个失败。不新增硬编码词句、不借阅读器chapter身份、不放宽同文异译歧义门禁。044更新通道修复仍不等于`frida-agent.dll`首次注入闪退修复。
