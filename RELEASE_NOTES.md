## 中文

- 设置面板、状态条、托盘及更新页支持简体中文、English、日本語，默认跟随系统，可即时切换；与游戏语言选择独立。
- 修复显示模式与实际手柄绑定脱节：一组切换绑定按所选模式工作。按住时只显示副语言，松开或失去游戏焦点恢复主语言；Toggle 按一下切换，再按一下切回；双语注解独立作为轨迹专用模式。
- 默认切换键为 Ctrl + Shift + F10，界面键仍为 Ctrl + Shift + F9。已有自定义绑定迁移保留；F11/F12 不再是独立的同时有效动作，请在“按键绑定”中查看当前组合。
- 界面文案或初始语言偏好的修改不再触发资源重解析；已验证旧索引可以复用。避免重复构建模型，改用快速 JSON 编码写入缓存。
- 同机离线对比：模型编译 12.3 秒 → 7.1 秒，输出一致；有效缓存读取约 0.8 秒。首次资源解析仍需时间，这些数据不是实机总连接时间保证。

## English

- Live UI switching between English, Simplified Chinese, and Japanese, including settings, status, tray, and updates. Defaults to the system locale, independent of game text languages.
- One binding now follows the selected mode: hold for secondary-only text and release to restore primary; toggle between the two on successive presses; Trails bilingual annotations remain a separate mode.
- Language switch: Ctrl + Shift + F10. Interface: Ctrl + Shift + F9. Existing custom bindings migrate; F11/F12 are no longer separate simultaneously active actions.
- UI labels and first-run preferences no longer invalidate parsed game resources. Reuses verified older indexes and removes duplicate model construction and slow streaming JSON encoding.
- Offline same-machine comparison: compilation 12.3 s → 7.1 s with identical output; valid cached model loading about 0.8 s. First-time parsing still takes time; these are not full in-game connection benchmarks.

## 日本語

- 設定、ステータスバー、トレイ、更新画面が日本語・英語・簡体字中国語に対応。システム言語を初期値とし、その場で変更できます。ゲームの言語設定とは独立しています。
- 同じ割り当てが選択中のモードに従います。押下中は副言語のみ、離すと主言語のみ。トグルは押すたびに両者を切り替えます。軌跡の二言語注釈は別モードです。
- 言語切り替えは Ctrl + Shift + F10、画面操作は Ctrl + Shift + F9。既存のカスタム割り当てを移行します。F11/F12 は別の同時有効な操作ではなくなりました。
- 画面の文言や初期言語設定の変更でゲームリソースを再解析しないよう修正。検証済み索引を再利用し、モデルの重複構築と低速な JSON 書き込みを削減しました。
- 同一環境のオフライン測定ではモデル構築が 12.3 秒から 7.1 秒に短縮し、出力は一致。有効なキャッシュの読み込みは約 0.8 秒。初回解析には時間がかかり、ゲーム内の接続全体の時間を保証する数値ではありません。

---

Download **bilingual-sora-2nd-0.2.3-windows-x64.zip**. Legacy-named assets are for v0.2.0 updater compatibility only.

Supported game: Steam build **25386012**, EXE **1.03.2**. Unit tests and actual Frida transport/hold/toggle checks use a disposable test process, never the game. In-game layout, controller hardware, and full connection timing still require acceptance testing. No game resources or loader DLL are bundled.
