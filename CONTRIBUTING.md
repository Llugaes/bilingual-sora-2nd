# 开发与验证

运行环境：Windows x64、Python 3.14、Node.js 22 或更新版本。开发安装：

~~~powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m tools.dev check
~~~

常用入口：

| 命令 | 用途 |
|---|---|
| python -m tools.dev format | 格式化 Python |
| python -m tools.dev check | 静态检查、格式检查、Python 和 JavaScript 测试 |
| python -m tools.dev test | 仅运行测试 |
| python -m tools.dev preview | 用隔离配置捕获三种语言的真实 Qt 操作图，不连接游戏 |
| python -m tools.dev publish-local | 语法校验后发布本机热加载清单 |
| python tests/check_overlay_update.py | 独立 Qt 进程验证界面重载，不连接游戏 |

本地资源回放工具使用 SORA_GAME_DIR 显式传入游戏目录。无本地资源的 CI 会跳过相应验证；跳过不能作为实机通过的证据。

排版、漏译与原生钩子修复先按[诊断与回归约定](docs/DEBUGGING.md)采集原入口的失败证据。Windows 下 `tools.dev check` 也运行自建隐藏进程的原生检查，包含字号分支与颜色公共出口的实际跳转；不会附加游戏。

语言覆盖检查使用本机生成的 `generated/catalog.json`，报告保留在 `generated/`，不提交游戏文本：

| 命令 | 验证范围 |
|---|---|
| python -m tools.audit_locale_coverage | 全部完整对白与表项的八语缺项、同原文异译风险 |
| python -m tools.audit_dialogue_coverage --model generated/runtime-HASH.json | 对应模型的完整对白配对与调用身份路径；将 HASH 换为实际缓存标识，并传入匹配的语言参数 |
| python tests/check_language_matrix.py | 八语来源／主文／副文的 512 种配置，对照资源目标值，另检查 Python/JavaScript 一致性 |
| python tests/check_all_models.py | 编译全部 64 种主副语言模型，需设置 SORA_GAME_DIR |
| python tests/check_reported_texts.py | 用全目录模型和正式 JS 解析器回放全屏说明、技能范围与效果、道具详情；默认简中来源、八种主语言、日文副语言，可用 --source / --secondary 更换 |
| python -m tools.audit_static_panels --game GAME_DIR --catalog generated/catalog.json --output generated/static-panels-check.json | 从八语言原始资源扫描全屏说明，区分静态可提取、动态排除、配对缺项和目录差异；GAME_DIR 替换为游戏目录 |
| python -m tools.audit_resource_inventory --game GAME_DIR --catalog generated/catalog.json --output generated/resource-inventory.json | 枚举八语全部原始脚本与表，逐项记录目录覆盖、拒绝参数、未识别 schema 和身份冲突；另写小型 summary.json |
| python tests/check_reported_texts.py --game-dir GAME_DIR --panel-audit generated/static-panels-check.json --output generated/panel-runtime.json | 全部静态面板的正式 JS 回放；全局失败保持失败，编译资源身份的结果单独记录，不能作为实机身份已传入的证明 |
| python tests/check_reported_texts.py --game-dir GAME_DIR --item-help-audit --output generated/item-help-runtime.json | 技能详情同族资源探针及已验证的 HP／EP 回复组装回放；保留原始字段分母、格式排除项与歧义，不把独立字段通过当作运行态全覆盖 |
| python tests/check_item_help_revive.py --game-dir GAME_DIR | 从原始槽和连接表核验类别 16 的复活＋恢复构造器，并回放八语主副文矩阵、完整目录英主日副及 JavaScript 富文本 |
| python tests/check_dynamic_and_history.py --game-dir GAME_DIR | 完整目录下的历史原串、说话人上下文与原始动态 producer 家族回放；同时核对翻译和副文层，不连接游戏 |
| python tests/check_history_identity.py --game-dir GAME_DIR | 从原始脚本调用捕获身份，再切换语言模型；核对全部源脚本 manifest 分母及同文异译，不连接游戏 |
| python tests/check_mixed_history.py --game-dir GAME_DIR | 从完整目录编译全部来源语言的旧日志索引，核对八语原串到日英目标及最终副文，不连接游戏 |
| python tests/check_quest_dialogue.py --game-dir GAME_DIR | 从原始脚本与任务表审计毛婆婆完整任务；独立枚举来源／主文／副文组合，并逐条列出旧日志缺失调用身份后的真实歧义，不连接游戏 |
| python tests/check_native_log_activation.py --exe GAME_EXE | 在自建隐藏宿主中执行原生日志 controller 激活函数，验证复用记录时正文与身份恢复；不附加游戏，GAME_EXE 为已安装游戏的可执行文件 |
| python tests/check_native_nested_ruby.py --exe GAME_EXE | 在自建隐藏宿主中执行磁盘 EXE 的原始 ruby initializer，并通过生产 parser／measurement／compensate bridge 验证嵌套注音缩放、只测量不绘制、bounds、flags 恢复与 Frida 重入抑制边界；不附加或启动游戏 |
| python tests/check_native_size_metrics.py --exe GAME_EXE | 在自建隐藏宿主中执行磁盘 EXE 的 S/s 后置字号算术，提取当前 `rubyContextCallbacks.absoluteFactor` 并经生产 parser 的 `set`、`applySize` 与 `sizeOnEnter` gate 验证相对主文倍率；不附加或启动游戏 |
| python tests/check_native_log_inset.py --exe GAME_EXE | 在自建隐藏宿主中执行磁盘 EXE 的九种日志锚点函数与投影乘法，提取生产 log inset 回调，验证临时矩阵位移、恢复和非累加；不附加或启动游戏 |

