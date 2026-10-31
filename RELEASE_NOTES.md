# 1.1.0

## 简体中文

- 改善首次连接和重新加载完整映射模型时的卡顿。模型按批读取、校验和构造，让游戏文本回调在加载期间继续运行。
- 新模型准备完成后一次替换，加载失败时保留完整旧模型；正常文本渲染不会执行加载阶段的让步逻辑。
- 保留 1.0.4 的文本关联修复，已有有效映射缓存可直接复用。兼容检查继续按实际使用的函数、调用关系和数据结构定位，不锁定游戏版本号或整个 EXE 哈希。

更新前请正常退出游戏和旧版工具，再安装新版；设置会保留。自动检查更新只提示，不自动安装。

本机正式 1.0.4 已成功连接当前安装的游戏，原先的不兼容提示未复现。1.1.0 修复了另行复现的模型加载阻塞，没有据此承诺未知游戏结构也能兼容。隐藏宿主同模型回放中，最长回调等待由约 5.2 秒降至约 54 毫秒；该结果不代表实机帧率。性能、兼容与实机验证范围见[检查记录](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/compatibility-1.1.0.md)。已审计资源仍有 8 条中文对白缺少对应官方日文，工具保留原文。

## English

- Reduced stalls during initial connection and full mapping-model reloads. Reading, validation and construction run in batches so native text callbacks can continue during loading.
- The replacement is published only after construction completes. Failed loads preserve the complete previous model; ordinary rendering does not run the loading checkpoints.
- Retained the text-association fixes from 1.0.4 and reuse of valid mapping caches. Compatibility checks still locate the required functions, call relationships and data structures without a game-version or whole-EXE hash lock.

Exit the game and the old tool normally before installing. Settings are preserved. Automatic update checks only notify and never install automatically.

The installed 1.0.4 release successfully connected to the local game; the reported incompatibility message was not reproduced. Version 1.1.0 addresses a separately reproduced model-loading stall and does not promise compatibility with unknown structural changes. In the owned native-host replay with the same full model, the longest callback wait fell from about 5.2 seconds to about 54 milliseconds. This is not an in-game frame-rate measurement. See the [verification report](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/compatibility-1.1.0.md). Eight audited Chinese dialogue lines still lack corresponding official Japanese text and retain their source text.

## 日本語

- 初回接続時や対応モデル全体の再読み込み時に発生する停止を軽減しました。読み込み・検証・構築を分割し、その間もゲームのテキストコールバックが動作できるようにしました。
- 新しいモデルの構築が完了してから一括で切り替えます。失敗した場合は既存のモデルを保持し、通常の描画では読み込み用の待機処理を実行しません。
- 1.0.4 のテキスト対応修正を維持し、有効な既存キャッシュを再利用します。互換性確認は必要な関数・呼び出し関係・データ構造を検証し、ゲームのバージョン番号や EXE 全体のハッシュには固定しません。

更新前にゲームと旧版ツールを通常の手順で終了してください。設定は保持されます。更新の自動確認は通知のみで、自動インストールは行いません。

手元の正式版 1.0.4 はインストール済みのゲームに接続でき、報告された互換性エラーは再現しませんでした。1.1.0 は別途再現したモデル読み込みの停止を修正するもので、未知の構造変更への対応を保証するものではありません。自作のネイティブ検証プロセスで同じ完全モデルを読み込んだ際、最長コールバック待機時間は約 5.2 秒から約 54 ミリ秒に短縮しました。これはゲーム内のフレームレート測定ではありません。詳細は[検証記録](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/compatibility-1.1.0.md)をご覧ください。対応する公式日本語がない中国語の会話 8 件は原文を保持します。
