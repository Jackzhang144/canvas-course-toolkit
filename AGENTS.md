# AGENTS.md — Canvas 课程自动化工具包（AI 代理总纲）

> 这份文件是给 AI 代理（Claude Code / Codex / DeepSeek Harness / Cursor 等）看的仓库总纲：
> 目录约定、Canvas 环境、API 速查、skills 开发契约。
> **人类读者请先看 [README.md](README.md) 与 [docs/setup.md](docs/setup.md)。**

## 1. 仓库定位

本仓库是一个**通用**的 Canvas LMS 课程自动化工具包，覆盖「资料下载 → 学习辅助 → 作业提交」。
设计前提：

- 使用者可能是任何学校、任何专业、任何年级的同学，**代码与文档里不写死学校、课程、学期**；
- 使用者不一定是计算机专业：命令与报错要人话，别让他去读源码才能用；
- 所有凭据走环境变量（§3），仓库内不存任何秘密；
- 能力以 **仓库级 skills** 形式提供（§6），脚本层保持精简、可复用。

## 2. 目录约定

```
canvas-course-toolkit/
├── AGENTS.md            # 本文件（代理总纲）
├── README.md            # 人类入口
├── COURSES.md           # 课程索引，由 canvas-summary --index 生成（不入库，见 .gitignore 说明）
├── scripts/             # 全部可执行逻辑
├── tests/               # 离线自测
├── docs/                # setup / canvas-api / security / examples
├── .dsh/skills/         # 仓库级 skills（DeepSeek Harness 原生项目级）
├── .agents/skills/      # 同一批 skills 的镜像（跨工具约定）
├── CourseFiles/         # 使用者下载的课程资料（**不入库**，只保留 README.md）
├── Assignments/         # 使用者的作业（**不入库**，只保留 README.md）
└── LearningSummaries/   # 使用者的学习总结（**不入库**，只保留 README.md 与 TEMPLATE.md）
```

命名规范（代理新建目录时必须遵守）：

- `CourseFiles/<课程代码>_<课程名slug>/<模块或分类>/…`
  例：`CourseFiles/CS101_Introduction_to_Programming/Week03_Pointers/`。
  目录名由 `canvas_client.course_dir_name()` 生成，不要手写一套别的规则。
  每个课程目录内必须有 `MANIFEST.md`（同步日期、文件清单、Canvas 文件 ID、本地状态），
  它同时是增量同步与去重的依据。
- `Assignments/<课程代码>/<作业 slug>/`
  slug 用 ASCII（如 `hw1-implement-vector`），内部至少包含：
  - `solution.*`：最终解答（`solution.ipynb` / `solution.pdf` / 源码）；
  - `README.md`：中文说明（完成思路、如何运行、对应的 Canvas 作业 ID）；
  - 必要时 `sources/`：引用资料快照。
- `LearningSummaries/`：`YYYY-MM-DD_to_YYYY-MM-DD.md`，骨架见 `TEMPLATE.md`。
- 下载的资料**一律不改**；要批注就写在 `Assignments/` 一侧的笔记里。
- **课程上下文优先读 `COURSES.md`**（课程 ID → 目录 → 考核要点），
  专项细节再进 `CourseFiles/<课程目录>/README.md`、`syllabus.md`。

## 3. Canvas 环境与配置

凭据只走环境变量，禁止硬编码、禁止写入任何会被提交的文件：

```bash
export CANVAS_HOST="https://<你的Canvas地址>"   # 托管版 *.instructure.com 或学校自建域名
export CANVAS_API_TOKEN="<访问令牌>"
export CANVAS_TERM="2025Fall"                   # 可选，仅用于人肉过滤
```

也可以放在仓库根 `.env`（`canvas_client.load_env()` 会读，`.gitignore` 已忽略）。
优先级：构造参数 > 环境变量 > `.env`。

- **令牌获取**：Canvas → Account（账户）→ Settings（设置）→ Approved Integrations → New Access Token。
  令牌等于密码，只显示一次。
- **令牌失效**：脚本报 401 时提示使用者重新生成并更新 `.env`，**不要反复重试**。
- 官方文档：<https://developerdocs.instructure.com/services/canvas/rest>
  与 <https://canvas.instructure.com/doc/api/all_resources.html>。
  部分自建实例不开放 `/doc/api`，以官方文档为准。
- 学校实例网络可能不稳定（偶发 60s 超时 / TLS 中断 / broken pipe）：
  `canvas_client.make_session()` 已内置 urllib3 Retry（连接/读各 4 次、指数退避、只重试 429/5xx）。
  401/403/404 属于业务错误，不重试。

## 4. Canvas REST API 速查（代理用）

- **Base URL**：`<CANVAS_HOST>/api/v1`；**认证**：`Authorization: Bearer $CANVAS_API_TOKEN`。
- **分页**：默认一页 10 条、上限 `per_page=100`，靠响应头 `Link: <...>; rel="next"` 翻页。
  **任何"列出全部 X"都必须循环翻页**（最常见翻车点）——用 `CanvasClient.get_all()`。
