# Bilingual Sora 2nd — 空之轨迹 the 2nd 双语字幕 Mod

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

**Trails in the Sky the 2nd bilingual subtitles & text mod · 空の軌跡 the 2nd 二言語字幕・テキスト表示 Mod**

《空之轨迹 the 2nd》PC 双语文本 Mod：对白与菜单可同屏对照，也可按住快捷键临时切换。主、副语言独立选择，支持简中、繁中、日、英、韩、法、德、西班牙文。

目前支持 Steam build `25386012` / EXE `1.03.2`。工具会核验游戏版本；其他版本不强行安装钩子。原始 PAC 和 EXE 不改写。项目处于早期阶段：已有离线回归和部分实机验证，完整游戏覆盖、所有语言的排版与手柄兼容性仍需实机反馈。

**日常游玩推荐：单语言显示＋按住显示副语言。** 平时看主语言，需要对照时按住快捷键，松开恢复。双语同屏仍可使用，但对话日志存在开页停顿和帧率下降的已知限制，详见下方说明。这是使用建议，不会重置已有配置。

## 显示效果

游戏实拍：中文正文＋日文副语言。点击图片可查看原尺寸。

![对话中的双语显示](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue.jpg)

<details>
<summary>查看道具、装备与场景界面</summary>

道具名称与底部说明：

![道具界面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/items.jpg)

装备名称与属性说明：

![装备界面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/equipment.jpg)

场景交互与提示：

![场景界面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/field.jpg)

</details>

<details>
<summary>英文正文＋日文副语言</summary>

![英日对话](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-en-ja.jpg)

![英日魔法列表与说明](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/arts-en-ja.jpg)

</details>

## 安装和启动

1. 从 [最新 Release](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) 下载 `bilingual-sora-2nd-版本-windows-x64-setup.exe`，双击完成安装。
2. 从开始菜单或桌面快捷方式打开 **Bilingual Sora 2nd**，首次选择界面语言并设置主、副语言。
3. 工具会自动寻找游戏并准备多语言字体，无需选择目录或游戏文字语言。保持游戏关闭，等字体显示就绪后正常启动游戏；工具会自动连接，首次语言映射初始化可能需要几分钟。

适用于 Windows 10/11 x64，无需管理员权限。Python 和运行依赖已内置，下载安装包后可离线安装，无需另外配置环境。界面支持中文、英文、日文，已有设置在升级时保留。

