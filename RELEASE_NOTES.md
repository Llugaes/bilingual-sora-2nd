# Bilingual Sora 2nd v0.3.21

## 简体中文

- 手柄绑定自动使用 PlayStation、Xbox、Nintendo Switch 的按键名称，区分肩键、扳机、摇杆按下、方向和面键。
- 按设备的 SDL 映射识别原始按钮与轴，不再把已识别的 L2/R2 显示成“轴 5/6”。兼容分离／共享轴扳机、反向轴、十字键和 Joy-Con 横／竖握名称。
- 快捷键页新增“手柄按键名称”，可为 Steam Input 等虚拟手柄选择显示样式。仅改变名称，保留已有组合键与触发阈值。
- 较大系统字号或窄窗口下，标签与录制按钮自动换行，避免英文界面出现横向滚动。
- 新录制的绑定保存设备名称映射，断开手柄或重启工具后仍可显示；旧绑定连接对应手柄即可识别。未提供 SDL 映射的输入保留原始编号。

已核对 DualSense 实际设备映射，完成自动化回归和中英日界面排版检查。Xbox、Switch 的映射语义通过自动化检查，尚未用对应实体手柄验收。设置与缓存保留。

## English

- Automatically display PlayStation, Xbox and Nintendo Switch button names, including bumpers, triggers, stick clicks, directions and face buttons.
- Resolve raw inputs through each device's SDL mapping, including shared or inverted trigger axes, hats and Joy-Con orientation-specific labels.
- Add a per-action **Controller button labels** selector for virtual-controller setups such as Steam Input. Labels do not change existing bindings or thresholds.
- Wrap labels and recording controls on narrow pages or with larger system text to avoid horizontal scrolling.
- Retain newly recorded labels after disconnecting or restarting. Older bindings are identified when the matching controller is connected. Inputs without an SDL mapping retain their raw numbers.

Verified the connected DualSense mapping, automated regressions and Chinese, English and Japanese layouts. Xbox and Switch mapping semantics have automated coverage; physical-device acceptance remains outstanding. Settings and caches are preserved.

## 日本語

- PlayStation・Xbox・Nintendo Switch に合わせて、ショルダーボタン、トリガー、スティック押し込み、方向、フェイスボタンの名前を表示します。
- SDL のデバイス別対応表を使用し、共有軸・反転軸のトリガー、方向キー、Joy-Con の横持ち・縦持ちに対応します。
- Steam Input などの仮想コントローラー向けに、操作ごとの「コントローラーのボタン名」を追加。表示のみを変更し、既存の割り当てやしきい値は保持します。
- 狭い画面や大きなシステム文字ではラベルと登録ボタンを折り返し、横スクロールを防ぎます。
- 新しい登録は切断・再起動後もボタン名を保持します。既存の割り当ては該当するコントローラーの接続時に判別します。SDL 対応表のない入力は元の番号で表示します。

接続中の DualSense の対応表、自動回帰テスト、中英日の画面レイアウトを確認しました。Xbox・Switch の対応は自動検証済みですが、各実機での確認は未実施です。設定とキャッシュは保持します。
