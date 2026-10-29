# 1.0.4 剩余文本关联与显示路径排查

本页是当前任务状态入口。用户要求在 1.0.3 之后继续解决剩余 14 个动态调用及未确认显示路径，并自主测试、发布。反馈版本未知、无剧本 Mod。当前已实现修复和资源验证，正在核对最终回归、正式包及发布；离线测试与隐藏原生宿主不记作玩家实机验收。

## 已解决的构造与错配

13 个对白调用中嵌入角色动作。逐条追溯实际字节码后，动作处理器保留的寄存器值只能来自已证明的 helper 返回值：特殊零或编码的布尔零／一。原生文本 builder 与回调对这些值均不输出文字。新规则同时核对完整父子参数、控制流、返回值来源和实际调用位置；未知返回值继续拒绝。13 处位置沿用 [1.0.3 清单](dialogue-coverage-1.0.3.md)。

`mp0010_11/QS502_08_00_SELECT_00/1` 是七种耀晶石数量面板。每个数量须来自对应物品 ID 的 `item_count_get`，并与实际原串数字相等。七组 ID、图标、数量及执行顺序构成完整合同；没有将任意动态整数泛化为可翻译模板。多语言物理调用序号分别保留。

另发现 `mp4020_01/TK_GERVAIS` 的日文少了分支 `54021`。旧规则按文本之外相同的调用形状配对，将中文 17、19、21 错配给后续做饭对白。现在按实际分支条件对齐：中文 24、26、28 对应日文 17、19、21；缺失分支保持原文。八语每语 1,082 个脚本、933 个同类分支函数已核对，跨分支配对为 0。原先列作缺项的三句因此得到纠正；真正缺日文的是中文 17、19、21。

英文目标的旧日志回放还发现，官方尾部未闭合 `<R>` 被历史日志的保护条件拒绝。该目标原串已被中文来源的正常对白使用；原生 R 起始分支只记录基文起点，结束标记才进入读音布局。现在允许完整官方候选中的最后一个未闭合起始标记，保留原串；嵌套起始、残缺结束标记和部分文本匹配仍拒绝。全局词库没有取得此权限。

## 原始分母和验证

| 分母／入口 | 结果 |
|---|---|
| 原始八语 PAC | 每语 1,082 个脚本、315 个表文件；解析失败 0 |
| 中文静态对白与已声明显示表字段 | 63,128 个静态调用及 18,571 个字段都有目录来源 |
| 未直接组装的中文调用 | 114 / 114 个有编译路由；上一版为 100 / 114 |
| 完整目录 | 984,837 条；增加 27 条，另纠正三处跨分支配对；条目数不是画面数量 |
| 有限控制对白 | 608 个八语原始候选，1,024 个已证明语言变体；中文 150 个完整副文回放、600 个拒绝边界通过 |
| 剩余 14 个调用 | 生产回调夹具 276 项通过：首次捕获、重载、主副语言、注音、适用的日志显示／测量和恢复原文 |
| 完整 wire 模型 | 隐藏 Frida V8 宿主 147 项通过，使用实际 SCP 字节和生产哈希，没有哈希替身 |
| NPC 分支 | 完整模型及生产回调 39 项通过，含三句正确配对和三句缺项拒绝 |
| 原生语义 | 只读取得的实际回调、flag 处理器和 R 起始块在隐藏自建进程执行，13 项通过 |
| 中文完整对白变体至日文 | 63,256 个中 63,248 个最终渲染通过，8 个官方缺项 |
| 八语旧日志至日文 | 992,512 项加权查询：933,127 精确、59,385 完整候选；渲染失败 0 |
| 中文对白及八语旧日志至英文 | 63,251 个对白变体通过，5 个官方缺项；992,554 项旧日志查询通过 |
| 英文尾部 R 旧日志 | 同路径红绿：344 项拒绝归零；160 个原串的生产日志显示、测量、切换和恢复共 1,120 项通过 |
| 动态生产者 | 400 个规则、1,607 项完整副文回放、856 项既有调用身份及日志检查通过；排除 0 |

目录 SHA-256：`1b29ef52dad76fd20419b79d326076638e638d6d8bdcaebde64bdcc195c83984`。中日文模型 SHA-256：`1dbf1ca563d1458b54f2a13862bad2cb725697754e392e09465dba99ec403e88`。wire SHA-256：`2c0da766bf5e17c0ced4f2d00b0e7a0c62c81bcf4f990fb13ffb24f78231539f`。分支证明的扫描优化前后，三者逐字节相同。

原反馈三个函数的 146 条对白，第一阶段已用正式 1.0.2 对照完成 2,920 项回放。截图原句原本已有配对，截图故障未被复现；不能将其他缺陷说成截图故障的确定原因。

## 未声明表字段的去向

此前每语 367 个未知表段是 schema 数量，不能直接统计成漏译。对八语所有 315 个表的文本指针候选再次核对：30 组、198,281 条线索全部分类。

