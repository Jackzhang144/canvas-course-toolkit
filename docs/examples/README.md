# 生成的文档长什么样（脱敏样例）

`canvas download` / `canvas-summary` 会在你的本地 `CourseFiles/` 里生成几份 Markdown。
课程内容本身不入库，这里只放**同样结构、内容全部虚构**的样例，让你先看清产出物。

> 样例中的课程（CS101 / MATH101）、教师、日期、文件 ID 全部是编的，仅用于展示格式。

| 文件 | 说明 |
|---|---|
| [COURSES.md](COURSES.md) | 顶层课程索引，`canvas-summary --index` 生成 |
| [course-README.md](course-README.md) | 单门课的要点，`canvas-summary <course_id>` 生成 |
| [MANIFEST.md](MANIFEST.md) | 该课的同步清单，`canvas download` / `canvas manifest` 生成 |

这三份都是**给你自己和 AI 代理看的**工作区文件，可以放心写清流程；
交给老师的提交件是另一套口径，见 [../security.md](../security.md)。
