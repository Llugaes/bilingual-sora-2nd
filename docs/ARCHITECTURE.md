# 工程结构与契约

这个仓库只负责《空之轨迹 the 2nd》。其他游戏可以建立同命名系列仓库；在第二个真实接入需求出现之前，不引入通用游戏插件框架或工厂层。

## 模块职责

| 目录 | 职责 | 不承担的工作 |
|---|---|---|
| sora_bilingual/app | Qt 界面、展示状态、自动连接调度 | 游戏文本解析、资源下载 |
| sora_bilingual/game | 受版本约束的 Frida 接入、原生脚本、后台生命周期 | UI 控件、网络更新 |
| sora_bilingual/localization | 本地资源解析、身份映射、文本编译、索引缓存 | Qt、进程附加、网络 |
| sora_bilingual/config | 语言元数据、配置规范化、显示动作策略 | 资源扫描、视图创建 |
| sora_bilingual/platform | Windows 进程与输入、SDL 手柄 | 游戏翻译业务 |
| sora_bilingual/fonts | 本机字库合并、校验和可恢复安装 | 分发游戏字库 |
| sora_bilingual/updates | GitHub 协议、后台检查、安装事务、本地热更新 | Qt、游戏钩子 |
| tools | 构建、验证、诊断 | 运行时依赖 |
| tests | 单元、契约、故障恢复和独立进程验证 | 自动启动游戏 |

launch.py 是稳定桌面入口，bootstrap.py 是组装入口：先恢复未完成的安装，再导入 Qt 应用。模块层级依赖由 tests/test_architecture.py 检查；运行代码不能反向导入开发工具。早期 overlay 的兼容测试实现归档在 legacy，不进入发行包。

## 状态和副作用

- paths.py 是安装根目录与持久化目录的唯一定位入口。进程以模块方式启动，并明确设置工作目录；不依赖调用者当前目录或固定 Steam 盘符。
- 所有用户状态保存在 generated/；安装清单只管理明确拥有的程序文件。目录重构不移动配置、字体安装记录或索引缓存。
- ActionPolicy 按选定模式处理同一个 switch_binding 的按下、按住和松开。Hold / Toggle 输出主或副语言单语；annotation 使用本游戏的原生注音能力。旧 hotkeys 仅作迁移来源，运行时不再同时监听三个动作。原生后端是“当前已生效模式”的事实来源。
- ui_language 与游戏语言独立。app/i18n.py 保存中英日界面文本，app/ui_widgets.py 保留 Qt 控件的源文案并在语言改变时重新翻译；不改动游戏文本模型。app/presentation.py 只把状态转换成可显示内容，不创建 Qt 对象、不访问文件。
- 资源缓存的语言依赖只包含档案名称映射，界面名称和默认偏好不参与失效判断。编译器代码及游戏资源变化仍使缓存失效；旧索引必须匹配资源和旧解析器指纹才能迁移。模型构建复用全局配对结果，缓存通过 C JSON 编码器原子写入。
- ConnectionPolicy 按 PID 和进程创建时间去重。界面与后端为不同进程；收起、隐藏、退出界面都不卸载游戏钩子。
- ModelPreparation 负责异步编译、丢弃过时结果。编译器在短期工作进程中运行；已连接的驻留脚本使用分块事务接收新索引，失败保持旧索引。
- GitHubClient 封装网络和协议校验；UpdateService 只负责策略与后台调度；update_installer 负责包验证、互斥锁、备份和恢复日志。测试通过客户端替身和临时安装根目录验证同一个接口，不需要公网或游戏。

## 更新协议

发行包格式为协议 1：ZIP 加 SHA-256 清单。安装时只接受根目录程序文件、sora_bilingual/ 中的 Python/JavaScript 和图标资源；拒绝路径穿越、Windows 保留名、链接和本地文件冲突。

安装先获得后端互斥锁，再写备份与 prepared 日志，原子替换程序文件，最后记录 committed 并发布热加载清单。未提交中断恢复旧文件；已提交中断补完热加载清单。运行中不替换 Python 依赖或游戏 DLL。

发布文件由 release-files.json 明确列出。架构测试验证完整运行时已列入、开发工具与本地状态未列入。GitHub Actions 只有带版本标签、测试通过的提交能发布；全部资源先传到草稿，随后公开。版本一致性同时检查标签、distribution.json 与 pyproject.toml。

## 扩展方式

- 新增语言：维护语言元数据和资源规则，不在 UI 或渲染器中添加语言对专用分支。
- 新增文本表：扩展结构解析与身份对齐，补最小合成输入和跨语言回放，不用截图 OCR 兜底替换。
- 支持新游戏 EXE：新增并验证版本契约，再修改原生接入；不放宽现有摘要门槛。
- 新增界面选项：先定义配置含义和后端确认方式，再接入视图。不得让 UI 提前宣称尚未应用的状态。
- 新增更新格式：同步客户端验证、构建器与中断恢复测试；不能只修改打包脚本。

## Windows 便携发行

`tools/build_portable.py` 在构建端校验官方 CPython 压缩包，安装固定版本的 wheel，保留许可证，再调用文件白名单打包器。用户端不运行 pip。`BilingualSora2nd.exe` 是短生命周期 GUI 启动器，读取 `runtime/current.txt` 并启动对应内置 Python；不依赖 PATH。

发行环境仅保留应用使用的 Qt Core、Gui、Widgets、Network 绑定及窗口、样式、图片、网络插件，并通过 PE 普通和延迟导入递归保留其 DLL 依赖。软件 OpenGL 回退、VC 运行库与许可证保留；QML、Qt 开发工具和 pygame 示例、测试、文档正文不进入发行包。新增 Qt 模块时同步构建根集合；测试检查应用导入以及成品图标、SVG、样式、TLS 和 SDL 输入初始化。ZIP 使用标准 Deflate 压缩，Windows 资源管理器即可解压。GitHub 附件直接展示 `bilingual-sora-2nd-<version>-windows-x64.zip` 文件名，使用说明放在发布正文。

运行环境目录使用内容摘要作为标识，不可原地修改。同一环境的文件更新时跳过，新依赖写入新目录；旧环境保留，界面重载通过 EXE 选择新环境。更新日志仅备份有变化的文件，配置与缓存仍在 generated。首次运行打开设置；后续双击复用常驻实例。

CI 在无游戏环境运行提取后 EXE：清除 PATH 中的 Python，测试含空格/中文路径、全部依赖导入、隐藏恢复、真实 UI 热重载和单实例。开发检查仍使用 source-only 小包，发行流水线只发布便携 ZIP 与统一更新清单。
