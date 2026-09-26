"""UI translations only. Game language selection never changes this locale."""

import locale
from functools import lru_cache

UI_LANGUAGES = {
    "auto": "跟随系统",
    "zh-Hans": "简体中文",
    "en": "English",
    "ja": "日本語",
}
_language = "zh-Hans"

# Chinese source messages are stable UI keys. Do not put game text in this catalog.
_ROWS = """
跟随系统|Follow system|システムに従う
语言|Language|言語
文字排版|Text layout|文字レイアウト
更新|Updates|更新
选择界面语言|Choose interface language|画面言語を選択
初始语言设置|Initial language setup|初期言語設定
选择游戏当前的文本语言|Choose the game's current text language|ゲームの現在の表示言語を選択
默认副语言|Default secondary language|既定の副言語
继续|Continue|続ける
退出|Exit|終了
语言与显示设置|Language and display|言語と表示
快捷操作|Quick actions|クイック操作
更新与维护|Updates and maintenance|更新とメンテナンス
显示设置|Display settings|表示設定
文字与排版|Text and layout|文字とレイアウト
快捷键|Shortcuts|ショートカット
实时生效|Applies immediately|即時反映
修改自动保存|Changes save automatically|変更は自動保存されます
界面语言与 Mod 显示语言独立保存。|The interface locale is saved separately from the mod display languages.|画面言語は Mod の表示言語とは別に保存されます。
当前连接中的快捷键和排版会立即应用。|Shortcuts and layout apply to the current connection immediately.|ショートカットとレイアウトは現在の接続にすぐ反映されます。
更新会在游戏连接结束后安装。|Updates install after the game connection ends.|更新はゲーム接続の終了後にインストールされます。
界面语言|Interface language|画面の言語
主语言|Primary language|主言語
副语言|Secondary language|副言語
连接状态|Connection status|接続状態
检测到的游戏内文字语言|Detected in-game text language|検出されたゲーム内の表示言語
简中|Simplified Chinese|簡体字中国語
繁中|Traditional Chinese|繁体字中国語
日文|Japanese|日本語
英文|English|英語
韩文|Korean|韓国語
法文|French|フランス語
德文|German|ドイツ語
西文|Spanish|スペイン語
设置|Settings|設定
游戏内文字语言|In-game text language|ゲーム内の表示言語
游戏内文字语言须与游戏设置一致，用于识别原文。|Match the game's text language so the mod can identify the source text.|原文を識別するため、ゲーム内の表示言語と一致させてください。
游戏内文字语言（自动检测）|In-game text language (detected)|ゲーム内の表示言語（自動検出）
由后端检测游戏内文字语言；检测完成前会显示等待状态。|The backend detects the in-game text language. It remains waiting until detection completes.|ゲーム内の表示言語はバックエンドが検出します。完了まで待機中と表示されます。
等待检测|Waiting for detection|検出待ち
由后端检测，无法在设置中编辑。|Detected by the backend and cannot be edited here.|バックエンドが検出するため、ここでは編集できません。
后端已检测到游戏内文字语言。|The backend detected the in-game text language.|バックエンドがゲーム内の表示言語を検出しました。
等待后端检测游戏内文字语言。|Waiting for the backend to detect the in-game text language.|バックエンドによるゲーム内の表示言語の検出を待機中です。
检测状态：|Detection status: |検出状態：
状态：|Status: |状態：
语言组合：|Language pair: |言語の組み合わせ：
快捷键：|Shortcut: |ショートカット：
打开或关闭设置。|Open or close settings. |設定を開閉します。
连接游戏|Connect game|ゲームに接続
重新连接|Reconnect|再接続
正在连接…|Connecting…|接続中…
正在重新连接…|Reconnecting…|再接続中…
连接器准备中…|Connector preparing…|接続機能を準備中…
自动连接器正在准备，请稍候…|The auto-connector is preparing. Please wait…|自動接続機能を準備中です。お待ちください…
已请求重新连接，正在检查游戏状态…|Reconnect requested; checking the game state…|再接続を要求しました。ゲームの状態を確認中です…
重新连接请求失败：|Reconnect request failed: |再接続要求に失敗しました：
连接器已关闭|Connector closed|接続機能は停止しました
自动连接器已关闭，无法请求重新连接。|The auto-connector is closed and cannot accept a reconnect request.|自動接続機能は停止しており、再接続を要求できません。
手动连接游戏|Connect game manually|ゲームに手動接続
请求自动连接器立即重新检查，不会启动游戏或替换现有连接。|Ask the auto-connector to check immediately. It does not start the game or replace an existing connection.|自動接続機能に即時の再確認を要求します。ゲームを起動せず、既存の接続も置き換えません。
可打开设置后手动重新连接。|Open settings to reconnect manually.|設定を開いて手動で再接続できます。
副语言颜色|Secondary text color|副言語の色
副语言颜色与透明度|Secondary text color and opacity|副言語の色と不透明度
副语言透明度|Secondary text opacity|副言語の不透明度
选择副语言颜色|Choose secondary text color|副言語の色を選択
打开颜色选择器，保存副语言 RGB 颜色。|Open the color picker and save the secondary text RGB color.|カラーピッカーを開き、副言語の RGB 色を保存します。
打开颜色选择器，保存副语言 RGB 颜色和透明度。|Open the color picker and save secondary text RGB color and opacity.|カラーピッカーを開き、副言語の RGB 色と不透明度を保存します。
拖动滑块，实时保存副语言透明度。|Drag the slider to save secondary text opacity immediately.|スライダーをドラッグすると、副言語の不透明度がすぐに保存されます。
主、副语言只改变 Mod 显示，不修改游戏设置。|Primary and secondary languages affect the mod only, not the game's settings.|主言語と副言語は Mod の表示にのみ適用され、ゲーム設定は変更しません。
主语言字号|Primary text scale|主言語の文字倍率
副语言字号|Secondary text scale|副言語の文字倍率
副语言上方间距|Secondary text gap|副言語との間隔
副语言左右偏移|Secondary horizontal offset|副言語の左右位置
双语文本上下偏移（正值向下）|Bilingual vertical offset (+ moves down)|二言語テキストの上下オフセット（＋で下へ）
多行间距|Extra line spacing|行間の追加幅
以游戏原生注音字号为基准|Relative to the game's native ruby text size|ゲーム本来のルビサイズが基準です
负数向左，正数向右|Negative moves left; positive moves right|負の値は左、正の値は右へ移動
修改实时生效。字号为比例，间距沿用游戏布局单位。|Changes apply immediately. Sizes are ratios; spacing uses game layout units.|変更は即時反映されます。文字サイズは倍率、間隔はゲームのレイアウト単位です。
重试语言切换|Retry language change|言語の切り替えを再試行
切换语言|Switch language|言語切り替え
操作|Action|操作
清除手柄绑定|Clear controller shortcut|コントローラーの登録を解除
按下组合键保存；Esc 取消。|Press the shortcut to save. Esc cancels.|キーを押して保存。Esc でキャンセル。
先松开所有按键，再按住组合，全部松开后保存。|Release all controls, hold your combination, then release to save.|すべてのボタンを離してから組み合わせを押し、離すと保存されます。
拖动顶部，一起移动状态条和设置|Drag to move the status bar and settings together|ドラッグしてステータスバーと設定を一緒に移動
修改自动保存  ·  Esc 收起设置|Changes save automatically · Esc closes settings|変更は自動保存 · Esc で設定を閉じる
自动更新|Automatic updates|自動更新
自动更新已关闭|Automatic updates are off|自動更新はオフです
自动下载稳定版，退出游戏后安装。设置会保留。|Download stable updates automatically and install after the game exits. Your settings are kept.|安定版を自動ダウンロードし、ゲーム終了後に適用します。設定は保持されます。
检查更新|Check for updates|更新を確認
查看更新日志|Open update logs|更新ログを開く
使用说明|User guide|使い方
发行说明|Release notes|リリースノート
；开启自动更新即可安装|; enable automatic updates to install|。自動更新をオンにするとインストールされます
语言与模式|Languages and mode|言語とモード
字号与位置|Size and position|文字サイズと位置
按键绑定|Bindings|キー割り当て
版本更新|Updates|更新
Sora Native 双语设置|Sora bilingual settings|Sora 二言語設定
Sora 双语控制台|Sora bilingual controls|Sora 二言語コントロール
双语控制台|Bilingual controls|二言語コントロール
打开设置|Open settings|設定を開く
隐藏界面（后台继续运行）|Hide interface (keep running)|画面を隠す（動作は継続）
退出界面程序（保留双语连接）|Exit interface (keep game connection)|画面を終了（接続は維持）
隐藏界面，后台继续运行；可从托盘或快捷键打开|Hide interface; reopen from the tray or shortcut|画面を隠す。トレイまたはショートカットで再表示
关闭设置，保留小状态条|Close settings; keep status bar|設定を閉じ、ステータスバーを残す
拖动状态条|Drag the status bar|ステータスバーをドラッグ
× / Esc 关闭设置，保留状态条  ·  拖动顶部移动|× / Esc closes settings · Drag the header to move|× / Esc で設定を閉じる · 上部をドラッグして移動
启用双语 Mod|Enable mod|Mod を有効にする
显示模式|Display mode|表示モード
双语模式|Bilingual mode|二言語モード
单语言模式|Single-language mode|単言語モード
单语言切换方式|Single-language switching|単言語の切替方法
同时显示双语|Bilingual annotations (Trails)|二言語注釈（軌跡）
按一下切换语言|Toggle primary / secondary|押すたびに言語を切り替え
按住显示副语言|Hold for secondary language|押している間だけ副言語
立即切换到所选模式|Apply selected mode|選択したモードを適用
高级：原文识别|Advanced: source matching|詳細：原文の照合
游戏原文语言（匹配用）|Game text language (matching)|ゲーム原文の言語（照合用）
主文字号比例|Primary text scale|本文の倍率
副字相对原生注音比例|Annotation scale relative to native ruby|副言語の倍率（元のルビ基準）
副字向上偏移 / 间距|Annotation upward offset / gap|副言語の上方向オフセット・間隔
副字水平偏移（右为正）|Annotation horizontal offset (+ right)|副言語の横方向オフセット（＋は右）
多行额外行距|Extra spacing between lines|複数行の追加間隔
恢复推荐排版|Reset layout|推奨レイアウトに戻す
语言切换（按所选模式）|Language switch (selected mode)|言語切り替え（選択中のモード）
展开 / 隐藏界面|Show / hide interface|画面の表示・非表示
录制键盘组合|Record keyboard shortcut|キーの組み合わせを登録
录制手柄组合|Record controller shortcut|コントローラー操作を登録
清除该动作的手柄绑定|Clear controller binding|コントローラーの割り当てを解除
取消录制|Cancel recording|登録をキャンセル
绑定已保存|Binding saved|割り当てを保存しました
请按组合键…|Press your shortcut…|キーを押してください…
按住组合键后全部松开…|Hold the combination, then release all…|組み合わせを押し、すべて離してください…
录制超时，点击重试|Recording timed out; retry|時間切れ。再試行してください
键盘：|Keyboard: |キーボード：
手柄：|Controller: |コントローラー：
设备：|Devices: |デバイス：
按钮 |Button |ボタン\x20
轴 |Axis |軸\x20
 正向| positive| 正方向
 反向| negative| 逆方向
未绑定|Not bound|未登録
未检测到手柄，可使用键盘|No controller detected; keyboard available|コントローラー未検出。キーボードは使用可能
设备：等待后端上报|Devices: waiting for backend|デバイス：バックエンド待ち
手柄绑定：由后端同步|Controller binding: synced by backend|コントローラー割り当て：バックエンドと同期
后端状态：等待状态文件|Backend: waiting for status|バックエンド：状態待ち
后端状态：|Backend: |バックエンド：
运行中|Running|動作中
未保存：|Not saved: |保存できません：
不支持的键盘组合|Unsupported keyboard shortcut|未対応のキーの組み合わせ
该按键暂不支持；未保存|Unsupported key; not saved|未対応のキーのため保存していません
未知快捷键动作|Unknown shortcut action|不明なショートカット操作
键盘组合含不支持的 Win32 按键|Shortcut contains an unsupported Win32 key|未対応の Win32 キーが含まれています
不支持的面板键盘组合|Unsupported panel shortcut|未対応の画面操作キー
显示动作和面板需要使用不同的键盘快捷键|Language switch and panel need different shortcuts|言語切り替えと画面操作には別のキーを指定してください
显示动作和面板需要使用不同的手柄组合|Language switch and panel need different controller bindings|言語切り替えと画面操作には別のコントローラー操作を指定してください
快捷键不能包含另一个动作的完整组合，否则会同时触发|One shortcut cannot include the other's entire combination|一方のキーの組み合わせに他方を含めることはできません
双语同时显示|Bilingual annotations|二言語注釈
单击切换|Toggle|トグル
按住 / 松开|Hold / release|押す・離す
手动显示|Manual display|手動表示
双语|Bilingual|二言語
连接异常|Connection error|接続エラー
正在准备多语言字体，当前连接继续运行|Preparing multilingual fonts; connection remains active|多言語フォントを準備中。接続は継続します
字体已准备，等待安全安装|Fonts prepared; waiting to install safely|フォント準備完了。安全にインストールできるまで待機中
字体待安装：退出游戏后自动安装，下次启动生效|Fonts pending: installed after game exit, active next launch|フォントはゲーム終了後に自動インストールされ、次回起動時に有効になります
字体安装遇到已有 MOD 文件，请查看详情|Font installation conflicts with existing mod files; see details|既存の MOD ファイルと競合しています。詳細をご確認ください
字体准备或安装失败，请查看详情|Font preparation or installation failed; see details|フォントの準備またはインストールに失敗しました。詳細をご確認ください
多语言字体已就绪|Multilingual fonts ready|多言語フォントの準備完了
多语言字体已安装|Multilingual fonts installed|多言語フォントをインストールしました
正在从本机游戏资源准备多语言字体|Preparing multilingual fonts from local game resources|ローカルのゲームデータから多言語フォントを準備中
字体已准备；请退出并重启游戏后生效|Fonts prepared; exit and restart the game to apply|フォント準備完了。ゲームを終了して再起動すると有効になります
字体安装与已有 MOD 文件冲突|Font installation conflicts with existing mod files|フォントのインストールが既存の MOD ファイルと競合しています
字体准备失败|Font preparation failed|フォントの準備に失敗しました
字体安装失败|Font installation failed|フォントのインストールに失敗しました
正在连接游戏|Connecting to game|ゲームに接続中
已连接|Connected|接続済み
正在连接已有游戏进程，请稍候。|Connecting to the existing game process. Please wait.|起動済みのゲームに接続しています。お待ちください。
已连接到游戏，设置会实时同步。|Connected to the game; settings synchronize live.|ゲームに接続済みです。設定は即時同期されます。
连接未完成；可使用下方按钮重新连接。|Connection did not complete; use the button below to reconnect.|接続を完了できませんでした。下のボタンで再接続できます。
等待已有游戏进程；可离线调整设置。|Waiting for an existing game process; settings can be edited offline.|起動済みのゲームを待機中です。設定はオフラインでも変更できます。
正在准备语言索引…|Preparing language index…|言語索引を準備中…
正在同步|Synchronizing|同期中
未连接游戏|Game not connected|ゲーム未接続
设置已保存 · 连接后生效|Settings saved · Apply on connection|設定を保存済み · 接続後に適用
已停用 · 游戏原文|Disabled · Original game text|無効 · ゲームの原文
连接保留，可随时重新启用|Connection retained; enable whenever needed|接続は維持され、いつでも再有効化できます
按住中 · 副语言|Held · Secondary language|押下中 · 副言語
已松开 · |Released · |解放 ·\x20
正在准备新语言，当前语言继续显示…|Preparing new languages; current text remains…|新しい言語を準備中。現在の表示を維持します…
正在应用新语言…|Applying new languages…|新しい言語を適用中…
正在应用设置…|Applying settings…|設定を適用中…
松开后恢复之前的显示|Release to restore primary language|離すと主言語に戻ります
设置实时生效|Settings apply live|設定は即時反映されます
自动连接异常|Automatic connection error|自動接続エラー
等待游戏 · 自动连接|Waiting for game · Auto-connect|ゲーム待機中 · 自動接続
点击设置展开|Click Settings to expand|設定をクリックして展開
自动关联已运行的游戏；游戏稍后启动也会自动连接|Automatically connects when the game is running|起動中のゲームに自動接続します
自动连接已开启，等待游戏启动|Auto-connect enabled; waiting for game|自動接続有効。ゲームの起動待ち
正在后台准备语言缓存，完成后自动连接|Preparing language cache in the background; connecting when ready|言語キャッシュを準備中。完了後に自動接続します
预缓存失败：|Cache preparation failed: |キャッシュの準備に失敗：
正在安装更新，稍后自动连接|Installing update; connection will follow|更新を適用中。完了後に自動接続します
检测到多个游戏进程，请保留一个|Multiple game processes detected; keep one|複数のゲームを検出しました。一つだけ起動してください
自动连接正在运行|Automatic connection in progress|自動接続中
已发现游戏，正在自动连接…|Game found; connecting…|ゲームを検出。接続中…
连接未成功|Connection unsuccessful|接続できませんでした
连接失败：|Connection failed: |接続失敗：
自动检测暂不可用：|Detection temporarily unavailable: |自動検出を利用できません：
正在连接，请稍候…|Connecting; please wait…|接続中です。お待ちください…
后端已连接，直接调整设置即可|Connected; settings can be adjusted now|接続済み。設定を変更できます
正在连接；首次加载索引需要几秒。不会启动游戏。|Connecting; preparing the local index. The game is not launched.|接続中。ローカル索引を準備します。ゲームは起動しません。
连接未成功，请确认游戏已运行后重试。|Connection failed; check the game is running.|接続できません。ゲームが起動しているか確認してください。
配置读取失败：|Cannot read settings: |設定を読み込めません：
后端状态：状态文件读取失败：|Cannot read backend status: |バックエンドの状態を読み込めません：
未连接游戏 · 可离线调整并保存设置|Offline · Settings can still be edited and saved|未接続 · 設定の変更と保存は可能です
后端状态：未运行或连接已中断|Backend stopped or disconnected|バックエンド停止または接続切断
正在连接并准备索引…|Connecting and preparing index…|接続・索引準備中…
正在准备语言索引，当前语言继续显示…|Preparing index; current text remains…|索引準備中。現在の表示を維持します…
正在应用语言索引…|Applying language index…|言語索引を適用中…
后端状态：已停用，连接保留至游戏退出|Disabled; connection stays until the game exits|無効。ゲーム終了まで接続を維持します
后端状态：异常，正在恢复原文|Backend error; restoring original text|バックエンド異常。原文を復元中
；可点击“立即切换”重试|; apply the selected mode to retry|。「適用」で再試行できます
；已应用 |; applied to |。適用数：
 处；| labels; | 箇所：
当前版本：|Version: |現在のバージョン：
GitHub 发行版本|GitHub releases|GitHub リリース
自动检查并安装稳定版|Automatically install stable updates|安定版を自動確認・インストール
仅检查并提示|Check and notify only|確認と通知のみ
关闭自动检查|Disable automatic checks|自動確認を無効にする
立即检查更新|Check for updates|今すぐ更新を確認
当前是开发目录：可检查版本，自动更新不会覆盖本地源码。|Development checkout: checks are available; source is never overwritten.|開発フォルダー：更新の確認は可能ですがソースは上書きしません。
等待检查更新|Waiting to check for updates|更新確認待ち
正在检查 GitHub 稳定版…|Checking GitHub stable releases…|GitHub の安定版を確認中…
仓库尚未发布稳定版|No stable release published yet|安定版はまだ公開されていません
当前已经是最新稳定版|Already on the latest stable release|最新の安定版です
正在下载 |Downloading |ダウンロード中：
更新未完成：|Update incomplete: |更新未完了：
；当前目录不会被覆盖，请使用发行包|; source checkout is protected; use a release package|。開発フォルダーは保護されています。配布版を使用してください
；选择自动安装后生效|; select automatic installation to apply|。自動インストールを選択すると適用されます
；已验证，连接结束后安装|; verified; install after game disconnects|。検証済み。ゲーム切断後に適用します
已安装 |Installed |インストール済み：
，界面将自动刷新|; interface will reload|。画面を再読み込みします
primary|Primary language|主言語
secondary|Secondary language|副言語
annotation|Bilingual annotations|二言語注釈
idle|idle|待機中
recording|recording|登録中
release_to_save|release to save|離すと保存
complete|complete|完了
"""
MESSAGES = {
    parts[0]: {"en": parts[1], "ja": parts[2]}
    for row in _ROWS.strip().splitlines()
    if len(parts := row.split("|")) == 3
}
MESSAGES.update(
    {
        "按住：副语言单语，松开：主语言单语。单击切换：主／副单语来回切换。\n双语注解是轨迹专用模式；所有对话、菜单与过场字幕均在主文上方显示副语言。": {
            "en": "Hold: secondary only; release: primary only. Toggle: alternate between the two.\nTrails annotations show the secondary language above primary text in menus, dialogue and cutscenes.",
            "ja": "押している間は副言語のみ、離すと主言語のみ。トグルは押すたびに切り替えます。\n二言語注釈では、メニュー・会話・カットシーンのすべてで主言語の上に副言語を表示します。",
        },
        "同一组快捷键按所选模式工作：按住、单击切换，或轨迹双语注解。\n录制键盘：按下组合键；Esc 取消。\n录制手柄：先松开所有按键和摇杆，再按住组合，全部松开后保存。": {
            "en": "One binding follows the selected mode: hold, toggle, or Trails annotations.\nKeyboard: press your shortcut; Esc cancels.\nController: start neutral, hold the combination, then release all to save.",
            "ja": "同じ割り当てが選択中のモードに従います。\nキーボード：組み合わせを押して登録。Esc でキャンセル。\nコントローラー：すべて離した状態から組み合わせを押し、離すと保存します。",
        },
        "这是游戏输出文本的来源；请在标题画面更改游戏语言后再调整。\n主语言只决定 Mod 显示的正文，不会修改游戏设置。": {
            "en": "Match the game's own text language. Update this only after changing the language on the title screen.\nPrimary language controls the mod's output and never changes the game setting.",
            "ja": "ゲーム自体の表示言語に合わせます。タイトル画面でゲーム言語を変更した後にだけ更新してください。\n主言語は Mod の本文表示だけを決め、ゲーム設定は変更しません。",
        },
        "修改自动保存并热应用。偏移和行距采用游戏布局单位。\n原文自带注音、强调点的位置保持不变；只调整新增的副语言层。\n副语言默认与主文字左缘对齐，所有对话与过场字幕共用上方注解布局。": {
            "en": "Changes save and apply live. Offsets use game layout units.\nOriginal ruby and emphasis stay in place; only the added annotation layer moves.\nAnnotations align with the primary text's left edge, including dialogue and cutscenes.",
            "ja": "変更は自動保存・即時適用されます。位置と間隔はゲームのレイアウト単位です。\n元のルビと傍点を保ち、追加した副言語だけを調整します。\n副言語は主言語の左端に揃え、会話・カットシーンでも上方に表示します。",
        },
        "每 6 小时检查一次。游戏连接期间先下载，连接结束后安装。\n设置、语言资源和缓存保留；安装完成后界面自动恢复。": {
            "en": "Checks every 6 hours. Downloads while connected; installs after disconnection.\nSettings and caches are preserved; the interface restores automatically.",
            "ja": "6 時間ごとに確認します。接続中にダウンロードし、切断後に適用します。\n設定とキャッシュは保持され、画面は自動で復元されます。",
        },
    }
)


