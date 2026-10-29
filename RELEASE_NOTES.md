# 1.0.4

## 简体中文

- 补齐上一轮剩余的 14 个动态调用：13 处含动作调用的对白，以及七种耀晶石的实时数量面板。
- 修正 NPC 的三句错配：不同语言的剧情分支有增减时，按实际分支条件关联，避免后续台词整体错位。
- 补齐英文目标下部分旧日志的副文。官方原串末尾未闭合的 `<R>` 标记保留原样，仅对已确定的完整官方配对生效。
- 增加八语分支检查、表字段文本候选分类和 ASCII 扫描。原始 114 个动态调用均有编译路由；未来新增的未知字段和错误渲染会让相应检查失败。

更新前请正常退出游戏和旧版工具，再安装新版；设置会保留。新规则会重建映射缓存。自动检查更新只提示，不自动安装。

已检查的中日文资源中，有 8 条中文对白缺少对应官方日文；工具保留原文。资源审计、生产回调和隐藏原生宿主验证的范围，见[检查记录](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.4.md)。本次没有逐场景玩家实机验收。

## English

- Covered the 14 dynamic calls left by the previous audit: 13 dialogue calls containing nested actions and the live quantity panel for all seven sepith types.
- Corrected three NPC dialogue pairs shifted by a localized story branch. Associations follow the actual branch selector when a language adds or removes a branch.
- Restored secondary text in some older logs with English as the target. A trailing unmatched `<R>` in an official resource is preserved and accepted only for a verified complete official pair.
- Added branch checks across eight languages, table-field candidate classification and an ASCII-inclusive scan. All 114 raw dynamic calls now have compiled routes; new unknown fields and incorrect rendering fail their respective audits.

Exit the game and the old tool normally before installing. Settings are preserved. The new rules rebuild the mapping cache once. Automatic update checks only notify and never install automatically.

Eight Chinese dialogue lines in the audited resources lack corresponding official Japanese text and retain their original text. The [verification report](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.4.md) separates resource audits, production callbacks and owned native-host checks. This release has not received scene-by-scene player acceptance.

## 日本語

- 前回の調査で残った 14 件に対応しました。動作呼び出しを含む会話 13 件と、7 種類のセピスの所持数表示が対象です。
- 言語別のシナリオ分岐によってずれていた NPC の会話 3 件を修正しました。分岐が増減しても、実際の分岐条件に沿って対応付けます。
- 英語を副言語にした際、一部の過去ログで副言語が表示されない問題を修正しました。公式原文の末尾で閉じていない `<R>` は保持し、全文の公式対応が確認できた場合だけ処理します。
- 8 言語の分岐確認、テーブル項目のテキスト候補分類、ASCII を含む検索を追加しました。元の動的呼び出し 114 件すべてに生成経路があり、新しい未分類項目や描画結果の不一致は検証失敗になります。

更新前にゲームと旧版ツールを通常の手順で終了してください。設定は保持されます。新しい規則により対応キャッシュを再構築します。更新の自動確認は通知のみで、自動インストールは行いません。

調査済みリソースには、対応する公式日本語がない中国語の会話が 8 件あります。これらは原文を保持します。リソース照合、製品のコールバック、自作のネイティブ検証プロセスの範囲は[検証記録](https://github.com/Llugaes/bilingual-sora-2nd/blob/main/docs/verification/dialogue-coverage-1.0.4.md)をご覧ください。今回、プレイヤーによる全場面の実機確認は行っていません。
