# 贡献指南

欢迎 PR。这个仓库的目标是**让任何学校、任何专业的同学都能用上**，
所以最有价值的贡献通常不是加功能，而是"让不懂技术的人也能跑通"。

## 最有用的贡献

1. **适配你的学校**：自建域名、特殊端点、你们学校的令牌在哪拿——补进 `docs/setup.md` 与 `docs/canvas-api.md`。
2. **修 bug**：尤其是权限/网络相关的边界情况（403 回退、超时、断点续传、文件名乱码）。
3. **让报错更人话**：使用者大多不是计算机专业，错误信息要能直接告诉他怎么办。
4. **补测试**：`tests/` 里的自测必须保持**离线**——不联网、不需要令牌。

## 提交前必做

```bash
uv sync --dev
uv run --dev pytest                        # 离线自测必须全绿
uv run python -m py_compile scripts/*.py   # 语法自检
uv run canvas --help                       # CLI 能正常打印帮助
```

- 改动网络逻辑时，**只改 `scripts/canvas_client.py`**，不要在别处复制一份 requests 调用。
- 新增接口请同时补一条离线测试（纯函数优先）。
- 新增/修改 skill 时，`.dsh/skills/` 与 `.agents/skills/` **两份必须同步**，
  改完跑 `diff -r .dsh/skills .agents/skills` 确认一致。
- 提交信息用中文或英文都行，但要写清"改了什么、为什么"。

## 不要提交的内容

- `.env`、任何令牌或 cookie；
- `CourseFiles/`、`Assignments/`、`LearningSummaries/` 里的真实课程内容
  （版权 + 隐私 + 体积，`.gitignore` 已忽略，**不要用 `git add -f` 强加**）；
- 真实姓名、学号、成绩、教师姓名等个人信息——示例一律用 `ZHANG San`、`12345` 这类虚构值；
- 大文件（模型权重、数据集、PDF 合集）。需要展示产出物时，放虚构样例到 `docs/examples/`。

提交前自查：

```bash
git status --short
git diff --cached --stat
grep -rInE "CANVAS_API_TOKEN *= *[\"'][^\"']+|instructure\.com/courses/[0-9]+" \
  --exclude-dir=.venv --exclude-dir=.git . || true
```

## 代码风格

- Python 3.10+，只用标准库 + `requests`，**不要引入重依赖**（同学装不上就白搭）。
- 纯函数优先，便于离线测试；网络调用集中在 `canvas_client.py`。
- 注释与文档写中文（面向的使用者以中文为主），标识符与命令用英文。
- 长注释解释"为什么这么做"（比如为什么要 `.part` 临时文件、为什么要回退捞链接），
  不要复述代码在做什么。

## 报 bug 时请附上

1. 你跑的命令；
2. 完整报错输出（**先把令牌打码**）；
3. 你的 `CANVAS_HOST` 形态（`xxx.instructure.com` / 自建域名），**不要贴完整 URL 或令牌**；
4. Python 版本与操作系统。

## 许可

提交即表示你同意以 [MIT](LICENSE) 许可发布你的贡献。
