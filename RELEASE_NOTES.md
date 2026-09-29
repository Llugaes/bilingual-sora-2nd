# Bilingual Sora 2nd v0.3.17

## 简体中文

- 修复 0.3.16 的首次连接回归：初始化提前释放了控制句柄，导致双语无法连接。
- 修复游戏或后端退出后仍显示“正在连接”，以及已连接时仍把常驻后端误判为连接中的问题。失败会保留原因并恢复重试入口。
- 新增醒目的阶段状态卡：字体／映射准备为黄色，识别语言／关联进程／应用映射为蓝色，就绪为绿色，失败为红色。每个阶段都有大标题、说明和进行中提示。

完整生产连接入口已在独立原生宿主中通过首次连接、退出、断线及重连回归；中英日界面经过离线渲染检查。真实游戏画面仍需下一次正常启动确认。设置与缓存保留。

## English

- Fix a first-connection regression in 0.3.16: initialization invalidated the control handle too early, preventing bilingual connection.
- Stop showing “Connecting” after the game or backend exits. A connected resident backend is no longer mistaken for an unfinished connection. Failures retain their cause and allow retry.
- Add prominent stage cards: yellow for font/mapping preparation, blue for language detection/connection/mapping application, green for ready, and red for errors. Each stage includes a heading, explanation, and activity indicator.

The production connection entry passed initial connection, exit, disconnect, and reconnect checks in an isolated native host. Chinese, English, and Japanese UI previews were reviewed offline. Actual game display still needs confirmation on the next normal launch. Settings and caches are preserved.

## 日本語

- 0.3.16 の初回接続の不具合を修正しました。初期化中に制御ハンドルが早く無効になり、二言語表示に接続できなくなっていました。
- ゲームやバックエンドの終了後も「接続中」が残る問題と、接続済みの常駐バックエンドを接続中と誤判定する問題を修正しました。失敗理由を表示し、再試行できます。
- 処理段階を大きな状態カードで表示します。フォント／マッピング準備は黄色、言語確認／接続／適用は青色、準備完了は緑色、エラーは赤色です。見出し、説明、処理中の表示を備えます。

実際の接続入口を使い、独立したネイティブホストで初回接続・終了・切断・再接続を検証しました。中英日の画面もオフラインで描画確認済みです。ゲーム画面は次回の通常起動時に確認が必要です。設定とキャッシュは保持されます。
