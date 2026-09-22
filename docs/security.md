# 安全与责任边界

用自动化工具处理自己的课程，本身就是正常需求。这份文档说清三件事：
**凭据怎么管、什么不要做、交上去的文件要注意什么。**

---

## 1. 凭据

| 规则 | 原因 |
|---|---|
| 令牌只放本地 `.env` 或环境变量 | 它等同你的密码，能读写你账号里的一切 |
| 不要把 `.env`、令牌粘进聊天、Issue、截图、群文件 | 一旦泄露，别人就能以你的身份操作 Canvas |
| 不要把令牌写进任何脚本/Notebook 单元格 | 提交/分享时会连带泄露 |
| 怀疑泄露立刻吊销 | Canvas → Account → Settings → Approved Integrations → 对应令牌 Delete |
| 换设备/期末结束时顺手吊销 | 令牌可以永不失效，忘了就是个长期后门 |

本仓库的姿态：**代码里不存在任何硬编码凭据**，`.gitignore` 已忽略 `.env`、
`CourseFiles/`、`Assignments/`、`LearningSummaries/`，`tests/` 也全部离线、不需要令牌。
如果你 fork 后改了代码，提交前跑一次：

```bash
git status --short          # 确认没有 .env / CourseFiles / Assignments 冒出来
grep -rIl "CANVAS_API_TOKEN" --exclude-dir=.venv --exclude-dir=.git . | grep -v example
```

## 2. 不要做的事

工具只读取**你自己账号本来就能看到的内容**，也只用你本来就能用的提交功能。请守住这几条：

- ❌ 别用它抓别人的课程、别人的提交、别人的成绩——没权限的端点会 403，绕过权限是另一回事，别做。
- ❌ 别拿它做高频轮询（比如每 10 秒扫一次作业）。学校实例是公共资源，工具本身是串行 + 退避的，别改成一堆线程。
- ❌ 别把下载到的课件二次分发。课件版权属于学校和老师，下载自己看没问题，
  上传到公开网盘/仓库是侵权（这也是本仓库 `.gitignore` 忽略 `CourseFiles/` 的原因）。
- ❌ 别把本仓库当成"绕过学术诚信"的手段。用工具整理资料、跟踪截止、排版，都没问题；
  但**作业的内容、理解与结论必须是你的**。多数学校对"生成式 AI 代写作业"有明确规定，
  违反的后果由你自己承担，跟用什么工具无关。

## 3. 提交件必须"干净"

这是最容易翻车、也最容易被忽略的一条。

**问题**：你在工作区里用脚本、用 AI 代理干活，很容易顺手把痕迹写进最终交上去的文件里——
比如 PDF 末页出现：

```
所有计算均以脚本复核（见 check-answers.py）。
生成时间：2026-09-22 20:17
```

`check-answers.py` 是工作区文件名、"脚本复核"是流程描述、时间戳是机器口径。
**这些字样等于在作业上盖章"这不是我独立完成的"。** 老师一眼就能看出来。

**因此，交付口径必须分成两套：**

| 场合 | 可以写什么 |
|---|---|
| 工作区文件（`README.md`、`*.py`、日志、`MANIFEST.md`） | 随便写：流水线、脚本名、幂等重跑、回退方案…… |
| **交给老师/学校的文件**（`solution.pdf`、报告、演示稿、截图） | 只留必要身份信息（姓名、学号、课程、作业名），其余一律不提 |

**提交前检查清单：**

- [ ] 文中不含工作区文件名：`canvas_client.py`、`course_summary.py`、`check-answers.py`、
      `scripts/`、`MANIFEST`、`AGENTS.md`、本仓库名；
- [ ] 不含"脚本 / AI / agent / 模型 / 自动化 / 程序生成 / 复核"之类字样；
- [ ] 不含生成日期戳（除非作业格式本身要求填日期）；
- [ ] 不含内部流程描述（"回退方案""幂等重跑""读取 Canvas API""清单已更新"）；
- [ ] 脚注/页眉只留姓名、学号、课程、作业名；
- [ ] **PDF 要专门翻到最后一页看一遍**（页脚、脚注最容易残留）；
- [ ] 顺手看一眼 PDF 属性（`pdfinfo solution.pdf`）：LaTeX 默认会写
      `Creator: XeTeX`、`CreationDate`，用 `\hypersetup{pdfcreator=...,pdfauthor=...}` 显式覆盖；
