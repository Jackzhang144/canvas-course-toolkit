---
name: canvas-list-due-work
description: 查 Canvas 上近期要交的作业/考试与截止时间，汇总「这周/这个月要交什么」，并检查我的提交状态。
whenToUse: 当用户问「这周要交什么」「最近有什么作业」「XX 作业什么时候截止」「我交了没有」「看下 due / deadline / 截止日期」时使用。
---

# 查近期作业与截止时间

用一个命令回答"我接下来要交什么、什么时候交、交了没有"。

## 步骤

1. **确认环境**：`CANVAS_HOST`/`CANVAS_API_TOKEN` 缺失就按 `AGENTS.md` §3 引导配置（见 `docs/setup.md`）。
   网络异常时先跑 `uv run canvas doctor` 定位问题，不要盲目重试。

2. **列截止**：`uv run canvas deadlines --days <N>`
   - 默认 14 天；用户说"这周"就用 `--days 7`，"这个月"用 `--days 30`。
   - 输出为按截止时间排序的表格：截止(本地时间) / 课程 / 作业 / 提交方式。
   - 该命令只算 Canvas 已发布且带 `due_at` 的作业；**考试在 Canvas 里也是 assignment**，会一并列出。

3. **补齐细节**（用户需要时）：
   - 作业要求正文：`GET /courses/:id/assignments/:aid`（`scripts/canvas_client.py` 的 `assignment()`）；
     附件通常在 `description` 里，或已被 `course_summary` 存进课程目录。
   - 我的提交状态：`client.submissions(course_id, assignment_id)` —— 看 `submitted_at`/`score`/`workflow_state`，
     用来回答"我交了没有""得了多少分"。
   - 课程整体考核占比与作业全表：读 `CourseFiles/<课程目录>/README.md`
     （没有就 `uv run canvas-summary <course_id>` 生成）。

4. **汇总给用户**：按时间顺序列清单，标出 48 小时内到期的；说明"以 Canvas 当前 due_at 为准，
   老师可能调整，重要作业请再核对 Canvas 页面"。

## 校验

- 是否**翻页拉全**了（`get_all()` 自动翻页；若手写请求，必须跟随 `Link rel="next"`）。
- 是否区分了「已交」与「未交」——只有作业带 `submission` 或额外查询才能判断，不要凭 `due_at` 猜。
- 线下提交/邮件提交的作业，`submission_types` 里没有 `online_upload`，要提示用户别在 Canvas 等。
