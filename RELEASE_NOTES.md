# Bilingual Sora 2nd v0.3.18

## 简体中文

- 修正放大对白的副语言被二次缩小；普通对话、逐字显示与日志共用字号处理，保留嵌套注解的独立行高。
- 增加游戏运行期间加载多语言字体：首次准备结束后直接应用，无需因字体准备而关闭游戏。自动寻找目录并复用缓存。
- 补齐脚本设置的说话人姓名在复制后的来源关联，包括“女子的声音”这一类名称。
- 游戏过程中的主动语音正文稍向下移，普通剧情对话的位置不变。

代码回归、隐藏原生宿主与打包启动检查已通过；新增字体加载和排版改动开放实机测试。已有设置与缓存保留。由旧版升级时，新底层代码在游戏下次正常启动后生效；这与首次字体准备免重启是两个不同环节。

## English

- Remove an extra shrink from enlarged secondary dialogue. Live dialogue, typewriter text, and history share size handling; nested readings retain independent height reserves.
- Load prepared multilingual fonts into a running game without a font-related restart. Game discovery and cache reuse remain automatic.
- Preserve script provenance when speaker names are copied, including generic voice labels.
- Move active-voice text slightly down without shifting ordinary story dialogue.

Code, isolated native-host, and packaged-launch checks passed. The new font-loading and layout changes are available for in-game testing. Settings and caches are preserved. When upgrading an older resident version, the new native code takes effect on the next normal game launch.

## 日本語

- 拡大された副言語が再び縮小される問題を修正。通常会話・文字送り・ログで字号処理を共通化し、入れ子のルビの行高を保持します。
- 準備した多言語フォントを起動中のゲームへ読み込む機能を追加。フォント準備のための再起動は不要で、自動検出とキャッシュ再利用も継続します。
- 「女性の声」など、スクリプトから設定された話者名のコピー後も出典を保持します。
- アクティブボイスの本文を少し下げ、通常のイベント会話の位置は変更しません。

コード回帰・独立ネイティブホスト・配布版の起動確認を通過しました。新しいフォント読み込みとレイアウトは実ゲームでテストできます。設定とキャッシュは保持されます。旧版から更新したネイティブコードは、次回の通常のゲーム起動から有効になります。