- **签名 URL 会过期**：`GET /files/:id` 返回的 `url` 有时效，下载前重新取，不要缓存。

| 目的 | 端点 | 备注 |
|---|---|---|
| 我的信息 | `GET /users/self` | 拿 user_id，也是最快的连通性自检 |
| 我的课程 | `GET /courses?enrollment_state=active&per_page=100` | 返回 `{id, name, course_code, term}` |
| 课程详情 | `GET /courses/:id` | `include[]=term,syllabus_body` |
| 模块 | `GET /courses/:id/modules` | `include[]=items` |
| 模块项 | `GET /courses/:id/modules/:mid/items` | 类型：File/Assignment/Page/Quiz… |
| 课程文件 | `GET /courses/:id/files` | 扁平列表，需按 `folder_id` 还原层级 |
| 文件夹树 | `GET /courses/:id/folders` | `include[]=files`，`full_name` 即相对路径 |
| 单文件 | `GET /files/:fid` | 拿带签名的临时下载 `url` |
| 作业 | `GET /courses/:id/assignments` | `include[]=submission,due_dates` |
| 我的提交 | `GET /courses/:id/assignments/:aid/submissions/self` | `include[]=submission_history` |
| 公告 | `GET /courses/:id/discussion_topics?only_announcements=1` | 公告也是 topic |
| 页面 | `GET /courses/:id/pages` | `GET .../pages/:url` 拿正文 |

**下载资料的标准流程**：

1. `GET /courses/:id/files`（或 `folders` + `include[]=files`）拿到 `id`/`display_name`/`size`/`updated_at`；
2. 逐文件 `GET /files/:fid` 取临时 `url` → 下载到 `CourseFiles/<课程目录>/<相对路径>/`；
3. 下载前先按 `display_name` + `size` + 远端 `updated_at` 与本地比对，**跳过未变化的文件**（幂等、可重跑）；
4. 失败的文件必须逐条上报，最后汇总，不要静默吞掉。

**403 回退（重要，已实测于多门课）**：个别课程对 `/courses/:id/files` 返回 403，
但 `folders`、`pages`、`GET /files/:id` 仍然可用。此时用 `CanvasClient.list_course_files()`：
它会自动回退到**从页面/公告/作业正文的 `<a href=".../files/<id>...">` 里捞 file_id**，
再逐个 `GET /files/:id` 取真实名称并下载——课件照样全量同步，`MANIFEST.md` 会标注回退来源。
正文里没有链接的"裸文件"仍拿不到，属权限限制，让使用者手动从网页下载。

**提交作业的标准流程**（Canvas 不接受直接把本地路径指给它，必须两步）：

1. `POST /users/self/files`（`name`/`parent_folder_path`/`size`/`content_type`）
   → 得到 `upload_url` 与 `upload_params`（含签名、短时有效）;
2. `multipart/form-data` 把 `upload_params` 各字段连同文件二进制（字段名 `file`）POST 到 `upload_url`；
3. `POST /courses/:id/assignments/:aid/submissions`，
   body：`submission[submission_type]=online_upload`、`submission[file_ids][]=<file_id>`；
4. 先 `GET` 作业详情读 `submission_types`，不支持 `online_upload`（纸面/外部工具）就不要硬传。

**提交件自曝检查（强制）**：交给老师/学校的文件必须是干净的"人写的文件"。
提交前确认其中**不出现**：`canvas_client.py` / `course_summary.py` / `check-answers.py` /
`scripts/` / `MANIFEST` / `AGENTS.md` 等仓库文件名，"脚本复核""AI/agent/自动化/生成时间"
等字样，以及生成日期戳。工作区一侧的 `README.md`、`*.py`、日志照旧写清流水线，
**两者口径必须分开**；PDF 要专门读一遍最后一页。细节见 [docs/security.md](docs/security.md)。
`canvas-submit` 的演练会自动做两件事：**PDF 先抽文本层再扫**（不是只扫 `.tex` 源码），
并把 `/Creator`、`/Producer` 等 PDF 属性列出来提醒。

**提交件排版检查（强制）**：越界、缺字、编译告警和自曝痕一样会扣分，而且**文本抽取看不出来**
（长 URL 在抽取文本里就是正常换行）。交 PDF 前必须：
① 读编译日志，`grep -nE "Overfull|Underfull|Missing character" <build>.log` 期望无输出
（`canvas-submit` 会自动找作业目录及其 `build/` 下的 `*.log` 并逐条列出）；
② 把 PDF 渲染成图片（`gs -sDEVICE=png16m -r120 ...`）**真的用眼睛过一遍**首页、带表格/公式页、末页。
常见对策：长 URL 加 `\usepackage{xurl}`，宽表格用 `tabularx`，长公式用 `multline`/`split`。

