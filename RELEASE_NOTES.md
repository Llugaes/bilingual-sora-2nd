# Bilingual Sora 2nd v0.3.7

## 简体中文

- 加速首次索引构建：完全相同的跨语言脚本只解析一次，独立脚本使用最多 4 个工作进程处理。语言覆盖、结构校验和输出顺序保持一致。
- 加速 EXE 校验：保留完整文件 SHA-256、机器架构和唯一特征匹配，只跳过连接时不使用的 PE 数据目录解析。
- 修复全角／半角数字被重复注解的问题；纯图标、相同拉丁文本保持原样。章节名和难度等混合文本保留正文尺寸及后续文本的占位和基线。
- 修复无关奖励提示的本地化格式差异导致整段对白漏配的问题。新增独立的完整对白序列校验，继续核对调用位置、数量、说话人和语音；本机索引新增 13,289 条记录，原记录全部保留。
- 普通文字与带格式文字统一按引擎测量的注解高度计算间距，消除各界面不同的原生偏移；原文注音／强调点保留原位置。视觉效果仍需游戏内验收。
- 本机离线对比：索引与模型准备约 96 秒 → 34 秒，已有模型读取约 1.1 秒，EXE 校验约 2.6 秒 → 0.04–0.43 秒。这些是阶段测量，不是游戏内总连接时间承诺。
- 首次使用本版会重建索引；后续连接复用缓存。构建过程中不会启动或附加游戏。

## English

- Parse byte-identical localized scripts once and build independent scripts with at most four worker processes. Language coverage, structural validation and output ordering are preserved.
- Keep full-file SHA-256, architecture and unique signature checks while skipping unused PE data directories during connection verification.
- Suppress duplicate annotations for fullwidth/ASCII equivalents and icon-only text. Mixed chapter/difficulty labels retain native main-text sizing, advances and following baselines.
- Prevent unrelated reward-message formatting from rejecting an entire dialogue sequence. The fallback still validates complete dialogue order, call positions/count, speakers and voices. The local catalog adds 13,289 records and preserves every existing record.
- Use measured annotation extents for consistent spacing across ordinary and formatted text, independent of surface-specific native offsets. Original ruby/emphasis stays in place. In-game visual acceptance is still pending.
- Local offline measurements: index/model preparation about 96 → 34 seconds, cached model reading about 1.1 seconds, EXE verification about 2.6 → 0.04–0.43 seconds. These are stage timings, not a guarantee of total in-game connection time.
- The first run of this version rebuilds the index; subsequent connections reuse it. Index construction does not launch or attach to the game.

## 日本語

- 内容が完全に同じ言語別スクリプトは一度だけ解析し、独立したスクリプトを最大 4 プロセスで処理します。言語の対応範囲、構造の検証、出力順序は維持します。
- EXE 全体の SHA-256、アーキテクチャ、シグネチャの一意性を確認しつつ、接続時に使用しない PE データディレクトリの解析を省きます。
- 全角・半角の数字などの重複注釈を抑止し、アイコンのみの文字列も変更しません。章名と難易度が混在する場合は本文のサイズ、文字送り、後続文字の基準位置を維持します。
- 報酬メッセージなどの書式差異によって会話全体が対応付けから外れる問題を修正しました。会話順、呼出位置・数、話者、音声を引き続き検証します。ローカル索引では既存記録をすべて維持し、13,289 件を追加しました。
- 注釈の実測高さを使い、通常テキストと装飾付きテキストの間隔計算を統一しました。原文のルビや強調点は元の位置に残します。ゲーム内の見た目は引き続き確認が必要です。
- オフライン計測では、索引・モデル準備が約 96 秒から 34 秒、キャッシュ読込が約 1.1 秒、EXE 検証が約 2.6 秒から 0.04–0.43 秒となりました。ゲーム内の接続全体の所要時間を保証する値ではありません。
- このバージョンの初回は索引を再構築し、以降はキャッシュを再利用します。索引構築はゲームの起動や接続を行いません。

## Downloads

New users: `bilingual-sora-2nd-0.3.7-windows-x64-setup.exe` or `bilingual-sora-2nd-0.3.7-windows-x64.zip`. The app/runtime ZIPs and JSON manifest are updater components. Existing 0.3.4–0.3.6 installations reuse their runtime and retain settings. Updates wait until the game connection ends.
