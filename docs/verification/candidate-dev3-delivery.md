# 1.0.0-dev3：候选辨识与安全启动交付

2026-10-05，本轮仅补充 DEV 辨识、最小回归、重新打包、启动及交付校验。三阶段范围和原始证据见 [综合候选说明](comprehensive-candidate.md)，没有重做或扩展实现。原 `comprehensive-1.0.0-dev2`、其摘要与测试证据保留。

## 可用候选

- 候选 ID：`comprehensive-1.0.0-dev3`；DEV 显示：`1.0.0-dev3`。
- 目录：`<CHECKOUT>\dist\comprehensive-1.0.0-dev3\DEV`。
- 明确启动入口：`Start-1.0.0-dev3.cmd`，调用本目录 `BilingualSora2nd.exe --expanded`。用户验收前由执行者启动，不要求用户自行打开 DEV。
- 标题栏、展开面板品牌、托盘提示、关于页显示 DEV 候选号。正常安装的稳定版不使用 DEV 后缀。
- 本体及包协议版本仍为 `0.4.2`：当前更新、组件和安装校验使用三段稳定版本，未为候选改动该协议、稳定版本、tag 或远端。`dev-manifest.json` 单独保存候选 ID、显示版本、目标版本和验收 pending。
- `packages/bilingual-sora-2nd-0.4.2-windows-x64.zip` 是经既有安装协议校验的程序载荷；实际验收使用上面的完整准备 DEV 目录及其候选标识。单独解压这个载荷会使用稳定包标识，不包含准备好的游戏缓存／字体或 DEV 启动入口。

程序 ZIP：109,227,387 bytes，SHA-256：

`4d8d7da6f7751725b02f9e86dbd63a2cb4d1c29d93584db4c311b3db78eb5d86`

启动并正常退出后的 DEV 全目录快照：5,357 文件、2,458,878,545 bytes；清单 `generated/comprehensive-1.0.0-dev3-delivery/candidate-files-sha256.json`，SHA-256：

`b0c38e93f6fc1b3cb225302215c7fc19d7ba031ddd19d70eb508c325b51a332d`

664 个包受管文件逐一校验，当前分发源码漂移为空。旧 dev2 的5,354文件和旧 ZIP 摘要亦逐一核对不变。驻留 JS 摘要仍为 `8a8aae4a6fd4d6b5f961ce86995c172052e3db638b5a7bcf40b8d0c43a00d78f`。

## 回归口径与证据

本轮证据：`generated/comprehensive-1.0.0-dev3-delivery/`。

| 证据 | 结果与边界 |
|---|---|
| `minimal-regression.log` | 本轮76运行、76通过、0跳过、0失败；包含 DEV 标识、稳定版抑制／坏清单边界、Qt 面板／托盘／关于页、正常离线生命周期、更新和架构回归 |
| 原 `python-tests-history.log` | **608 是总运行数：603通过、5跳过、0失败**；原完整门槛未在本轮重复，也不能写成608全部通过 |
| 原 `javascript-tests.log` | 179通过；JS 未改动，沿用原证据，不称为本轮重跑 |
| `startup-smoke.json` | 真正程序 EXE／Windows UI 启动、状态和退出通过；不是离线渲染图 |
| `final-verification.json` | 新旧包／受管文件／全目录摘要、源码漂移、原 ITERATION_PLAN 摘要、退出状态核对通过 |
| `candidate-font-preparation.json` | 新目录通过正常准备入口生成，healthy、11,902字形；没有复制旧字体缓存、写游戏或更改旧受限 ACL |

本轮 Ruff 与格式检查、diff 空白检查通过。除 DEV 辨识与只读状态字段外，模型／解析／驻留代码没有再次变化，因此不重复无关全量回放。

## 实际启动与旧 UI 状态

旧 UI PID55144 的实际路径确认是 `E:\Bilingual Sora 2nd DEV\runtime\bac6e42e94e62356\BilingualSora2nd.UI.exe`。旧 UI 的受支持 `status` IPC 返回 `QLocalSocket::connectToServer: Access denied`；两次只读磁盘快照不变，但 `native-live running=false` 属于静态旧记录。不能证明实时构建／注入写入／录制／未保存编辑已结束，故**没有关闭旧 UI**，也没有再尝试绕过该拒绝。证据 `old-ui-readonly.json`。

