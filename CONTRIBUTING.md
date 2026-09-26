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
| python -m tools.dev preview | 使用合成状态渲染离线预览 |
| python -m tools.dev publish-local | 语法校验后发布本机热加载清单 |
| python tests/check_overlay_update.py | 独立 Qt 进程验证界面重载，不连接游戏 |

本地资源回放工具使用 SORA_GAME_DIR 显式传入游戏目录。无本地资源的 CI 会跳过相应验证；跳过不能作为实机通过的证据。

语言覆盖检查使用本机生成的 `generated/catalog.json`，报告保留在 `generated/`，不提交游戏文本：

| 命令 | 验证范围 |
|---|---|
| python -m tools.audit_locale_coverage | 全部完整对白与表项的八语缺项、同原文异译风险 |
| python -m tools.audit_dialogue_coverage --model generated/runtime-HASH.json | 对应模型的完整对白配对与调用身份路径；将 HASH 换为实际缓存标识，并传入匹配的语言参数 |
| python tests/check_language_matrix.py | 八语来源／主文／副文的 512 种配置，对照资源目标值，另检查 Python/JavaScript 一致性 |
| python tests/check_all_models.py | 编译全部 64 种主副语言模型，需设置 SORA_GAME_DIR |

矩阵可用 `--slice 0/8 --output generated/language-matrix-0.json` 分片运行，完整检查须汇总所有分片。同原文异译的情况要与成功翻译分开统计，不能以“保留原文”或两套实现输出一致作为翻译通过。资源齐全、模型可编译也不能证明游戏控件已经传入正确身份；新增原生接入与实际排版仍需实机验证。

运行时依赖锁定在 requirements.txt，pyproject.toml 直接读取此文件；不要维护第二份依赖清单。源码包可用 python -m build 构建，面向玩家的安装包使用下面的发行命令，包含启动入口和版本清单。

发布前：

1. 同步更新 distribution.json、pyproject.toml 与 RELEASE_NOTES.md。
2. 新文件加入 release-files.json；tools.dev check 验证目录契约。
3. 检查游戏资源、用户配置、个人路径及日志未进入提交。
4. 推送 vX.Y.Z 标签，由 GitHub Actions 验证并发布。需要手动检查构建时运行：

~~~powershell
python -m tools.build_release --version 0.2.1 --repository Llugaes/bilingual-sora-2nd
~~~

游戏内的布局、实际手柄和过场字幕仍需单独实机验收。调试时不要热卸载驻留脚本；更改底层接入后正常退出游戏再验证新连接。
