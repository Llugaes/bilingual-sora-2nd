# dev5 显示身份与渲染单元合同

这是生产回放和现场补采的合同，不是用户验收。执行者未见截图像素，没有操控冻结DEV3或游戏。证据和候选状态见[综合覆盖](dev5-system-coverage.md)与[最新续接](dev5-resource-epoch-and-cache.md)。

## 两个独立门槛

**准入保留完整输入身份。** base原串、原生控制码、物理资源SHA、稳定record/called/option/key、formatter角色和动态槽共同决定可否选择主副文。全局同文冲突不能靠排序、局部词或宽松字符归一化消除。真实控件未采到的source/key/scope/pointer/动态值只能记为pending。

**渲染按已证明的语义单元定位。** 完整效果组获得准入之后，每个独立效果成员保留自己的资源ID、stat/name/turns/value角色及主副锚点。分隔符不是副文单元，数值与回合不是另一个效果名。所有可行完整分段的主副输出必须一致，才选择更细单元；互相冲突、缺角色、未绑定槽、超预算、未知control、原生ruby或硬换行继续拒绝，不把完整整句准入偷换成片段授权。

仅有某个物品description的合同，不证明没有description的提示也属于该作用域；详情表、战斗即时提示、已装备槽、列表、选项与弹窗按钮不能共用未证实的入口身份。HP/CP原字段可能同时作为效果name或构造参数，字段同文不等于同义。

## 正负边界及可观察证据

| 路径 | 正边界 | 拒绝／未测边界 |
| --- | --- | --- |
| 对白、主动语音 | 原资源完整body与唯一peer；有限K控制及物理called；active voice完整group/sequence/record | 动态参数和分支未证明、缺目标、冲突peer不借其它同文或片段。实际运行frame/var/消费入口pending |
| 原生效果组 | 原生构造角色、完整连接串、稳定单元ID，控制保持；完整方案输出一致后更细分段 | 独立短串失去完整准入或角色冲突仍拒绝。着色/截断/复制后的实际原串及glyph位置pending |
| 通知模板 | 有限opcode-17物品流、数量/货币类型、每语言实际called与参数语法；有界槽预算 | 外围模板与物品名分开验证；物品名已两语不证明外围。未知动态/分支不抹掉，实际通知控件pending |
| formatter key | key真实匹配完整模板；1–4个canonical%d/%i/%u，三语言kind和范围一致 | 陈旧key、片段、%s/float/宽度/精度/位置参数、非canonical数字拒绝。现场key是否保留pending |
| 静态菜单 | 完整create/options/open/wait/close，字节码push与physical called一致；已证明同源副本 | 不进入区域内部的分支，不覆盖动态/重复/未知选项；指针合同成功不代表控件保存指针 |
| 物品description printf | 独立PE局部函数与callee、字段/容量/槽合同，物理description；零槽%%也执行格式化 | 普通label、脚本、动态printf不能套用；literal-copy分支与实际场景raw pending |
| 换行与宽度 | 原始硬换行与控制保留，通用CJK/拉丁词边界机制；水泵原SCP逗号归第一literal | 离线layer正确不代表原生字形禁则/宽度/注音排版通过，实际窗口和像素pending |

缓存拒绝也属于生产边界：找不到记录与损坏记录可以按既有规则生成；权限拒绝必须传播，不能变成空索引、缺语言或重建以隐藏失败。新增负例只使用项目TEMP和模拟archive错误，不访问真实受限路径或更改ACL。

## 独立oracle与现场证据分开

回归expected来自原PAC物理字段/调用以及独立PE构造合同，不由当前translator输出生成。完整模型字节相同只证明重复生成稳定和优化没有改变输出；源码用例、20组合、24个离线入口合同均不证明12类实际显示入口全部覆盖。script宽度差异分类不放宽原始断言，也不授权全局字符替换。

每族报告保留：资源/规则代次，稳定ID和上下文，完整base→主→副输入与输出，formatter/动态槽，准入/冲突/拒绝原因与fallback，模型/渲染单元，实际入口与普通用户生命周期状态。原资源遗漏/未知pointer的清单不是可见漏译分母。

现场需要父在安全时点协调：报错控件与相邻正常控件的完整original/display、key及reason、path/surface、source/scope/script/table/pointer身份、动态槽、formatter、layers及model/resident revision。已有快照可先使用；不修改当前DEV3诊断配置，不重attach、不加hook、不清缓存。新的普通用户自动准备及按钮→prepare→publish→wire→resident ack由新候选的新游戏进程验证，`--no-auto-connect`不能替代它。
