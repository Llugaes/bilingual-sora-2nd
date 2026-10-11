# Sora Bilingual — 空の軌跡 the 2nd 二言語 Mod

[简体中文](README.md) · [English](README.en.md) · **日本語**

PC 版で二つの言語を同時表示、またはショートカットを押している間だけ切り替えます。日本語・英語・簡体字・繁体字・韓国語・フランス語・ドイツ語・スペイン語に対応。

**[ダウンロード · GitHub](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) · [Gitee ミラー](https://gitee.com/Llugaes/bilingual-sora-2nd/releases) · [更新履歴](RELEASE_NOTES.md)**

![中国語と日本語の会話](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-zh-ja.jpg)

## ゲーム内の表示例

会話・メニュー・アイテム説明を二言語で表示したり、必要なときだけ長押しで切り替えたりできます。以下は過去の各バージョンで撮影した実機の表示例です。文字サイズや間隔はバージョンと設定によって異なり、1.0.2 の全画面を検証した記録ではありません。

| アイテム名と説明 | 装備と能力値 |
|---|---|
| ![アイテム画面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/items.jpg) | ![装備画面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/equipment.jpg) |

<details>
<summary>会話履歴、フィールドの表示、英語と日本語の比較を見る</summary>

![二言語の会話履歴](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-log-zh-ja.jpg)

![フィールドの表示](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/field.jpg)

![英語と日本語の会話](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/dialogue-en-ja.jpg)

![英語と日本語のアーツ一覧と説明](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/arts-en-ja.jpg)

</details>

## インストール

1. [GitHub Releases](https://github.com/Llugaes/bilingual-sora-2nd/releases/latest) または [Gitee](https://gitee.com/Llugaes/bilingual-sora-2nd/releases) から安定版の `windows-x64-setup.exe` をダウンロードしてインストール。
2. **Bilingual Sora 2nd** を開き、画面言語を選んでからゲームを起動。ゲームの検出、文字言語の識別、フォントとマッピングの準備は自動です。初回は数分かかる場合があります。
3. 「言語と表示」で副言語を選択。主言語はゲームの言語に自動で追従します。ゲームを現在の副言語に変更すると両者を入れ替え、それ以外の言語に変更した場合は副言語を保持します。同じ言語は選べません。

Windows 10/11 x64。管理者権限や Python の別途導入は不要。オフラインでインストールでき、更新時も設定を保持します。ポータブル版は展開して `BilingualSora2nd.exe` を実行。ゲーム言語の初回検出時に副言語の初期値を設定し、その後はゲームの言語と重なって入れ替える場合を除き、副言語の選択を保持します。ゲームの言語設定、元の PAC と EXE は変更しません。

初期状態でオフの **Experimental** を有効にすると、主言語を手動で選択できます。実験的な機能のため、不安定な動作、予期しない挙動や不具合が生じる可能性があります。別の主言語を体験する場合は、ゲーム内で言語を変更することを推奨します。オフにすると再びゲームの言語に追従します。

## 使い方

**普段は単言語モード → 押している間だけ副言語を推奨。** 押すと比較、離すと元に戻ります。二言語モードは同時表示。「文字レイアウト」でサイズ・間隔・色・透明度を調整できます。

| 表示方法 | 通常の表示 | 言語切り替えキーの動作 |
|---|---|---|
| 単言語・長押し | 主言語 | 押している間だけ副言語、離すと戻る |
| 単言語・押すたびに切り替え | 選択中の一言語 | 主言語と副言語を切り替える |
| 二言語 | 主言語と副言語 | 副言語の表示をオン／オフ |

下の画像は **1.0.2 の実際の設定画面をオフラインで生成**したものです。ゲームには接続していません。左で表示方法と副言語、右で文字サイズ・間隔・色を設定します。変更は自動保存されます。

| 言語と表示 | 文字レイアウト |
|---|---|
| ![1.0.2 言語設定](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/settings-ja.png) | ![1.0.2 文字レイアウト](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/layout-ja.png) |

| 操作 | 初期ショートカット |
|---|---|
| 画面の表示／非表示 | Ctrl + Shift + F9 |
| 現在のモードで言語切り替え | Ctrl + Shift + F10 |

「クイック操作」で操作を選び、キーボードやコントローラーの組み合わせを記録。ボタン名は自動識別、または PlayStation・Xbox・Switch を手動選択できます。名称変更は割り当てを変更しません。

<details>
<summary>キーボードとコントローラーの割り当て画面を見る</summary>

![クイック操作](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/shortcuts-ja.png)

</details>

小さなウィンドウや歯車をクリックして設定を開き、長押しで移動。「—」と設定画面の「×」はトレイに隠します。完全終了はトレイを右クリック。文字・記号・色で構築中、接続中、準備完了、無効、異常を区別します。「ツールの外観」で三つのテーマ、中文／英語／日本語の画面言語、背景透明度を変更できます。

![小ウィンドウ：言語、接続状態、設定ボタン](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/status-bar-ja.png)

<details>
<summary>三つのテーマ、画面言語、背景の透明度を見る</summary>

![ツールの外観](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/appearance-ja.png)

</details>

追加フォントは手元のゲームリソースから自動で準備し、接続後に読み込みます。進捗やエラーは画面に表示されます。通常、手動でのフォント導入は不要です。初回の準備には時間がかかる場合があります。

## 制限と互換性

- 二言語の会話履歴は、開く際の一時停止やフレームレート低下が残っています。単言語の長押し切り替えで負荷を軽減できます。
- 不確かな対応は原文を保持。画像・動画内の文字は対象外。固定のテキスト枠に長文が収まらない場合は、サイズを下げるか単言語に切り替えてください。
- 新しい組み合わせにはマッピング構築が必要。有効な言語単位の解析・識別キャッシュを再利用しますが、待ち時間ゼロは保証しません。
- 今回は Steam PC 1.04 で実機検証しました。対象は『空の軌跡 the 2nd』で、『空の軌跡 the 1st』には対応していません。
- 0.4.2 の実機確認サンプルは原版 Steam build 25386012 / EXE 1.03.2 と full-voice MOD 1.0.7 同梱 EXE。後者は EXE の置き換えのみで、音声リソース一式は未検証です。他の改造 EXE、ゲーム全体、全言語の組み合わせは個別に検証していません。

## 更新とサポート

**1.0.2 では二言語表示中の継続的なメモリ増加を修正し、モデル準備時のピーク使用量を削減しました。** 装備の専用条件の表示、小見出しとアイテム説明の共通レイアウト、メニューを開いた直後の位置ずれも修正しています。測定方法、r7 候補版との比較、検証範囲は[メモリ検証記録](docs/verification/memory-r8.md)を参照してください。ゲーム全体のフレームレート向上を示すものではありません。

1.0.1 の起動時の修正も含まれます。初回やゲームリソース更新後には引き続き準備が必要です。1.0.0 は安定版の更新対象から除外したままです。

自動確認は通知のみ。ダウンロード・導入・ロールバックは手動確認が必要です。更新前にゲームを終了してください。中国国内は Gitee を優先、GitHub に完全ポータブル版と旧版があります。旧版の完全パッケージで設定を保持して戻せます。必要なら更新確認を無効にしてください。

<details>
<summary>更新と過去のバージョンの選択画面を見る</summary>

![1.0.2 更新画面](https://raw.githubusercontent.com/Llugaes/bilingual-sora-2nd/main/docs/images/updates-ja.png)

</details>

| ファイル | 用途 |
|---|---|
| `windows-x64-setup.exe` | 推奨：インストール・上書き更新 |
| `app` / `runtime` を含まない `windows-x64.zip` | 完全ポータブル版。展開して実行 |
| `app` / `runtime` ZIP、`update.json` | ツール内更新用。個別の手動導入は不要 |

接続失敗は状態の詳細を確認して再試行、フォント異常はフォント状態を確認。ツール画面にはウィンドウ／ボーダーレス表示が適しています。不具合報告にはツール・ゲームの版、ゲーム文字言語、主副言語と短いエラー内容を添えてください。ゲーム資源・キャッシュ・セーブの全体をアップロードしないでください。

開発資料：[貢献](CONTRIBUTING.md)、[構成](docs/ARCHITECTURE.md)、[診断](docs/DEBUGGING.md)、[検証](docs/verification/README.md)。公開前にローカル候補版の明示的な実機ユーザー確認が必要です。

## ライセンスと謝辞

コードは [MIT](LICENSE)。依存ライブラリ・派生コードの表記は [THIRD_PARTY.md](THIRD_PARTY.md)。0xDC00/scripts、Tom、FPACker、Ingert、sora2looseload、Frida、Qt/PySide6、pygame-ce/SDL、pefile、LZ4、Inno Setup と中文翻訳の保守者に感謝します。

非公式ツールです。ゲーム・商標・美術資源は各権利者に帰属。配布物にゲーム資源、生成フォント、完全なテキスト索引、ユーザー設定は含みません。
