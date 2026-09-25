# Bilingual Sora 2nd v0.3.6

## 简体中文

- 修复部分剧情回顾、主动语音、NPC 对话和临时角色名缺少副语言：兼容不同语言的对白分行，修正主动语音记录配对，并保留真实歧义保护。
- 所有对话（包括过场字幕）统一使用上方小字注解，不再追加第二段语言；原有注音和强调标记保留原位。
- 副语言注解与主文字左侧对齐，增加 Tips 等带格式文本的上下间距。
- 修复关闭详细设置后状态条也消失的问题。× / Esc 只收起设置；状态条的关闭按钮仍可隐藏界面，后台继续运行。
- 已通过本地文本回放、八种语言组合检查和自动回归测试；新的排版仍需在实际游戏画面中验收。

## English

- Restore missing annotations in some dialogue history, Active Voice, NPC dialogue and temporary speaker names. Pair dialogue across locale-specific wrapping and correct Active Voice record identities while retaining ambiguity safeguards.
- Use annotations above the main text for all dialogue, including cutscenes, instead of appending a second language block. Original ruby and emphasis remain in place.
- Left-align secondary annotations with their main text and increase clearance for formatted text such as Tips.
- Closing settings with × / Esc now retains the status bar. The status bar's own close button still hides the interface without stopping the backend.
- Local text replay, combinations of all eight languages and automated regression tests pass. The new layout still requires visual validation in the game.

## 日本語

- 一部の会話履歴、アクティブボイス、NPC 会話、仮の話者名で対訳が表示されない問題を修正しました。言語ごとの改行差とアクティブボイスの対応付けを改善し、訳が曖昧な場合の保護は維持しています。
- カットシーンを含むすべての会話で、対訳を本文の上に小さく表示します。別の段落としての追加は行いません。元のルビと強調記号は元の位置に保持します。
- 対訳を本文の左端に揃え、Tips など装飾付きテキストとの間隔を広げました。
- × / Esc で設定を閉じてもステータスバーを残します。ステータスバー側の閉じるボタンでは、バックグラウンド処理を止めずに画面を非表示にできます。
- ローカルテキストの再生、全 8 言語の組み合わせ、自動回帰テストを確認済みです。新しい配置の見た目はゲーム内での確認が必要です。

## Downloads

For a new installation, choose `bilingual-sora-2nd-0.3.6-windows-x64-setup.exe`, or the complete portable `bilingual-sora-2nd-0.3.6-windows-x64.zip`. The `app` / `runtime` ZIPs and JSON manifest are for the updater. Updates from 0.3.4 / 0.3.5 reuse the installed runtime and retain settings. Installation waits until the game connection ends.

Version 0.2.2 requires manual installation because of its old updater's file-count limit. Exit the old tool before migrating settings; see the [README](https://github.com/Llugaes/bilingual-sora-2nd#readme).
