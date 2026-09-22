#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canvas REST API 客户端（共享模块）。

这是整个工具包**唯一的网络入口**：其他脚本与 skills 一律复用它，
不要各写一份（重试、翻页、签名 URL、上传这些坑只修一次）。

依赖只有 `requests`，用 uv 或 pip 安装皆可。

凭据优先级（从高到低）：
    1. 构造参数 host=/token=
    2. 环境变量 CANVAS_HOST / CANVAS_API_TOKEN
    3. 仓库根的 `.env` 文件

`.env` 示例见仓库根的 `.env.example`；该文件已被 .gitignore 忽略，永远不要提交。
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

#: 仓库根目录（本文件位于 <root>/scripts/canvas_client.py）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")

#: 默认挂到 Canvas 上的 per_page（上限 100，必须靠 Link 头翻页拿全）
PAGE_SIZE = 100

#: 会把用户文件放进去的目录名（见 AGENTS.md §2）
COURSE_FILES_DIR = "CourseFiles"

#: 网络抖动时的重试次数（连接/读）；401/403/404 这类业务错误不重试
RETRY_TOTAL = 4


# --------------------------------------------------------------------------- #
# 错误类型
# --------------------------------------------------------------------------- #
class CanvasError(Exception):
    """Canvas 返回了业务错误（401/403/404 …），**不要重试**，直接把原因告诉用户。"""

    def __init__(self, status, body):
        self.status = status
        self.body = body
        preview = body if isinstance(body, str) else str(body)
        super().__init__("Canvas API %s: %s" % (status, preview[:300]))

    @property
    def hint(self):
        """给用户的排查提示（CLI 与 skills 直接打印这一句）。"""
        return {
            401: "令牌失效或填错：去 Canvas → 账户 → 设置 → Approved Integrations 重新生成，再更新 .env",
            403: "权限不足：你可能不是这门课的成员，或该课程未开放此端点",
            404: "资源不存在：course_id/assignment_id 可能不对，或该内容被老师隐藏",
        }.get(self.status, "未预期的状态码，请把这条错误原样反馈")


class NotConfigured(RuntimeError):
    """缺少 CANVAS_HOST / CANVAS_API_TOKEN，还没法发请求。"""


# --------------------------------------------------------------------------- #
# 配置读取
# --------------------------------------------------------------------------- #
def load_env(path=ENV_PATH):
    """极简 .env 解析：支持 `export K=V`、引号、`#` 注释。返回 dict。"""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^export\s+", "", line)
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip("\"'")
    return env


def normalize_host(host):
    """把用户写的各种形式统一成 `https://域名`（不带结尾斜杠）。

    Canvas 的 host 有的是 `school.instructure.com`，有的是学校自建域名
    `canvas.example.edu`，还有的带子路径 `/canvas`。这里只做最小归一化。
    """
    host = (host or "").strip().strip("\"'")
    if not host:
        return ""
    if not re.match(r"^https?://", host, re.I):
        host = "https://" + host
    return host.rstrip("/")


