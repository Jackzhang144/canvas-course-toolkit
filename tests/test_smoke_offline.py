# -*- coding: utf-8 -*-
"""端到端冒烟测试：起一个**假的 Canvas 服务器**，把整条命令链跑一遍。

不联网、不需要真令牌，因此在 CI 和任何人的机器上都能跑。覆盖：

  doctor → courses → files → download（含 403 回退、幂等重跑）→ deadlines

跑法：
    uv run --dev pytest tests/test_smoke_offline.py
    python tests/test_smoke_offline.py          # 不装 pytest 也能跑
"""
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COURSE_ID = 12345
ASSIGNMENT_ID = 67890
FILE_PDF = 550011
FILE_LOCK = 550012          # 模拟 PowerPoint 的 ~$ 锁文件，必须被过滤掉

PDF_BYTES = b"%PDF-1.4\nfake lecture slides\n%%EOF\n"
LOCK_BYTES = b"lock"

BASE = "http://127.0.0.1:%d"


def _page(items, per_page):
    """按 Canvas 的方式分页：一次给 per_page 条，其余由 Link 头翻页。"""
    return items[:per_page]


class FakeCanvas(BaseHTTPRequestHandler):
    """只实现冒烟测试需要的几个端点，行为尽量贴近真实 Canvas。"""

    protocol_version = "HTTP/1.1"
    hits = []               # 记录请求路径，供断言使用

    def log_message(self, *args):   # 静音
        pass

    # ---- 工具 ----
    def _json(self, payload, links=None, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if links:
            self.send_header("Link", links)
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth_ok(self):
        if self.headers.get("Authorization") != "Bearer test-token":
            self._json({"errors": ["invalid token"]}, status=401)
            return False
        return True

    # ---- 路由 ----
    def do_GET(self):                                        # noqa: N802
        path, _, query = self.path.partition("?")
        FakeCanvas.hits.append(path)
        # 下载地址是带签名的临时 URL，真实 Canvas 不会再要 Bearer 头，这里保持一致
        if not path.endswith("/download") and not path.startswith("/files/"):
            if not self._auth_ok():
                return
        base = "/api/v1"

        if path == base + "/users/self":
            return self._json({"id": 1650, "name": "ZHANG San"})

        if path == base + "/courses":
            per_page = int(re.search(r"per_page=(\d+)", query).group(1)) if "per_page" in query else 10
            courses = [{"id": COURSE_ID, "name": "CS101 Introduction to Programming",
                        "course_code": "CS101", "term": {"name": "2025 Fall"}},
                       {"id": 12346, "name": "MATH101 Calculus I",
                        "course_code": "MATH101", "term": {"name": "2025 Fall"}}]
            first = _page(courses, per_page)
            links = None
            if len(first) < len(courses):
                # 触发第二页：验证 get_all 真的会翻页
                links = '<%s%s?page=2&per_page=%d>; rel="next"' % (self.server.url, base + "/courses", per_page)
            return self._json(first, links=links)

        if path == "%s/courses/%d" % (base, COURSE_ID):
            return self._json({
                "id": COURSE_ID, "name": "CS101 Introduction to Programming",
                "course_code": "CS101", "term": {"name": "2025 Fall"},
                "syllabus_body": "<p>Course Description</p><p>Learn to program in Python.</p>"
                                 "<p>Assessment</p><p>Assignments\n30%</p><p>Final\n70%</p>"
                                 "<p>5. Group Project</p><p>Form groups of 3 to 4 members.</p>",
            })

        if path == "%s/courses/%d/pages" % (base, COURSE_ID):
            return self._json([{"url": "week1", "title": "Week 1"}])

        if path == "%s/courses/%d/pages/week1" % (base, COURSE_ID):
            # 正文里挂着附件链接 —— 这是 403 回退方案的数据来源
            return self._json({
                "title": "Week 1",
                "html_url": "%s/courses/%d/pages/week1" % (self.server.url, COURSE_ID),
                "body": '<p>Slides: <a href="/courses/%d/files/%d?verifier=abc&wrap=1">'
                        'Lecture01.pdf</a></p>' % (COURSE_ID, FILE_PDF),
            })

        if path == "%s/courses/%d/discussion_topics" % (base, COURSE_ID):
            return self._json([{"id": 1, "title": "Group Project Team Registration"}])

        if path == "%s/courses/%d/discussion_topics/1" % (base, COURSE_ID):
            return self._json({"id": 1, "title": "Group Project Team Registration",
                               "posted_at": "2025-09-10T02:00:00Z",
                               "message": "<p>Register your team by Friday of Week 6.</p>"})

        if path == "%s/courses/%d/assignments/%d" % (base, COURSE_ID, ASSIGNMENT_ID):
            return self._json({"id": ASSIGNMENT_ID, "name": "HW1 - Variables",
                               "points_possible": 100,
                               "submission_types": ["online_upload"],
                               "due_at": "2099-09-20T15:59:00Z"})

        if path == "%s/courses/%d/assignment_groups" % (base, COURSE_ID):
            return self._json([{"id": 1, "name": "Assignments", "group_weight": 30.0}])

        if path == "%s/courses/%d/assignments" % (base, COURSE_ID):
            return self._json([
                # 三态各一个：未提交 / 已提交 / 已评分 —— 顺带验证状态标签不会串
                {"id": ASSIGNMENT_ID, "name": "HW1 - Variables", "points_possible": 100,
                 "submission_types": ["online_upload"],
                 "due_at": "2099-09-20T15:59:00Z", "description": "",
                 "submission": {"submitted_at": None, "workflow_state": "unsubmitted"}},
                {"id": 67891, "name": "Midterm Exam", "points_possible": 100,
                 "submission_types": ["on_paper"],
                 "due_at": "2099-10-20T01:59:00Z", "description": "",
                 "submission": {"submitted_at": "2099-10-19T02:00:00Z",
                                "workflow_state": "submitted"}},
                {"id": 67892, "name": "HW2 - Loops", "points_possible": 100,
                 "submission_types": ["online_upload"],
                 "due_at": "2099-10-25T15:59:00Z", "description": "",
                 "submission": {"submitted_at": "2099-10-24T01:00:00Z",
                                "graded_at": "2099-10-30T01:00:00Z",
                                "workflow_state": "graded"}},
                # 没有 submission 字段：必须显示「状态未知」，不能冒充「未提交」
                {"id": 67893, "name": "HW3 - Files", "points_possible": 100,
                 "submission_types": ["online_upload"],
                 "due_at": "2099-10-30T15:59:00Z", "description": ""},
            ])

        if path == "%s/courses/%d/folders" % (base, COURSE_ID):
            return self._json([{"id": 7, "full_name": "course files/Week1"}])

        # 关键：文件列表端点一律 403，逼出回退逻辑
        if path == "%s/courses/%d/files" % (base, COURSE_ID):
            return self._json({"errors": ["forbidden"]}, status=403)

        if path == "%s/courses/%d/assignments/%d/submissions/self" % (base, COURSE_ID, ASSIGNMENT_ID):
            return self._json({"id": 1, "submitted_at": None, "attempt": None,
                               "workflow_state": "unsubmitted", "score": None})

        if path == base + "/files/%d" % FILE_PDF:
            return self._json({"id": FILE_PDF, "display_name": "Lecture01.pdf", "size": len(PDF_BYTES),
                               "folder_id": 7, "updated_at": "2025-09-01T03:00:00Z",
                               "url": "%s/files/%d/download" % (self.server.url, FILE_PDF)})

        if path == base + "/files/%d" % FILE_LOCK:
            return self._json({"id": FILE_LOCK, "display_name": "~$Lecture01.pdf", "size": len(LOCK_BYTES),
                               "folder_id": 7, "updated_at": "2025-09-01T03:00:00Z",
                               "url": "%s/files/%d/download" % (self.server.url, FILE_LOCK)})

        if path == "/files/%d/download" % FILE_PDF:
            return self._raw(PDF_BYTES)

        return self._json({"errors": ["not found: %s" % path]}, status=404)

    # ---- 上传 / 提交（第 1、2 步）----
    def do_POST(self):                                       # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path.split("?")[0]
        FakeCanvas.hits.append("POST " + path)
        base = "/api/v1"

        if path == base + "/users/self/files":
            # 第 1 步：返回带签名的上传地址与参数
            payload = json.dumps({"upload_url": "%s/uploads/abc" % self.server.url,
                                  "upload_params": {"key": "%s/files/160000" % self.server.url,
                                                    "policy": "signed-policy",
                                                    "signature": "sig"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/uploads/abc":
            # 第 2 步：multipart 上传。真实 Canvas 走完这步返回文件对象。
            assert b"file" in body and b"PDF" in body.replace(b"application/pdf", b"PDF"), \
                "multipart 里必须带着文件内容"
            FakeCanvas.uploaded = body
            payload = json.dumps({"id": 160000, "display_name": "solution.pdf",
                                  "size": len(PDF_BYTES)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "%s/courses/%d/assignments/%d/submissions" % (base, COURSE_ID, ASSIGNMENT_ID):
            FakeCanvas.submission_body = body.decode("utf-8", "replace")
            payload = json.dumps({"submission": {"submitted_at": "2099-01-01T00:00:00Z",
                                                 "attempt": 1, "workflow_state": "submitted"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        return self._json({"errors": ["not found: %s" % path]}, status=404)


class FakeServer:
    """上下文管理器：起服务器、给出 client，退出时关掉。"""

    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeCanvas)
        self.httpd.url = BASE % self.httpd.server_address[1]      # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def url(self):
        return self.httpd.url                                        # type: ignore[attr-defined]

    def client(self):
        from scripts.canvas_client import CanvasClient
        return CanvasClient(host=self.url, token="test-token")


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #
def test_end_to_end(tmp_path=None):
    import tempfile

    from scripts import canvas_client as cc
    from scripts import cli

    FakeCanvas.hits = []
    tmp = tempfile.mkdtemp()
    cwd = os.getcwd()
    os.chdir(tmp)                       # 让 COURSE_FILES_DIR 落在临时目录，别污染仓库
    try:
        with FakeServer() as server:
            client = server.client()

            # 1) 自检链路
            assert client.whoami()["name"] == "ZHANG San"
            assert cli.cmd_doctor(client) == 0

            # 2) 翻页：courses 必须拿全 2 门（per_page=100 一次就够）
            courses = client.courses()
            assert [c["id"] for c in courses] == [COURSE_ID, 12346]

            # 3) 目录命名
            assert cc.course_dir_name(courses[0]) == "CS101_Introduction_to_Programming"

            # 4) 403 回退：文件列表走页面链接
            files, note = client.list_course_files(COURSE_ID)
            assert "403" in note and "回退" in note, note
            assert [f["id"] for f in files] == [FILE_PDF]
            assert files[0]["_dir"] == "course files/Week1"

            # 5) 下载 + 幂等重跑
            assert cli.cmd_download(client, str(COURSE_ID)) == 0
            target = os.path.join("CourseFiles", "CS101_Introduction_to_Programming",
                                  "course files", "Week1", "Lecture01.pdf")
            assert os.path.isfile(target), "文件应当已下载到 %s" % target
            with open(target, "rb") as fh:
                assert fh.read() == PDF_BYTES

            mtime = os.path.getmtime(target)
            assert cli.cmd_download(client, str(COURSE_ID)) == 0     # 重跑不该报错
            assert os.path.getmtime(target) == mtime, "内容未变时不应重下"

            # 6) 锁文件必须被过滤：清单里不能出现 ~$
            manifest = open(os.path.join("CourseFiles", "CS101_Introduction_to_Programming",
                                         "MANIFEST.md"), encoding="utf-8").read()
            assert "~$" not in manifest
            assert "Lecture01.pdf" in manifest
            assert "本地" in manifest

            # 7) course_summary 生成 README，并解析出评分占比与组队要求
            cli_summary = __import__("scripts.course_summary", fromlist=["x"])
            from scripts import course_summary as cs
            cs.process_course(client, COURSE_ID)
            readme = open(os.path.join("CourseFiles", "CS101_Introduction_to_Programming",
                                       "README.md"), encoding="utf-8").read()
            assert "Assignments：30%" in readme
            assert "Final：70%" in readme
            assert "3 to 4 members" in readme
            assert "Group Project Team Registration" in readme
            assert os.path.isfile(os.path.join("CourseFiles", "CS101_Introduction_to_Programming",
                                               "syllabus.md"))

            # 8) 索引
            cs.rebuild_index(client)
            index = open("COURSES.md", encoding="utf-8").read()
            assert "CS101_Introduction_to_Programming" in index
            assert "Assignments 30%" in index

            # 9) deadlines：要带「交没交」的状态，且读不到状态时不得冒充未提交
            assert cli.cmd_deadlines(client, days=30) == 0

            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_deadlines(client, days=40000)     # 放宽时间窗，确保四项都进来
            table = buf.getvalue()
            assert "未提交" in table, table
            assert "已提交 2099-10-19" in table, table
            assert "已评分" in table, table
            assert "状态未知" in table, table
            # 状态未知的那一项不能被算成未提交
            unknown_line = [l for l in table.splitlines() if "HW3 - Files" in l]
            assert unknown_line and "状态未知" in unknown_line[0], unknown_line
    finally:
        os.chdir(cwd)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_submit_two_step_upload(tmp_path=None):
    """验证提交作业的两步流程：上传拿 file_id → 把 file_id 挂到 submission 上。

    只打本地假服务器，绝不接触真 Canvas。
    """
    import tempfile

    from scripts import canvas_client as cc
    from scripts import submit as submit_cmd

    FakeCanvas.uploaded = None
    FakeCanvas.submission_body = None
    tmp = tempfile.mkdtemp()
    cwd = os.getcwd()
    os.chdir(tmp)
    # submit_cmd.main 内部自己构造 client，所以要靠环境变量指到假服务器
    old_env = {k: os.environ.get(k) for k in ("CANVAS_HOST", "CANVAS_API_TOKEN")}
    try:
        local = os.path.join(tmp, "solution.pdf")
        with open(local, "wb") as fh:
            fh.write(PDF_BYTES)

        with FakeServer() as server:
            os.environ["CANVAS_HOST"] = server.url
            os.environ["CANVAS_API_TOKEN"] = "test-token"
            client = server.client()

            # 第 1、2 步：上传
            info = client.upload_file(local)
            assert info["id"] == 160000
            assert FakeCanvas.uploaded is not None, "必须真的把文件 POST 到 upload_url"

            # 第 3 步：挂到提交上，参数名与 Canvas 约定一致
            client.submit_online_upload(COURSE_ID, ASSIGNMENT_ID, [info["id"]])
            body = FakeCanvas.submission_body or ""
            assert "submission%5Bsubmission_type%5D=online_upload" in body or \
                   "submission[submission_type]=online_upload" in body, body
            assert "160000" in body

            # 演练模式：不加 --confirm 时只打印，绝不发 POST
            FakeCanvas.submission_body = None
            rc = submit_cmd.main([str(COURSE_ID), str(ASSIGNMENT_ID), "--files", local])
            assert rc == 0, "dry-run 应当成功返回"
            assert FakeCanvas.submission_body is None, "dry-run 不得真的提交"
            assert FakeCanvas.uploaded is not None

            # 加了 --confirm 才真提交
            rc = submit_cmd.main([str(COURSE_ID), str(ASSIGNMENT_ID),
                                  "--files", local, "--confirm"])
            assert rc == 0, "confirm 后应当提交成功"
            assert FakeCanvas.submission_body is not None, "confirm 后必须真的提交"
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.chdir(cwd)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_end_to_end()
    print("端到端冒烟测试通过：doctor / courses / files / download(403回退+幂等) / summary / index / deadlines")
    test_submit_two_step_upload()
    print("提交链路测试通过：upload_file(两步) / submit_online_upload / dry-run 不提交 / --confirm 才提交")
