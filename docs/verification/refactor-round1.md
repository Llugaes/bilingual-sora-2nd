# 第一轮等价重构：本地候选

状态：本地候选已构建、离线验证通过，等待用户实机验收。未 push、未创建公开发布、未覆盖现有安装、未启动或附加游戏。

## 来源与范围

- 基线：`70e00b4cdb74ad8295d4215641b3d2c85c6125fd`，包含当天性能分支及 1.0.1 开发代码。
- 分支：`refactor/behavior-preserving-round1`。
- 候选源码：`2923204ce96dc2d13457aa4d8c3dce00bfb0098a`。本记录是随后补入的文档，不改变包内代码。
- A：`a7c3590`，分离代码指纹，避免旧 catalog 迁移额外扫描；预建路径前缀集合，说话人检查移出语言循环。
- B：`db5d1fa`，分段发布 wire，流式读取已发布文件计算摘要；保留完整字节兼容接口。
- C：`1ec8f08`、`6d4d8df`，拒绝策略改为一份 Python 数据模块，JS 由它生成。最初的嵌套 JSON 被旧更新器拒绝，候选打包前已改回旧更新器支持的 Python 文件形式。
- D：`2bb02a9`，原子效果算法显式返回成员决定，组合器直接消费；历史失败表仍在原来的位置生效。
- `2923204` 补入架构说明，并使便携检查的模拟更新仅包含受管文件，不把 DEV 附加文件混进正式更新夹具。

UI、设置、字体、几何排版、原生钩子、原生传输读取端及驻留生命周期没有修改。`update_installer.py` 和 `pyproject.toml` 的最终内容与基线一致。此轮尚未消除 Python/JS 整套算法的双实现，也未将组合解析器变成纯函数。

## 本地交付

- 解压目录：`E:/_Proj/Self/sora-bilingual-validation/2026-10-10/refactor-round1/dist/refactor-round1/DEV`
- 启动文件：上述目录中的 `BilingualSora2nd.exe`。
- ZIP：`dist/refactor-round1/packages/bilingual-sora-2nd-1.0.1-dev1-r1-windows-x64.zip`
- ZIP 大小：109,351,196 字节。
- ZIP SHA-256：`f4c2e790e31ae115cbe85ae614011d6147bf0aaa328c4bf34d61d227981bb048`。
- 672 个受管文件逐一校验；552 个启动器/运行环境文件复用已验证的 1.0.1 包，运行环境 ID 为 `bac6e42e94e62356`。
- 运行环境来源 ZIP SHA-256：`8e153c7b151508adbd7e51942e2225a58aa6bfbf3dbb672a04064bab6d3a020c`。

ZIP 不包含游戏资源或用户配置。仅本机解压目录预置本轮重新构建并核对的 catalog/model/wire，保留文件时间以复用有效 wire；没有复制旧 agent 令牌、会话状态或字体缓存。可见设置和快捷键取自上一个 `p0-performance/generated/live-101-r4` 本地候选，原配置未被修改。候选更新策略关闭，避免验收期间自行换版。

已以 `--no-auto-connect --expanded` 打开独立候选，IPC 确认标题为 `Sora Bilingual · DEV 1.0.1-dev1-r1`、面板展开、自动连接关闭。用户启动游戏后可在面板中启动连接；此预览不代表已经完成实机验收。

## 验证证据

完整本地证据位于：`E:/_Proj/Self/sora-bilingual-validation/2026-10-10/refactor-round1-evidence`。

