# Canvas 课程自动化工具包

把 Canvas LMS 上的课程自动化：**同步课件 → 看清这周要交什么 → 辅助完成与提交作业**，
并把这些能力封装成 AI 代理可以直接调用的 skills。

- 只要你的学校用 **Canvas LMS**（Instructure），任何专业、任何年级都能用；
- 不挑语言、不挑课程，代码里没有写死任何学校或课程；
- 全程在你自己的电脑上跑，凭据只存在本地 `.env`，不会上传到任何地方。

> 本仓库只包含**工具本身**。课程课件、作业解答、个人学习记录都不在仓库里
> （`.gitignore` 已忽略），它们留在你自己的机器上。

## 它能帮你做什么

| 场景 | 你打的命令 |
|---|---|
| 第一次用：看看还差什么配置 | `uv run canvas init` |
| 一次性确认"我能不能用" | `uv run canvas doctor` |
| 把一门课的全部课件下载到本地（幂等，可重跑） | `uv run canvas download 12345` |
| 看清未来两周有什么要交（含"交没交"） | `uv run canvas deadlines --days 14` |
| 为每门课生成一份课程要点（评分占比/作业/组队要求） | `uv run canvas-summary --all` |
| 提交作业（会真的提交，默认演练） | `uv run canvas-submit 12345 67890 --confirm` |

## 三步上手

```bash
# 1) 拿到代码
git clone https://github.com/Jackzhang144/canvas-course-toolkit.git
cd canvas-course-toolkit

# 2) 装依赖（uv 最省事；没有 uv 见 docs/setup.md 的 pip 方案）
uv sync --dev

# 3) 初始化：生成 .env 并告诉你还差哪一步（幂等，不会覆盖已填好的令牌）
uv run canvas init
#    按它的提示填好 CANVAS_HOST 与 CANVAS_API_TOKEN，然后只检测不改文件：
uv run canvas init --check

# 4) 自检 + 打通
uv run canvas doctor
```

`canvas init --check` 是**只读**的，只报告"还差什么"，不会动你的文件；
它给出的状态就是唯一依据：`no_env` / `missing_host` / `missing_token` /
`token_placeholder` / `host_looks_wrong` / `ready`。

`doctor` 会依次验证：凭据是否读到 → 能否登录 → 有几门课 → 页面/作业/公告/文件权限是否开放。
**它成功就等于全流程可用。** 详细说明（含"令牌在哪里拿""没有 uv 怎么办""各种报错怎么修"）
见 **[docs/setup.md](docs/setup.md)**。用 AI 代理的话，直接说"初始化一下"，
`canvas-init-setup` skill 会照着同一套状态检测带你走。

## 命令行速查

```bash
uv run canvas init                   # 首次初始化：生成 .env + 报告还差什么
uv run canvas init --check           # 只检测状态（只读，不改任何文件）
uv run canvas doctor                 # 自检（配置齐了以后的第一步）
uv run canvas whoami                 # 我是谁
uv run canvas courses                # 我的课程 + 课程 ID
uv run canvas courses --all-terms    # 连历史课程一起列
uv run canvas files 12345            # 这门课有哪些文件可下（先看再下）
uv run canvas download 12345 --dry-run   # 演练：只列出将要下载的文件
uv run canvas download 12345         # 真下载到 CourseFiles/<课程目录>/
uv run canvas manifest --all         # 为所有课程更新 MANIFEST.md 增量清单
uv run canvas deadlines --days 7     # 未来 7 天要交什么

uv run canvas-summary 12345          # 生成/刷新这门课的 README（要点）
uv run canvas-summary --all          # 所有课程
uv run canvas-summary --index        # 重建顶层 COURSES.md 索引

uv run canvas-submit 12345 67890 --files solution.pdf          # 演练（不提交）
uv run canvas-submit 12345 67890 --files solution.pdf --confirm # 真提交
uv run canvas-submit 12345 67890 Assignments/CS101/hw1 --latex-log build/solution.log  # 指定要查的编译日志
```

演练阶段会自动做三项预检：**PDF 文本层自曝扫描**（`pdftotext`/`gs`，两者都没有会明确说"未覆盖"）、
**PDF 属性**（`/Creator`、`/Producer` 等）、**LaTeX 日志版面告警**（`Overfull`/`Underfull`/缺字）。
`--latex-log` 不传时会自动在作业目录及其 `build/` 下找 `*.log`。

不用 uv 也可以用 `python -m scripts.cli doctor` 之类的方式调用，见 docs/setup.md。

## 目录结构

