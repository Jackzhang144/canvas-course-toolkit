# LearningSummaries/ — 阶段学习总结

这里放**你自己**的阶段学习总结（比如每两周一篇），用于复盘学了什么、卡在哪、接下来怎么补。

- 文件名：`YYYY-MM-DD_to_YYYY-MM-DD.md`（起止日期）
- 骨架：[TEMPLATE.md](TEMPLATE.md)
- **不入库**（`.gitignore` 已忽略）——总结里通常会带姓名、学号、课程进度等个人信息。

## 怎么用

1. 复制模板：`cp LearningSummaries/TEMPLATE.md LearningSummaries/2026-09-01_to_2026-09-14.md`
2. 先把这段时期的课程内容看一遍（`CourseFiles/<课程>/README.md` + 对应周次课件 + 公告），
   再动笔，别凭文件名猜内容。
3. 四节写满、落到具体概念，别写"收获很大"这种空话。

## 让 AI 代理帮你写

如果你用 Claude Code / Codex / DeepSeek Harness 这类代理，把下面这段话发给它即可：

> 读 `AGENTS.md` 和 `LearningSummaries/TEMPLATE.md`，再读我这段时间的课程资料，
> 帮我写 `2026-09-01_to_2026-09-14` 的学习总结，保存到 `LearningSummaries/` 下。

代理会按模板四个章节组织，并且**不会编造**你没做过的活动、分数或组队结果。
你也可以照这个思路，把"写总结"这件事写成自己的 skill 放进 `.dsh/skills/`
（写法见 `AGENTS.md` §6）。