def _parse_dt(value):
    """把 Canvas 的 ISO 时间（如 2026-09-03T05:21:00Z）转成 aware datetime。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def make_session():
    """配置好重试的 requests.Session。

    - 连接/读各重试 4 次，指数退避（1s、2s、4s…）
    - 只对 429/5xx 这类「重试就可能好」的状态重试
    - 超时显式设定：本类学校实例常见 60s 卡住，不要用默认无限等
    """
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "canvas-course-toolkit/1.0"})
    return session


# --------------------------------------------------------------------------- #
# 文件名 / 目录名工具（纯函数，可离线单测）
# --------------------------------------------------------------------------- #
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize(name, fallback="untitled"):
    """把任意字符串变成单层、安全的文件名。

    去掉路径分隔符（防止老师把文件命名成 `../../.env` 之类的穿越路径）、
    控制字符、Windows 保留名，并限长。
    """
    name = unicodedata.normalize("NFC", str(name or ""))
    name = name.replace("\\", "/")
    name = name.split("/")[-1]                      # 只取最后一段，杜绝路径穿越
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
    name = re.sub(r'[:*?"<>|]+', "_", name)
    name = name.strip().strip(".")
    if not name:
        return fallback
    stem, dot, ext = name.rpartition(".")
    if dot and stem.upper() in _WIN_RESERVED:
        name = "_" + name
    if len(name) > 180:                             # 留出扩展名
        stem, dot, ext = name.rpartition(".")
        name = stem[:170] + (dot + ext if dot else "")
    return name


def safe_join(dest_dir, relative_path):
    """把相对路径安全地拼到 dest_dir 下，越界（越狱）直接报错。"""
    dest_abs = os.path.abspath(dest_dir)
    parts = [sanitize(p) for p in str(relative_path).replace("\\", "/").split("/") if p]
    target = os.path.abspath(os.path.join(dest_abs, *parts))
    if target != dest_abs and not target.startswith(dest_abs + os.sep):
        raise ValueError("拒绝写出目录之外的路径: %s" % relative_path)
    return target


def course_dir_name(course, prefix_term=False):
    """由课程对象生成目录名，风格 `<课程代码>_<课程名slug>`。

    `CS101 Introduction to Programming (1101)`
        -> `CS101_Introduction_to_Programming`

    不同学校代码形态差异很大，所以先用宽松正则从 name 里抽代码，
    抽不到就退回 Canvas 自带的 course_code。对非英文课程名（全中文等）
    slug 可能偏短，此时用 course_code 兜底，保证目录名非空。
    """
    name = (course.get("name") or "").strip()
    code = (course.get("course_code") or "").strip()
    rest = name

    match = re.match(r"^\s*([A-Za-z]{1,6}[\s-]?\d{2,5}[A-Za-z]?)\s*[:\-–]?\s+(.*)$", name)
    if match:
        code = re.sub(r"[\s-]+", "", match.group(1)).upper()
        rest = match.group(2)
    elif not code:
        code = "course"

    rest = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", rest).strip()  # 去掉结尾 (1101)
    slug = re.sub(r"[^\w]+", "_", rest, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")

    parts = [sanitize(code, "course")]
    if slug:
        parts.append(slug[:80])          # 目录名别太长，兼容 Windows 路径上限
    if prefix_term:
        term = (course.get("term") or {}).get("name") or ""
        term_slug = re.sub(r"[^\w]+", "_", term).strip("_")
        if term_slug:
            parts.insert(0, term_slug[:40])
    return "_".join(parts)


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
class CanvasClient:
    """Canvas REST 客户端。

    用法：
        client = CanvasClient()            # 从环境变量 / .env 读凭据
        me = client.whoami()
        for course in client.courses():
            files, note = client.list_course_files(course["id"])
    """

    def __init__(self, host=None, token=None, env_path=ENV_PATH, timeout=(10, 60)):
        env = load_env(env_path)
        self.host = normalize_host(
            host or os.environ.get("CANVAS_HOST") or env.get("CANVAS_HOST") or ""
        )
        self.token = (
            token or os.environ.get("CANVAS_API_TOKEN") or env.get("CANVAS_API_TOKEN") or ""
        ).strip()
        self.env_path = env_path
        self.timeout = timeout
        if not self.host or not self.token:
            raise NotConfigured(
                "未配置 Canvas 凭据：需要的环境变量是 CANVAS_HOST 与 CANVAS_API_TOKEN。\n"
                "请在仓库根目录创建 .env（可从 .env.example 复制），填好后重试。\n"
                "令牌获取：Canvas → 账户 → 设置 → Approved Integrations → New Access Token。"
            )
        self.base = self.host + "/api/v1"
        self.session = make_session()

    # ---- 底层 HTTP ------------------------------------------------------- #
    @property
    def _headers(self):
        return {"Authorization": "Bearer " + self.token}

    def _check(self, resp):
        """业务错误立刻抛出，不做无意义的退避重试。"""
        if resp.status_code in (401, 403, 404):
            raise CanvasError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise CanvasError(resp.status_code, resp.text)
        return resp

    def get_json(self, path, params=None):
        url = path if path.startswith("http") else self.base + path
        resp = self._check(self.session.get(url, headers=self._headers,
                                           params=params, timeout=self.timeout))
        return resp.json()

    def get_all(self, path, params=None):
        """自动翻页：跟随响应头 `Link: <...>; rel="next"`，直到没有下一页。

        **任何「列出全部 X」都必须走这里。** Canvas 一页最多 100 条，
        只取第一页是最常见的翻车点。
        """
        items = []
        url = path if path.startswith("http") else self.base + path
        query = dict(params or {})
        query.setdefault("per_page", PAGE_SIZE)

        prepared = requests.PreparedRequest()
        prepared.prepare_url(url, query)
        url = prepared.url

        while url:
            resp = self._check(self.session.get(url, headers=self._headers, timeout=self.timeout))
            data = resp.json()
            if not isinstance(data, list):
                raise CanvasError(resp.status_code, "期望列表，实际返回: %s" % str(data)[:200])
            items.extend(data)
            nxt = resp.links.get("next")
            url = nxt["url"] if nxt else None
        return items

    def post_json(self, path, data=None, files=None):
        url = path if path.startswith("http") else self.base + path
        resp = self._check(self.session.post(url, headers=self._headers,
                                            data=data, files=files, timeout=self.timeout))
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    # ---- 账号 / 课程 ------------------------------------------------------ #
    def whoami(self):
        """`GET /users/self` —— 拿自己的 user_id，也是最快的连通性自检。"""
        return self.get_json("/users/self")

    def courses(self, enrollment_state="active", enrollment_type=None):
        """我的课程列表（自动翻页）。

        默认只取 active 的；`enrollment_state=None` 可以拿到全部（含已结束课程）。
        """
        params = {"include[]": "term"}
        if enrollment_state:
            params["enrollment_state"] = enrollment_state
        if enrollment_type:
            params["enrollment_type"] = enrollment_type
        return self.get_all("/courses", params)

    def course(self, course_id, includes=("term", "syllabus_body")):
        params = {"include[]": list(includes)}
        return self.get_json("/courses/%s" % course_id, params)

    def course_with_syllabus(self, course_id):
        """课程详情 + 大纲正文。Canvas 需要重复的 include[] 参数，不能逗号连写。"""
        return self.course(course_id, includes=("term", "syllabus_body"))

    # ---- 课程内容 -------------------------------------------------------- #
    def pages(self, course_id):
        return self.get_all("/courses/%s/pages" % course_id)

    def page(self, course_id, url_or_id):
        return self.get_json("/courses/%s/pages/%s" % (course_id, url_or_id))

    def announcements(self, course_id):
        """公告：公告本质是 discussion topic，用 only_announcements=1 过滤。"""
        return self.get_all("/courses/%s/discussion_topics" % course_id,
                            {"only_announcements": 1})

    def announcement(self, course_id, topic_id):
        return self.get_json("/courses/%s/discussion_topics/%s" % (course_id, topic_id))

    def modules(self, course_id, include_items=True):
        params = {"include[]": "items"} if include_items else None
        return self.get_all("/courses/%s/modules" % course_id, params)

    def assignments(self, course_id, bucket=None):
        """作业列表。`bucket="upcoming"` 可只看近期（配合 due_at 排序）。"""
        params = {"include[]": ["submission", "due_dates"]}
        if bucket:
            params["bucket"] = bucket
        return self.get_all("/courses/%s/assignments" % course_id, params)

    def assignment(self, course_id, assignment_id):
        return self.get_json("/courses/%s/assignments/%s" % (course_id, assignment_id))

    def assignment_groups(self, course_id):
        return self.get_all("/courses/%s/assignment_groups" % course_id)

    def submissions(self, course_id, assignment_id, user_id="self"):
        """我的提交记录（含分数、评语）。"""
        return self.get_json(
            "/courses/%s/assignments/%s/submissions/%s" % (course_id, assignment_id, user_id),
            {"include[]": "submission_history"},
        )

    # ---- 文件 ------------------------------------------------------------ #
    def folder_map(self, course_id):
        """folder_id -> 相对路径，用来把 Canvas 的扁平文件列表还原成层级。"""
        try:
            folders = self.get_all("/courses/%s/folders" % course_id)
        except CanvasError:
            return {}
        return {f.get("id"): (f.get("full_name") or "").lstrip("/") for f in folders}

    def course_files(self, course_id):
        """`GET /courses/:id/files` + 用 folders 还原相对路径。

        返回的每个 dict 上额外挂了：
            _dir  相对目录
            _rel  相对路径（目录 + 文件名）
        """
        files = self.get_all("/courses/%s/files" % course_id)
        # 过滤 PowerPoint/Office 的 `~$` 锁文件、macOS 的 .DS_Store 之类垃圾
        files = [f for f in files
                 if not (f.get("display_name") or "").startswith("~$")
                 and (f.get("display_name") or "") not in (".DS_Store", "Thumbs.db")]
        folders = self.folder_map(course_id)
        for item in files:
            item["_dir"] = folders.get(item.get("folder_id"), "")
            item["_rel"] = os.path.join(item["_dir"], sanitize(item.get("display_name")))
        return files

    def files_from_page_links(self, course_id):
        """回退方案：`/courses/:id/files` 被禁（403）时，改从正文里捞附件。

        很多课程的页面/公告/作业描述里会插入附件链接，形如
        `<a href="/courses/<id>/files/<file_id>?...">名字.pdf</a>`。
        列表端点没权限，但**单个 `GET /files/:id` 往往仍可读**，
        于是照样能把课件捞下来。返回结构与 `course_files` 一致。
        """
        folders = self.folder_map(course_id)
        found = {}

        def harvest(body, source):
            if not body:
                return
            for match in re.finditer(
                r'<a[^>]+href="([^"]*?/files/(\d+)[^"]*)"[^>]*>(.*?)</a>',
                body, flags=re.S | re.I,
            ):
                _, fid, text = match.group(1), int(match.group(2)), match.group(3)
                label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
                found.setdefault(fid, {"id": fid, "_label": label, "_source": source})
            for match in re.finditer(r'href="([^"]*?/files/(\d+)[^"]*)"', body, flags=re.I):
                found.setdefault(int(match.group(2)),
                                 {"id": int(match.group(2)), "_label": "", "_source": source})

        for page in self.pages(course_id):
            try:
                body = (self.page(course_id, page.get("url")) or {}).get("body")
            except CanvasError:
                continue
            harvest(body, "页面 %s" % page.get("url"))

        for ann in self.announcements(course_id):
            try:
                body = (self.announcement(course_id, ann.get("id")) or {}).get("message")
            except CanvasError:
                continue
            harvest(body, "公告 %s" % ann.get("title"))

        for assignment in self.assignments(course_id):
            harvest(assignment.get("description"), "作业 %s" % assignment.get("name"))

        files = []
        for fid, meta in sorted(found.items()):
            try:
                info = self.file_info(fid)
            except CanvasError as exc:
                meta["_err"] = "HTTP %s" % exc.status
                meta["_rel"] = sanitize(meta.get("_label") or ("file_%s" % fid))
                files.append(meta)
                continue
            info["_dir"] = folders.get(info.get("folder_id"), "")
            info["_rel"] = os.path.join(info["_dir"], sanitize(info.get("display_name")))
            info["_source"] = meta.get("_source", "")
            if meta.get("_label"):
                info["_label"] = meta["_label"]
            files.append(info)
        return files

    def list_course_files(self, course_id):
        """统一的「列文件」入口：优先 `/files`；403 时自动回退正文链接。

        返回 `(files, note)`；note 非空时必须转告用户，说明清单来源是回退方案。
        """
        try:
            return self.course_files(course_id), ""
        except CanvasError as exc:
            if exc.status != 403:
                raise
            files = self.files_from_page_links(course_id)
            note = "文件列表端点返回 403，已回退为「页面/公告/作业正文链接」清单（%d 个）" % len(files)
            return files, note

    def file_info(self, file_id):
        """单个文件元信息 —— 里面的 `url` 带签名且**会过期**，
        所以下载前要重新取一次，不要缓存 URL。"""
        return self.get_json("/files/%s" % file_id)

    def download_file(self, file_id, dest_dir, dry_run=False):
        """下载单个文件到 dest_dir。**幂等**：已存在且大小、修改时间都没变就跳过。

        本地 mtime 会被设成远端的 `updated_at`，这样老师更新了课件、
        本地 mtime 落后时能自动重下。

        返回 `(downloaded: bool, path: str)`；dry_run=True 时只判断并返回路径。
        """
        info = self.file_info(file_id)
        name = info.get("display_name") or info.get("filename") or ("file_%s" % file_id)
        path = os.path.join(dest_dir, sanitize(name))
        size = info.get("size")
        updated = _parse_dt(info.get("updated_at"))

        if os.path.exists(path):
            same_size = size is None or os.path.getsize(path) == size
            fresh = updated is None or os.path.getmtime(path) >= updated.timestamp()
            if same_size and fresh:
                return (False, path)
        if dry_run:
            return (False, path)

        url = info.get("url")
        if not url:
            raise CanvasError("nourl", "文件 %s 没有可用下载地址" % file_id)
        os.makedirs(dest_dir, exist_ok=True)
        # 先写临时文件再改名：中途断网不会留下半截文件冒充"已下载"
        tmp_path = path + ".part"
        with self.session.get(url, stream=True, timeout=(10, 120)) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        fh.write(chunk)
        os.replace(tmp_path, path)
        if updated is not None:
            os.utime(path, (time.time(), updated.timestamp()))
        return (True, path)

    # ---- 上传 / 提交 ------------------------------------------------------ #
    def upload_file(self, local_path, parent_folder_path="submissions"):
        """把本地文件上传到「我的文件」区，返回 Canvas 的 file 对象。

        Canvas 提交作业必须走两步：先上传拿 file_id，再把 file_id 挂到提交上。
        这里是第 1 步（`POST /users/self/files` → 签名 upload_url → multipart POST）。
        """
        local_path = os.path.abspath(local_path)
        if not os.path.isfile(local_path):
            raise FileNotFoundError("找不到要上传的文件: %s" % local_path)
        fname = os.path.basename(local_path)
        size = os.path.getsize(local_path)

        slot = self.post_json("/users/self/files", data={
            "name": fname,
            "parent_folder_path": parent_folder_path,
            "size": size,
            "content_type": "application/octet-stream",
        })
        upload_url = slot.get("upload_url")
        if not upload_url:
            raise CanvasError("upload", "Canvas 未返回 upload_url: %s" % str(slot)[:200])

        # upload_params 里带签名，必须原样带上；文件字段名固定为 `file`
        params = slot.get("upload_params") or {}
        with open(local_path, "rb") as fh:
            files = {"file": (fname, fh, "application/octet-stream")}
            resp = self._check(self.session.post(upload_url, data=params, files=files,
                                                 timeout=(10, 600)))
        try:
            result = resp.json()
        except ValueError:
            # 部分实例上传成功但返回空体，这时按 file_id 回查
            location = resp.headers.get("Location") or ""
            match = re.search(r"/files/(\d+)", location)
            if not match:
                raise CanvasError(resp.status_code, "上传响应无法解析: %s" % resp.text[:200])
            return self.file_info(int(match.group(1)))
        return result

    def submit_online_upload(self, course_id, assignment_id, file_ids):
        """把已上传的 file_id 提交到作业上（第 2 步）。

        **这是不可逆动作**：会真的产生/覆盖提交记录，调用前必须让用户确认。
        """
        ids = [int(i) for i in (file_ids if isinstance(file_ids, (list, tuple)) else [file_ids])]
        data = [("submission[submission_type]", "online_upload")]
        data += [("submission[file_ids][]", str(i)) for i in ids]
        return self.post_json(
            "/courses/%s/assignments/%s/submissions" % (course_id, assignment_id), data=data)


# --------------------------------------------------------------------------- #
# MANIFEST.md（增量同步清单）
# --------------------------------------------------------------------------- #
def write_manifest(course, files, dest, note="", page_count=None, now=None):
    """在课程目录写/更新 `MANIFEST.md`：记录课程 ID、同步时间、文件清单与本地状态。

    它是「幂等重跑」的依据：下次同步前先看这里，就知道哪些已下载、哪些当时失败。
    """
    os.makedirs(dest, exist_ok=True)
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    term = (course.get("term") or {}).get("name", course.get("enrollment_term_id"))

    lines = [
        "# MANIFEST — %s" % course.get("name"),
        "",
        "- 课程 ID: %s" % course.get("id"),
        "- 学期: %s" % term,
        "- 最近同步: %s" % now,
        "- 课程目录: %s" % dest,
    ]
    if note:
        lines.append("- 备注: %s" % note)
    if page_count is not None:
        lines.append("- 页面数: %s" % page_count)
    lines.append("")

    if files is None:
        lines += ["## 文件清单", "", "（该课程未开放文件列表，未能列出）", ""]
    else:
        lines += [
            "## 文件清单", "",
            "| 文件ID | 文件名 | 大小(bytes) | 最近修改(updated_at) | 路径 | 状态 |",
            "|---|---|---|---|---|---|",
        ]
        for item in files:
            rel = item.get("_rel") or "untitled"
            status = "本地" if os.path.exists(os.path.join(dest, rel)) else "未下载"
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                item.get("id"), item.get("display_name"), item.get("size"),
                (item.get("updated_at") or "")[:19], rel, status))
    lines += ["", "---", "*由 `scripts/canvas_client.py` 生成，可反复重跑刷新。*"]

    out = os.path.join(dest, "MANIFEST.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out


def host_label(host):
    """从 host 里取个短名字用于日志（不含 token，安全）。"""
    try:
        return urlparse(normalize_host(host)).netloc or "(未配置)"
    except Exception:
        return "(未配置)"
