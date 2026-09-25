# Bilingual Sora 2nd v0.3.3

## 简体中文

- Windows ZIP 从 **146.9 MiB 缩减到约 98.9 MiB（约 33%）**。移除未使用的 Qt QML、开发工具以及 pygame 文档、示例和测试；保留运行依赖、手柄支持、图形回退及许可证。
- GitHub 附件直接展示规范文件名，包含游戏名、版本、系统及架构；使用说明放在正文，不再遮住文件名。
- 下载 **bilingual-sora-2nd-0.3.3-windows-x64.zip**，完整解压后双击 **BilingualSora2nd.exe**。无需另装 Python 或下载依赖。更新清单 JSON 无需手动下载。
- 0.3.x 便携版可自动升级，保留设置。升级时旧运行环境仍保留用于恢复，因此已有安装目录不会立即缩小到全新解压的大小。

## English

- Windows ZIP reduced from **146.9 MiB to approximately 98.9 MiB (33%)**. Removes unused Qt QML/developer tools and pygame documentation, examples, and tests; retains runtime dependencies, controller support, graphics fallback, and licenses.
- Release assets now show their actual game/version/platform/architecture filenames instead of descriptive labels.
- Download **bilingual-sora-2nd-0.3.3-windows-x64.zip**, extract the entire archive, and run **BilingualSora2nd.exe**. No Python installation or dependency downloads. The JSON asset is only for the updater.
- Portable 0.3.x installations upgrade automatically and keep settings. Previous runtimes remain available for recovery, so an existing installation does not immediately shrink to the size of a fresh extraction.

## 日本語

- Windows ZIP を **146.9 MiB から約 98.9 MiB へ約 33% 削減**。未使用の Qt QML・開発ツールと pygame のドキュメント・サンプル・テストを除外。実行に必要な依存関係、コントローラー対応、描画フォールバック、ライセンスは保持しています。
- GitHub 添付ファイルには、ゲーム名・バージョン・OS・アーキテクチャを含む実際のファイル名を表示します。
- **bilingual-sora-2nd-0.3.3-windows-x64.zip** を全て展開し、**BilingualSora2nd.exe** を実行してください。Python のインストールや追加ダウンロードは不要です。JSON は自動更新用です。
- 0.3.x のポータブル版は設定を保持して自動更新できます。復旧用に旧ランタイムを残すため、既存フォルダーの容量が直ちに新規展開時のサイズになるわけではありません。

---

Validation: 188 Python tests (resource-dependent skips) and 37 JavaScript tests; packaged EXE checks without Python on PATH, Unicode paths, icon/SVG loading, styles, TLS, SDL input initialization, interrupted-update recovery, live updates, hot reload, and single instance. No game launch or attachment was performed for this packaging change.

Supported game: Steam build **25386012**, EXE **1.03.2**. No game resources are distributed. See the [README](https://github.com/Llugaes/bilingual-sora-2nd#readme) for setup and migration from 0.2.x.
