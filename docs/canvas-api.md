# Canvas REST API 速查（自己写脚本时看）

Canvas 的 REST API 是公开、稳定、有官方文档的，但坑不少。这份速查只记**实际会用到的端点与真实踩过的坑**，
配合 `scripts/canvas_client.py` 使用——那里已经把这些坑都封装好了。

官方文档（以它为准，本文件可能滞后）：
- REST 总览：<https://developerdocs.instructure.com/services/canvas/rest>
- 全部资源列表：<https://canvas.instructure.com/doc/api/all_resources.html>

> 部分学校自建实例**不开放** `/doc/api`（返回 404），别指望它，直接看上面的官方站点。

---

## 基本约定

```bash
BASE="https://<你的Canvas域名>/api/v1"
curl -H "Authorization: Bearer $CANVAS_API_TOKEN" "$BASE/users/self"
```

- 认证：请求头 `Authorization: Bearer <token>`（不要用 `?access_token=`，那会写进日志）。
- 响应是 JSON；出错时返回 `{"errors": [...]}` 加一个 HTTP 状态码。
- 状态码含义：
  | 码 | 含义 | 要不要重试 |
  |---|---|---|
  | 401 | 令牌无效/过期 | ❌ 重新生成令牌 |
  | 403 | 无权限（非课程成员、端点未开放） | ❌ 换思路或放弃该端点 |
  | 404 | 资源不存在或被隐藏 | ❌ 检查 ID |
  | 429 | 触发限流 | ✅ 退避后重试 |
  | 5xx | 服务端/网关问题 | ✅ 指数退避重试 |

## 分页（最容易翻车的地方）

Canvas 默认一页 **10** 条，最大 `per_page=100`。**返回头里有 `Link` 关系链**：

```
Link: <https://.../courses?page=2&per_page=100>; rel="next", <...>; rel="last"
```

必须循环跟随 `rel="next"` 直到没有为止，否则你只会拿到前 10 条而毫无察觉。
`CanvasClient.get_all()` 做的就是这件事：

```python
from scripts.canvas_client import CanvasClient
client = CanvasClient()
courses = client.courses()          # 自动翻页，返回全部
```

## 端点速查

`{cid}` = course_id，`{aid}` = assignment_id，`{fid}` = file_id。

| 目的 | 端点 | 备注 |
|---|---|---|
| 我的信息 | `GET /users/self` | 拿自己的 `id`，最快的连通性自检 |
| 我的课程 | `GET /courses?enrollment_state=active` | 返回 `{id, name, course_code, term}`；加 `enrollment_type=student` 只取学生身份 |
| 课程详情 | `GET /courses/{cid}?include[]=term&include[]=syllabus_body` | **`include[]` 必须重复写，逗号连写不生效** |
| 模块 | `GET /courses/{cid}/modules?include[]=items` | 就是左侧"课程模块"那条学习路径 |
| 模块项 | `GET /courses/{cid}/modules/{mid}/items` | `type` 可能是 File/Assignment/Page/Quiz/ExternalUrl |
| 全部文件 | `GET /courses/{cid}/files` | **扁平列表**，靠 `folder_id` 才能还原目录层级 |
| 文件夹 | `GET /courses/{cid}/folders` | `full_name` 就是相对路径，可用来建目录树 |
| 单文件 | `GET /files/{fid}` | 返回带签名的 `url`，**会过期**，下载前重新取 |
| 作业列表 | `GET /courses/{cid}/assignments?include[]=submission&include[]=due_dates` | 加 `bucket=upcoming` 看近期 |
| 作业详情 | `GET /courses/{cid}/assignments/{aid}` | 看 `submission_types` 决定能不能在线交 |
| 我的提交 | `GET /courses/{cid}/assignments/{aid}/submissions/self?include[]=submission_history` | 查分数/评语/提交时间 |
| 交作业 | `POST /courses/{cid}/assignments/{aid}/submissions` | 见下面两步流程 |
| 公告 | `GET /courses/{cid}/discussion_topics?only_announcements=1` | 公告就是 discussion topic |
| 单个公告 | `GET /courses/{cid}/discussion_topics/{tid}` | 正文在 `message` 字段 |
| 页面 | `GET /courses/{cid}/pages` | `GET /courses/{cid}/pages/{url}` 拿 `body` |
| 上传文件 | `POST /users/self/files` | 两步提交的第 1 步 |

## 下载文件：签名 URL 会过期

```
GET /files/{fid}  →  { "url": "https://...verifier=...", "display_name": "...", "size": 12345,
                       "updated_at": "2026-01-02T03:04:05Z" }
```

