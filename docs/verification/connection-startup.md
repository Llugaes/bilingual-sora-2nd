# 0.3.17 连接启动与状态验证

## 现场证据与修复

0.3.16 的连接日志表明映射准备约 3.7 秒即完成，随后 `startcontrol` 报
`frida.InvalidOperationError: script has been destroyed`，未进入 `connection_ready`。
清理时旧 RPC 再次报错，最终状态写入被跳过，留下 running=true / connecting。
游戏和后端退出后，UI 仍采用过期 phase；另一条件还把已就绪的常驻后端当作连接中。

原因是初始化过早调用 `Script.eternalize()`，使 Python Script RPC 失效。
现在先创建认证控制通道，再移交脚本所有权，后续只使用新通道。失败清理保留原始
异常并写入停止状态；无法移交所有权的特殊异常继续遵守不热卸载游戏钩子的约定。
连接展示统一读取新鲜心跳、实际游戏存在状态和错误；ready 与后端存活分别处理。

阶段卡片提供彩色边框、大标题、具体说明及不定进度。准备字体／映射为黄色，
识别／关联／应用为蓝色，就绪为绿色，异常为红色。无需靠颜色单独判断状态。

## 回归证据

- `tests/check_native_control.py` 已改为四次调用生产 `NativeLabels.attach`，在自建隐藏
  宿主中使用真实 Frida；首次连接、正常退出、断线停用和重连均覆盖。只替换依赖游戏
  地址的脚本体，不替换 attach、publish、eternalize 或 Script RPC。
- 修改前该检查重现同一 `script has been destroyed`；修改后通过。
- 两项 UI 回归修改前失败、修改后通过：过期 connecting 不锁死按钮；fresh ready
  加存活后端仍显示已连接。
- 初始化与清理同时抛 destroyed 异常的回归确认最终 running=false、原始错误保留、
  驻留锁关闭。
- `tools.dev check`：416 项 Python 测试通过（5 项按条件跳过）、151 项 JavaScript
  检查通过，全部隐藏原生宿主检查通过。未运行真实游戏测试。
- `tests.render_connection_preview` 使用真实 Qt 控件离线生成中英日阶段预览，检查
  卡片与设置区域不重叠，并人工检查文字、颜色与边框。无游戏和用户设置副作用。

本机证据位于 generated/diagnostic-144-*.log 与 generated/connection-states-*.png，
不包含在发行包。真实游戏画面与继续游玩需在用户下一次正常游戏进程中确认。
