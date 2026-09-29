# Bilingual Sora 2nd v0.3.23

## 简体中文

- 修复托盘退出误报“后端尚未安全退出”：Windows 保留已结束进程的句柄时，仍能正确确认进程结束，关闭工具并允许重新打开连接。
- 任务管理器中使用明确的进程名：`BilingualSora2nd.UI.exe`、`BilingualSora2nd.Backend.exe`、`BilingualSora2nd.Worker.exe`，描述中也显示工具名称，方便识别。
- 保留设置、语言缓存及正常退出时的效果恢复。不会关闭游戏。

本版是退出问题的加急修复。首次免重启安装的 HUD 乱码、游玩卡顿及设置页调整仍在调查，不包含在本版修复声明中。

## English

- Fix tray exit incorrectly reporting that the backend has not stopped when Windows retains a handle to an already terminated process. The tool can exit and reconnect after reopening.
- Use identifiable Task Manager process names and descriptions: `BilingualSora2nd.UI.exe`, `BilingualSora2nd.Backend.exe`, and `BilingualSora2nd.Worker.exe`.
- Preserve settings, language caches and normal effect restoration on exit. The game is not closed.

This is an urgent exit fix. First-install HUD corruption without a game restart, gameplay stuttering and settings-page changes remain under investigation and are not claimed as fixed in this release.

## 日本語

- 終了済みプロセスのハンドルを Windows が保持している場合に、バックエンドが終了していないと誤判定する問題を修正。トレイから終了し、再起動後に再接続できます。
- タスクマネージャーで識別しやすいプロセス名と説明を使用します：`BilingualSora2nd.UI.exe`、`BilingualSora2nd.Backend.exe`、`BilingualSora2nd.Worker.exe`。
- 設定と言語キャッシュ、終了時の表示復元を維持します。ゲームは終了しません。

本版は終了問題の緊急修正版です。ゲーム起動中の初回導入時に発生する HUD 表示異常、プレイ中の処理停止、設定画面の変更は引き続き調査中で、本版の修正対象には含みません。
