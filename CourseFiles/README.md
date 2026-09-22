# CourseFiles/ — 你的课程资料

这里放**你从 Canvas 同步下来的课程资料**：课件、习题、页面、公告快照。

```
CourseFiles/
└── CS101_Introduction_to_Programming/        # 目录名由工具按「课程代码_课程名」生成
    ├── README.md                             # 课程要点（评分占比/作业/组队要求）
    ├── MANIFEST.md                           # 同步清单：文件 ID、大小、本地状态
    ├── syllabus.md                           # 大纲全文
    ├── Week01/Lecture01-Introduction.pdf
    ├── Week02/Tutorial/Tutorial02-Questions.pdf
    ├── pages/*.md                            # 课程页面转 Markdown
    └── announcements/*.md                    # 公告全文
```

## 怎么生成

```bash
uv run canvas courses                # 先看课程 ID
uv run canvas download 12345         # 下载课件 + 写 MANIFEST.md
uv run canvas-summary 12345          # 生成这门课的 README.md / syllabus / pages / announcements
uv run canvas-summary --index        # 重建顶层 COURSES.md 索引
```

## 约定

- **原始资料不改动**。要批注、要写笔记，写到 `Assignments/` 一侧，别改这里的文件。
- **可反复重跑**：已下载且未变化的文件会自动跳过，断网中断后直接再跑一次即可。
- **不入库**。整个目录被 `.gitignore` 忽略，原因有两个：
  1. 课件版权属于学校和老师，不能二次分发；
  2. 体积大（一门课几百 MB 很常见）。
- 看到 `MANIFEST.md` 里状态是"未下载"的文件：重跑一次；若依然如此，
  说明该文件是权限受限的"裸文件"，需要你登录 Canvas 网页手动下载。
