# 0.4.1 — 改善 EXE 兼容检查与确认框排版

- 放宽过于严格的 EXE 检查。同一构建中不影响运行的文件信息、资源和调试信息差异，不再一律导致连接失败。
- 语言识别允许四个样本中有一个被其他 MOD 修改，只要另外三个明确对应同一种语言；存在实际语言冲突时仍会提示错误。
- 修正部分确认框首次排版时的高度与文字间隔。普通对话和日志保持 0.4.0 的行距，不再因颜色、控制符或逐字显示额外撑开。
- 连接失败会保留具体原因，不再被“字体已准备”的提示盖住；EXE 兼容问题也不会再笼统显示为字体安装失败。

本版已通过中日双语实机验收。更新仍由用户手动选择，保留现有配置与历史版本回退入口。请正常退出游戏和工具后安装，再重新启动。

已知限制：这不是对任意 EXE 或补丁的通用适配。全语音 MOD 1.0.7 附带的 EXE 改写了代码地址和字体读取流程，暂未支持。

## English

- Relaxed overly strict EXE checks: harmless metadata, resource and debug-information differences within the adapted build no longer cause rejection solely due to a different file hash.
- Language detection tolerates one modified sample when three other samples clearly identify the same language. Conflicting language samples still report an error.
- Corrected initial layout timing for some confirmation windows. Ordinary dialogue and logs retain the 0.4.0 spacing without extra gaps caused by formatting or typewriter animation.
- Connection errors now keep their actual cause instead of being hidden by a font-ready notice or mislabeled as font installation failures.

Tested in game with Chinese/Japanese bilingual text. Updates remain manual, with settings and version rollback preserved. Exit the game and tool before installing, then relaunch.

Known limitations: this does not support arbitrary executables or patches. The EXE bundled with the full-voice MOD 1.0.7 still needs a separate adapter.

## 日本語

- EXE の検証条件を緩和しました。対応済みビルドの動作に影響しないメタデータ・リソース・デバッグ情報の差だけで、接続を拒否しなくなりました。
- 言語判定用の四つのサンプルのうち一つが他の Mod で変更されていても、残り三つが同じ言語を示せば判定できます。異なる言語が検出された場合はエラーを表示します。
- 一部の確認ウィンドウで初回レイアウトのタイミングを修正しました。通常の会話とログは 0.4.0 の行間を維持し、書式や文字送りによる余分な空白を追加しません。
- 接続失敗の原因を「フォント準備完了」の表示で隠したり、フォントのインストール失敗と誤表示したりしないよう修正しました。

中国語・日本語の二言語表示で実機確認済みです。更新は引き続き手動で、設定と過去バージョンへの復元機能を保持します。ゲームとツールを終了してから更新し、再起動してください。

既知の制限：すべての EXE やパッチに対応するものではありません。全ボイス Mod 1.0.7 に同梱された EXE は個別対応が必要です。