- 那个 `url` 带签名且**有时效**，缓存起来过一会儿就 403 了：每次下载前重新 `GET /files/{fid}`。
- 增量同步的判断依据：`display_name` + `size` + `updated_at`。
  本地文件 mtime 设成远端 `updated_at`，下次就能判断"老师更新了课件"。
- 下载时先写 `.part` 再 `os.replace()` 改名，避免断网留下半截文件被当成"已下载"。

## 权限不够时的回退（很实用）

有些课程的 `GET /courses/{cid}/files` 直接 **403**（老师没开文件列表权限），
但下面这些仍然可用：

- `GET /courses/{cid}/folders`（文件夹结构）；
- `GET /courses/{cid}/pages`、公告正文；
- `GET /files/{fid}`（**单个**文件信息）。

而老师插在页面/公告/作业描述里的附件，HTML 形如：

```html
<a href="/courses/833/files/161540?verifier=...&wrap=1" data-api-endpoint="...">PS1 题面.pdf</a>
```

**从 HTML 里正则捞出 `/files/(\d+)` 拿到 file_id，再逐个 `GET /files/{fid}` 下载**——
列表端点没权限，单文件往往有权限，于是课件照样能同步。`CanvasClient.list_course_files()`
自动做这个回退，`MANIFEST.md` 里会标注来源。

拿不到的情况：正文里完全没有链接的"裸文件"（老师直接上传到 Files 但没在任何页面引用），
这属于权限限制，让使用者从网页手动下载。

## 交作业：必须两步

Canvas **不接受**"把本地路径指给它"，必须先上传到个人文件区、再挂到提交上：

```bash
# 第 1 步：申请上传位置（签名 URL 短时有效）
curl -X POST "$BASE/users/self/files" \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=solution.pdf" -F "parent_folder_path=submissions" \
  -F "size=$(stat -f%z solution.pdf)" -F "content_type=application/pdf"
# → {"upload_url": "...", "upload_params": {...}}

# 第 2 步：multipart 上传到 upload_url（upload_params 原样带上，文件字段名固定为 file）
curl -X POST "<upload_url>" -F "key=..." -F "policy=..." ... -F "file=@solution.pdf"
# → {"id": 987654, ...}  这个 id 就是 file_id

# 第 3 步：把 file_id 挂到提交上
curl -X POST "$BASE/courses/{cid}/assignments/{aid}/submissions" \
  -H "Authorization: Bearer $TOKEN" \
  -d "submission[submission_type]=online_upload" \
  -d "submission[file_ids][]=987654"
```

要点：
- 先读作业的 `submission_types`：不含 `online_upload` 就别硬传（可能是纸质提交、外部工具或只是打分项）；
- `upload_params` 里是签名，**必须原样**回传，字段顺序无所谓但一个都不能少；
- 有些实例上传成功却返回空响应体，此时从响应头 `Location: .../files/123` 里取 `file_id`；
- 提交是不可逆动作，重复提交会覆盖上一次记录（`attempt` +1），脚本要先读已有提交再确认。

## 其它坑

- **别用 `?access_token=`**：URL 会进服务器日志/浏览器历史/代理缓存。一律用 Bearer 头。
- **加 User-Agent**：有些学校的 WAF 会拦没有 UA 的脚本请求。
- **限流礼貌**：串行请求 + 失败退避；不要一上来就开 20 个线程把学校服务器打挂。
- **老 Quiz 端点**：`/quizzes` 正被 "New Quizzes"（LTI 工具）取代，部分实例 REST 查不到，属正常。
- **Canvas 的"考试"也是 assignment**：`due_at` 里出现的 quiz/exam 往往就是考试时间。
- **时区**：API 返回的 `due_at` 是 UTC（带 `Z`），显示给用户时要转本地时间。

## 直接读源码

想改行为，改这几处就够：

| 文件 | 作用 |
|---|---|
| `scripts/canvas_client.py` | 唯一网络入口：`get_json` / `get_all`（翻页）/ `download_file`（幂等）/ `upload_file` + `submit_online_upload` |
| `scripts/course_summary.py` | 大纲解析与 README 生成；顶部 `SECTION_*` / `GROUP_KEYWORDS` / `PERCENT_PATTERN` 是适配别的语言用的可调常量 |
| `scripts/cli.py` | `canvas` 各子命令 |
| `scripts/submit.py` | 两步提交与提交前自检 |

改完跑一遍离线自测（不联网）：

```bash
uv run --dev pytest
```