- 条件与参数数组按元素宽度、计数和边界验证；空数组指针碰巧指向后面的文本，不作为显示字段。
- 任务／书籍记录的紧凑 ID 是数值，按指针解读得到的字符串属于误报。
- 语音转录、状态注释、表情名、天气标签及卡牌文本，在八份官方资源中没有不同的文本版本。此分类表示没有另一份本地化译文，不声称它们全都不可显示。
- 事件标签在部分语言中不同。核对了构造、注册、发现的原生消费者和传递的行指针；已审阅消费者没有把标题字段作为显示串读取。41 段原生代码及本次 EXE 的摘要绑定在开发审计中；EXE 变化后必须重新搜索消费者，避免漏掉新增函数。这不是运行时的整 EXE 白名单，也不是任意版本的可达性证明。

另扫描所有未声明的对齐 64 位字段，包含纯 ASCII：1,578 组字符串线索中，15 组有跨语差异。它们落到上述类型、已声明的非显示资源选择符，或只有 `0`／横线的占位字段；未分类的语言差异字段为 0。新字段不会自动沿用“非显示”结论。

这些文本候选已经查清分类。未知二进制 schema 没有被伪装成完整解码；资源与机器码检查不等于逐场景观察全部控件。

## 官方语言缺项

中日文仍有 8 个中文完整对白变体无对应官方日文：

- `mp4020_01/TK_GERVAIS/called/{17,19,21}`：日文资源没有分支 `54021`；日文所有脚本中同名 NPC 函数仅有此处。
- `mp6600/MayaEvent09_35_00_03_SubTitle/called/{3,5,7,11,13}`：这组歌词字幕只存在于简中、繁中和韩文资源。

缺项保留原文，不从其他剧情借句子，也不补造官方翻译。

## 性能与发布

同机顺序测量，基线来自实际 1.0.3 CI 包；准备进程包含固定 2 秒观察期：

| 测量 | 正式 1.0.3 | 1.0.4 |
|---|---:|---:|
| 首次准备时长 | 262.99 秒 | 267.82 秒 |
| 首次准备峰值私有内存 | 1,964.11 MiB | 1,865.80 MiB |
| 暖缓存时长 | 3.43 秒 | 3.54 秒 |
| 暖缓存峰值私有内存 | 19.09 MiB | 19.33 MiB |
| 暖日志查询及渲染中位耗时 | 1.004 微秒 | 0.813 微秒 |

首次准备约增加 1.8%；两次均通过原有 2 GiB 私有内存门槛。本轮绝对耗时高于第一阶段，使用本轮同机对照，不跨时段宣称提速。运行时只对已证明的数量面板多核对七个整数；普通静态字面量保持直接比较，没有新增逐帧资源扫描、游戏钩子或无限增长缓存。这些测量不代表游戏 FPS。

最终 `tools.dev check` 通过：861 项 Python（9 项条件跳过）、234 项 JavaScript、25 个隐藏原生宿主检查入口以及 Ruff。普通 CI 中需要本地 EXE 的专项入口按既有条件跳过；本轮新增的 13 项原生检查单独使用本机 EXE 完成。运行时源码不新增 native hook。实际 CI 包及升级回退尚在核对，发布后补入成品记录。

## 重复检查

先通过正常准备入口，从本机合法游戏资源生成完整目录及中日文模型。原始资源不随仓库或发行包分发。

```powershell
python -m tools.audit_resource_inventory --game <game> --catalog <cache>/catalog.json --output <evidence>/resource-inventory.json
python -m tools.audit_dynamic_coverage --inventory <evidence>/resource-inventory.json --catalog <cache>/catalog.json --output <evidence>/dynamic-coverage.json
python -m tools.audit_branch_dialogue --game <game> --output <evidence>/branches.json
python -m tools.audit_table_candidates --game <game> --inventory <evidence>/resource-inventory.json --exe <game>/sora_2nd.exe --output <evidence>/table-candidates.json
python -m tools.audit_table_strings --game <game> --candidate-report <evidence>/table-candidates.json --output <evidence>/table-strings.json
python tests/check_control_dialogue_resources.py --game-dir <game> --catalog-dir <cache> --evidence-dir <cache>
python tests/check_remaining_dialogue.py --game-dir <game> --model-dir <cache>
python tests/check_remaining_indexed.py --model-dir <cache>
python tests/check_branch_dialogue_resources.py --game-dir <game> --model-dir <cache>
python tests/check_nested_return_native.py --exe <game>/sora_2nd.exe --output <evidence>/native.json
python -m tools.audit_history_dialogue_coverage --game-dir <game> --catalog <cache>/catalog.json --ja-model <model.json> --save-contexts <evidence>/history --out <evidence>/history.json
python tests/check_orphan_history_resources.py --contexts <evidence>/history/history-en.json --output <evidence>/orphan-history.json
python -m tools.dev check
```

回放使用 `<cache>/full-model-builds.json` 中的模型路径和配置。控制对白检查会产生后续回放所需的原始调用输入。历史审计分别统计官方缺项、调用身份和旧日志候选；错误配对、拒绝合法候选和最终渲染失败会返回非零。详细证据保存在维护者本地 `generated/continuation/` 和 `generated/release-1.0.4/`。
