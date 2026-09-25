# Bilingual Sora 2nd

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

《空之轨迹 the 2nd》PC 原生双语文本 Mod。主、副语言独立选择：简体中文、繁体中文、日文、英文、韩文、法文、德文、西班牙文。使用中文游玩时，首次设置默认保留中文正文，配上日文小字注解，方便对照学习。

目前支持 Steam build `25386012` / EXE `1.03.2`。工具会核验游戏版本；其他版本不强行安装钩子。原始 PAC 和 EXE 不改写。项目处于早期阶段：已有离线回归和部分实机验证，完整游戏覆盖、所有语言的排版与手柄兼容性仍需实机反馈。

## 安装和启动

1. 安装 Windows x64 的 Python **3.14**（包含 Python Launcher）。
2. 从 [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) 下载 `bilingual-sora-2nd-版本-windows-x64.zip`，解压到有写权限的独立目录。不要下载 GitHub 自动生成的 Source code 包来代替发行包。
3. 双击 `Setup.cmd` 安装依赖并创建桌面快捷方式。这是首次安装步骤，后续同运行环境的软件更新会自动安装。
4. 双击桌面 **Sora Bilingual**。首次启动先选择游戏当前的文本语言；工具据此设置主、副语言，然后自动关联已运行的游戏，也会等待稍后启动的游戏。工具本身不启动游戏，取消首次设置会退出工具，稍后可重新打开。
5. 在“语言与模式”自由选择主、副语言。若以后在游戏中更改语言，请同步修改“高级：原文识别”。主语言是 Mod 显示的正文，识别源语言用于匹配游戏传入的原文，两者职责不同。目前不自动识别游戏语言。

### 首次运行的默认语言

| 游戏当前文本语言 | 主语言 | 副语言 |
|---|---|---|
| 简体中文／繁体中文 | 与游戏一致 | 日文 |
| 英文 | 英文 | 日文 |
| 日文 | 日文 | 英文 |
| 韩文／法文／德文／西班牙文 | 与游戏一致 | 日文 |

这些只是首次设置的默认值，所有语言均可自由搭配。已有配置在重启或升级时保留，不按新规则重置。首次语言选择提供中英日提示；完整设置面板目前主要使用中文，README 的语言不决定游戏或 Mod 的显示语言。

首次加载会在本地解析游戏语言资源并建立缓存，可能耗时。后续对白由游戏原生文本控件显示；Qt 界面负责配置和状态。窗口化／无边框下可用，独占全屏不保证能看到设置界面。

### 多语言字库

某些跨语言组合需要补充游戏字库，否则游戏原字体没有的字符可能显示为问号。字库必须从自己的游戏资源生成，不随本项目分发。退出游戏后执行：

```powershell
.venv\Scripts\python.exe -m sora_bilingual.fonts.universal_fonts --game "你的游戏安装目录"
.venv\Scripts\python.exe -m sora_bilingual.fonts.install_font_patch --game "你的游戏安装目录" --loader "xinput1_4.dll 的路径" --install
```

