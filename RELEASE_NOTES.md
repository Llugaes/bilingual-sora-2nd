# Bilingual Sora 2nd v0.3.16

## 简体中文

- 修复合法语言缓存被误判为损坏、导致后续启动反复构建映射的问题。相同资源和语言组合复用已有缓存；首次构建仍可能需要数分钟。
- 托盘“退出工具”现在关闭双语效果，等待界面、后端和准备进程全部结束后再移除图标。游戏继续运行，重新打开工具可恢复双语。
- 初始化期间退出会取消准备任务并回收子进程；重新连接复用游戏内的停用模块，避免重复安装钩子。

通过自动回归、独立原生宿主的退出／重连检查及完整缓存加载验证。真实游戏画面恢复与不同电脑上的加载耗时仍需实机反馈。

从 0.3.15 或更早版本升级时，请先正常退出游戏，结束旧连接后检查更新。新退出机制需下一次游戏启动后生效；个人设置与缓存保留。

## English

- Fix valid language caches being rejected as corrupt, causing repeated mapping builds on later launches. Unchanged resources and language selections reuse the existing cache; the first build can still take several minutes.
- Tray **Exit tool** now disables bilingual effects and waits for the UI, backend, and preparation processes to end before removing the icon. The game keeps running, and reopening the tool restores bilingual display.
- Exiting during initialization cancels preparation and its child processes. Reconnecting reuses the disabled in-game module instead of installing hooks again.

Verified with automated regression tests, exit/reconnect checks in an isolated native host, and full-cache loading checks. In-game display restoration and loading times on other computers still need gameplay feedback.

When upgrading from 0.3.15 or earlier, exit the game normally to end the old connection, then check for updates. The new exit mechanism takes effect on the next game launch. Settings and caches are preserved.

## 日本語

- 正常な言語キャッシュを破損と判定し、次回以降もマッピングを再構築する問題を修正しました。リソースと言語設定が同じ場合は既存キャッシュを再利用します。初回構築には引き続き数分かかる場合があります。
- トレイの「ツールを終了」で二言語表示を無効にし、画面・バックエンド・準備用の全プロセスが終了してからアイコンを消します。ゲームはそのまま続けられ、ツールを開き直すと二言語表示を再開できます。
- 初期化中の終了では準備と子プロセスを停止します。再接続時はゲーム内の停止済みモジュールを再利用し、フックを重複して導入しません。

自動回帰テスト、独立したネイティブホストでの終了・再接続、完全なキャッシュの読み込みを検証しました。実際のゲーム画面の復元と別の PC での読み込み時間は、引き続き実機での確認が必要です。

0.3.15 以前から更新する場合は、ゲームを通常終了して旧接続を終了してから更新を確認してください。新しい終了方式は次回のゲーム起動から有効になります。設定とキャッシュは保持されます。
