# 1.0.3

## 简体中文

- 修复带分支、分页和表情控制的动态对白漏关联；相同正文的不同表情保留各自的原始调用身份。
- 补齐使用额外工作标志的物品交付消息，以及对白、字幕中的完整物品消息。
- 修复函数内片段词库抢先处理物品整句、导致只翻译半句的问题；完整调用现在直接选取整句配对。
- 修复部分外语旧日志因原始注音标记不完整而缺少副文的问题。仅使用整句官方候选，保留普通文本与已捕获对白的身份边界。
- 增加原始脚本与编译结果的交叉检查；未分类调用和缺少官方译文的条目保留在报告中，供后续复查。

升级前请正常退出游戏和旧版工具，再安装新版；设置会保留。首次使用新编译规则时会重建映射缓存。自动更新检查只提示，不自动安装。

本次修复有明确资源分母和回归记录，但不承诺全游戏全部文本已关联。官方语言资源缺项、未知显示路径和候选实机画面仍须分别核实。详细结果见[文本关联检查记录](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.3.md)。

## English

- Fixed missing associations for dynamic dialogue with branches, page controls and expressions. Expression variants with identical bodies retain their original call identities.
- Added item handover messages using additional work flags, and complete item messages in dialogue and subtitles.
- Fixed partial item-message translations caused by function-local fragments taking precedence over a complete message. Verified calls now select their full pairs directly.
- Fixed missing secondary text in some older foreign-language logs containing incomplete native ruby markup. Only complete official candidates are used; ordinary text and captured dialogue retain their identity boundaries.
- Added a cross-check between raw script calls and compiled producers. Unknown calls and missing official translations remain in the report for investigation.

Exit the game and the old tool normally before installing. Settings are preserved. The updated compilation rules rebuild the mapping cache once. Automatic update checks only notify; they never install automatically.

The fixes have resource-based coverage and regression evidence, but do not establish complete coverage of every game text. Missing official resources, unknown display paths and in-game validation remain separate concerns. See the [verification report](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.3.md).

## 日本語

- 分岐、改ページ、表情制御を含む動的な会話の対応漏れを修正しました。同じ本文でも、表情が異なる場合は元の呼び出し情報を保持します。
- 追加の作業フラグを使うアイテム引き渡し通知と、会話・字幕内のアイテムを含む全文の対応を追加しました。
- 関数内の断片的な対応が優先され、アイテムを含む文章の一部しか翻訳されない問題を修正しました。確認済みの呼び出しから全文の対応を直接選択します。
- 原文のルビ記法が不完全な一部の外国語の過去ログで、副言語が表示されない問題を修正しました。全文の公式候補だけを使い、通常のテキストや取得済みの会話の識別条件を維持します。
- 元のスクリプト呼び出しと生成結果の照合を追加しました。未分類の呼び出しと公式訳の欠落は、後から確認できるよう報告に残します。

更新前にゲームと旧版ツールを通常の手順で終了してください。設定は保持されます。新しい生成規則の適用時に対応キャッシュを再構築します。更新の自動確認は通知のみで、自動インストールは行いません。

修正対象にはリソースに基づく網羅確認と回帰検証がありますが、全ゲーム内テキストへの対応を保証するものではありません。公式リソースの欠落、未確認の表示経路、実機確認は個別に扱います。詳細は[検証記録](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.3.md)をご覧ください。