加载器取自 [sora2looseload](https://github.com/lmaple0/sora2looseload)。当前安装器只接受已校验的 DLL，SHA-256 为 `e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7`，不接受任意新版本替换。遇到摘要不匹配时保留现有文件并反馈，不要跳过校验。安装器拒绝覆盖其他 Mod 的文件；已有本工具安装记录时可添加 `--update` 更新。软件自动更新不修改游戏目录、加载器或生成字库。

## 配置和快捷键

小状态条常驻；点击“设置”展开详情。详情页 **× / Esc** 只收起详情。状态条 **×** 隐藏界面、保留后台运行；系统托盘或桌面快捷方式可以重新打开。

| 动作 | 默认快捷键 |
|---|---|
| 展开／隐藏界面 | Ctrl + Shift + F9 |
| 注解开关 | Ctrl + Shift + F10 |
| 按一下切换主／副语言 | Ctrl + Shift + F11 |
| 按住副语言，松开恢复 | Ctrl + Shift + F12 |

“按键绑定”中可录制键盘组合、SDL 支持的手柄按钮／方向帽／扳机组合。默认在游戏前台响应。面板提供同时显示、单击切换、按住切换三种模式，字号、偏移、上下间距可动态调整。

普通菜单、道具、技能、NPC 和剧情对话使用小字注解；仅原生过场字幕使用整段主文在上、副文在下。原文自带注音／强调标记保留在原位置，副语言另走小字层。图像或影片中已经烧录的文字不在覆盖范围内；无法确定对应关系时保留原文，不猜测翻译。

## 自动更新

“版本更新”页默认 **自动检查并安装稳定版**：启动时和每 6 小时检查本仓库 Releases。可以立即检查，也可以选择仅提示或关闭自动检查。

更新包在后台下载并核验仓库、版本、文件清单及 SHA-256。游戏连接期间等待，连接结束后安装；完成后控制界面自动重载，恢复位置和展开／隐藏状态。配置和缓存保留在 `generated/`，依赖保留在 `.venv/`。安装发生中断时，下次从快捷方式启动会先完成提交或恢复旧文件。备份在 `generated/updates/backup-*`。

自动更新只适用于带 `installed-manifest.json` 的发行包安装。Git 开发目录及被手工改动的软件文件不会被覆盖。更新若要求不同的 Python 或依赖版本，会提示按发行说明升级运行环境；不会在运行中替换 Python/DLL。预发布、草稿和旧版本不会自动安装。

## 开发和发布

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m tools.dev check
```

`tests/check_overlay_update.py` 使用独立配置验证真实 Qt 界面重载；不会连接游戏。`tests/check_native_transport.py` 需要本地资源，只附加自己创建的测试进程。它们不属于 CI 的无游戏单元测试。

开发修改通过 `python -m tools.dev publish-local` 语法检查并原子发布本地热加载清单；界面和文本逻辑自动切换，底层驻留钩子更新等待游戏下一次启动。不要在游戏运行时强杀或卸载注入脚本。

工程布局与依赖规则见 [架构说明](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/ARCHITECTURE.md)，日常修改流程见 [贡献指南](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/CONTRIBUTING.md)。

维护者同步修改 distribution.json 和 pyproject.toml 版本后推送 `vX.Y.Z` 标签。GitHub Actions 在 Windows 上验证测试，从明确的文件白名单构建 ZIP 和更新清单，上传到草稿 Release 后一起公开；后续客户端自动发现。手动构建：

```powershell
.venv\Scripts\python.exe -m tools.build_release --version 0.2.2 --repository Llugaes/bilingual-sora-2nd
```

发布包和仓库不包含游戏资源、生成字库、完整文本索引、日志、截图或用户配置。报告问题时请附工具版本、游戏版本、语言组合与精简错误信息，避免上传完整游戏数据。

## 许可

项目代码使用 [MIT](LICENSE)。第三方代码与格式参考见 [THIRD_PARTY.md](THIRD_PARTY.md)。游戏、商标和游戏资源属于其权利人；本项目为非官方工具。

## 致谢

感谢以下开源项目及其维护者，让这个工具得以实现：

- [0xDC00/scripts](https://github.com/0xDC00/scripts)，以及 Tom（tomrock645）：游戏文本钩子的调用点签名参考与衍生代码。
- [FPACker](https://github.com/coinkillerl/FPACker)、[Ingert](https://github.com/Aureole-Suite/Ingert)：资源容器与脚本格式参考。
- [sora2looseload](https://github.com/lmaple0/sora2looseload)：可选的游戏字库加载器；DLL 不随本工具分发。
- [Frida](https://github.com/frida/frida)：运行时原生文本处理；[Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)：设置与状态界面。
- [pygame-ce / SDL](https://github.com/pygame-community/pygame-ce)：手柄输入；[pefile](https://github.com/erocarrera/pefile)：PE 文件读取；[python-lz4 / LZ4](https://github.com/python-lz4/python-lz4)：字库纹理压缩。

依赖按各自许可证提供；引用代码的声明保留在 [THIRD_PARTY.md](THIRD_PARTY.md)。
