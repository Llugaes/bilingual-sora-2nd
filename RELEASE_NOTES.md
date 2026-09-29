# Bilingual Sora 2nd v0.3.15

## 简体中文

- 修复对话日志只有最新一句显示双语的问题。新对白按游戏脚本与调用身份保存；缺少来源的旧日志使用原资源译文兜底。
- 补齐技能、回路效果、道具取得和食谱等提示的文本关联，修正“休息”和部分说话人名称漏译。回路标题仅关联属性名称与“属性值”，保留原有图标和数值。
- 修复资源表中不同记录被误认为同一身份而丢失译文的问题，保留独立记录和帮助页续行的对应关系。
- 修正放大或彩色正文的副语言缩放，保留主副语言各自注解的缩放和上方空间；调整双语日志的人名及正文位置。
- 恢复自动寻找游戏目录，在游戏启动前自动准备和检查字体，无需填写首次准备表单。

本次修复已通过自动回归检查及用户实机验收。首次语言映射构建仍可能需要数分钟；后续启动的加载速度将作为下一版本的重点。

请退出游戏和托盘中的双语工具后安装更新，再启动工具与游戏。升级保留个人设置。

## English

- Fix bilingual dialogue appearing only in the newest log entry. New entries retain their game-script and call identities; older entries without provenance fall back to translations from the original resources.
- Extend matching for skill and quartz effects, item and recipe notifications, the Rest action, and speaker names. Quartz headings translate only the element label and Value, preserving native icons and numbers.
- Keep distinct table records separate instead of discarding translations due to identity collisions, including help-page continuations.
- Correct secondary scaling for enlarged and colored text, preserve independent primary and secondary readings and spacing, and adjust bilingual log positioning.
- Restore automatic game discovery and font preparation before game launch, without an initial setup form.

This release passed automated regression checks and user testing in the game. The first language-map build may still take several minutes; subsequent-launch performance is the focus of the next version.

Exit the game and the bilingual tool from its system-tray menu before updating. Restart both afterward. Personal settings are preserved.

## 日本語

- 会話履歴の最新の一文だけが二言語表示になる問題を修正しました。新しい履歴にはゲームのスクリプトと呼び出しの識別情報を保存し、出典情報のない既存履歴には元リソースの訳文を使用します。
- 技・クオーツの効果、アイテム取得・料理レシピの通知、「休む」、話者名の照合を改善しました。クオーツの見出しは属性名と属性値のラベルだけを翻訳し、アイコンと数値はそのまま表示します。
- リソース表の異なる記録が同じ識別情報と判断され、訳文が失われる問題を修正しました。ヘルプの続きの行も対応する記録に保持します。
- 拡大文字・色付き文字の副言語の縮小率を修正しました。主文と副文それぞれのルビと上側の余白を維持し、二言語履歴の配置を調整しました。
- ゲームの自動検出と起動前のフォント準備・確認を復元しました。初回準備フォームの入力は不要です。

自動回帰テストと利用者による実機確認を通過しました。初回の言語マップ構築には数分かかる場合があります。2回目以降の起動速度は次のバージョンで重点的に改善します。

ゲームとシステムトレイの二言語ツールを終了してから更新し、両方を再起動してください。個人設定は保持されます。
