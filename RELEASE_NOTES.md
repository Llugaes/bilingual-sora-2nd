# 1.0.2

## 简体中文

- 修复开启双语后游戏内存持续增长的问题。修正原生回调依赖中的释放缺陷，保留现有文字显示和交互。
- 降低文本模型准备的内存峰值；已有完整缓存通过校验后直接复用，减少重复解析和临时数据。
- 统一料理等菜单小标题的字号适配，修复小字号下主副文字大小颠倒、位置偏低的问题，保留正常字号页面的表现。
- 补齐装备“女性专用／男性专用／角色专用”等文本关联，共用原生八语资源编译规则。
- 统一所有道具说明的双语整体居中，保留图标与混排文本；修复重新进入菜单时位置跳动、切换道具后才恢复的问题。
- 合并重复的效果判断与模型写入逻辑，保留完整文本关联和原有拒绝边界。

升级前请正常退出游戏和旧版工具，再安装新版；已有设置会保留。自动检查更新只提示，不自动安装。

同机对已验收 r7 与本次 r8 候选的模型准备进程树实测：冷缓存峰值从 2451 降至 1858 MiB，热缓存峰值从 1096 降至 21 MiB。冷准备耗时约 207 → 212 秒，热准备约 2.73 → 1.03 秒；本次不声称冷准备加速。固定菜单验证未再出现此前约 10 MiB/分钟的线性增长；这不代表所有游戏场景或帧率测试。方法与验证范围见 [内存验证记录](https://github.com/Llugaes/bilingual-sora-2nd/blob/v1.0.2/docs/verification/memory-r8.md)。

## English

- Fixed continuous growth in game memory while bilingual display is enabled by correcting a native callback cleanup defect in a dependency. Existing text display and interaction are preserved.
- Reduced peak memory during text-model preparation. Fully validated existing caches are reused directly, avoiding repeated parsing and temporary data.
- Unified scaling for small menu headings, including the recipe screen. Fixed reversed primary/secondary text sizes and downward displacement at small font sizes, while preserving normal-size layouts.
- Added equipment restriction labels such as female-only, male-only and character-only through shared compilation rules for the game's eight language resources.
- Unified vertical centering of all bilingual item descriptions while preserving icons and mixed text. Fixed position jumps on menu entry that previously recovered only after selecting another item.
- Consolidated duplicate effect decisions and model-writing logic while preserving complete text associations and existing rejection rules.

Exit the game and the old tool normally before installing. Your settings are preserved. Automatic update checks only notify; they never install automatically.

On the same machine, model-preparation process-tree measurements comparing the accepted r7 candidate with r8 showed cold-cache peak memory falling from 2451 to 1858 MiB, and warm-cache peak memory from 1096 to 21 MiB. Preparation took approximately 207 → 212 seconds cold and 2.73 → 1.03 seconds warm; no cold-start speedup is claimed. Fixed-menu validation no longer showed the previous linear growth of roughly 10 MiB/minute. This does not cover every game scene or establish a frame-rate improvement. See the [memory verification report](https://github.com/Llugaes/bilingual-sora-2nd/blob/v1.0.2/docs/verification/memory-r8.md) for methods and scope.

## 日本語

- 二言語表示中にゲームのメモリ使用量が増え続ける問題を修正しました。依存ライブラリのネイティブコールバック解放処理を修正し、既存の文字表示と操作は維持しています。
- テキストモデル準備時のピークメモリ使用量を削減しました。完全性を検証済みのキャッシュを直接再利用し、再解析や一時データを減らしています。
- 料理画面などの小見出しの文字サイズ調整を共通化しました。小さい文字で主言語と副言語のサイズが逆転したり、下にずれたりする問題を修正し、通常サイズの表示は維持しています。
- 「女性専用」「男性専用」「キャラクター専用」などの装備条件の対応を追加しました。ゲームの八言語リソースを共通ルールで処理します。
- すべてのアイテム説明で二言語全体を上下中央に配置する処理を共通化し、アイコンや混在する文字を維持しました。メニューを開くと位置がずれ、別のアイテムを選ぶまで戻らない問題も修正しました。
- 重複していた効果の判定とモデル書き出しを整理し、テキストの対応関係と従来の拒否条件を維持しました。

更新前にゲームと旧版ツールを通常の手順で終了してください。設定は保持されます。更新の自動確認は通知のみで、自動インストールは行いません。

同一環境で、実機確認済みの r7 候補版と r8 のモデル準備プロセス全体を測定しました。キャッシュなしのピークは 2451 → 1858 MiB、キャッシュありは 1096 → 21 MiB でした。処理時間はそれぞれ約 207 → 212 秒、2.73 → 1.03 秒で、初回準備の高速化は主張しません。固定メニューでの検証では、従来の約 10 MiB／分の継続的な増加は再現しませんでした。全場面の検証やフレームレート改善を示すものではありません。測定方法と範囲は[メモリ検証記録](https://github.com/Llugaes/bilingual-sora-2nd/blob/v1.0.2/docs/verification/memory-r8.md)を参照してください。
