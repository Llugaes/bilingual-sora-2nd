# Bilingual Sora 2nd

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

《空之轨迹 the 2nd》PC 原生双语文本 Mod。主、副语言独立选择：简体中文、繁体中文、日文、英文、韩文、法文、德文、西班牙文。使用中文游玩时，首次设置默认保留中文正文，配上日文小字注解，方便对照学习。

目前支持 Steam build `25386012` / EXE `1.03.2`。工具会核验游戏版本；其他版本不强行安装钩子。原始 PAC 和 EXE 不改写。项目处于早期阶段：已有离线回归和部分实机验证，完整游戏覆盖、所有语言的排版与手柄兼容性仍需实机反馈。

## 安装和启动

1. 从 [Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) 下载 **bilingual-sora-2nd-版本-windows-x64.zip**，完整解压到有写权限的独立文件夹。
2. 双击 **BilingualSora2nd.exe**。包内已带 Python 和全部运行依赖，无需安装 Python、运行 CMD 或首次联网安装依赖。适用于 Windows 10/11 x64。
3. 首次选择游戏当前的文本语言，随后直接进入设置。工具自动关联正在运行的游戏，也会等待游戏启动；它不会替你启动游戏。

“版本更新”页可以创建桌面快捷方式、打开日志与配置文件夹、查看使用说明。再次双击 EXE 会打开已有界面，不会重复启动后台。界面支持中文、英文、日文。

Release 中只需下载 ZIP；`bilingual-sora-2nd-update.json` 给自动更新使用，GitHub 的 Source code 附件给开发者使用。请保留解压后的完整目录，不要单独移动 EXE。

从 **0.2.x** 升级：旧版更新器无法安装内置运行环境，需要一次手动迁移。退出旧工具，将新包解压到新目录，复制旧目录的 `generated/native-control.json` 和 `generated/overlay-window.ini`（不要复制 `.venv/`、`generated/updates/` 或旧热加载清单），再运行新 EXE。之后便携版的程序和依赖都支持自动更新。开发目录继续保留，不覆盖其源码。

主、副语言可在“语言与模式”中自由搭配。若修改了游戏本身的语言，请同步修改“高级：原文识别”；游戏源语言用于识别文本，主语言决定 Mod 显示的正文。

### 首次运行的默认语言

| 游戏当前文本语言 | 主语言 | 副语言 |
|---|---|---|
| 简体中文／繁体中文 | 与游戏一致 | 日文 |
| 英文 | 英文 | 日文 |
| 日文 | 日文 | 英文 |
| 韩文／法文／德文／西班牙文 | 与游戏一致 | 日文 |

这些只是首次设置的默认值，所有语言均可自由搭配。已有配置在重启或升级时保留，不按新规则重置。界面支持简体中文、英文、日文，默认跟随系统；可在“界面语言”中即时切换。界面语言、游戏识别语言、主副语言各自独立。

首次加载会在本地解析游戏语言资源并建立缓存，可能耗时。后续对白由游戏原生文本控件显示；Qt 界面负责配置和状态。窗口化／无边框下可用，独占全屏不保证能看到设置界面。

### 多语言字库

某些跨语言组合需要补充游戏字库，否则游戏原字体没有的字符可能显示为问号。字库必须从自己的游戏资源生成，不随本项目分发。退出游戏后执行：

```powershell
$runtime = Get-Content runtime/current.txt
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.universal_fonts --game "你的游戏安装目录"
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.install_font_patch --game "你的游戏安装目录" --loader "xinput1_4.dll 的路径" --install
```

加载器取自 [sora2looseload](https://github.com/lmaple0/sora2looseload)。当前安装器只接受已校验的 DLL，SHA-256 为 `e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7`，不接受任意新版本替换。遇到摘要不匹配时保留现有文件并反馈，不要跳过校验。安装器拒绝覆盖其他 Mod 的文件；已有本工具安装记录时可添加 `--update` 更新。软件自动更新不修改游戏目录、加载器或生成字库。

## 配置和快捷键

小状态条常驻；点击“设置”展开详情。详情页 **× / Esc** 只收起详情。状态条 **×** 隐藏界面、保留后台运行；系统托盘或桌面快捷方式可以重新打开。

| 动作 | 默认快捷键 |
|---|---|
| 展开／隐藏界面 | Ctrl + Shift + F9 |
| 当前模式的语言切换 | Ctrl + Shift + F10 |

“按键绑定”中录制一组键盘或 SDL 手柄组合；切换模式后仍使用这组绑定。旧版已有的自定义绑定会迁移，旧的 F11/F12 不再作为独立动作同时监听。默认在游戏前台响应。

- **按住模式**：平时只显示主语言；按住时所有已匹配文本切成副语言单语，松开或失去游戏焦点后恢复主语言。
- **Toggle 模式**：按一下切成副语言单语，再按一下恢复主语言；持续按住不会重复切换。
- **轨迹双语注解模式**：利用游戏的原生注音布局同时显示两种语言，快捷键切换注解开关。这是本游戏的特殊显示能力。

字号、偏移、上下间距可动态调整。首次解析资源仍需要时间；已有有效缓存可直接加载。界面翻译和初始语言偏好的变更不会再使游戏资源索引失效。连接日志会分别记录模型准备耗时和总连接耗时。

普通菜单、道具、技能、NPC 和剧情对话使用小字注解；仅原生过场字幕使用整段主文在上、副文在下。原文自带注音／强调标记保留在原位置，副语言另走小字层。图像或影片中已经烧录的文字不在覆盖范围内；无法确定对应关系时保留原文，不猜测翻译。

## 自动更新

“版本更新”页默认 **自动检查并安装稳定版**：启动时和每 6 小时检查本仓库 Releases。可以立即检查，也可以选择仅提示或关闭自动检查。

更新包在后台下载并核验仓库、版本、文件清单及 SHA-256。游戏连接期间等待，连接结束后安装；完成后控制界面自动重载，恢复位置和展开／隐藏状态。配置和缓存保留在 `generated/`，内置依赖位于 `runtime/`。安装发生中断时，下次从快捷方式启动会先完成提交或恢复旧文件。备份在 `generated/updates/backup-*`。

自动更新只适用于带 `installed-manifest.json` 的发行包安装。Git 开发目录及被手工改动的软件文件不会被覆盖。运行环境更新会写入新的版本目录，界面重载后切换；不覆盖正在使用的 Python/DLL。旧运行环境保留供恢复，可能占用额外磁盘空间。预发布、草稿和旧版本不会自动安装。

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
.venv\Scripts\python.exe -m tools.build_portable --version 0.3.1 --repository Llugaes/bilingual-sora-2nd
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
