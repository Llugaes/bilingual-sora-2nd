# Bilingual Sora 2nd v0.3.5

## 简体中文

- 修复“已是最新稳定版”时仍显示“下载完整包”的误导：下载入口与恢复说明仅在自动更新失败时出现，恢复正常后隐藏。
- 从 0.3.4 升级只需下载程序组件，复用现有依赖；配置保留。

## English

- Hide the recovery download button when updates are healthy, including when already up to date. Show it with recovery instructions only after an update failure, and hide both once recovered.
- Updates from 0.3.4 reuse existing dependencies and download only the application component. Settings are retained.

## 日本語

- 最新版でも表示されていた復旧用ダウンロードボタンを修正しました。更新失敗時のみ復旧手順とともに表示し、正常に戻ると非表示にします。
- 0.3.4 からは既存の依存関係を再利用し、プログラム部分だけを取得します。設定は保持されます。

## Downloads

For a new installation, choose `bilingual-sora-2nd-0.3.5-windows-x64-setup.exe`, or the complete portable `bilingual-sora-2nd-0.3.5-windows-x64.zip`. The `app` / `runtime` ZIPs and JSON manifest are for the updater.

Version 0.2.2 requires manual installation because of its old updater's file-count limit. Exit the old tool before migrating settings; see the [README](https://github.com/Llugaes/bilingual-sora-2nd#readme).