便携版、旧版迁移及排障步骤见下方 [常见问题](#常见问题faq)。

“更新”页提供使用说明和发行说明。再次打开程序会显示已有界面，不会重复启动后台。

设置分为“语言”“文字排版”“快捷键”“更新”四页。主、副语言可在“语言”页自由搭配。“游戏内文字语言”由后端自动检测，只展示状态，不能编辑。主语言只决定 Mod 显示的正文，不会修改游戏设置。连接失败时会自动重试，也可点击语言页的连接按钮重试。

### 首次运行的默认语言

主语言默认与游戏一致；副语言默认日文，游戏为日文时则默认英文。

这些只是首次设置的默认值，所有语言均可自由搭配。已有配置在重启或升级时保留，不按新规则重置。界面支持简体中文、英文、日文，首次启动时选择；也可在“界面语言”中即时切换或跟随系统。界面语言、游戏识别语言、主副语言各自独立。

工具自动发现 Steam 游戏目录。首次进入游戏后自动检测实际文字语言、解析本地资源并建立语言缓存；有效缓存会复用，不会修改游戏语言。后续对白由游戏原生文本控件显示；Qt 界面负责配置和状态。窗口化／无边框下可用，独占全屏不保证能看到设置界面。

### 多语言字库

某些跨语言组合需要补充游戏字库，否则游戏原字体没有的字符可能显示为问号。工具发现游戏目录后会从本机游戏资源自动准备字库，并在游戏关闭时安装。首次启动游戏前完成准备即可直接生效；若已开游戏，则先暂存，退出后安装，下次启动生效。界面会显示字体的就绪、冲突或失败状态。游戏字库不随本项目分发；程序另附 OFL 许可的两个补充字形。

## 配置和快捷键

选择显示方式，按需要调整字号和间距。以下为真实设置界面的离线截图，未连接游戏；左图选中推荐的“单语言＋按住显示副语言”。

| 语言与模式 | 文字排版 |
|---|---|
| ![语言设置](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/settings-zh-Hans.png) | ![排版设置](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/layout-zh-Hans.png) |

小状态条常驻；点击“设置”展开，再点一次收起。拖动状态条的文字、空白、把手或详情顶部，两者一起移动；按钮保留点击操作。详情页 **× / Esc** 只收起详情。状态条 **×** 隐藏界面、保留后台运行；系统托盘或桌面快捷方式可以重新打开。

| 动作 | 默认快捷键 |
|---|---|
| 展开／隐藏界面 | Ctrl + Shift + F9 |
| 当前模式的语言切换 | Ctrl + Shift + F10 |

“快捷键”中录制一组键盘或 SDL 手柄组合；切换模式后仍使用这组绑定。已有自定义绑定会保留。默认在游戏前台响应。

- **双语模式**：利用游戏的原生注音布局同时显示两种语言，快捷键开关副语言。
- **单语言模式**：选择“按一下切换语言”或“按住显示副语言”。按一下切换不会因持续按住而重复触发；按住显示会在松开或失去游戏焦点后恢复主语言。

字号与间距修改后实时生效，切页后保留。副语言颜色按原 RGB 分量相乘，默认 230 / 230 / 230，不透明度 90%；颜色按钮下方的滑块调整不透明度。整体上下偏移仅双语模式生效，正值向下。

首次使用或游戏资源变化后，工具会在连接游戏时自动准备语言缓存，可能需要几分钟；有效缓存会直接复用。

## 推荐用法与已知限制

优先流畅度时，选择 **单语言模式 → 按住显示副语言**，在快捷键页绑定一个方便按住的键盘或手柄组合。平时只显示主语言；需要对照时按住切换，松开恢复。此方式不持续同屏排版两种语言，是目前推荐的日常用法；切换时仍可能有短暂重排，不保证完全没有延迟。

- **双语对话日志的性能问题尚未消除。** 打开日志可能明显停顿，停留时帧率也可能低于单语言模式；实机反馈中出现过约 **700 ms** 的开页停顿，重复打开也可能发生。实际表现随历史记录量、语言组合和设备而变化。已有缓存与原生优化降低了部分耗时，但不保证消除卡顿，不应视为已经修复。遇到此问题可用上述单语言按住切换方式查看日志。
- **原因涉及排版和解析，不只是字体绘制。** 双语使用游戏的原生注音布局，日志会集中处理历史文本，并在显示期间反复解析部分控件。改变副语言颜色或透明度不会移除这些工作。
- **首次语言准备需要时间。** 首次连接、使用尚未缓存的语言组合或游戏资源变更时，需要解析本机资源。初始化会自动进行，完成后显示副语言；这与日志开页卡顿是不同阶段。
- **覆盖和空间仍有边界。** 无法可靠配对的文本保留原文，图片／影片内的文字不处理。双语不会自动增大游戏的固定文本框，长文本或较大字号仍可能拥挤；可调小字号，或改用单语言模式。完整游戏及所有语言组合尚未全部验证。
- **正常对白按脚本调用身份区分。** 相同原文可对应不同译文，新对白与日志应保存各自的调用身份。旧日志不一定保留唯一身份；无法恢复时显示稳定选择的官方候选译文，可能与原场景不完全一致，不将候选冒充原对话 ID。项目的资源审计分别报告精确配对、候选兜底和未覆盖项，开发检查入口见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 自动更新

“更新”页的 **自动更新** 默认开启：启动时和每 6 小时检查稳定版，在后台下载并校验，游戏连接结束后安装。完成后界面自动重载，保留设置、缓存及窗口状态。关闭自动更新后，仍可手动检查版本。

## 常见问题（FAQ）

<details>
<summary>已经退出工具，安装器为什么仍提示正在运行？</summary>

0.3.15 及更早版本的游戏连接会保留到游戏退出，因此可能仍被安装器检测到。请先保存并退出游戏，再从托盘退出工具后重试。

从 0.3.16 起：从托盘选择“退出工具”会关闭双语效果，并等待界面、后端和准备进程全部结束，完成后托盘图标才消失。游戏继续运行，重开工具可恢复双语；收起或隐藏界面仍保持连接。旧版本已经建立的连接需要先随游戏正常退出一次，才能使用新的退出机制。

</details>

<details>
<summary>不想安装，怎样使用便携版？Release 里其他文件是什么？</summary>

从 Release 下载不带 `app` 或 `runtime` 后缀的完整 `bilingual-sora-2nd-版本-windows-x64.zip`，解压到有写权限的独立文件夹，双击 **BilingualSora2nd.exe**。保留完整目录，不要单独移动 EXE。

`app`、`runtime` ZIP 和 `bilingual-sora-2nd-update.json` 供自动更新使用，GitHub 的 Source code 附件供开发者使用。更新器会复用未变化的运行环境，无需逐级升级。

</details>

<details>
<summary>旧版升级失败，或提示“更新包文件过多”怎么办？</summary>

从 **0.2.x** 升级：旧版更新器无法安装内置运行环境，需要一次手动迁移。退出旧工具，将新包解压到新目录，复制旧目录的 `generated/native-control.json` 和 `generated/overlay-window.ini`（不要复制 `.venv/`、`generated/updates/` 或旧热加载清单），再运行新 EXE。之后便携版的程序和依赖都支持自动更新。开发目录继续保留，不覆盖其源码。

0.2.2 的“更新包文件过多”也是旧更新器限制，请按上述步骤迁移。0.3.0–0.3.3 首次自动升级仍下载完整包，之后使用组件更新。

</details>

<details>
<summary>如何覆盖安装或卸载？</summary>

覆盖安装或卸载前，从托盘退出工具并结束游戏连接。重新运行最新版安装器即可覆盖安装；也可从 Windows“已安装的应用”中卸载。个人配置保留，安装器不会强行关闭游戏。

</details>

<details>
<summary>字库自动准备失败，怎样排查？</summary>

通常无需手动操作。仅在自动准备失败时，可用下列命令排查或重试：

```powershell
$runtime = Get-Content runtime/current.txt
& ".\runtime\$runtime\python.exe" -m sora_bilingual.fonts.install_font_patch --game "你的游戏安装目录" --install
```

安装器随程序附带经过审计的 [sora2looseload](https://github.com/lmaple0/sora2looseload) 加载器，SHA-256 为 `e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7`。摘要不匹配时不会跳过校验或覆盖其他 Mod 的文件。

</details>

<details>
<summary>自动更新失败后怎样恢复？配置保存在什么位置？</summary>

更新失败时，“更新”页提供下载与日志入口，可下载最新安装 EXE 重新安装。

更新包在后台下载并核验仓库、版本、文件清单及 SHA-256。游戏连接期间等待，连接结束后安装；完成后控制界面自动重载，恢复位置和展开／隐藏状态。配置和缓存保留在 `generated/`，内置依赖位于 `runtime/`。安装发生中断时，下次从快捷方式启动会先完成提交或恢复旧文件。备份在 `generated/updates/backup-*`。

自动更新只适用于带 `installed-manifest.json` 的发行包安装。Git 开发目录及被手工改动的软件文件不会被覆盖。运行环境更新会写入新的版本目录，界面重载后切换；不覆盖正在使用的 Python/DLL。旧运行环境保留供恢复，可能占用额外磁盘空间。预发布、草稿和旧版本不会自动安装。

</details>

## 开发和发布

<details>
<summary>开发环境、测试与发布命令</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m tools.dev check
```

`tests/check_overlay_update.py` 使用独立配置验证真实 Qt 界面重载；不会连接游戏。`tests/check_native_transport.py` 需要本地资源，只附加自己创建的测试进程。它们不属于 CI 的无游戏单元测试。

开发修改通过 `python -m tools.dev publish-local` 语法检查并原子发布本地热加载清单；界面和文本逻辑自动切换，底层驻留钩子更新等待游戏下一次启动。不要在游戏运行时强杀或卸载注入脚本。

工程布局与依赖规则见 [架构说明](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/ARCHITECTURE.md)，日常修改流程见 [贡献指南](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/CONTRIBUTING.md)。

本轮文本覆盖、日志身份和未验证项见 [文本核查报告](docs/verification/README.md)。离线检查、本地候选与实机验收分别记录。

维护者同步修改 distribution.json 和 pyproject.toml 版本后推送 `vX.Y.Z` 标签。GitHub Actions 在 Windows 上验证测试，从明确的文件白名单构建完整 ZIP、更新组件及离线安装器，通过便携版启动和安装器检查后，上传到草稿 Release 并一起公开；后续客户端自动发现。手动构建：

```powershell
$distribution = Get-Content distribution.json | ConvertFrom-Json
.venv\Scripts\python.exe -m tools.build_portable --version $distribution.version --repository $distribution.repository
```

仓库仅在文档中收录精选演示截图；发行包不附带这些图片。发布包和仓库不包含游戏资源包、从游戏生成的字库、完整文本索引、日志或用户配置。报告问题时请附工具版本、游戏版本、语言组合与精简错误信息，避免上传完整游戏数据。

</details>

## 许可

项目代码使用 [MIT](LICENSE)。第三方代码与格式参考见 [THIRD_PARTY.md](THIRD_PARTY.md)。游戏、商标和游戏资源属于其权利人；本项目为非官方工具。

## 致谢

感谢以下开源项目及其维护者，让这个工具得以实现：

- [0xDC00/scripts](https://github.com/0xDC00/scripts)，以及 Tom（tomrock645）：游戏文本钩子的调用点签名参考与衍生代码。
- [FPACker](https://github.com/coinkillerl/FPACker)、[Ingert](https://github.com/Aureole-Suite/Ingert)：资源容器与脚本格式参考。
- [sora2looseload](https://github.com/lmaple0/sora2looseload)：随本工具分发的游戏字库加载器。
- [Frida](https://github.com/frida/frida)：运行时原生文本处理；[Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)：设置与状态界面。
- [pygame-ce / SDL](https://github.com/pygame-community/pygame-ce)：手柄输入；[pefile](https://github.com/erocarrera/pefile)：PE 文件读取；[python-lz4 / LZ4](https://github.com/python-lz4/python-lz4)：字库纹理压缩。
- [Inno Setup](https://jrsoftware.org/) 及 [简体中文翻译](https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation)：Windows 安装向导。

依赖按各自许可证提供；引用代码的声明保留在 [THIRD_PARTY.md](THIRD_PARTY.md)。
