# Bilingual Sora 2nd v0.3.25

## 简体中文

- 增加可选的原生耗时诊断，补上旧计时遗漏的游戏线程等待脚本回调时间，并分别记录文本更新的进入、原生执行和退出阶段。
- 诊断在游戏线程上使用固定容量的原生记录，由工具后端保存、去重及轮换，不记录对白正文；默认关闭。排查时可在启动游戏前将 `generated/native-control.json` 中的 `performance_diagnostics` 设为 `true`，记录保存在 `generated/native-performance.jsonl` 及其上一份文件中。
- 独立宿主验证了旧计时显示 0 ms 时，新计时能捕获约 174 ms 的脚本锁等待，并保留原有参数、返回值及嵌套回调行为。

地图移动时偶发顿挫尚未取得足够实机证据，本版不宣称卡顿已经修复。保留 0.3.24 的地点、字体及界面修正；原生诊断在下次启动游戏时生效。

## English

- Add optional native timing around text callbacks, including time spent waiting to enter JavaScript, with separate enter, native-body and leave measurements.
- Keep a bounded native event buffer and write deduplicated, rotating records from the tool backend. Dialogue text is not recorded. Diagnostics are off by default: set `performance_diagnostics` to `true` in `generated/native-control.json` before starting the game. Records are saved in `generated/native-performance.jsonl` and its previous-file counterpart.
- A separate host captured about 174 ms of script-lock waiting that the old in-callback timer reported as 0 ms, while preserving callback arguments, return values and nesting.

Intermittent field-movement stutters remain under investigation; this release does not claim to fix them. It retains the map, font and UI changes from 0.3.24. Native diagnostics take effect on the next game launch.

## 日本語

- テキスト処理の任意のネイティブ計測を追加。JavaScript コールバックを待つ時間も含め、入口・ネイティブ本体・出口を分けて記録します。
- ゲーム側は固定容量の記録だけを保持し、ツール側で重複を除いて保存・ローテーションします。会話本文は記録しません。既定では無効です。調査時はゲーム起動前に `generated/native-control.json` の `performance_diagnostics` を `true` にしてください。記録先は `generated/native-performance.jsonl` とその前世代ファイルです。
- 独立した検証プロセスで、従来の計測では 0 ms になっていた約 174 ms のスクリプトロック待ちを捕捉し、引数・戻り値・入れ子の動作も確認しました。

フィールド移動中の一時停止は引き続き調査中であり、本版で解消したとはしていません。0.3.24 の地名・フォント・UI 修正を維持します。ネイティブ計測は次回のゲーム起動から有効です。
