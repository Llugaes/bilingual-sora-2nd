# 固定 Frida 回调内存修复

运行时依赖 `frida==17.18.0+sora.1`，来自官方 17.18.0 源码和本目录的单行补丁，不可退回未修补的 PyPI wheel。

`gum_v8_native_callback_invoke` 把 CPU context 的释放交给弱回调后，又提前删除弱句柄，使回调无法释放复制的 context。补丁只删除这次提前释放；所有 ABI、调用参数、业务解析及排版代码不变。

来源：[gumv8core.cpp](https://github.com/frida/frida-gum/blob/17.18.0/bindings/gumjs/gumv8core.cpp)、[gumv8value.cpp](https://github.com/frida/frida-gum/blob/17.18.0/bindings/gumjs/gumv8value.cpp)。上游源码及许可证仍归 Frida 作者所有。构建保留 wheel 的许可证。

## 构建与安装

在 Windows x64、Python 3.14、Node 22、Git、Visual Studio Build Tools 与 Windows SDK 环境运行：

```powershell
python -m tools.build_frida_runtime
python -m pip install --find-links build/frida -e ".[dev]"
python -m tools.dev check
```

首次构建使用临时目录下的短路径 `sora-frida-17180`；可用 `--build-root` 指定独立短路径。脚本固定上游提交、补丁摘要和微软编译器归档摘要；编译器解压到私有构建目录，不安装或替换系统工具链。Frida SDK 由该提交的上游构建程序下载。使用 x64 / V8，关闭跨架构兼容、独立工具和测试目标，不交付 Android/iOS/32-bit 组件。

输出 `build/frida/*.whl` 与 `build-receipt.json`；后者记录源码、补丁、wheel、扩展摘要与泄漏检查结果。配方或构建脚本变化会失效缓存。便携包的 runtime identity 同时包含实际 wheel 摘要，避免继续使用旧依赖。

`tests/check_native_callback.py` 在独立隐藏主机中执行 40 万次真实 NativeCallback，验证指针、64-bit 整数、浮点及 void ABI，并检查回收后原生堆增长。GC 只用于这项诊断检查；产品未增加 GC 定时器。普通 PyPI 17.18.0 在此检查中失败。

CI 仍仅生成 draft；这个构建入口不发布文件。切换驻留原生依赖必须重新启动游戏，不能向现有游戏重复安装。
