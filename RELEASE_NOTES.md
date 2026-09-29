# Bilingual Sora 2nd v0.3.24

## 简体中文

- 修复地图列表“神秘森林”等地点名称因复制后丢失来源、与其他表同文异译而不显示副语言的问题；整张地点表使用相同规则，覆盖八种语言。
- 补齐游戏运行期间加载字体时，已有 HUD、战斗及弹窗文本材质仍引用旧图集的刷新。保持同文、阴影和切回原字体时也会核对。
- 减少普通文本初始化时不必要的 JavaScript 回调，单语和双语都受益。隐藏原生宿主中 12,000 次普通初始化从约 81.8 ms 降至 2.0 ms；此结果不代表完整游戏帧耗时，战斗、宝箱和日志的实际卡顿仍需游玩验证。
- “界面语言”移入“设置和更新”；“语言”页的启用开关置顶，主副语言并排，下拉框不再被滚轮误切换。
- 每次新启动游戏时，主语言自动同步游戏实际文字语言一次。同一次游戏中手动调整和重新连接会保留选择，副语言及其他偏好保留。

包含 0.3.23 的彻底退出修复及可识别的 UI／Backend／Worker 进程名。本版底层改动在下一次正常启动游戏时生效，不强制结束当前游戏。首次安装的字体免重启 HUD 画面仍待实机确认；代码回归、原生宿主和全表审计记录见仓库验证报告，不宣称所有卡顿已经消失。

## English

- Fix copied map location names such as Mistwald losing their source context when another table has a different translation. Apply one rule to the complete map-spot family across eight languages.
- Refresh existing HUD, battle and popup label materials when fonts load into a running game, including unchanged text, shadows and restoration of the original font atlas.
- Remove unnecessary JavaScript callbacks for ordinary text initialization in both single and bilingual modes. A hidden native host improved from about 81.8 ms to 2.0 ms for 12,000 calls; this is not a complete game-frame benchmark. Battle, chest and log stutters still require gameplay validation.
- Move Interface language to Settings and updates. Put the enable switch first and primary/secondary choices side by side. Scrolling over closed dropdowns no longer changes selections.
- Sync the primary language once from the actual game text language for each new game process. Later manual changes and reconnects to that process retain the selection; secondary language and other preferences are preserved.

Includes the 0.3.23 exit fix and identifiable UI/Backend/Worker process names. Native changes take effect on the next normal game launch; the current game is not forcibly closed. First-install HUD appearance without a font-related restart still needs in-game confirmation. Passing regression and hidden-host checks does not establish that all stutters are gone.

## 日本語

- マップ地点名のコピーによる参照元の消失と、別テーブルとの訳語の相違により「神秘森林」などの副言語が表示されない問題を修正。地点名テーブル全体を八言語で確認しました。
- ゲーム起動中のフォント読み込み時に、既存の HUD・戦闘・通知テキストが古い画像を参照し続ける問題を修正。変更のない本文、影、元フォントへの復元も確認します。
- 通常テキストの初期化で不要だった JavaScript コールバックを削減。単言語・二言語とも対象です。独立したネイティブ検証プロセスでは 12,000 回が約 81.8 ms から 2.0 ms に短縮しましたが、ゲーム全体のフレーム時間を示すものではありません。戦闘・宝箱・履歴の停止は実プレイでの確認が必要です。
- 画面の言語を「設定と更新」へ移動。「言語」タブの有効化スイッチを最上部に、主言語と副言語を横並びに配置。閉じたドロップダウンでホイールによる誤変更を防止します。
- ゲームを新しく起動するたびに実際の表示言語を主言語へ一度だけ同期。その後の手動変更や同じプロセスへの再接続では選択を保持し、副言語とその他の設定も維持します。

0.3.23 の終了修正と、識別しやすい UI／Backend／Worker プロセス名を含みます。ネイティブ部分の変更は次回の通常起動で有効になり、現在のゲームは強制終了しません。初回導入時のフォント関連の再起動なしでの HUD 表示は実機確認待ちです。回帰検証の成功は、すべての処理停止が解消されたことを意味しません。
