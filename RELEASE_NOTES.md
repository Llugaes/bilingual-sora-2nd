# Bilingual Sora 2nd v0.3.8

## 简体中文

- 修复菜单切页后注解尺寸恢复错误的问题：游戏晚于文本创建设置字号时，也会重新按当前配置排版。
- 标题、兑换栏和带颜色的底部说明改用正文实际字形上缘计算注解间距，避免把排版起点当作文字边界。保留原文颜色、注音及强调标记。未更改用户字号和间距配置；游戏内视觉效果待验收。
- 修复存档详情组合文本只处理第一行姓名的问题。逐行处理姓名，保留项目符号、换行和等级数字。
- 等待游戏时提前准备当前语言组合的本地缓存，自动发现 Steam 库或使用此前连接过的安装位置。准备过程中不启动或附加游戏。
- 完整模型无损去重，通过本机文件直接载入 V8，减少重复序列化和逐块传输。本机样本从约 190 MB 降至约 60 MB，语言覆盖不变。缓存损坏时回退原传输方式，避免破坏已生效的模型。
- 缓存就绪后的离线连接路径三次实测为 3.55–3.69 秒，包含读取、EXE 校验、附加测试进程和运行时载入。实际游戏初始化及钩子安装仍需游戏内测量；首次缓存准备不包含在此时间内。
- 已验证 64 种主／副语言组合的 172,032 项回放检查。

## English

- Keep live annotation sizing after menus recreate their labels, including font sizes assigned after text creation.
- Anchor spacing to measured main-text ink bounds on headings, exchange columns and colored footers. Preserve original colors, ruby and emphasis without changing saved layout preferences. In-game visual acceptance remains pending.
- Annotate every matched name in multiline save details while retaining bullets, line breaks and level numbers.
- Prepare the selected language cache while waiting for the game, using Steam libraries or a previously connected installation. Preparation never starts or attaches to the game.
- Deduplicate the complete model losslessly and load it directly into V8 from a local file. The local sample shrinks from about 190 MB to 60 MB without reducing language coverage. Invalid caches fall back to bounded transfer without replacing the active model prematurely.
- Three cached offline connection-path measurements took 3.55–3.69 seconds, including reading, EXE verification, helper attachment and runtime loading. Game initialization and hook installation require separate in-game measurement; first-time cache preparation is excluded.
- Validated 172,032 replay checks across 64 primary/secondary language combinations.

## 日本語

- メニューの再作成後も注釈サイズを維持します。テキスト作成後にゲームが文字サイズを変更する場合にも再計算します。
- 見出し、交換画面、色付きフッターでは、本文の実測境界を使って間隔を計算します。元の色、ルビ、強調点と保存済みの設定を維持します。ゲーム内の見た目は確認待ちです。
- セーブ情報の複数行の名前をすべて処理し、箇条書き、改行、レベル数値を維持します。
- Steam ライブラリまたは接続済みのインストール先を見つけ、ゲーム起動待ち中に選択中の言語キャッシュを準備します。準備時にゲームの起動・接続は行いません。
- モデルを情報損失なく共有化し、ローカルファイルから V8 に直接読み込みます。ローカルサンプルは約 190 MB から 60 MB に縮小し、言語対応範囲を維持しました。破損時は従来の分割転送に戻ります。
- キャッシュ準備後のオフライン接続処理は 3 回の計測で 3.55–3.69 秒でした。読込、EXE 検証、検証用プロセスへの接続、ランタイム読込を含みます。ゲーム初期化・フック設置は実機確認が必要で、初回のキャッシュ作成時間は含みません。
- 64 言語ペア、172,032 件の再生検証を実施しました。

## Downloads

New users: `bilingual-sora-2nd-0.3.8-windows-x64-setup.exe` or `bilingual-sora-2nd-0.3.8-windows-x64.zip`. App/runtime ZIPs and the JSON manifest are updater components. Existing installations retain settings and reuse unchanged dependencies. Updates apply after the game connection ends. Open the tool before the game to let first-time cache preparation finish in the background.
