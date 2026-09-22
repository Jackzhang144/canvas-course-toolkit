---
name: canvas-init-setup
description: 首次使用或配置不完整时，先检测 Canvas 初始化状态，再一步步引导用户配好 CANVAS_HOST 与访问令牌；只有凭据齐备才继续后面的下载/看作业/提交。
whenToUse: 用户第一次使用本工具包、说「怎么开始」「初始化」「配置」「用不了」「报错说没配置凭据」，或任何 Canvas 操作在检查阶段发现凭据缺失时使用。
---

# 初始化 Canvas 配置

**先检测、再引导、不替用户猜。** 目标是把用户带到"凭据齐备、`doctor` 通过"的状态，
然后交给对应的 skill（下载 / 看截止 / 交作业）。

## 一、先检测（不要一上来就让用户去改文件）

```bash
uv run canvas init --check
```

它是**只读**的：不联网、不创建、不修改任何文件，可以安全反复运行。
输出里的 `初始化状态` 就是唯一权威判断：

| 状态 | 含义 | 你要做的 |
|---|---|---|
| `no_env` | 还没有 `.env` | 走第二步创建 |
| `missing_host` | `CANVAS_HOST` 空着 | 问用户学校 Canvas 网址，告诉他填哪一行 |
| `host_looks_wrong` | host 里带了 `/api/v1` 或具体页面路径 | 让他只留域名部分 |
| `missing_token` | `CANVAS_API_TOKEN` 空着 | 按第三步引导拿令牌 |
| `token_placeholder` | 令牌位还是模板占位符 | 让他换成真令牌（常见错误：复制了 `.env.example` 的说明文字） |
| `ready` | 配置齐全 | 直接跑 `uv run canvas doctor` 验证，成功即结束本 skill |

## 二、需要创建 `.env` 时

```bash
uv run canvas init
```

它**幂等且不破坏**：文件不存在才创建（权限 600）；已存在就一个字节都不改；
只缺 `CANVAS_HOST`/`CANVAS_API_TOKEN` 两个键时，只追加这两行（原有内容照旧）。
**绝不要手动覆盖用户已有的 `.env`**——里面可能有他刚拿到的令牌。

## 三、引导用户拿令牌（要讲清楚，别看他自己会不会）

告诉用户：

1. 浏览器登录 Canvas；
2. 点右上角头像 → **Account / 账户**；
3. 左侧 **Settings / 设置**；
4. 往下找 **Approved Integrations** → **+ New Access Token**；
5. Purpose 随便写（如 `course-toolkit`），Generate；
6. **立刻复制**那一串——它只显示这一次。

然后让他把它填进 `.env` 的 `CANVAS_API_TOKEN="..."`。
⚠️ 必须说明：**令牌等于密码**，不要贴进聊天群、不要提交到 git、不要截图；
疑似泄露就去同一页面 **Delete/Revoke** 后重新生成。

自建实例（老版本 Canvas）这个入口位置可能不同，让他用页面搜索找 "Access Token"，
找不到就参照 `docs/setup.md` 第 3 节，**不要凭空给他一个 URL**。

## 四、收尾验证

```bash
uv run canvas init --check     # 期望：初始化状态：已就绪（ready）
uv run canvas doctor           # 期望：身份、课程数、页面/作业/公告/文件权限都打出来
```

- `doctor` 通过 = 全流程可用，可以进入下载/看截止/交作业。
- `doctor` 报 **401**：令牌失效或填错，回到第三步重新生成（**不要反复重试**）。
- `doctor` 报 **403**：他能登录，但不是某些课程的成员；换一门自己的课再试。
- 网络超时/TLS 中断：客户端已自动重试 4 次；仍失败就让他过几分钟再来。

## 五、常见用户疑问

- **"我的学校不是 instructure.com"**：能用于任何自建 Canvas 实例，填学校域名即可（自动补 `https://`）。
- **"一定要用 uv 吗"**：不一定，`requirements.txt` + `python -m scripts.cli ...` 等价，
  例如 `python -m scripts.cli init --check`。详见 `docs/setup.md`。
- **"会不会把令牌传到哪去"**：不会。全部在本机运行，令牌只从 `.env`/环境变量读，
  只用于请求用户自己的 Canvas 实例。

## 不要做的事

- 不要在没检测前就让用户改配置——他可能只差一个键，或其实已经配好了。
- 不要用 `cat .env` 把令牌打印到对话或日志里；要看内容就用 `canvas init --check`
  （它只报告状态和令牌长度，不回显令牌本身）。
- 不要在 `.env` 里硬编码或替用户编造一个令牌；令牌只能由用户自己生成。
- 配置未就绪时**不要**继续执行下载/提交：先让本 skill 走完。
