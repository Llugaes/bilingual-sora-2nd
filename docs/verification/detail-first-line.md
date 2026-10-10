# 双语说明首行留白

> r4 未通过用户实机验收：回复药与装备最终位置仍不一致。此文仅保留历史证据；首行补偿已由 [r5 整块居中](unified-help-layout.md) 取代，不再作为现行布局合同。

基线 `44fab0d`，对应代码候选 r3 `94cdbc0`。用户反馈：属性开头没有副文时，整个说明缺少原有下移，上方副文难以看清；希望所有双语说明统一处理。只修复此显示条件，第二轮内存重构未开始，不发布。

## 现场和追溯

只读采集用户停留的另一件同症状装备，控件 `root/help/text`，字号 32，flags 0。完整显示开头为 STR+800、ATS+530、SPD+20，随后才是必杀率、回避率副文，第二行是神秘双剑说明。首行原生 line-info 的 ruby 标记为 1。游戏为 CAB62，采集器的全局地址与 vtable 使用当前 `native_report` 的验证结果；采集仅使用 ReadProcessMemory，没有追加 Frida 会话、修改游戏或配置。

去掉已生成的 R 包装重建来源，交给 r2、r3 各自完整模型和解析器，得到的完整 plan 相同，均逐字等于现场显示。这属于资源/显示重建，不能称为原始 setter 抓包。最小模型仍输出同一显示，已保存为 `tests/fixtures/detail-first-line.json`。

`r2 → r3` 没有原生排版修改。`git blame` 追溯到 `dab2d84` 引入的姓名/混排原点恢复、后续 `2b9bec5` 保留的 `preservePrimaryLayout` 条件；r2 的 `468dc69` 只追加小字号普通标题分支。本例是 `kind=ruby`、`preservePrimaryLayout=true`，不进入小字号适配。属性是跨语同文时保留为普通片段，旧混排规则同时撤销了整个说明的原生首行 margin。这是以前的布局分类遗漏，本轮文本验收未覆盖到它。

## 修复合同

- 通过已有 `detailBodyBoundary` 或完整 `detailSources` 判断说明归属；只在实际输出 ruby/layered 副文时登记 `detailBilingual`，每次重算清空。
- 统一在现有首行 hook 设置 `incoming_y - native_margin`；当前 margin 为 -12，意味着整块向下 12。控件自身非零 margin 仍优先。正常说明已获得的下移不会再次相加，不按语种、词语或第一个锚点分支。
- 仅最外层绘制的第一行参与；测量、后续行距、字形缩放、原注音额外预留和标题/正文间距算法不变。flags 8/256 的原生禁止规则、辅助解析上下文保留。
- 单语、禁用、无实际副文、未知说明、姓名、脚本对白、日志和存档不因本项下移；料理小标题继续其已验收规则。

## 验证

`python -B -X utf8 tests/check_detail_first_line.py` 在自建隐藏主机执行正式 resolver、生产 callback 和 CAB 原生首行 leaf。修复前重现：本例与“标题无副文、仅正文有副文”的起点保持 100，期望为原生留白后的 112；重复执行均失败。修复后 3,360 项通过，包括八来源 × 八主语言 × 八副语言、六次模式/启停顺序，保留跨语同文条件。此矩阵是资源组合的布局合同检查，不是 512 个游戏场景。

已有 `check_owned_title_layout.py` 的全部 19 项合同通过，小字号修复与正常原点、字体失效、测量/绘制比例均保留。新检查纳入 `tools.dev check`。

完整 `python -B -X utf8 -m tools.dev check` 退出码 0：Python 819 项（9 项原有跳过）、Node 225 项、已启用的隐藏原生宿主检查通过；默认 6 项 EXE 专用检查继续明确跳过。发布/上传/连接文本出自隔离测试替身，不代表本轮发生了这些对外操作。日志位于相邻 `detail-inset-evidence/full-check.log`。

隐藏主机证明原点，不克隆完整字体排版或 GPU 绘制。最终上下边界、邻接内容和实际画面仍需新游戏进程加载候选验收；旧游戏里的 r3 保留，未热更。

## r4 本地候选

- 代码冻结：`4729ef417be480eea0d9015ff5bad52613392aeb`，显示版本 `DEV 1.0.1-dev1-r4`。
- 入口：`dist/detail-inset-r4/DEV/BilingualSora2nd.exe`；ZIP：`dist/detail-inset-r4/packages/bilingual-sora-2nd-1.0.1-dev1-r4-windows-x64.zip`。
- ZIP 为 109,353,779 字节，SHA-256 `f443acc382438f72e13d6592850fe854bf7ac30c195a59aec4fdc69aa913a223`。
- 磁盘和 ZIP 的 672 个受管文件逐项核验；相对 r3 仅 `native_agent.js` 改变，552 个启动器/运行环境文件保持一致，文本解析器及语言编译器未变。
- 使用候选自己的 Python、Frida/V8、包内源码，分别重跑说明原点 3,360 项和小标题全部 19 项合同，通过。测试辅助反汇编依赖只来自外部测试环境，未加入分发包；独立临时目录已删除。
- 本机 DEV 目录预置与当前代码/真实资源指纹匹配的 catalog、模型和 wire，复制 r3 白名单内的可见设置；更新策略关闭，不复制 agent token 或驻留状态，ZIP 不含游戏资源/用户设置。

证据保存在相邻 `detail-inset-evidence`：`final-package-audit.json`、`packaged-native-audit.json`、`packaged-detail-first-line.json` 和 `title-boundary/packaged-title-layout.json`。未 push、未发布、未启动 r4，当前游戏与 r3 未替换。用户需退出游戏与 r3 后，在新游戏进程验收该候选；重点检查首段无副文、首段有副文、仅正文副文的说明及容器下沿。
