# 附项：酒店“休息”按钮

状态：真实控件已采集，目录准入已修正；新候选实机显示待验证。

## 根因

`diagnostic-134-rest-live.json`：layout 10 的 `root/sub/text` 实际正文为 `休息`，字号 32。相邻 `root/main/text` 已有 `交谈 / 話す`。

按钮残留 text-key hash `0x4c72d2c3` 对应 `TXT_TALK_GUIDE_FISHING`（钓鱼），与脚本改写后的正文不符。运行时拒绝这个过期 key 是正确行为，不能把钓鱼 ID 硬映射为休息。

完整官方表 `TXT_USE_HEAL_MACHINE` 和脚本静态参数均给出 `Rest / 休憩する`。三条 `/code/.../alignment/...` 不完整字节码片段缺少目标字段，却把全局唯一完整配对否决了。

## 改动与验证

准入按资源类型处理：不完整字节码 alignment 片段不再否决唯一、且已有目标字段一致的完整配对；独立表记录和物理对话调用的缺项、真实异译继续分别保留。没有按“休息”这个词添加例外，也没有放宽过期 key 校验。

`test_unique_complete_label_is_not_blacklisted_by_missing_fragment` 修改前复现失败，修改后通过。地图同名不同 ID／缺项与表指针身份回归一起通过。完整 ja/en 模型回放实际 `休息` 输入，分别得到 `休憩する`、`Rest`，最终 render 非 plain。

该证据证明真实输入进入解析器后的行为；不等于当前进程已经显示修复结果。当前原配置保留，未替换运行中钩子。
