# 战斗效果中的标点误关联

2026-10-04 用户在主英副日的 Heaven's Kiss II 效果条中看到重复的「をセットすると、」。目录中的 `script/scena/system.dat/TutorialOrbmentQuatzEditChr/called/9/arg/7` 英文恰好是 `,`，日文是该教程句子片段。富文本按颜色拆段后，效果分隔逗号被当成这个片段翻译；不是字号或坐标错误。

修改前，完整英文来源模型对 `<c698>Quick</C><c698>, </C><c698>STR/SPD (4 turns)</C><c698>, </C><c698>CP+15</C>` 的最终 `render` 生成了两处 `<R>,</Rをセットすると、>`。此输入按截图与既有颜色构造合同重建，未声明为现场采集到的完整控件串。Python 和 JS 的回归同时复现了这一错误。

修复只约束已经拆分的 `component` 和 printf 字符串参数：不含文字／数字的片段保持原样。完整对白、完整资源键及上下文匹配先于拆分，因此省略号对白仍保留官方译文。没有改动行距、字号、原生钩子和几何坐标。

JS 使用共享的 Unicode 16.0 字母／数字区间表，按码点二分查询，并对 ASCII 文字快速返回；Python 回归从全部 Unicode 码点重新生成区间，与 `str.isalnum` 逐项核对。不能只枚举词典已有的标点串，因为 `-%s-` 等模板还能接收未入库的 `---`、图形符号等。也不能使用 Unicode 属性正则：本机 Node 支持该语法，但随发行包运行的 Frida V8 不支持。隐藏原生宿主检查已覆盖实际脚本加载及该效果条的最终副文。

验证入口：

- `tests/test_menu_text.py`、`tests/test_runtime_text.js`：富文本效果条、字符串参数、空白包围、最终副文及完整省略号对白。
- 审查发现并修复中点列表的直接配对旁路；`Quick・,`、反向及三成员组合均验证。模板产生的新标点串与未知 emoji 同样保持原样，不借用教程片段。
- `tests/check_runtime_text_engine.py`：在自建隐藏进程的 Frida V8 中执行生产解析器，已纳入 `tools.dev check`。
- `tests/check_punctuation_fragments.py --output <report>`：以完整目录中所有纯标点资源为分母，八个来源、56 个来源／目标组合、5,040 个输入，分别验证 Python 与 JS 的 component、字符串参数、富文本 translate 和最终 render；首次修复后全部通过。

该证据说明片段不会向效果条注入教程文字，不等于所有技能效果均已翻译，也不能替代当前候选的实机验收。

同轮最终 `tools.dev check`：573 项 Python（5 项原有条件跳过）、177 项 JS 通过；20 项隐藏原生检查带已安装 EXE 路径完成，仅操作自建宿主。中点列表不得把空成员／项目符号包进注音，原有 party-row 几何回归曾检出这一扩展影响，修正为回退逐组件后通过。复活恢复的独立资源族检查见 `tests/check_item_help_revive.py`；512 种来源／主副语言配置的 7,168 个有界构造用例及英日完整目录回放通过。