单实例按 control 的绝对路径隔离；smoke 使用项目内独立 `ui-smoke-state/native-control.json` 和 `--no-auto-connect`。配置、退出信号及窗口状态均落到独立状态目录。该模式不创建 AutoConnector；自启动更新检查也未启用。自动连接代码只识别 `sora_2nd.exe`，本轮没有启动连接器或任何游戏，不干扰前作 QA／离线 adapter。

真实候选 UI PID55080，实际路径位于新 DEV 的 `runtime/bac6e42e94e62356/BilingualSora2nd.UI.exe`；启动约1.032秒。实际 UI 状态确认展开、`auto_connect=false`，窗口标题 `Sora Bilingual · DEV 1.0.0-dev3`。日志只有 pygame 启动信息，无异常；没有后端进程、状态文件或游戏附加。

通过受支持 `quit` 完成正常退出，候选进程及 IPC 端点均结束，没有强杀。旧 PID55144保留，旧控制／窗口／状态文件摘要不变。smoke 独立配置也未变化。当前没有可用的原生 GUI 截图工具，**没有目视实际窗口像素**；之前的离线 Qt 图只保留其原证据含义。

## 性能及待验收边界

仍按原实测口径：缓存关闭基线67.767秒，新组合对调47.171秒，该样本减少约20.6秒；首次缓存87.279秒，完整模型热读1.489秒。新组合仍有配对、身份关联及序列化成本。这是同机会话单次样本且测量期间有回归负载，不是严格隔离排名；用户没有设定1–3秒硬指标，不新增该要求。

用户实机仍 pending：主动语音 P0 和 Joshua 的现场 source/key/scope/var、效果／副文位置、宽度与注音像素、真实语言切换性能及硬件录制。启动 smoke 不替代这些验收，不把旧 Mod EXE 样本通过扩大为全覆盖保证。

## 最短明早步骤及恢复

1. 父 Planner 协调确认旧 UI 没有用户工作后，通过旧工具托盘“退出工具”正常退出；当前执行环境无法可靠查询／关闭它，不能强杀。只关闭游戏外的旧工具，不关闭任何未知游戏进程。
2. 执行者确认旧 UI 已退出，再自动启动项目内 `Start-1.0.0-dev3.cmd` 对应候选。项目内运行不需增加文件写根；启动前再只读检查游戏／字体状态。本轮没有留下新候选驻留进程。
3. 用户以新游戏进程，先游戏简中／主日副简中复测主动语音四句，再游戏英文／主英副日复测 Joshua、HP／CP Regen；顺带核对水泵分段、窄宽界面、注音，再验证 Swap、三主题状态和快捷操作。
4. 父记录明确通过或失败；失败继续修复→新候选→DEV验收。最终明确通过前，禁止 push／CI／tag／正式发布／公告。

退出新候选用其托盘“退出工具”，窗口×只隐藏。恢复旧 DEV 可在新工具正常退出、确认没有旧驻留游戏冲突后运行旧 `E:\Bilingual Sora 2nd DEV\BilingualSora2nd.exe`；本轮旧目录／配置／游戏／存档未改，不需恢复文件。项目内候选均留存。

如选择部署到旧外部 DEV，仍需为 **`E:\Bilingual Sora 2nd DEV`** 提供明确写权限并协调正常退出旧 UI。具体动作延用综合说明：逐文件备份可读的包受管应用／清单以及 `generated/native-control.json`、`game-location.json`、`overlay-window.ini` 到该目录内独立备份目录，再更新新包受管文件、DEV候选清单／启动入口和经核对的新模型／wire／语言事实缓存；相同 runtime 文件按摘要复用。不得整目录复制、读取／覆盖受限字体缓存或触碰存档；遇到拒绝停在具体动作。回退仅恢复已备份的应用／清单。项目外安装尚未执行。

仓库 `main`，HEAD `d62231fec5e11eeed79dfa201c8fe617c82d3587`；源码修改均未提交，列表见本轮 `git-status.txt`。原 `docs/ITERATION_PLAN.md` 摘要仍为 `fb0c2624e7e1d4463730b3125e4b837343e9b84b9f3bc1dcea07b699e73deb90`。实际策略：workspace-write、approval never、网络受限，仅项目可写；无权限扩张、远端操作或全局设置改动。