MESSAGES.update(
    {
        "× / Esc 只收起设置；隐藏界面后可从托盘或再次双击程序打开。": {
            "en": "× / Esc collapses settings. Reopen a hidden interface from the tray or by launching the app again.",
            "ja": "× / Esc は設定を閉じるだけです。非表示の画面はトレイかアプリの再起動で開けます。",
        },
        "打开使用说明": {"en": "User guide", "ja": "使い方"},
        "打开日志与配置文件夹": {
            "en": "Open logs and settings folder",
            "ja": "ログと設定フォルダーを開く",
        },
        "创建桌面快捷方式": {
            "en": "Create desktop shortcut",
            "ja": "デスクトップショートカットを作成",
        },
        "桌面快捷方式已创建": {
            "en": "Desktop shortcut created",
            "ja": "ショートカットを作成しました",
        },
        "创建快捷方式失败：": {
            "en": "Could not create shortcut: ",
            "ja": "ショートカットを作成できません：",
        },
        "此功能需要 Windows 便携发行包": {
            "en": "Requires the Windows portable release",
            "ja": "Windows ポータブル版が必要です",
        },
        "下载完整包（含 EXE）": {
            "en": "Download complete package (includes EXE)",
            "ja": "完全版をダウンロード（EXE 同梱）",
        },
        "下载安装程序": {"en": "Download installer", "ja": "インストーラーをダウンロード"},
        "自动更新未完成。请重试，或使用下方下载入口重新安装；原目录与配置请保留。详细原因见日志。": {
            "en": "Automatic update could not finish. Retry, or use the download button below to reinstall. Keep your original folder and settings. Details are in the logs.",
            "ja": "自動更新を完了できませんでした。再試行するか、下のダウンロードボタンから再インストールしてください。元のフォルダーと設定は保持してください。詳細はログに記録されています。",
        },
        "安装版请运行下载的 Setup；便携版请完整解压后运行 EXE。迁移到新目录前先退出旧工具，复制 generated/native-control.json 和 generated/overlay-window.ini；保留原目录，不复制旧程序或更新缓存。": {
            "en": "Run Setup for the installer, or extract the complete portable ZIP and run its EXE. To move folders, exit the old tool and copy generated/native-control.json and generated/overlay-window.ini. Keep the original folder; do not copy old program files or update caches.",
            "ja": "インストーラーは Setup を実行し、ポータブル版は全体を展開して EXE を実行してください。移行時は旧ツールを終了し、generated/native-control.json と generated/overlay-window.ini をコピーしてください。元フォルダーは保持し、旧プログラムや更新キャッシュはコピーしないでください。",
        },
        "解压完整包后运行 BilingualSora2nd.exe。迁移时先退出旧工具，将 generated/native-control.json 和 generated/overlay-window.ini 复制到新目录；不要复制旧程序或更新缓存。": {
            "en": "Extract and run BilingualSora2nd.exe. To migrate, exit the old tool first, then copy generated/native-control.json and generated/overlay-window.ini to the new folder. Do not copy old program files or update caches.",
            "ja": "展開後に BilingualSora2nd.exe を実行します。移行時は旧ツールを終了し、generated/native-control.json と generated/overlay-window.ini を新フォルダーにコピーしてください。旧プログラムや更新キャッシュはコピーしないでください。",
        },
        "正在下载程序更新…": {
            "en": "Downloading application update…",
            "ja": "プログラム更新をダウンロード中…",
        },
        "正在下载变更的运行依赖…": {
            "en": "Downloading changed runtime dependencies…",
            "ja": "変更された実行環境をダウンロード中…",
        },
    }
)


def set_language(value):
    global _language
    if value == "auto":
        system = (locale.getlocale()[0] or "en").lower()
        value = (
            "ja"
            if system.startswith(("ja", "japanese"))
            else "zh-Hans"
            if system.startswith(("zh", "chinese"))
            else "en"
        )
    _language = value if value in UI_LANGUAGES and value != "auto" else "en"


def tr(text):
    return _translate(text, _language)


def current_language():
    return _language


_FRAGMENTS = tuple(
    sorted(
        (s for s in MESSAGES if any("\u4e00" <= c <= "\u9fff" for c in s)), key=len, reverse=True
    )
)


@lru_cache(maxsize=2048)
def _translate(text, language):
    if not isinstance(text, str) or language == "zh-Hans":
        return text
    if text in MESSAGES:
        return MESSAGES[text][language]
    # Dynamic messages contain versions, device names, or diagnostic details.
    # Translate known fragments only; leave unknown diagnostics verbatim.
    for source in _FRAGMENTS:
        if source in text:
            text = text.replace(source, MESSAGES[source][language])
    return text
