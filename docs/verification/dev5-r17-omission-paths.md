# r17 遗漏链与默认关闭诊断

r17承接精确r16 `328b455671682e2a358b47eb0b38802b2cf08632`。本轮只修补可观测缺口；不声明书籍或终端现场漏译已修复。r15的044、偏好、地图和通知修复，以及r16的Tips／HelpTitle、HUD和商店资源身份修复均继承。候选与实际加载状态须独立核对，不能以模型层通过替代实机验收。

## 静态证据

资源证据读取当前游戏PAC及已验收r14目录，未执行游戏。目录SHA256为`d852deee306912e0a9d1d65bd9e2b40422cfc7ab0f58d5965a7df8f96f76db66`。原始八语的两条物品正文和一条类别完整字段逐行核对，结果保存在独立clone的`generated/replacement-r17-book-resources.json`；复查脚本为任务目录的`inspect-r17-book-resource.py`。原分母／模型回放继续引用`generated/replacement-r15/raw-map-book-coverage.json`、`model-path-replay.json`及`generated/replacement-r16/complete-model-replay.json`。

- 青色提示属于`ItemKindHelpData`完整description：`Books [<c698>Can be accessed from the 'Book List' tab</C>]  `。英文物理行0，字段+8，首scalar为`0x000d0002`。八语完整字段都有译文，裸青色句没有独立资源项。正式解析器能处理完整字段；尚未取得现场完整SetText原串，不能认定游戏传入了裸片段，也不能按裸句补全局词典。
- 正文`Volume 1 of a popular novel published in the Kingdom of Liberl.`对应独立物品ID342与372，英文物理行98／109，description字段+232，pool offset分别364782／365806。两者英文同文而SC／JA译文不同；全局拒绝正确，两个确定owner各可翻译。英文pool指针不同，不能误称为共享pool歧义；复制或丢失owner后的全局同文歧义是另一层。
- 当前官方EXE SHA256为`cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea`。`347b70`入口静态可见RDX输入的`+e8`字符串，某一分支以2047为限复制到R8输出并封零；另一分支继续归一化／效果组装。这只能证明存在复制路径。该函数输入结构与PAC `ItemTableData`的全部字段尚未证明同型：函数bit-test `+18`，PAC schema把十进制+24登记为opaque pointer，不能把这两个字段直接叫作相同flags。未证明两条现场书籍走哪个分支、哪个owner及最终控件。旧入口到当前入口的63字节前缀／相同PDATA长度匹配仅用于定位后再读当前指令，不是新增原生准入合同。详见`generated/replacement-r17-current-item-prefix.log`。
- 终端`LP_Terminal`五项原始带方括号选项，在精确r14缓存和r16完整EN→SC／JA模型回放均可译。`system.dat`／`talk_common.dat`的`menu_additem`原字节码发出group15、command1、argc3；不属于group5对白构造入口。
- 当前`CommandMenu` RTTI对应vtable `b122f8`，实例在manager `+98`，其command1 callback槽`+20`指向`4ad450`。处理器从VM `+70` argc、`+64` stack top、`+58` stack读取menuID／字符串token／optionID，字符串按原SCP base＋offset解码，tail-call `532580`。该入口按菜单类型0／1调用`531880`，2／3调用`531c20`；两构造器分别在`531b51`／`531e07`调用生产已恢复的SetText `5892c0`，RDX仍为原字符串，无去括号或格式拼接。`CommandUI`是另一类，不能用其处理器解释终端。日志为`generated/replacement-r17-command-menu.log`、`replacement-r17-menu-handler.log`、`replacement-r17-menu-consumers.log`；这里只读当前磁盘机器码，未验证游戏执行了该路径。

因此终端目前没有可证的新钩子缺项；书籍目前没有可证的安全owner传播修复。第一现场失败仍未知，禁止据此新增宽泛scope、任选同文译文、借用阅读器chapter身份或直接把表ID套入未知原生结构。

## r17改动及验证

`ScriptIdentities.pointerSelect`增加可选阶段回调，保留原SHA、header、model source和不同译文歧义检查；表回调增加物理file／record／field／string offset。诊断由既有SetText／Update记录，每类最多12事件，截断后仍保留最终阶段。最多64输入，原串／显示文字各2048字符；截断不声称与完整原串精确一致。caller RVA只在实际module范围内有效，不做stack walk。

`status`报告实际resident诊断schema／开关、磁盘EXE摘要、native contract、module范围、实际来源语言／epoch／render mode、成功提交模型的transport路径／格式／长度。模型路径及长度明确`content_hash_verified:false`，只提供后续核对线索，不伪造内容SHA。加载失败保留先前模型及provenance。

自动遥测使用原控制通道的`snapshot(true)`，只从有界捕获集合生成`generated/native-input-identities.json`；没有新控制连接、新方法、新钩子或背景内存读取。原显式`snapshot()`接口保持完整只读兼容。Python使用刚取得的status判断；旧resident／诊断关闭时不请求可能无限大的旧快照，而报告`resident_unsupported`／`diagnostics_disabled`。以前的`native-labels.json`不再是自动更新证据，旧文件须按时间视为历史。

定向回归：164项生产JS（agent／identity／transport）、36项Python（native lifecycle／loading／snapshot／model wire／portable build／update／architecture）通过。新增trace与bounded snapshot检查先在r16失败，再在r17通过。第一次Python组合测试因Windows默认GBK解码两项旧Node子进程输出失败，改用`-X utf8`后全部通过，未改相关产品逻辑。Ruff检查及diff whitespace通过。

`tests/check_native_input_diagnostics.py`在本任务新建隐藏Python宿主中验证实际Frida V8加载完整agent语法、真实NativePointer script hash拒绝阶段、64记录／2048字符快照和关闭状态。`tests/check_native_books.py`再次执行生产初始化、外部指令改写先拒绝及实际页查询；只附加自建宿主，未附加游戏。这些测试不执行终端／物品游戏控制器，也不是字体／画面验收。

## 最小后续实机门槛

由父线程安排候选切换。当前运行r16 ROOT及配置保持不动；r17默认关闭diagnostics，源改动只允许在新游戏进程加载。无需为此自动启动游戏。

待允许复现时，在独立候选初始化前选择诊断配置，核对实际schema2／enabled和resident revision；保存候选清单／ZIP SHA、模型transport文件只读SHA、检测来源语言和主副配置。只用现有控制通道取一次相同控件的setter与Update记录：先看终端caller `531b56`／`531e0c`及原串，再看是否global pair／是否被后续owned copy改写；书籍分别比较完整类别字段与正文、table／script失败阶段和实际物品owner。`owned_update`只证明已复制原串，不能代替setter provenance。长于2048字符的输入明确截断，需用已有只读控件采集取得完整原串，不能把诊断片段当作完整解析输入。

先确定资源→模型→输入identity／分段→控件生命周期的首个失败，再扩展有证据的同族合同。仍未知：书籍真实owner／分段、终端实际加载模型／控件生命周期、044首次注入`frida-agent.dll`闪退根因。当前无实机验收、无1.0或稳定版公开发布。
