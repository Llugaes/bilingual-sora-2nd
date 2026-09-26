# Bilingual Sora 2nd v0.3.10

## 简体中文

- 统一普通注音与独立注解的间距计算。副语言按实际绘制字形的边缘定位，涵盖对话、姓名、跳过按钮和带颜色的底部说明；按钮图标不参与文字间距计算，原文注音和强调点保留原位置。
- 修复只调整主字号才刷新、切换设置页后位置不一致的问题。只修改副语言间距或字号也会重新排版。
- 固定对话框中的姓名保留原生基线，避免新增注解把姓名向正文挤压。
- 补上绕过普通文本设置接口的读档角色名单。姓名旁的等级、章节旁的难度以及游玩时间保留原有布局，无需按姓名或语言写特例。
- 修复暂停中的长对话在单语／双语切换后消失的问题；重排时保留文本显示进度。
- 已在游戏内测量对话、姓名、隐藏界面和两个跳过按钮的间距，并验证读档姓名与设置页重建。缓存就绪后的本次真实游戏连接耗时为 3.81 秒，不含首次缓存准备；实际耗时取决于机器和游戏初始化。
- 已知限制：固定高度的窄标题条可能容不下当前字号和新增注解。统一间距不会扩大背景或自动缩小用户字号；不同控件的缩放与字形留白仍可能造成视觉差异。

## English

- Use one glyph-bound spacing calculation for native ruby and separate annotations, including dialogue, speaker names, skip controls and colored footers. Exclude button icons from text bounds and preserve original ruby and emphasis positions.
- Reflow on secondary-size or gap changes as well as main-size changes. Keep initial layout and recreated settings pages consistent.
- Retain the native speaker-name baseline in fixed dialogue boxes.
- Catch save-party text written outside the regular setter. Preserve levels, difficulty labels and playtime without language- or name-specific rules.
- Keep paused dialogue visible when switching between single-language and annotated modes, retaining reveal progress during reflow.
- Verified live gaps in dialogue, names, Hide UI and both skip controls, plus save-party names and settings-page recreation. One real-game connection with a prepared cache took 3.81 seconds; first-time cache preparation is excluded and timing varies by system and game initialization.
- Known limitation: fixed-height narrow headings may not fit the selected sizes plus annotations. Unified spacing does not enlarge backgrounds or automatically shrink saved font sizes. Widget scaling and glyph padding can still affect perceived spacing.

## 日本語

- 会話、名前、スキップ操作、色付きフッターの注釈間隔を、実際に描画する文字の境界から共通計算します。ボタンアイコンは計算から除外し、元のルビ・強調点の位置を維持します。
- 主言語の文字サイズだけでなく、副言語サイズや間隔の変更でも再配置します。設定ページの初回表示と再作成後の配置を統一しました。
- 固定会話ウィンドウの話者名を元のベースラインに維持します。
- 通常のテキスト設定処理を通らないセーブ情報のキャラクター名にも対応。レベル、難易度、プレイ時間の配置を維持し、特定の名前や言語に依存しません。
- 一時停止中の長い会話で、単言語／注釈表示を切り替えると本文が消える問題を修正。再配置時も表示進行度を維持します。
- 実機で会話・名前・UI非表示・両スキップ操作の間隔、セーブ情報の名前、設定ページの再作成を確認しました。キャッシュ準備済みの実ゲーム接続は今回 3.81 秒でした。初回キャッシュ作成を含まず、環境やゲームの初期化によって変わります。
- 既知の制限：高さが固定された細い見出しには、設定した文字サイズと注釈が収まらない場合があります。背景の拡張や文字サイズの自動縮小は行いません。ウィジェットの倍率と文字の余白によって見た目の間隔に差が残る場合があります。

## Downloads

New users: `bilingual-sora-2nd-0.3.10-windows-x64-setup.exe` or `bilingual-sora-2nd-0.3.10-windows-x64.zip`. App/runtime ZIPs and the JSON manifest are updater components. Existing installations retain settings and reuse unchanged dependencies. Native-hook updates apply after the current game connection ends; no game restart is forced.
