# Bilingual Sora 2nd v0.3.11

## 简体中文

- 修复直接以双语模式进入菜单时，部分模板复制控件不应用副语言字号、间距，且无法切回单语的问题。新控件在首次排版前继承原文；已验证道具页的耀晶石标题、使用和舍弃提示。
- 修复重要道具“利贝尔王国地图”遗漏副语言的问题。道具名称按所属资源范围匹配，不再与同名地图菜单混淆。
- 修复 DLC 资源跨语言关联。当前游戏的 30 组 DLC 名称和说明均已对齐八种语言，不依赖手写翻译或固定语言组合。
- 已验证直接双语进入、动态还原单语、字号缩放，以及地图和 DLC 列表。更新包含底层接入改动，当前游戏连接会保留；完整改动在游戏下次启动时自动应用。

## English

- Fix copied menu controls ignoring secondary size and spacing, and failing to return to a single language when the menu opens in annotated mode. New controls inherit their source before their first layout. Verified the inventory Sepith heading and Use/Discard hints.
- Resolve the inventory's Map of Liberl name within item resources, without confusing it with a separate map-menu label.
- Fix cross-language DLC resource alignment. All 30 DLC names and descriptions in the supported game now align across eight languages, without handwritten translations or fixed language pairs.
- Verified annotated entry, single-language restoration, font scaling, and the map and DLC lists. This update includes native integration changes; the current game connection remains active and the complete update applies on the next game launch.

## 日本語

- 双言語表示でメニューを開くと、複製された一部の項目に副言語の文字サイズ・間隔が反映されず、単言語表示にも戻せない問題を修正しました。初回配置前に元のテキストを引き継ぎます。アイテム画面のセピス見出し、「使う」「捨てる」で確認しました。
- アイテム名「リベール王国の地図」をアイテム用リソース内で照合し、別の地図メニュー項目との混同による表示漏れを修正しました。
- DLC リソースの言語間対応付けを修正しました。対応するゲームの全30組の DLC 名称・説明が8言語で対応し、手書きの訳文や固定の言語ペアに依存しません。
- 双言語での初回表示、単言語への復帰、文字サイズ変更、地図・DLC 一覧を確認しました。ネイティブ接続部分の変更を含むため、現在の接続は維持し、完全な更新は次回のゲーム起動時に適用します。
