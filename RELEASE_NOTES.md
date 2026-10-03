# Bilingual Sora 2nd v0.3.35

## 简体中文

- 紧急修复 0.3.33／0.3.34 首次连接时可能报 `book_count` 校验失败的问题：书籍模块先安装钩子，后续校验把本工具自己的修改误判为异常。现在先校验全部入口，再初始化原生模块。
- 将生产启动顺序、真实 Frida 改写和正常／异常入口检查加入发版必跑流程，防止独立功能测试通过、实际连接失败的情况再次漏检。
- 保留 0.3.34 的多行双语提示行高修复。本补丁不改变更新策略；手动确认更新和版本回退会单独迭代。

本次启动错误已在独立隐藏进程复现并通过修复回归。若当前游戏进程已经出现连接失败，请正常退出游戏，更新后再启动；不要在该进程反复连接。

## English

- Fix the first-connection `book_count` validation failure in 0.3.33/0.3.34. Book hooks were installed before code validation, causing the tool to reject its own patches. All entry points are now validated before native adapters initialize.
- Add the production startup sequence, real Frida patches, and clean/modified-entry checks to mandatory release validation.
- Retain the multiline bilingual spacing fix from 0.3.34. Update confirmation and rollback will be addressed separately; this hotfix does not change update policy.

The startup failure was reproduced and fixed in an isolated native process. If connection has already failed in the current game process, exit the game normally, update, then start it again.

## 日本語

- 0.3.33／0.3.34 の初回接続で `book_count` の検証に失敗する問題を修正しました。書籍フックを先に設置し、その変更を異常と誤判定していました。すべての入口を検証してからネイティブ処理を初期化します。
- 製品コードの起動順序と実際の Frida フックを使う正常／異常ケースを、リリース前の必須テストに追加しました。
- 0.3.34 の複数行の双語表示の修正は含まれます。更新前の確認とバージョンの巻き戻しは別途対応し、この修正版では更新方針を変更しません。

独立した検証プロセスで同じ起動エラーを再現し、修正を確認しています。現在のゲームで接続に失敗した場合は、ゲームを通常終了し、更新後に起動し直してください。
