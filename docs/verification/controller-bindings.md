# 手柄按键名称检查（0.3.21）

## 实现与边界

绑定仍保存原始设备 GUID、按钮、轴方向和阈值。新增的 `profile` 与 `label_style`
只描述显示名称，不参与快捷键匹配、冲突判断或游戏文本排版。
旧绑定连接对应设备即可识别；新录制绑定携带映射，断开或重启后也能显示。
无法取得 SDL 映射的输入保留原始编号，不按未知设备的轴序号猜测按钮。

设置页发现设备时，读取 pygame 所用 SDL 的设备类型与映射，按连接实例缓存。
断开后删除缓存，重连重新读取。后端 `InputManager` 不查询名称元数据。
同一设备的录制、已保存显示、手动切换样式共用格式化入口。
Steam Input 隐藏物理设备时，自动识别以操作系统暴露的设备为准，用户可选择名称样式。

## 检查结果

| 检查 | 结果与证据 |
| --- | --- |
| 真实设备读取 | pygame-ce 2.5.8 / SDL 2.32.10 读取已连接 DualSense，类型 PS5；实际映射 `lefttrigger:a4`、`righttrigger:a5` 显示 L2/R2，`leftstick:b7`、`rightstick:b8` 显示 L3/R3。仅只读查询，未模拟实体按键或操作游戏 |
| 设备差异 | 不同按钮序号、不同扳机轴号、扳机映射为按钮、帽开关方向、共享轴扳机、反向轴、正负半轴及按钮映射为摇杆方向均有回归 |
| Nintendo | 检查按钮标签／位置两种 SDL 配置下的 A/B/X/Y 顺序；单只 Joy-Con 横握、竖握与成对模式分别检查面键、SL/SR、L/R/ZL/ZR 与摇杆按下 |
| 旧配置与生命周期 | 检查按 GUID 或实例选择对应设备、不借用其他已连接设备的名称、拔插缓存失效、序列化后离线名称恢复、录制后真实输入匹配不变 |
| 设置与国际化 | 检查显示样式按动作保存、切换动作不回写配置、录制中禁用样式选择、清除绑定、无有效游戏状态时仍可识别设备；中英日实际 Qt 控件截图检查，长组合可换行 |
| 窄窗口／系统字号 | 0.3.20 发布前 CI 拦住英文页面横向溢出；本地用 17px 字号复现为 115px 溢出。表单与录制行统一允许自动换行，新增中英日控件回归通过；0.3.20 未发布 |
| 完整回归 | `python -m tools.dev check` 退出码 0：445 项 Python（5 项资源相关跳过）、161 项 JavaScript；可执行的隐藏原生检查通过，两个需要显式游戏 EXE 的检查跳过。本次未修改原生钩子 |
| 发行契约 | 新模块登记至发行文件与 UI／resident 重载清单；便携包检查新增真实 bundled SDL API 加载与格式化断言，由发布流水线执行 |

专项回归在 `tests/test_gamepad_labels.py`，设置页流程在 `tests/test_native_overlay.py`。
本地完整日志位于 `generated/controller-dev-check.log`，不随发行包分发。
Xbox、Switch 实体手柄尚未验收；自动化映射检查不等同于实体按键验证。

## 映射依据

- [SDL2 映射格式](https://wiki.libsdl.org/SDL2/SDL_GameControllerAddMapping)：使用映射中的按钮、轴和帽开关关系。
- [设备映射读取 API](https://wiki.libsdl.org/SDL2/SDL_GameControllerMappingForDeviceIndex)：返回字符串由 SDL 释放，代码使用 `finally` 保证释放。
- [Nintendo 按钮标签选项](https://wiki.libsdl.org/SDL2/SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS)：设备边界读取已有选项，不修改用户输入配置。
- [SDL 2.32.10 Switch 驱动](https://github.com/libsdl-org/SDL/blob/release-2.32.10/src/joystick/hidapi/SDL_hidapi_switch.c)：单 Joy-Con 的 mini-gamepad 与 combined 模式采用不同的语义键位，名称转换据此区分。
