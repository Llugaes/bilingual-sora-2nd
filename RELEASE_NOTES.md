## 中文

- 规范化内置依赖的 RECORD 清单，避免相同依赖因构建机器不同而被当成新的运行环境。

- **下载 ZIP，解压后双击 BilingualSora2nd.exe 即可使用。** 内置 Python 3.14.7 和全部运行依赖，无需自行安装环境或运行 CMD。
- 发布附件统一为 bilingual-sora-2nd-VERSION-windows-x64.zip 和自动更新清单；去掉重复的旧名称安装包。
- 修复“关闭窗口只隐藏”的处理拦截热更新退出、导致重载偶发超时的问题。
- 首次设置后直接打开面板；更新页新增桌面快捷方式、日志/配置目录与说明入口。依赖更新使用独立版本目录，保留配置、缓存和正在使用的 DLL。
- **0.2.x 用户需一次手动迁移**：退出旧工具，解压新包到新目录，复制 generated/native-control.json 和 generated/overlay-window.ini，再启动新 EXE。之后自动更新内置运行环境。无需复制旧 .venv 或 generated/updates。

- 设置面板、状态条、托盘及更新页支持简体中文、English、日本語，默认跟随系统，可即时切换；与游戏语言选择独立。
- 修复显示模式与实际手柄绑定脱节：一组切换绑定按所选模式工作。按住时只显示副语言，松开或失去游戏焦点恢复主语言；Toggle 按一下切换，再按一下切回；双语注解独立作为轨迹专用模式。
- 默认切换键为 Ctrl + Shift + F10，界面键仍为 Ctrl + Shift + F9。已有自定义绑定迁移保留；F11/F12 不再是独立的同时有效动作，请在“按键绑定”中查看当前组合。
- 界面文案或初始语言偏好的修改不再触发资源重解析；已验证旧索引可以复用。避免重复构建模型，改用快速 JSON 编码写入缓存。
- 同机离线对比：模型编译 12.3 秒 → 7.1 秒，输出一致；有效缓存读取约 0.8 秒。首次资源解析仍需时间，这些数据不是实机总连接时间保证。

## English

- Normalize bundled wheel records so identical dependencies keep a stable runtime identity across build machines.

- **Extract the ZIP and run BilingualSora2nd.exe.** Includes Python 3.14.7 and all runtime dependencies; no Python installation or CMD scripts.
- One consistently named Windows ZIP plus updater metadata; duplicate legacy assets removed.
- Fix close-to-hide handlers cancelling the explicit exit used for hot updates.
- First launch opens settings. Desktop shortcut creation, logs/settings folder, and help are available in Updates. Runtime upgrades are side by side, preserving settings and loaded DLLs.
- **One-time migration from 0.2.x:** exit the old tool, extract into a new folder, copy generated/native-control.json and generated/overlay-window.ini, then run the new EXE. Do not copy .venv or generated/updates. Future portable releases update the runtime automatically.

- Live UI switching between English, Simplified Chinese, and Japanese, including settings, status, tray, and updates. Defaults to the system locale, independent of game text languages.
- One binding now follows the selected mode: hold for secondary-only text and release to restore primary; toggle between the two on successive presses; Trails bilingual annotations remain a separate mode.
- Language switch: Ctrl + Shift + F10. Interface: Ctrl + Shift + F9. Existing custom bindings migrate; F11/F12 are no longer separate simultaneously active actions.
- UI labels and first-run preferences no longer invalidate parsed game resources. Reuses verified older indexes and removes duplicate model construction and slow streaming JSON encoding.
- Offline same-machine comparison: compilation 12.3 s → 7.1 s with identical output; valid cached model loading about 0.8 s. First-time parsing still takes time; these are not full in-game connection benchmarks.

## 日本語

- 同梱依存ライブラリの RECORD を正規化し、ビルド環境が変わっても同じランタイムとして識別します。

- **ZIP を展開し BilingualSora2nd.exe を実行するだけ。** Python 3.14.7 と依存ライブラリを同梱し、環境構築や CMD は不要です。
- 配布ファイルはゲーム名入りの Windows ZIP と更新用メタデータに統一。旧名称の重複配布を削除しました。
- ホット更新時の終了が「閉じると非表示」の処理に阻止される問題を修正。
- 初回は設定画面を開きます。更新タブにショートカット作成、ログ・設定フォルダー、使い方を追加。ランタイム更新は別フォルダーで適用し、設定と使用中の DLL を保持します。
- **0.2.x からは一度だけ手動移行が必要です。** 旧ツールを終了し、新フォルダーへ展開後、generated/native-control.json と generated/overlay-window.ini をコピーして新 EXE を実行してください。.venv や generated/updates はコピー不要です。以降はランタイムも自動更新します。

- 設定、ステータスバー、トレイ、更新画面が日本語・英語・簡体字中国語に対応。システム言語を初期値とし、その場で変更できます。ゲームの言語設定とは独立しています。
- 同じ割り当てが選択中のモードに従います。押下中は副言語のみ、離すと主言語のみ。トグルは押すたびに両者を切り替えます。軌跡の二言語注釈は別モードです。
- 言語切り替えは Ctrl + Shift + F10、画面操作は Ctrl + Shift + F9。既存のカスタム割り当てを移行します。F11/F12 は別の同時有効な操作ではなくなりました。
- 画面の文言や初期言語設定の変更でゲームリソースを再解析しないよう修正。検証済み索引を再利用し、モデルの重複構築と低速な JSON 書き込みを削減しました。
- 同一環境のオフライン測定ではモデル構築が 12.3 秒から 7.1 秒に短縮し、出力は一致。有効なキャッシュの読み込みは約 0.8 秒。初回解析には時間がかかり、ゲーム内の接続全体の時間を保証する数値ではありません。

---

Download **bilingual-sora-2nd-0.3.1-windows-x64.zip**. The JSON asset is for automatic updates; you do not need to download it manually.

Supported game: Steam build **25386012**, EXE **1.03.2**. Unit tests and actual Frida transport/hold/toggle checks use a disposable test process, never the game. In-game layout, controller hardware, and full connection timing still require acceptance testing. No game resources or loader DLL are bundled.
