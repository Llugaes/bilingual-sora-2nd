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
