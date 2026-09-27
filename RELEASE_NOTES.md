# Bilingual Sora 2nd v0.3.14

## 简体中文

- 修正带分隔线等前缀的日志在反复排版时主副文字持续缩小；补齐带动态表情控制头的完整对白匹配，防止先拆行而遗漏副文。纯图标行不再消耗下一行的译文。
- 补充详情内 HP／EP 百分比回复、全部回复与直接效果标签的资源组合，保留各语言的词序；如“HP回复30％／解除减益”。
- 修正字号钩子误入公共格式出口造成的副语言反复缩小，保留强调字号与副语言的比例。扩展几何范围尺寸、效果程度、彩色分段及道具类型的详情匹配。
- 补充全屏说明的多段文本提取，覆盖“游击士协会招牌”等由颜色标记、字符串与换行组成的说明；不能确认的动态控制流仍保留原文。
- 支持连续窗口标记，补齐“第三把钥匙”等居中提示；修正地图跳转点、调查点、名称、状态和提示表的跨语言资源身份。增加未经过滤的原始资源清单，保留动态和歧义项，不将入库数量当作实机覆盖率。
- 对话日志继承新记录写入时的对白来源，区分原文相同、译文不同的剧情分支；旧记录无法确认来源时继续保留原文。增加八语资源缺项、歧义与目标文本检查。
- 统一首次显示与热切换后的排版流程，修复图鉴左侧名称及技能、装备、道具底部详情的上下位置不一致。补充字号、混排图标、多行文字和动画状态的回归检查。
- 改进书籍长文本换行、图鉴名称、任务记录及手册规章的副语言读取，保留正文中的数字和图标尺寸。
- 副语言支持 RGB 颜色系数、透明度滑块及双语整体上下偏移；加入按主文进度显示副文和副文图标的处理。新配置默认采用 RGB **230 / 230 / 230、不透明度 90%**。已有自定义设置继续保留。
- 精简悬浮窗与设置界面，支持中／英／日界面语言；设置窗跟随悬浮窗移动，扩大拖动区域，增加手动重连入口。显示模式分为双语与单语言，**仅单语言模式显示切换方式整行选项**。
- 随包提供跨语言字体补齐所需的加载器与独立后备字形。合并字库在用户本机从游戏文件生成，发行包不包含游戏字库。
- 优化语言资源准备、日志测量缓存及持续解析开销。**双语日志仍可能在打开时出现约 700 ms 停顿并降低帧率，这不是已消除的问题。** 对流畅度敏感的玩家，推荐“单语言模式＋按住切换”。

本次包含驻留底层代码与字库更新。请退出游戏后安装更新，再重新启动游戏以完整生效。安装包与便携包均可使用；升级保留个人设置。

## English

- Fix cumulative text shrinking when log rows with decorative prefixes rebuild. Match complete dialogue bodies before splitting lines when live expression controls differ, and keep icon-only lines from consuming the next line's translation.
- Add detail-scoped HP/EP percentage and full-recovery combinations plus direct effect labels, preserving each locale's word order.
- Isolate the font-size hook from the shared formatting exit to stop repeated secondary-text shrinking at color changes, preserving the scale during native emphasis. Extend detail matching for geometric range sizes, effect grades, colored fragments, and item categories.
- Extract multipart full-screen notes, including the Bracer Guild signboard note, assembled from color tags, strings, and line breaks. Unverified dynamic control streams retain their source text.
- Handle repeated window controls in centered hints and correct resource identities in map destinations, interaction labels, names, status, and tips. Inventory raw resources before filtering and retain unresolved dynamic or ambiguous entries; catalog totals are not in-game coverage claims.
- Retain dialogue provenance when new log records are written to distinguish identical source lines with different translations. Older records without a verified origin keep their source text. Add checks for missing locales, ambiguity, and target text across eight languages.
- Unify first-entry and hot-switch layout, fixing vertical-position differences in catalog names and skill, equipment, and item details. Extend regression coverage for font size, mixed icons, multiline text, and animated states.
- Improve secondary-text lookup for catalog names, quest records, and handbook rules, and wrapping for long book text. Preserve native number and icon sizes.
- Add RGB tint multipliers, an opacity slider, and a bilingual vertical offset, plus secondary reveal tied to primary progress and secondary icon handling. New configurations default to **RGB 230 / 230 / 230 with 90% opacity**. Existing custom settings are preserved.
- Simplify the overlay and settings, with Chinese, English, and Japanese UI languages, coupled window movement, a larger drag area, and manual reconnect. Display modes are bilingual or single language; **the entire switching-method row appears only in single-language mode**.
- Bundle the loader and independent fallback glyphs needed for cross-language font coverage. Merged fonts are generated from the user's local game files; game fonts are not redistributed.
- Reduce resource-preparation, log-measurement, and ongoing parsing overhead. **Opening the bilingual log may still hitch for around 700 ms and reduce frame rate; this limitation remains.** For smoother play, use single-language mode with hold-to-switch.

