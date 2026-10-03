# 动态通知身份与全文回放

2026-10-03 更新。资源编译、身份传递和最终渲染分别检查，不以全局词典命中代替调用身份。

## 物品通知

全部八种来源语言各有 159 个静态物品调用：42 个 TK、95 个带默认参数的 EV、22 个显式参数 EV。
日文 helper 没有前缀，因此 command 8 使用 5 个参数；其他语言的分段前后缀形式使用 6 个。
此前按固定外层参数数目推断栈，漏掉 TK 和默认参数形式。现在读取实际 `arg_types`，只移除已验证
的默认参数标志，并执行已验证的局部栈转发指令；不把 VM 局部变量序号当作固定参数字段。

`check_native_dynamic_identity.py --exe <游戏EXE> --catalog generated/catalog.json` 验证原生
opcode 2 的相对栈访问、command 8 参数顺序、builder 与 SetText 的缓冲交接，以及全部 1,272 个
原始调用。八语各 159 个身份均编译成功，冲突和拒绝数为 0。隐藏原生进程再回放 8 种实际参数流。

身份为脚本摘要、helper、实际原始参数向量所确定的独立外层调用键；运行时还检查 PC 和完整输出。
例如物品 220 的两个调用在中文显示相同，在英语分别使用 Received 和 Obtained，必须保留两个调用。
`ScriptIdentities.capture → LogIdentities → RuntimeText` 使用正式模型回放每个物品调用及四种图标值。
无 ID 的全局路径仍会报告这两个调用的八个英文歧义案例，不把它们算成全文翻译成功。

## 书籍登记

纠正旧报告：`RegisterBook` 的 opcode-17 参数是**物品整数 ID**，不是任意 VM 字符串。
原始 `BooksTitle` 24 字节记录在 `+0x10` 保存库存物品 ID；八语对应的 26 个非零 ID 一致。
`OnBooksNoteClose` 转发该整数到 `RegisterBook`，后者把它交给物品名称构造器。
因此 `register_book` 与物品通知、食谱共用按实际库存 ID 构造完整提示的代码，不按书名文本猜配。
原始脚本检查同时覆盖日文无前缀形式和其他语言的前后缀形式。

## 其他提示与复现

食谱 157 个库存 ID、26 个书籍库存 ID、BP 和休息模板及静态弹窗各自保留原始分母。
图标使用实际数值槽，不固定为某个物品或食谱图标。
任务完成的原始完整提示已在 `OnQuestEnd` 中按独立调用配对；不将任务标题 ID 强行映射到不同值域的脚本分支。

```powershell
python tests/check_notification_omissions.py --game-dir '<游戏目录>' --existing-catalog-dir generated --model-path ja=<最终日语模型> --model-path en=<最终英语模型> --all-producers --output generated/todo-notification-omissions.json
python tests/check_native_dynamic_identity.py --exe '<游戏EXE>' --catalog generated/catalog.json --output generated/todo-native-dynamic-identity.json
```

完整结果与版本验收见 [本轮复查](todo-review-20261003.md)。原始缺项、无身份全局歧义及正式身份路径
结果分别保留；不得通过删掉失败案例把总状态改成通过。检查不附加真实游戏，仍需新游戏进程确认现场表现。
