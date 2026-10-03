# 0.4.0 — 恢复排版，改为手动更新

撤回 0.3.34 引入的多行高度改动，恢复 0.3.33 的游戏排版行为，避免菜单、提示框和普通对话被异常拉长。保留 0.3.35 的连接入口校验修复。此前报告的少数多行提示拥挤暂未解决，后续先提供本地候选实测。

更新现在只自动检查和提醒。用户点击“下载安装”并确认后才会更新；游戏仍连接时需要退出游戏后再次点击，不会自动排队安装。已有自动更新配置迁移为只检查。

支持选择历史稳定版本回退，保留配置，并关闭旧版自动更新，防止再次自动升回问题版本。此后的正式版本必须经过本地实机验收；CI 只生成草稿发行版。

已安装 0.3.34／0.3.35 的用户可更新到 0.4.0。请先正常退出游戏再安装；当前进程中的旧排版代码需要新游戏进程才能替换。

## English

Restores the game layout behavior of 0.3.33, withdrawing the multiline-height change that stretched menus, popups and dialogue boxes. The 0.3.35 connection-preflight fix remains. Some crowded multiline hints are still a known limitation.

Updates now check and notify only. Download and installation require explicit confirmation; an active game connection requires a manual retry after the game exits. Previous automatic-install preferences become check-only.

You can select an older stable release to restore, preserving settings and disabling legacy automatic updates. Future stable releases require in-game acceptance; CI creates drafts only. Exit the game before installing 0.4.0, then relaunch it to replace the resident layout code.

## 日本語

メニュー・説明ウィンドウ・会話が縦に伸びる原因となった複数行の高さ変更を撤回し、0.3.33 のレイアウトに戻します。0.3.35 の接続時チェック修正は保持します。一部の複数行説明が窮屈になる問題は引き続き確認中です。

更新は自動確認と通知のみになります。ダウンロード・適用には明示的な確認が必要です。ゲーム接続中の場合は終了後にもう一度適用してください。以前の自動更新設定は確認のみに移行します。

設定を保持して過去の安定版に戻せます。旧版の自動更新はオフにします。今後の正式版は実機確認後に公開し、CI は草稿のみ作成します。0.4.0 の適用前にゲームを終了し、適用後に起動し直してください。
