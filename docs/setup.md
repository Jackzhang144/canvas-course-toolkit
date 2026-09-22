# 上手配置（从零到跑通）

按顺序做一遍，大概 5 分钟。卡在哪一步，看最后一节的报错对照表。

---

## 0. 你需要准备什么

| 条件 | 说明 |
|---|---|
| 学校用 **Canvas LMS** | 登录后网址是 `xxx.instructure.com` 或 `canvas.你的学校.edu` 就是了 |
| 一个能登录 Canvas 的账号 | 你自己平时用的那个 |
| Python **3.10+** | `python3 --version` 看一眼；macOS 自带的一般够 |
| `uv`（推荐） | 装法：`curl -LsSf https://astral.sh/uv/install.sh \| sh`；不想装看下面的 pip 方案 |

> 不会命令行也没关系：把本文件连同仓库地址一起丢给 AI 代理（Claude Code / Codex / DeepSeek Harness 等），
> 它可以按 `AGENTS.md` 和 `.dsh/skills/` 里的说明代你执行。

---

## 1. 拿到代码

```bash
git clone https://github.com/Jackzhang144/canvas-course-toolkit.git
cd canvas-course-toolkit
```

## 2. 装依赖

**方式 A：uv（推荐，自动建虚拟环境）**

```bash
uv sync --dev
```

之后所有命令都可以写成 `uv run canvas ...`。

**方式 B：pip 用户**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # 或 pip install requests
```

之后用 `python -m scripts.cli ...` 代替 `uv run canvas ...`，例如
`python -m scripts.cli doctor`、`python -m scripts.course_summary --all`。

## 3. 拿到你的访问令牌（Access Token）

1. 浏览器登录 Canvas；
2. 点右上角头像 → **Account / 账户**；
3. 左侧 **Settings / 设置**；
4. 页面往下找 **Approved Integrations**（已授权的集成）；
5. 点 **+ New Access Token**：
   - Purpose 随便写，如 `course-toolkit`；
   - Expires 可以留空（永不过期）或设一个学期后；
6. 点 Generate，**立刻复制**那一串 —— 它只显示这一次。

> 如果你学校的 Canvas 是自建的老版本，这个入口可能在
> 「头像 → Settings → 最下方」，或需要访问 `/profile/settings`；找不到就用页面内的搜索框搜 "Access Token"。

⚠️ 这串令牌等于你的密码：不要贴到聊天群、不要提交到 git、不要截图。万一泄露，
回同一个页面点该令牌右边的 **Delete/Revoke** 立刻吊销，再生成新的。

## 4. 填配置

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
CANVAS_HOST="https://你的学校域名"     # 形如 https://xxx.instructure.com 或 https://canvas.xxx.edu
CANVAS_API_TOKEN="刚才复制的那串"
CANVAS_TERM=""                        # 可留空
```

- `CANVAS_HOST` 写域名就行，不写 `https://` 也能识别，但带上更保险；
- `.env` 已被 `.gitignore` 忽略，**不会被提交**；不想用文件也可以直接
  `export CANVAS_HOST=... CANVAS_API_TOKEN=...`。

## 5. 自检

```bash
uv run canvas doctor
```

正常输出长这样：

```
主机        : your-school.instructure.com
凭据来源    : .env
身份        : ZHANG San (id=12345)
在读课程    : 4 门
      12345  CS101 Introduction to Programming    2025 Fall
      ...
权限抽查    : 课 12345
   页面: 12 条
   作业: 5 条
   公告: 3 条
   文件: 48 个
自检结束。下一步: uv run canvas download <course_id>
```

看到这里就说明**全流程可用**。接着：

```bash
uv run canvas files 12345              # 看看这门课有什么
uv run canvas download 12345 --dry-run # 演练：只列出会下载什么
uv run canvas download 12345           # 真下载
uv run canvas deadlines --days 14      # 未来两周要交什么
```

---

## 6. 报错对照表

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `未配置 Canvas 凭据` | `.env` 没建、写错位置或变量名写错 | 变量名必须是 `CANVAS_HOST` / `CANVAS_API_TOKEN`；`.env` 放在仓库根目录 |
| `Canvas API 401` | 令牌失效/拼错/被吊销 | 去 Account → Settings → Approved Integrations 重新生成，更新 `.env` |
| `Canvas API 403` | 不是这门课的成员，或该端点未开放 | 换一门自己的课试；文件列表 403 时工具会自动回退从页面链接捞附件 |
| `Canvas API 404` | `course_id` / `assignment_id` 不存在 | 用 `uv run canvas courses` 重新拿 ID |
| 请求卡住很久 / `SSL_ERROR_SYSCALL` / `Broken pipe` | 学校实例网络抖动 | 客户端已自动重试 4 次；还失败就过几分钟再来，或先下少一点 |
| `uv: command not found` | 没装 uv | 用上面的 pip 方案，或按提示装 uv |
| 下载到一半中断 | 网络 | 直接重跑同一条命令：已下好的会自动跳过，只补缺的 |
| 有的课件就是下不到 | 老师设置的文件权限/正文里没有链接 | 登录 Canvas 网页手动下载那一个文件 |

## 7. 卸载 / 清理

- 删掉整个目录即可；工具不在系统里装任何常驻服务。
- 令牌不用了就去 Canvas 页面吊销。
- 想彻底清掉本地下载的资料：删 `CourseFiles/`。

## 8. 更多

- 想自己写脚本 → 看 [canvas-api.md](canvas-api.md)（端点速查 + 常见坑）。
- 关心凭据与作业安全 → 看 [security.md](security.md)。
- 想给本仓库加功能 → 看 [../CONTRIBUTING.md](../CONTRIBUTING.md)。
