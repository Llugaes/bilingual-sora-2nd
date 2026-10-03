# Bilingual Sora 2nd v0.3.32

## 简体中文

- 新增 Gitee 国内安装包下载和自动更新源，更新失败时自动尝试 GitHub。v0.3.31 及更早版本可通过原更新入口升级，无法访问 GitHub 时可从 Gitee 下载 Setup 覆盖安装，保留设置。
- 两端使用同一份原版文件，下载继续校验大小和 SHA-256；普通更新复用已有运行依赖。完整便携包和历史版本保留在 GitHub，Gitee 保留最新三个验证通过的稳定版。
- 发布流程先上传预览版，逐个匿名下载验证通过后才开放稳定更新；预览版和缺少组件的镜像不会被自动安装。

本版调整下载与更新流程，不改动游戏文本钩子和玩家配置。

## English

- Add a Gitee download mirror and preferred update source for mainland China, with GitHub fallback. Older clients can update through GitHub or install the mirrored Setup over their existing installation while preserving settings.
- Both sources serve identical artifacts with size and SHA-256 verification. Unchanged runtimes are reused. GitHub retains full portable ZIPs and release history; Gitee retains the latest three verified stable mirrors.
- Mirror uploads remain previews until every artifact passes anonymous download verification. Preview and incomplete releases are excluded from automatic installation.

## 日本語

- 中国本土向けに Gitee の配布・更新ミラーを追加。失敗時は GitHub に切り替えます。旧版は GitHub 経由、または Gitee の Setup による上書きで設定を保持して更新できます。
- 両配布元は同じファイルを使用し、サイズと SHA-256 を検証します。変更のないランタイムは再利用。完全なポータブル ZIP と履歴は GitHub、検証済みの最新 3 安定版は Gitee に保持します。
- 全添付ファイルの匿名ダウンロード検証後に安定版を公開。プレビュー版や不完全なミラーは自動インストールしません。
