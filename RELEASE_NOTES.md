# Bilingual Sora 2nd v0.3.31

## 简体中文

- 修复完整语言映射常驻大量对象、使运行时自动内存回收阻塞游戏文本回调的问题。映射改为按需读取，保留全部译文、对话 ID 和日志匹配数据；单双语共用此修复。
- 多行文本候选按需建立，减少启动时展开的数据。升级后首次转换缓存，后续直接复用。
- 完整模型逐字段一致性检查通过。在独立原生宿主的相同负载中，旧方式复现约 300 ms 停顿，新方式 90 秒、18.5 万次调用最长记录约 22 ms。该测试不等同于全部游戏场景的帧时间，实机持续游玩仍需复验。

底层修复在游戏下次启动时生效。已经运行的游戏保持原连接，不会强制关闭或热替换钩子。

## English

- Fix long native text callback waits caused by automatic garbage collection of the fully expanded language model. Load model values on demand while preserving translations, dialogue IDs, and history data in both single-language and bilingual modes.
- Build multiline candidates on demand. Convert the cache once after upgrading, then reuse it on subsequent starts.
- Full model field comparisons passed. An isolated native-host replay reproduced roughly 300 ms waits with the old format; the updated format recorded a maximum of about 22 ms over 185,000 calls in 90 seconds. This is a controlled regression test, not validation of every in-game frame.

The runtime fix takes effect on the next game launch. Existing game connections remain intact.

## 日本語

- 言語モデルの大量の常駐オブジェクトに対する自動メモリ回収が、ゲームのテキスト処理を長時間待たせる問題を修正。翻訳、会話 ID、ログ照合情報をすべて保持したまま、必要なデータだけを展開します。単言語・二言語の両モードに適用されます。
- 複数行テキストの候補も必要時に展開。更新後にキャッシュを一度変換し、次回以降は再利用します。
- モデル全項目の一致を確認。独立したネイティブテストでは旧方式の約 300 ms の待ち時間を再現し、新方式では 90 秒・約 18.5 万回の呼び出しで最長約 22 ms でした。実際のゲーム全場面での検証を意味するものではありません。

修正は次回のゲーム起動時に有効になります。起動中のゲームの接続は維持されます。
