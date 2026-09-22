---
name: canvas-download-files
description: 下载或同步 Canvas 课程资料（课件/页面/公告）到本地 CourseFiles/，并刷新 MANIFEST.md 增量清单与课程要点 README。
whenToUse: 当用户说「下载课件」「同步课程资料」「把课程资料拉下来」「更新课件」「刷新课程清单」「download files」等课程资料同步操作时使用。
---

# 同步 Canvas 课程资料

把指定课程（或全部课程）的课件、页面、公告同步到 `CourseFiles/<课程代码>_<课程名slug>/`，
并写/更新 `MANIFEST.md` 与课程要点 `README.md`。**全程幂等，可反复重跑。**

## 步骤

1. **确认环境**：检查 `CANVAS_HOST` 与 `CANVAS_API_TOKEN` 是否已配置（环境变量或仓库根 `.env`）。
   缺失就按 `AGENTS.md` §3 引导用户配置，不要假设已配置。
   用 `uv run canvas doctor` 一次性验证凭据、连通性与权限；401 时提示用户重新生成令牌，不要反复重试。

2. **定位课程**：优先读仓库根 `COURSES.md`（课程 ID → 目录名）。
   ID 不确定或有新课时用 `uv run canvas courses` 列出（`--all-terms` 含历史课程）。

3. **先看再下**：`uv run canvas files <course_id>` 列出可下载文件；
   文件多或用户只是想确认时，加 `--dry-run` 演练：`uv run canvas download <course_id> --dry-run`。

4. **下载**：
   - 单门课：`uv run canvas download <course_id>`（默认落到 `CourseFiles/<课程目录>/`）
   - 全部课程：对 `courses` 列出的每个 ID 依次执行 download。
   脚本会自动跳过未变化的已存在文件（比对文件名 + 大小 + 远端 `updated_at`），
   下载时先写 `.part` 再改名，断网不会留下半截文件。

5. **刷新清单与要点**：
   - `uv run canvas manifest --all` 为所有课程写/更新 `MANIFEST.md`（download 已自动写对应课程，此命令兜底）；
   - `uv run canvas-summary --all` 重生成各课 `README.md` 与 `syllabus.md`/`pages/`/`announcements/`；
   - `uv run canvas-summary --index` 重建顶层 `COURSES.md` 索引。

6. **校验并汇总**：向用户报告每门课的「新下载 N / 已存在跳过 M / 失败 K」，
   **失败文件必须逐条列出**，不要静默忽略。若有文件当时没拿到，说明原因（权限限制 / 正文无链接）。

## 注意

- 网络不稳时客户端已内置重试（连接/读 4 次、指数退避），401/403/404 不重试、直接报错。
- 若某课 `/files` 端点返回 403，`files`/`download` 已内置回退：自动从页面、公告、作业正文里的
  `/files/<id>` 链接捞 file_id 再逐个下载，`MANIFEST.md` 备注会标明回退来源。
  仅"正文里完全没链接的裸文件"需要用户手动从网页下载。
- **不要修改下载下来的原始资料**；需要批注就写到 `Assignments/` 一侧的笔记里。
- 下载内容已被 `.gitignore` 忽略，不要把它们提交进仓库。