| 检查 | 结果 | 证据 |
|---|---|---|
| `python -B -X utf8 -m tools.dev check` | 退出码 0；Ruff、生成一致性通过；Python 813 项含 9 项跳过；Node 225 项全部通过 | `full-check.log` |
| 状态序列 | 旧版冻结的 11 组、31 个事件，两端返回/plan、调用顺序、完整有序失败表 SHA 一致；覆盖 19,999/20,000 容量边界 | `tests/fixtures/effect-member-sequence-baseline.json` 及 result tests |
| 既有 renderer/authority 回放 | 26 个测试、437 个顶层调用，返回和历史表完全一致 | `baseline-render-trace.json`、`candidate-render-trace.json` |
| 全量模型回放 | 205,103 个源文本 × 3 模式 = 615,309 个 plan，零异常，摘要一致 | `baseline-full-render.json`、`candidate-full-render.json` |
| 独立原资源效果 oracle | 362 个字段、4 个混合组、4 个独立组合拒绝、12 个负例，完整报告与基线一致 | `raw-effect-fixtures.json`、`baseline-raw-effects.json`、`candidate-raw-effects.json` |
| 包内 Frida V8 + 生产 indexed transport | 1,168 个输入 × 3 模式 × 冷/热两遍 = 7,008 个 plan，与冻结基线零差异；使用候选自带解释器和 JS | `packaged-v8.json`、`baseline-v8-corpus.json` |
| 便携成品 | 清除系统 Python、中文/空格路径、单实例、UI 重载、中断更新恢复、已加载 DLL 时的模拟更新均通过 | `portable-check.log` |
| 旧更新器兼容 | 旧 70e00b4 生产 archive/manifest/package 校验接受当前 124 个发行源码文件；未放宽任意嵌套 JSON 白名单 | `c2-legacy-updater-compatibility.json` |
| 本地候选 | 文件摘要、有效私有缓存、DEV 标识及离线面板 IPC 均通过 | `candidate-build.json`（在 dist/refactor-round1）、`local-handoff.json`、`candidate-ui.json` |

全量回放摘要：`6e92166afee4abddebfdd9a66c39eea22c29394f25284c4f38df18861e7c433e`。

完整生产重建使用当前安装资源、`zh-Hans → ja`、all scope。以下三个文件均逐字节一致；模型文件名因代码指纹变化而不同：

| 产物 | 字节数 | SHA-256 |
|---|---:|---|
| catalog | 326,964,644 | `5dc6a9081b20e028b39f05e67f2167770aaf0e95817daeee801ef3d3e9544e77` |
| model | 268,874,568 | `2ef13095cb216dd45c3b5f8f94be9f62342f4c3eaf71f5b9e62acb4c920253ae` |
| wire | 173,262,112 | `112c204528421a17b8c97d08f0df3e390b454fff8163e71c150f3becfbda23d0` |

详见 `model-artifact-equivalence.json`。资源记录数 838,095，完整语言配对记录 585,613，缺副语言记录 252,482，均保持原值；没有把缺译改算为成功。

## 性能观测

同机、相同 Python 3.14.3、相同资源和配置，分别使用新建工具缓存目录。没有清空操作系统文件缓存；各一次测量，不能视为稳定提升比例或游戏 FPS 结论。

| 指标 | 基线 | 候选 |
|---|---:|---:|
| 完整冷构建总耗时（含探针末尾 2 秒等待） | 200.79 秒 | 193.66 秒 |
| 完整冷构建峰值私有内存 | 2452.70 MiB | 2454.67 MiB |
| 完整冷构建峰值工作集 | 2339.42 MiB | 2245.50 MiB |
| 单独发布同一个 wire 的耗时 | 9.74 秒 | 9.27 秒 |
| 单独 wire 发布进程峰值工作集 | 1744.11 MiB | 1609.31 MiB |

分段发布样本的峰值工作集低约 134.8 MiB，完整流程的峰值私有内存仍约 2.40 GiB。主要编译内存问题尚未解决；本轮不宣称整体内存显著下降或实机帧率提高。全量 render 回放只作为等价检查，候选回放期间并行运行了 V8 检查，其耗时不作性能比较。

## 保留的边界与用户验收

- Python 的 9 项跳过来自旧 `generated/table-next.json`、本地 FNT 和研究 DDS 夹具缺失；没有生成替身以强行转绿。
- 默认命令中的 6 个原生 EXE 特定检查未提供所需 EXE，仍为 skipped：font_materials、size_metrics、log_inset、log_activation、log_commit、dynamic_identity。未修改其原有 EXE 摘要门槛。其余被执行的隐藏宿主检查通过。
- 全模型回放覆盖全局 source/mode；记录身份、scope 的既有测试独立通过。它不等价于每个真实控件、全部语言组合、真实字形/GPU、所有存档和实机 FPS 覆盖。
- 便携日志中的 `installed 1.0.2` 是临时目录内构造的更新夹具，不是发布或用户安装操作。
- 下一步仅需用户验收此确切候选：常用页面的文字/字号/颜色/换行/注音与原来一致，显示切换、按住显示、快捷键及退出恢复正常，并观察实际帧率和切换手感。未收到此候选的明确验收前不发布；候选代码变化后需重新验证。

架构边界见 [工程结构与契约](../ARCHITECTURE.md)。本轮没有重新尝试 1ST 移植。
