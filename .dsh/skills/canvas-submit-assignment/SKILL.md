---
name: canvas-submit-assignment
description: 把完成的作业文件上传并提交到 Canvas 作业（两步上传法），提交前必须让用户确认文件与目标作业。
whenToUse: 当用户说「提交作业」「把这份交上去」「上传到 Canvas 作业」「交 hw1」「submit assignment」时使用。
---

# 提交作业到 Canvas

> **这是本仓库唯一不可逆的操作。** 提交会真的产生/覆盖记录，必须经用户确认。

## 前置检查（缺一不可）

1. 凭据已配置（`AGENTS.md` §3）；`uv run canvas doctor` 通过。
2. 待提交文件确实是**最终版**：`solution.pdf` / 源码 / 报告已生成、能打开、页数正确。
3. 该作业**支持在线提交**：`client.assignment(course_id, assignment_id)` 的 `submission_types` 里
   必须含 `online_upload`。只有 `on_paper` / `none` / `external_tool` 时不要硬传，先看作业说明。
4. **提交件自曝检查（强制）**：确认文件中**不出现**仓库文件名（`canvas_client.py`、`check-answers.py`、
   `scripts/`、`MANIFEST`、`AGENTS.md`）、"脚本复核 / AI / agent / 自动化 / 生成时间"等字样，以及生成日期戳。
   PDF 要用 `pdftotext solution.pdf - | tail -40` 读一遍末页。
   工作区的 `README.md` 可以写清流水线，提交件必须干净——细节见 `docs/security.md`。
   `canvas-submit` 会对文本类文件自动扫一遍并打印 ⚠ 命中行。

## 流程

1. **定位作业**：从 `COURSES.md` 拿 `course_id`；从课程 `README.md` 的作业表拿 `assignment_id`
   （或用 `client.assignments(course_id)` 查）。
2. **演练（默认）**：先不带 `--confirm` 跑一次，逐项核对打印信息——
   课程、作业名、截止时间、允许的提交方式、当前时间、待提交文件、是否已提交过、自曝扫描结果：
   ```bash
   uv run canvas-submit <course_id> <assignment_id> <作业目录>
   uv run canvas-submit <course_id> <assignment_id> --files solution.pdf
   ```
3. **向用户确认**：把演练结果原样呈现，明确问一句"确认提交吗"。
   **用户没明确同意就不要加 `--confirm`。** 已提交过要特别提示会覆盖。
4. **执行**：用户确认后加 `--confirm` 提交（脚本内部：上传到个人文件区 → 拿 `file_id` →
   `POST .../submissions` 挂上）。按 §4 两步流程，不要试图直接传本地路径。
5. **回写记录**：把提交时间、`file_id`、`attempt` 与作业结果写进该作业目录的 `README.md`，
   再回读一次 `client.submissions()` 确认 `submitted_at` 已更新。

## 失败处理

- 401 → 让用户重新生成令牌；403 → 用户可能不是该课成员；404 → `course_id`/`assignment_id` 不对。
- 上传成功但挂提交失败：file 已进个人文件区，**不要重复上传**，直接用返回的 `file_id` 重试第 2 步。
- 提交结果不确定时，让用户到 Canvas 页面核对，不要反复重提。