- [ ] 提交前用 `uv run canvas-submit ...`（不带 `--confirm`）演练一次，
      它会自动扫命中行并打印 ⚠ —— **PDF 会先抽文本层再扫**（`pdftotext` 或 `gs`），
      因为交上去的通常正是 PDF，只扫 `.tex` 等于没看真正被老师看到的那一面；
- [ ] **PDF 属性**（`/Creator`、`/Producer`、`/CreationDate`）也顺手清掉，
      `canvas-submit` 会把扫描到的属性名一并打印出来提醒。

**抽 PDF 文本自查：**

```bash
pdftotext solution.pdf - | tail -40          # 看末页文字
pdfinfo solution.pdf                          # 看元数据
pdftotext solution.pdf - | grep -niE "脚本|script|agent|AI|自动|生成|canvas|MANIFEST|check-answers"
```

### 3.1 还有一类翻车：排版越界（文本抽取查不出来）

自曝检查做得再全，**内容冲出页边距**照样扣分——而且这类问题有个阴险之处：

> **纯文本抽取看起来一切正常。** 长 URL 在抽取出的文本里就是正常换行，
> 和正常排版长得一模一样；`pdftotext` 也永远不会告诉你"它压到页边距外面了"。

真实案例：一份 PDF 第 1 行的链接是条 90+ 字符的 URL，LaTeX 断不开它，
整段冲出右边距 8.4cm。文件能编译、能打开、文本抽取正常，**直到人用眼睛看才发现**。
当时的编译日志里其实一直写着：

```
Overfull \hbox (238.92365pt too wide) in paragraph at lines 68--69
```

只是没人去看它。

**因此交 PDF 之前，这两件事必须都做（`canvas-submit` 会替你查日志，但看图只能你来）：**

```bash
# 1) 读编译日志（不要只看"编译成功"）—— 期望无输出
grep -nE "Overfull|Underfull|Missing character" build/*.log solution.log 2>/dev/null
#    用 latexmk 的话：latexmk ... 2>&1 | tee build.log
#    canvas-submit 会自动找 <作业目录>/*.log 与 <作业目录>/build/*.log 并逐条列出来

# 2) 渲染成图片，用人眼过一遍（首页、带表格/公式页、末页）
gs -q -dNOPAUSE -dBATCH -dNOSAFER -sDEVICE=png16m -r120 \
   -dFirstPage=1 -dLastPage=1 -sOutputFile=/tmp/p1.png solution.pdf
```

**常见溢出来源与对策：**

| 现象 | 原因 | 对策 |
|---|---|---|
| 长 URL 冲出右边距 | `url`/`hyperref` 只在有限字符处断行 | 导言区加 `\usepackage{xurl}`（可与 `\Urlmuskip=0mu plus 1mu\relax` 搭配） |
| 宽表格越界 | 列内容比版心宽 | `tabularx` 的 `X` 列、`\small`、缩短列内容 |
| 长公式越界 | 单行公式太长 | `multline`/`split`，或 `\resizebox`（下策：字号会不一致） |
| `Missing character` | 字体缺字形（emoji、特殊符号、生僻字） | 换字体或补字形；日志里搜 `Missing character` 逐条清 |

> 顺带一句：如果某门课的作业要求明确禁止使用 AI 辅助，那么本仓库的任何功能都不要用在它上面。
> 这是你自己的判断和责任。

## 4. 本地数据

- `CourseFiles/`：课件快照（第三方版权），只留本地；
- `Assignments/`：你的作业与解答，**这是最不该外传的目录**；
- `LearningSummaries/`：学习总结，可能含学号/姓名；
- 三者都被 `.gitignore` 忽略，`git status` 里不会出现。**但 fork 或新 clone 到别处时，
  如果你手动 `git add -f`，就能把它们提交上去**——别这么干。

如果误提交了：光删文件不够，历史里还在。
用 `git filter-repo`（或 GitHub 官方的敏感数据清理流程）重写历史，并立刻吊销令牌。
