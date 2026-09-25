# Bilingual Sora 2nd v0.3.4

## 简体中文

- **推荐下载 `bilingual-sora-2nd-0.3.4-windows-x64-setup.exe`**：中／英／日文安装向导，当前用户安装，无需管理员权限；离线安装、开始菜单、可选桌面快捷方式、卸载均支持，配置保留。
- **程序与依赖分离更新**：依赖未变时只下载约 0.2 MiB 程序包，依赖变更时才获取运行环境。逐文件校验、安装互斥、失败回滚与下载缓存复用继续有效。
- 失败时提供恢复说明及安装器／完整包下载按钮，技术错误仅写日志。
- **0.3.0–0.3.3** 先自动下载一次完整包升级，之后使用组件更新。**0.2.2 的“更新包文件过多”是旧更新器限制**：请手动安装，退出旧工具后将 `generated/native-control.json` 和 `generated/overlay-window.ini` 复制到新目录。不要复制旧程序、.venv 或更新缓存。
- 完善多语言仓库描述、Topics 和三语 README 搜索入口。

## English

- Recommended: **bilingual-sora-2nd-0.3.4-windows-x64-setup.exe**. Offline per-user setup without administrator rights; English/Japanese/Chinese wizard, Start menu entry, optional desktop shortcut and uninstall. Settings are retained.
- Separate application/runtime updates: unchanged dependencies require only the roughly 0.2 MiB application package. Runtime updates are downloaded only when needed, with file verification, rollback and reusable downloads.
- Update failures offer recovery instructions and installer/complete-package download. Technical diagnostics stay in logs.
- **0.3.0–0.3.3:** one full automatic upgrade enables component updates. **0.2.2:** its file-count limit requires manual installation. Exit the old tool, then copy `generated/native-control.json` and `generated/overlay-window.ini`; do not copy old program files, .venv or update caches.

## 日本語

- **bilingual-sora-2nd-0.3.4-windows-x64-setup.exe** を推奨。管理者権限不要のオフラインインストール。日／英／中文ウィザード、スタートメニュー、任意のショートカット、設定を保持するアンインストールに対応。
- 依存関係が同じ場合は約 0.2 MiB のプログラム部分だけを取得し、必要な場合だけ実行環境を取得します。ファイル検証・ロールバック・ダウンロード再利用に対応。
- 更新失敗時は復旧手順とダウンロード入口を表示し、詳細はログに記録します。
- **0.3.0–0.3.3** は一度の完全版自動更新が必要です。**0.2.2 の「更新包文件过多」は旧更新器の制限**です。手動インストール後、旧ツールを終了して上記の設定ファイルを移行してください。

## Downloads

| File | Purpose |
|---|---|
| `bilingual-sora-2nd-0.3.4-windows-x64-setup.exe` | Recommended offline installer |
| `bilingual-sora-2nd-0.3.4-windows-x64.zip` | Complete portable alternative |
| `bilingual-sora-2nd-0.3.4-app-windows-x64.zip` | Updater only: application |
| `bilingual-sora-2nd-runtime-<id>-windows-x64.zip` | Updater only: dependencies |
| `bilingual-sora-2nd-update.json` | Updater metadata |

Validation covers Python/JavaScript tests, program-only updates with real loaded DLLs, corruption and rollback, offline install/repair/uninstall, retained settings, and protection against installing over a running runtime. No game was launched.

Supported game: Steam build **25386012**, EXE **1.03.2**. No game resources are distributed. See the [README](https://github.com/Llugaes/bilingual-sora-2nd#readme).