This release updates resident native code and font delivery. Exit the game before updating, then restart it for all changes to apply. Both installer and portable packages are available; upgrades preserve personal settings.

## 日本語

- 区切り線などを含む履歴の再描画で主文・副文が縮み続ける問題を修正しました。実行時の表情指定が異なる会話も、行を分割する前に本文全体を照合します。アイコンだけの行が次行の訳文を消費する問題も修正しました。
- HP／EP の割合回復・全回復と直接表示される効果名の照合を追加し、各言語の語順を維持します。
- 文字サイズのフックを共通の書式処理から分離し、色変更のたびに副言語が縮小される問題を修正しました。強調時の比率を維持し、範囲サイズ、効果の程度、色で分割された文言、アイテム種別の説明照合を拡張しました。
- 「遊撃士協会の看板」など、色指定・文字列・改行を組み合わせた全画面の説明文を抽出します。確認できない動的な制御列は原文を保持します。
- 連続する表示制御を含む中央揃えのヒントに対応し、移動先・調査地点・名前・ステータス・ヒントの言語間リソース識別を修正しました。抽出前の全リソースを監査し、動的な文や曖昧な項目を明示します。登録件数を実機での表示確認済み件数とは扱いません。
- 新しい会話履歴には元の会話の識別情報を引き継ぎ、原文が同じで訳文が異なる台詞を区別します。出典を確認できない既存の履歴は原文を保持します。8言語の欠落・曖昧さ・表示対象テキストの検証を追加しました。
- 初回表示と表示モード切替後の配置処理を統一し、図鑑の項目名や技・装備・アイテムの説明で上下位置が異なる問題を修正しました。文字サイズ、アイコン混在、複数行、文字送りの回帰チェックも追加しました。
- 図鑑名、依頼記録、手帳の規則における副言語の取得と、書籍の長文の折り返しを改善しました。数字やアイコンの元のサイズを維持します。
- 副言語の RGB 係数、不透明度スライダー、二言語全体の上下位置調整を追加し、主文の表示進行に合わせた副文表示と副文アイコンにも対応しました。新規設定の初期値は **RGB 230 / 230 / 230、不透明度 90%** です。既存の個別設定は保持します。
- 小型ウィンドウと設定画面を整理し、中国語・英語・日本語の UI、ウィンドウの連動移動、広いドラッグ領域、手動再接続を追加しました。表示モードは二言語と単一言語の二種類で、**切替方法の行全体は単一言語モードでのみ表示**します。
- 多言語フォント補完用のローダーと独立した補助字形を同梱しました。統合フォントは利用者のゲームファイルから端末上で生成し、ゲームのフォントは再配布しません。
- 言語リソースの準備、ログの計測キャッシュ、継続的な解析処理を軽減しました。**二言語ログを開く際の約 700 ms の停止やフレームレート低下は、現在も発生する場合があります。** 滑らかさを優先する場合は「単一言語モード＋押している間だけ切替」を推奨します。

常駐コードとフォント処理の更新を含みます。ゲームを終了してから更新し、再起動してください。インストーラー版とポータブル版を用意しており、更新時も個人設定を保持します。