**边界**：401 = 令牌失效；403 = 权限不足（可能不是这门课的成员）；404 = 资源不存在或被隐藏。
作业提交是**不可逆**动作：必须先向使用者展示待提交文件与目标作业，得到确认后再执行；
已提交过要主动提示，避免覆盖。

## 5. 三类核心自动化

1. **下载课程资料**：同步模块文件/课程文件/页面到 `CourseFiles/`，写/更新 `MANIFEST.md`。
2. **学习辅助**：读模块与页面 → 生成该课学习路线或笔记草稿；回答"这周学什么/什么时候截止"
   （用 §4 端点查 upcoming，或直接 `canvas deadlines`）。跨课程阶段总结放 `LearningSummaries/`。
3. **完成与提交作业**：按作业详情在 `Assignments/` 起草解答 → 生成提交件 → 按 §4 上传 →
   **经使用者确认后**提交 → 把提交状态写回该作业的 `README.md`。

## 6. Skills 开发契约

skills 放在 **`.dsh/skills/<skill-name>/SKILL.md`**，并**镜像**一份到 **`.agents/skills/`**，
两份内容保持一致（DSH 只读这两个目录的**一层**：`<root>/<name>/SKILL.md`，不递归）。

每个 skill：

- frontmatter 用 YAML：必填 `name`（kebab-case）与 `description`
  （说明"何时使用"，**带上触发词**，如"下载课件/同步资料/看作业截止/提交作业"）；
- 正文写逐步指令 + 校验步骤，**不要重复仓库级约定**，引用本文件 §号即可；
- **单一职责**：一个 skill 只做一个工作流；
- 需要凭据时**先跑 `uv run canvas init --check`**（只读、不联网，由 `setup_check.check_setup()`
  给出状态），不是 `ready` 就交给 `canvas-init-setup` skill 引导配置，**不得假设已配置、
  也不得在未就绪时继续执行下载/提交**；
- 涉及网络副作用（上传/提交/删除）前，先展示将执行的动作并请求确认。

仓库级规则（对任何 skill 一律生效）：

- 网络逻辑**只能**复用 `scripts/canvas_client.py`，不要在 skill 或新脚本里各写一份；
- 所有下载/同步都设计成**幂等、可重跑**；
- 日志与结果写在用户看得见的汇总段落里，不要只写临时文件；
- 一切读写只发生在 §2 定义的目录内，不往仓库根目录或仓库外散落产物。

## 7. 共享助手（scripts/，已落地）

```bash
uv run canvas init [--check]         # 首次初始化：生成 .env / 只检测状态（只读）
uv run canvas doctor                 # 自检：凭据/连通性/权限
uv run canvas courses                # 我的课程（自动翻页）
uv run canvas files <course_id>      # 课程文件清单
uv run canvas download <course_id>   # 下载到 CourseFiles/（自动写 MANIFEST）
uv run canvas manifest --all         # 为所有课程写/更新 MANIFEST.md
uv run canvas deadlines --days 14    # 近期截止（带"交没交"状态）
uv run canvas-summary <course_id>    # 生成课程 README + syllabus/pages/announcements
uv run canvas-summary --index        # 重建顶层 COURSES.md
uv run canvas-submit <course_id> <assignment_id> [dir] [--confirm]
```

- `setup_check.py`：初始化状态检测（纯本地、不联网）。`check_setup()` 的 `state`
  是「还差什么」的唯一权威判断，**任何 skill 在动手前都应据此决定是否先引导配置**；
  `ensure_env_file()` 幂等且绝不覆盖已有 `.env` 的值。

- `canvas_client.py`：**唯一网络入口**。`get_json` / `get_all`（翻页）/ `download_file`（幂等）/
  `upload_file` + `submit_online_upload`（两步提交）/ `write_manifest`。
- 新增接口一律加在 `canvas_client.py` 里，改完先跑
  `uv run python -m py_compile scripts/canvas_client.py` 与 `uv run --dev pytest`。
- 非英文课程的适配：`course_summary.py` 顶部的 `SECTION_*` / `GROUP_KEYWORDS` / `PERCENT_PATTERN`
  是可调常量，改这里就能适配别的语言或别的教务措辞，不用改逻辑。

## 8. 使用者上手路径

1. `git clone` + `uv sync --dev`；
2. 复制 `.env.example` 为 `.env`，填 `CANVAS_HOST` 与令牌（§3）；
3. `uv run canvas doctor` 确认全链路可用；
4. `uv run canvas download <course_id>` 先同步一门课，验证效果；
5. 再按 §5 顺序用学习辅助与提交能力。

> 当本文件与实际行为冲突时：以官方 Canvas REST 文档与使用者确认为准。
> 拿不准就先问使用者，不要臆造课程结构或执行提交动作。
