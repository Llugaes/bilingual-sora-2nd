# Bilingual Sora 2nd v0.3.34

## 简体中文

- 修复带颜色、图标等格式的多行双语说明中，副语言与上一行正文重叠的问题，例如“零力场生成器”提示。
- 按游戏实际测得的副语言高度预留行高，测量和绘制共用同一规则；保留原有换行、颜色、图标与原生注音，不再只依赖额外行距。
- 仅调整双语多行排版，单语言与关闭 MOD 后的原始排版不变；不新增文字解析或逐帧字形扫描。

已通过现场坐标回归、自动化检查及独立原生宿主验证。修复后的游戏内画面和提示框背景伸展仍待实机验证。本次涉及驻留排版代码，更新后须正常退出并重新启动游戏才会生效。

## English

- Fix secondary-language text overlapping the preceding primary line in multiline bilingual messages with colours or icons, such as the Zero Field Generator explanation.
- Reserve line height from the game's measured secondary-text bounds in both measurement and drawing. Existing line breaks, colours, icons and native readings are preserved.
- Single-language and disabled-MOD layouts are unchanged. No additional text parsing or per-frame glyph scans are introduced.

Captured-coordinate regressions, automated checks and isolated native-host tests passed. The resulting in-game appearance and popup background resizing still need visual verification. Restart the game after updating to load this resident layout-code change.

## 日本語

- 「零力場発生器」の説明など、色やアイコンを含む複数行の双語表示で、副言語が前の行の本文に重なる問題を修正しました。
- ゲームが計測した副言語の高さを行の領域に確保し、計測と描画で同じ処理を使用します。改行、色、アイコン、元のルビは保持します。
- 単一言語と MOD 無効時のレイアウトは変更しません。追加のテキスト解析や毎フレームの字形走査も行いません。

実機から取得した座標による回帰テスト、自動テスト、独立したネイティブ検証プロセスでの確認は通過しています。修正後のゲーム内表示とウィンドウ背景の伸縮は、実機での確認が必要です。常駐する描画処理の変更を反映するには、更新後にゲームを再起動してください。