```
canvas-course-toolkit/
├── scripts/                 # 全部可执行逻辑（唯一网络入口 canvas_client.py）
│   ├── canvas_client.py     # Canvas REST 客户端：翻页、重试、下载、上传、提交
│   ├── cli.py               # canvas 命令：init/doctor/courses/files/download/manifest/deadlines
│   ├── setup_check.py       # 初始化状态检测（只读、不联网）与 .env 幂等创建
│   ├── course_summary.py    # canvas-summary 命令：课程要点 README + COURSES.md 索引
│   └── submit.py            # canvas-submit 命令：两步上传提交（默认 dry-run）
├── tests/                   # 离线自测（不联网、不需要令牌）
├── .dsh/skills/             # AI 代理用 skills（DeepSeek Harness 等）
├── .agents/skills/          # 同一批 skills 的镜像（Codex / 其他代理工具）
├── docs/                    # 上手与原理文档
│   ├── setup.md             # 环境、令牌、常见报错
│   ├── canvas-api.md        # Canvas REST API 速查（自己写脚本时看）
│   ├── security.md          # 凭据与作业提交的安全边界
│   └── examples/            # 生成的文档长什么样（脱敏样例）
├── CourseFiles/             # 【你的】下载的课程资料（不入库）
├── Assignments/             # 【你的】作业（不入库）
├── LearningSummaries/       # 【你的】学习总结（不入库，附模板）
└── AGENTS.md                # 给 AI 代理的仓库总纲
```

## 给 AI 代理用（Claude Code / Codex / DeepSeek Harness 等）

本仓库自带 skills，代理读到 `.dsh/skills/` 或 `.agents/skills/` 后即可自动执行：

- `canvas-init-setup` —— **第一次用就靠它**：先检测配置齐不齐，缺什么就一步步带你配好
- `canvas-download-files` —— 同步课件、刷新清单与课程要点
- `canvas-list-due-work` —— 回答"这周/这个月要交什么"
- `canvas-submit-assignment` —— 整理提交件并提交（**必须用户确认后**才真提交）

后三个 skill 在动手前都会先跑一次只读检测（`uv run canvas init --check`）；
配置没就绪就转交 `canvas-init-setup`，不会带着残缺配置硬跑。

每个 skill 的 `SKILL.md` 里写了触发词与逐步指令。仓库级的约定、目录规范、
"提交件不能带机器痕迹"的硬规则都写在 `AGENTS.md`。

## 可信度

- `uv run --dev pytest` 共 36 项测试，**全部离线**：不联网、不需要令牌、不需要任何 secret，
  所以你在自己机器上和 CI 里跑的结果是同一个。
  其中包含一个**假 Canvas 服务器**，真实跑通整条链：
  自动翻页 → 403 回退从页面正文捞附件 → 幂等下载（重跑不重下）→ 清单/要点/索引生成 →
  两步上传并挂 `file_id` 完成提交（并断言 dry-run **绝不**发出提交请求）。
- **提交前预检**（`canvas-submit` 演练阶段）把三类翻车点摆到眼前：
  自曝痕（**PDF 会先抽文本层再扫**，不是只扫 `.tex`）、PDF 属性（`/Creator`、`/Producer`）、
  编译日志版面告警（`Overfull`/`Underfull`/缺字/未定义引用，自动找作业目录及其 `build/` 下的日志）。
  版面**还要求人眼**：文本抽取看不出越界，工具会打印渲染命令让你逐页看图。详见 [docs/security.md](docs/security.md)。
- 这套客户端在真实 Canvas 实例上做过**只读验收**：自动翻页拿全课程、
  目录命名与旧版实现逐一比对一致（所以能无缝接管你已有的 `CourseFiles/`，不会另起一套目录）、
  受限课程的 403 回退清单与本地已下载文件数吻合。
  验收过程只读，未下载、未提交任何东西。

> 想自己复验第 2 条：填好 `.env` 后跑 `uv run canvas doctor`（只读），
> 再 `uv run canvas files <course_id>` 对照浏览器里看到的文件数。

## 设计取舍

- **幂等**：下载按"文件名 + 大小 + 远端更新时间"跳过已存在文件，随便重跑。
- **有礼貌**：串行下载 + 指数退避重试，不做并发轰炸学校服务器；401/403/404 直接报错不重试。
- **可修复**：网络抖动自动重试；个别课程禁用文件列表（403）时自动回退到
  从页面/公告正文里捞附件链接，课件照样能同步。
- **不越权**：只用你账号本来就能看的课程；工具不会、也不能绕过权限。

## 常见问题

**Q: 我的学校不是 instructure.com 域名，能用吗？**
能。`CANVAS_HOST` 填学校自建域名即可（如 `canvas.yourschool.edu`），工具会自动补 `https://`。

**Q: 会不会被老师发现？**
拉取课件只是读取你自己账号本来就能看到的课程内容，和用浏览器打开没有区别。
请不要用于批量爬取他人课程或绕过权限。

**Q: 提交作业会不会出错？**
`canvas-submit` 默认只演练，逐项打印将提交的文件与目标作业；加 `--confirm` 才真提交，
且提交前会检查该作业是否支持在线提交、你是否已经交过。

**Q: 我的作业解答会被上传到 GitHub 吗？**
不会。`CourseFiles/`、`Assignments/`、`LearningSummaries/` 都被 `.gitignore` 忽略。

## 贡献

欢迎 PR：新增学校适配、修 bug、补文档都行。请先读 [CONTRIBUTING.md](CONTRIBUTING.md)，
跑一遍 `uv run --dev pytest` 确保自测通过。

## 许可

MIT，见 [LICENSE](LICENSE)。工具本身自由使用；**用它下载的课程资料版权属于学校和老师**，
请勿二次分发。
