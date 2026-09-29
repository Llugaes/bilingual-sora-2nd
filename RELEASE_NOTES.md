# Bilingual Sora 2nd v0.3.19

## 简体中文

- 修复复合状态与描述漏译，包括「冻结·即死」「中毒·炎伤」「睡眠·延迟」及三个以上词条的组合。
- 共用组合文本解析，覆盖不同中点字形、动态字符串参数、颜色和括号；完整资源译文优先，数字与图标保留。
- 修复宽泛模板吞入其他词条的问题，并扩查状态、效果、条件和范围资源。新增八语组合审计和最终副文回归，保留歧义及未覆盖项供后续检查。
- 修复说话人名称因同一脚本后续无关差异而漏掉语言配对的问题，并逐条检查“女子的声音／男子的声音／女孩的声音”等整组名称。
- 小对话气泡正文稍微下移，仅在双语模式且存在副文时生效；姓名、普通模式及两种单语模式保持原位。

自动化检查通过；截图案例已在完整生产模型回放，实际游戏画面待新版验证。设置与缓存保留。由旧版升级的驻留代码在下次正常启动游戏时生效。

## English

- Fix missing translations in compound status and description labels, including lists with three or more members.
- Share list parsing across middle-dot variants and dynamic string arguments while preserving complete translations, formatting, numbers, and icons.
- Prevent broad format templates from consuming preceding list members. Add eight-language resource audits and final annotation regression checks, retaining unresolved cases separately.
- Preserve proven speaker-name pairs when unrelated calls later in the script differ between languages; audit the full family of generic voice labels.
- Move small dialogue-bubble body text slightly downward only when bilingual annotations are present. Names, disabled mode, and both single-language modes retain their original positions.

Automated checks passed. Reported examples were replayed against full production models; in-game visuals remain to be verified. Settings and caches are preserved. Updated resident code takes effect on the next normal game launch.

## 日本語

- 複数の状態・説明を連結したテキストの翻訳漏れを修正。3 項目以上のリストにも対応します。
- 中点の表記違いと動的文字列引数に共通の解析を適用し、完全な訳文・書式・数値・アイコンを保持します。
- 汎用書式が前の項目まで取り込む問題を修正。8 言語のリソース監査と副言語表示の回帰検証を追加し、未解決の項目は別に記録します。
- スクリプト後半の無関係な差異による話者名の対応漏れを修正し、「女性の声」「男性の声」などの名前をまとめて検証します。
- 小さな会話吹き出しの本文を、対訳がある場合のみ少し下げます。名前・無効時・単一言語モードの位置は変わりません。

自動検証は通過しました。報告例は完全なモデルで再生済みですが、実ゲームの表示確認は別途必要です。設定とキャッシュは保持されます。更新した常駐コードは次回の通常起動から有効になります。