矩阵可用 `--slice 0/8 --output generated/language-matrix-0.json` 分片运行，完整检查须汇总所有分片。同原文异译的情况要与成功翻译分开统计，不能以“保留原文”或两套实现输出一致作为翻译通过。资源齐全、模型可编译也不能证明游戏控件已经传入正确身份；新增原生接入与实际排版仍需实机验证。

运行时依赖锁定在 requirements.txt，pyproject.toml 直接读取此文件；不要维护第二份依赖清单。源码包可用 python -m build 构建，面向玩家的安装包使用下面的发行命令，包含启动入口和版本清单。

发布前：

1. 同步更新 distribution.json、pyproject.toml 与 RELEASE_NOTES.md。
2. 新文件加入 release-files.json；tools.dev check 验证目录契约。
3. 检查游戏资源、用户配置、个人路径及日志未进入提交。
4. 推送 vX.Y.Z 标签，由 GitHub Actions 验证并发布。需要手动检查构建时运行：

~~~powershell
$distribution = Get-Content distribution.json | ConvertFrom-Json
python -m tools.build_portable --version $distribution.version --repository $distribution.repository
python -m tools.build_installer dist/bilingual-sora-2nd-update.json
~~~

游戏内的布局、实际手柄和过场字幕仍需单独实机验收。调试时不要热卸载驻留脚本；更改底层接入后正常退出游戏再验证新连接。

GitHub 正式版发布后，在已配置凭据的维护电脑主动执行一次 Gitee 中转；本机只上传经过校验的 GitHub 原包，不重新构建：

```powershell
powershell -NoProfile -File tools/local_release_relay.ps1 -Mode Run -Tag vX.Y.Z -WaitForRelease
```

把 `vX.Y.Z` 替换为本次标签。此命令仅在本次运行期间等待对应正式版，完成后退出；不需要计划任务或常驻程序。凭据配置、失败重试、匿名校验及保留最近三版的规则见 [Gitee 分发说明](docs/verification/GITEE_DISTRIBUTION.md)。

## 更新 README 操作图示

运行 `python -X utf8 tests/render_overlay_preview.py`，在 `generated/ui-guide/` 得到中文、英文、日文的真实 Qt 截图及尺寸清单。它使用临时配置，禁用联网、自动连接和输入录制，不连接游戏、不修改玩家设置。图中选中 README 推荐的单语言长按模式；动态状态保留“未连接／等待检查”，不伪装连接或更新成功。

逐张检查页签、选项、文字和控件边界后，只把 README 引用的 PNG 复制到 `docs/images/`。文档截图会展开窗口以完整显示滚动页面；游戏内截图与历史验收图片保留各自用途。修改页面结构时，同时核对三份 README 的操作名称及 `docs/UI_DESIGN.md`，不要继续复用按旧页签顺序生成的图片。
