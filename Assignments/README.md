# Assignments/ — 你的作业

这里放**你在做的作业**：草稿、解答、生成好的提交件、以及提交记录。

```
Assignments/
└── CS101/
    └── hw1-implement-vector/
        ├── solution.py            # 最终解答
        ├── solution.pdf           # 生成为提交件的版本（如果需要）
        ├── README.md              # 中文说明：思路、如何运行、对应 Canvas 作业 ID、提交记录
        └── sources/               # 引用资料快照（可选）
```

## 约定

- 目录名：`Assignments/<课程代码>/<作业 slug>/`，slug 用 ASCII，如 `hw2-functions`。
- 每个作业目录都要有 `README.md`，写清：完成思路、如何运行、**对应的 Canvas 作业 ID / course_id**。
- 提交状态回写到这里（提交时间、file_id、attempt），下次就知道交过没有。
- **不入库**（`.gitignore` 已忽略）——作业解答是最不该外传的东西，
  公开到 GitHub 可能被判定学术不端。

## 提交作业

```bash
# 1) 演练：只打印将提交的文件与目标作业，不做任何修改
uv run canvas-submit 12345 67890 Assignments/CS101/hw1-implement-vector

# 2) 看过输出、确认无误后再真提交
uv run canvas-submit 12345 67890 --files solution.pdf --confirm
```

⚠️ **提交前务必过一遍自曝检查**：交给老师的文件里不能出现仓库文件名、
"脚本复核/AI/自动化/生成时间"之类字样，以及生成日期戳。
提交命令会自动扫文本类文件并报告命中行，PDF 请自己翻到最后一页看。
完整清单见 [docs/security.md](../docs/security.md)。
