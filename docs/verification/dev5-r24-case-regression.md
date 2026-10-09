# DEV5 r24：045 兼容合同合入验收边界

起点为封存的 r23-rev2 `10fde0de847d1d8e5b4246d2927eea643e34c455`。本地 bundle SHA-256 为 `1d7584dec8f163eb05b72b3b5e2c9a766627cda2faac199bd1ea7688b518397b`。真实执行 `git cherry-pick -x 541dbbd9fbfa2cb9364992d831403e69b59d7168`，指定 9 文件的 pick 提交为 `974364ddc209e56d762e63a03d359e2b6f89fb21`。未 pick 版本/发布说明提交 `7e79bdd7`；distribution、pyproject、发布说明均保持 r23。独立 DEV 标签为 `1.0.0-dev5-r24`，目标版本 1.0.0。

四个冲突按语义融合，保留 1.0 Shop/Tips 合同、扩展样本与包内生产测试入口。旧 symbol 与新 name 共用 IAT 校验。CRC 同时验证映射、只读权限、对齐、摘要及 callee 读取同一地址。固定 IAT 与迁址形式只在完整模板和依赖验证成功后比较已验证地址操作数的共同语义；不同依赖与歧义仍拒绝。没有旧变体绕过新门禁。

后续封装提交修正测试/生成器融合：迁址 CRC 正例使用只读区映射空隙，而非原 045 测试的可写 loader 节；模板提取按已验证语义去重。生成器先验证完整生产合同，再按原编译范围重编译 core，保留独立审计的 Shop/Tips 模块，避免额外全局别名改变旧指令分类。CRC callee 的生成数据引用与生产合同一致。两种真实 voice 往返增加 0 模板，输出与现完整合同一致。没有放宽生产门禁或修改 hook 脚本。

| 项目 | 证据等级与结果 | 未验证 |
| --- | --- | --- |
| 四个官方/voice PE | 精确原始 PE 经生产 resolver 全部准入，70 个原生点；包含既有 1.0 safe MOD/voice 形式 | 实际 MOD 动态注入、资源及 GPU |
| CRC/IAT 反例 | 完整 PE 检查拒绝 29 次 loader 变异；既有 MOD 检查拒绝 34 次变异；独审提供的 4 个 CRC/IAT 损坏 PE 全拒绝。包含只读权限、映射、callee 内部入口、同 CRC 内容不同地址、导入错名/歧义及旧变体 fallback | 动态游戏功能；检查次数包含重叠，不是唯一 case 数 |
| 合同与生成器 | 34 项定向测试；两种真实 voice --extend 往返成功，增加 0 模板，完整产品合同相等 | 非 live 注入；生成器读取现有 capstone 5.0.7，未安装或修改旧环境 |
| 文本、布局、strictsave | localization、全部 renderer/native-agent 脚本、app 按字节保留 r23；compiler/catalog/resources/config 指纹相同，完整模型与 wire 复用通过身份核对 | 原有实际 setter、glyph、clip、像素验收仍待用户；不因离线检查提升实机等级 |
| 独立新 DEV 包 | 新目录封装，检查实际包内 resolver 与 native revision；旧 r23 保留 | r24 需新的固定源码/包独审，不能继承 045 或 r23 的 PASS；未部署 |

现有完整模型 wire SHA-256 为 `9c6551ebf6671a25be596a8178da86002c3c7f63163e8574b5f17018c8055798`。复用的旧 V8 报告只覆盖字节相同的模型与 renderer，新 native 准入另用当前 source/package PE 记录。没有重编译模型或强灌旧身份；没有复制用户 token、agent 或字体安装 receipts。

原 r23-rev2 ZIP、运行目录和用户设置保留。本轮未启动、关闭、重启或附加游戏，未创建新 RPC/替换 resident，未写存档，未公开发布。下一步仅交父线程对固定 r24 源码/包作新独审，未经新审计不得切换。
