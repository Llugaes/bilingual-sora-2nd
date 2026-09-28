# 对白与姓名历史全量审计

本审计读取原始 PAC 缓存 `generated/catalog.json`
的所有 `assembled_dialogue` 物理调用，并以已生成的完整模型回放正式 JavaScript
`ScriptIdentities.recordLookup` 与 `RuntimeText.historyContext`。它不启动或附加游戏。

执行命令：

```powershell
.venv\Scripts\python.exe -u tools\audit_history_dialogue_coverage.py `
  --game-dir 'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter' `
  --ja-model generated\runtime-9c50bec0e2c35f837c32.json `
  --en-model generated\runtime-bf83a770b526f155d191.json
```

本轮最终证据为 `generated/diagnostic-138-history-dialogue-coverage.json`（默认输出名为
`generated/history-dialogue-coverage.json`）。分母是 63,128 个独立原始
`assembled_dialogue` 调用；历史分母保留每种源语言、原始调用和姓名上下文，不把同文行
合并为词条数。目标是 `zh-Hans → ja` 与 `zh-Hans → en`。

| 目标 | ID 最终渲染通过 | 缺少完整官方配对 | ID 错配／编译丢失／运行时丢失／渲染失败 |
| --- | ---: | ---: | ---: |
| ja | 63,120 | 8 | 0 |
| en | 63,123 | 5 | 0 |

历史回放也通过最终 `render(..., "annotation")`：

| 目标 | 正文精确 ID／唯一上下文 | 正文授权旧记录 fallback | 姓名精确 ID／唯一上下文 | 姓名授权旧记录 fallback | 非官方候选／最终渲染失败 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ja | 918,052 | 57,235 | 11,461 | 2,483 | 0 |
| en | 911,028 | 64,301 | 11,524 | 2,511 | 0 |

fallback 仅用于没有真实调用身份的旧记录，所选项仍是完整官方 pair；它不生成或替代
`recordKey`。正常调用路径仍只接受实际 script call ID。

审计器将既有原生 `<R>` 注音与本轮生成的副文分开：原文已存在的 ruby 不能被误报为
新增副文。它以独立断言将 `</Rreading>` 的 reading 作为可见内容（不复用
`RuntimeText.needsAnnotation` 的判定）；不同 reading 即使共享 Latin base，正式判定与
最终渲染都必须认可官方目标读取。

13 个缺项均已回查原始 PAC，不能伪造官方目标文本：

- `script/scena/mp4020_01.dat/TK_GERVAIS/called/24`、`26`、`28` 只有 ja 缺项。日文函数有
  24 个调用、9 段对白；其余七语有 31 个调用、12 段，因此三段没有日文原始调用。
- `script/scena/mp6600.dat/MayaEvent09_35_00_03_SubTitle/called/3`、`5`、`7`、`11`、`13`
  只存在 zh-Hans、zh-Hant、ko；ja、en、fr、de、es 的原始函数均缺失。

这份审计不把图片、成就或 card minigame 计入对白／姓名范围。
