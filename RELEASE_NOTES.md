# 0.4.4 — 更新通道修复（本地候选，未发布）

- 国内版本发现、历史版本、清单与包下载改用静态索引和固定 tag 附件，不依赖 Gitee releases/attachments API；GitHub 继续作为备用源。
- 保留版本、仓库、主机、大小和完整 SHA 校验，新增索引身份、HTML/重复字段、版本回退及同版清单变化拒绝。
- 缓存与失败退避跨重启保留，手动检查至少间隔 60 秒；两源失败时提供国内手动下载与 GitHub 备用入口。
- 延续 0.4.3 的游戏版本适配、外置字体默认行为及其他已验收功能，不包含 1.0 未验收功能。

新索引尚未公开；候选需 root 独立审查、索引端点验证与用户验收后才允许发布。已发 0.4.3 对象保持不变，旧客户端两源均不可用时需一次手动 Setup 迁移。raw 本机匿名验证成功不代表全国或永久可用。

## English

The local 0.4.4 candidate removes Gitee release-API dependence from discovery and component updates using a scoped static index and immutable release assets. Version, repository, HTTPS, size and SHA checks remain required. Cached checks and failure backoff survive restarts; both-source failures offer manual downloads. The new index is not public yet, and this candidate is not released. Existing 0.4.3 clients may require a one-time manual Setup migration.

## 日本語

0.4.4 のローカル候補では、限定された静的索引と固定タグの添付ファイルで国内更新を行います。バージョン・リポジトリ・HTTPS・サイズ・SHA の検証を維持し、確認結果と失敗時の待機時間を再起動後も保持します。新しい索引は未公開で、この候補も未リリースです。0.4.3 の既存クライアントは、一度手動で Setup を適用する必要があります。

# 0.4.3 — 新官方游戏版本兼容热修

- 恢复 Steam build 25721473（游戏 EXE 1.4.0.0）的原生函数定位，修复更新后无法连接的问题。
- 仅归一化已审查日志诊断调用的源码行号，同时校验对应诊断函数；对象字段、内部控制流、调用关系和进程指令快照检查继续保留。
- 已安装旧版合并字体时，只有本安装的完整受管收据、旧缓存和当前字体及加载器全部校验一致，才把旧字体作为新候选的替换源；未知或混杂字体继续拒绝。
- 保留 0.4.2 功能及手动更新方式。本次为版本兼容热修，动态效果描述的后续改进留待 1.0。

请正常退出游戏和工具后更新，再重新启动。兼容范围以已验证原生合同为准，不保证任意未来版本或 MOD 组合。

## English

- Restores native-function resolution for Steam build 25721473 (game EXE 1.4.0.0), fixing connection failures after the game update.
- Normalizes reviewed diagnostic source-line arguments while checking their diagnostic callee. Object fields, internal control flow, call relationships and live instruction checks remain required.
- Accepts a prior merged font only when this installation's complete managed receipt, cached font package, current fonts and audited loader all agree. Unknown or mixed files remain rejected.
- Keeps 0.4.2 features and manual updates. Further dynamic-effect text improvements remain planned for 1.0.

Exit the game and tool normally before updating, then relaunch. Compatibility requires the verified native contracts; arbitrary future builds and MOD combinations are not guaranteed.

## 日本語

- Steam build 25721473（ゲーム EXE 1.4.0.0）の関数検出を修正し、ゲーム更新後の接続失敗に対応しました。
- 検証済みの診断呼び出しのソース行番号のみを正規化し、呼び出し先も検証します。オブジェクトのフィールド、分岐、呼び出し関係、実行中の命令照合は引き続き必須です。
- 旧版の統合フォントは、このゲームの管理記録、完全なキャッシュ、現在のフォントと確認済みローダーがすべて一致する場合のみ認識します。不明または混在したファイルは拒否します。
- 0.4.2 の機能と手動更新を維持します。動的な効果説明の改善は 1.0 で継続する予定です。

ゲームとツールを通常の方法で終了してから更新し、再起動してください。任意の将来のバージョンや Mod の組み合わせを保証するものではありません。

# 0.4.2 — EXE 兼容与非中文游戏语言支持

- 按工具实际使用的原生函数和数据定位 EXE，允许已识别函数迁址；无关文件信息、代码和资源变化不再阻止连接。原版 EXE 和全语音 MOD 1.0.7 附带 EXE 已通过连接及双语显示实测。
- 游戏本身使用日文、英文等支持语言时，工具可正确准备语言映射；游戏内切换文字语言后会重新匹配，并保留用户选择的主副语言。
- 保留已验收候选中的跨语言旧存档摘要、Hide UI、复活恢复效果及标点误配修复。

本版已通过 DEV4 用户实机验收。自动检查新版本仍只提示，下载和安装由用户手动触发，保留现有配置。请正常退出游戏和工具后更新，再重新启动。

兼容实测仅替换上述 MOD 的 EXE，未安装完整语音资源包；不代表任意 EXE 或所有 MOD 组合均已适配。部分动态效果描述仍有遗漏，安排在 0.4.3 继续修补。

## English

- EXE compatibility now locates the native functions and data used by the tool, including recognized functions moved to new addresses. Unrelated metadata, code and resource changes no longer block connection. The original EXE and the EXE bundled with full-voice MOD 1.0.7 passed connection and bilingual-display checks.
- Language mapping works when the game itself uses Japanese, English or another supported language. Changing the game's text language refreshes the mapping while preserving your selected primary and secondary languages.
- Includes the accepted candidate's fixes for saved summaries from other languages, Hide UI, revival effects and incorrect punctuation matching.

DEV4 passed user playtesting. Update checks only notify; downloading and installation remain manual and preserve settings. Exit the game and tool normally before updating, then relaunch.

The MOD check replaced only its EXE, without installing the full voice resources. Arbitrary EXEs and all MOD combinations are not covered. Remaining dynamic-effect text gaps are scheduled for 0.4.3.

## 日本語

- ツールが使う関数とデータを基準に EXE を照合し、認識できる関数のアドレス移動にも対応しました。無関係なファイル情報・コード・リソースの変更で接続を拒否しなくなりました。原版と全ボイス Mod 1.0.7 同梱 EXE で接続と二言語表示を確認しました。
- ゲーム自体が日本語・英語などの対応言語でも言語マッピングを準備できます。ゲーム内の文字言語を変更した場合も、主言語・副言語の設定を保持したまま再照合します。
- 検証済み候補版の修正（別言語の古いセーブ概要、Hide UI、復活効果、句読点の誤訳）を含みます。

DEV4 はユーザーの実機確認を通過しました。更新確認は通知のみで、ダウンロードとインストールは手動です。設定を保持します。ゲームとツールを通常の方法で終了してから更新し、再起動してください。

Mod の実測は EXE の置き換えのみで、音声リソース一式は導入していません。すべての EXE や Mod の組み合わせを保証するものではありません。動的な効果説明の残りの欠落は 0.4.3 で修正を進めます。
