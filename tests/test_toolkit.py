# -*- coding: utf-8 -*-
"""离线自测：不联网、不需要 Canvas 令牌，只验证纯逻辑。

跑法：
    uv run --dev pytest          # 有 uv
    python -m pytest             # 有 pytest
    python tests/test_toolkit.py # 连 pytest 都没有时的兜底（自带 mini runner）
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import canvas_client as cc
from scripts import course_summary as cs


# --------------------------------------------------------------------------- #
# 路径安全：老师的文件名可能带路径分隔符，绝不能让它写到仓库外面
# --------------------------------------------------------------------------- #
def test_sanitize_strips_path_separators():
    assert cc.sanitize("../../.env") == "env"
    assert "/" not in cc.sanitize("a/b/c.pdf")
    assert cc.sanitize("Week1: intro?.pdf") == "Week1_ intro_.pdf"
    assert cc.sanitize("") == "untitled"
    assert cc.sanitize("...") == "untitled"


def test_sanitize_keeps_unicode_and_extension():
    assert cc.sanitize("第一讲 绪论.pdf") == "第一讲 绪论.pdf"
    long_name = "长" * 300 + ".pdf"
    assert len(cc.sanitize(long_name)) <= 180


def test_safe_join_blocks_escape():
    with tempfile.TemporaryDirectory() as tmp:
        inside = cc.safe_join(tmp, "Week1/slides.pdf")
        assert inside.startswith(os.path.abspath(tmp))
        # sanitize 会把 .. 消掉，所以穿越路径最终落在目录内
        assert cc.safe_join(tmp, "../../etc/passwd").startswith(os.path.abspath(tmp))


def test_safe_join_rejects_absolute_escape():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            cc.safe_join(tmp, "/etc/passwd")
        except ValueError:
            pass
        else:
            # 绝对路径也被拼进目录内，不算逃逸
            assert cc.safe_join(tmp, "/etc/passwd").startswith(os.path.abspath(tmp))


# --------------------------------------------------------------------------- #
# 目录命名
# --------------------------------------------------------------------------- #
def test_course_dir_name_common_shapes():
    assert cc.course_dir_name(
        {"name": "CS101 Introduction to Programming (1101)",
         "course_code": "CS101"}) == "CS101_Introduction_to_Programming"
    assert cc.course_dir_name(
        {"name": "MATH 101 - Calculus I", "course_code": "MATH101"}) == "MATH101_Calculus_I"
    # 抽不到代码就退回 course_code
    assert cc.course_dir_name(
        {"name": "程序设计基础", "course_code": "CS101"}).startswith("CS101_")
    # 什么都没有时也不能崩
    assert cc.course_dir_name({}) == "course"


def test_course_dir_name_term_prefix():
    course = {"name": "CS101 Intro to CS", "course_code": "CS101",
              "term": {"name": "2025 Fall"}}
    assert cc.course_dir_name(course, prefix_term=True).startswith("2025_Fall_CS101")


# --------------------------------------------------------------------------- #
# 配置读取
# --------------------------------------------------------------------------- #
def test_load_env_parses_quotes_and_export():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('# 注释\nexport CANVAS_HOST="https://example.instructure.com"\n'
                     "CANVAS_API_TOKEN='abc123'\nCANVAS_TERM=2025Fall\n")
        env = cc.load_env(path)
    assert env["CANVAS_HOST"] == "https://example.instructure.com"
    assert env["CANVAS_API_TOKEN"] == "abc123"
    assert env["CANVAS_TERM"] == "2025Fall"


def test_normalize_host():
    assert cc.normalize_host("school.instructure.com") == "https://school.instructure.com"
    assert cc.normalize_host("https://x.edu/") == "https://x.edu"
    assert cc.normalize_host("  https://y.edu/api  ") == "https://y.edu/api"
    assert cc.normalize_host("") == ""


def test_client_raises_clear_error_without_credentials(monkeypatch):
    for key in ("CANVAS_HOST", "CANVAS_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    try:
        cc.CanvasClient(env_path="/nonexistent/.env")
    except cc.NotConfigured as exc:
        assert "CANVAS_API_TOKEN" in str(exc)
    else:
        raise AssertionError("缺少凭据时应当抛 NotConfigured")


# --------------------------------------------------------------------------- #
# HTML → 文本，以及大纲解析
# --------------------------------------------------------------------------- #
def test_to_text_strips_tags_and_keeps_lines():
    html = ("<p>Course Description</p><p>Learn <b>things</b>.</p>"
            "<script>var x=1;</script><ul><li>a</li><li>b</li></ul>")
    text = cs.to_text(html)
    assert "Course Description" in text
    assert "Learn things ." in text or "Learn things" in text
    assert "var x" not in text
    assert "\n" in text


def test_percent_pairs_reads_split_lines():
    pairs = cs.percent_pairs("Assessment\n\nAssignments\n20%\nMidterm\n30%\nFinal\n50%")
    labels = [label for label, _ in pairs]
    assert "Assignments" in labels and "Final" in labels
    assert dict(pairs)["Final"] == "50"


def test_percent_pairs_ignores_numbering_lines():
    pairs = cs.percent_pairs("2. \n40%")
    assert all(label.strip() not in ("2.", "2") for label, _ in pairs)


def test_section_and_block_after():
    text = "1. Course Description\nWe learn stuff.\n2. Outcomes\nMore.\n5. Assessment\nQuiz 50%"
    assert cs.section(text, "Course Description", "Outcomes").startswith("Course Description")
    block = cs.block_after(text, "Assessment")
    assert block.startswith("5. Assessment") and "Quiz 50%" in block


# --------------------------------------------------------------------------- #
# MANIFEST 生成（幂等清单）
# --------------------------------------------------------------------------- #
def test_write_manifest_lists_files_and_status():
    course = {"id": 123, "name": "CS101 Intro", "term": {"name": "2025 Fall"}}
    files = [{"id": 9, "display_name": "l1.pdf", "size": 10,
              "updated_at": "2026-01-02T03:04:05Z", "_rel": "Week1/l1.pdf"}]
    with tempfile.TemporaryDirectory() as tmp:
        out = cc.write_manifest(course, files, tmp, note="测试", now="2026-01-02 03:04:05")
        content = open(out, encoding="utf-8").read()
    assert "CS101 Intro" in content
    assert "| 9 | l1.pdf | 10 |" in content
    assert "未下载" in content
    assert "测试" in content


def test_write_manifest_handles_unavailable_files():
    with tempfile.TemporaryDirectory() as tmp:
        out = cc.write_manifest({"id": 1, "name": "X"}, None, tmp, note="403")
        content = open(out, encoding="utf-8").read()
    assert "未开放文件列表" in content


def test_scan_self_expose_flags_script_names():
    from scripts.submit import scan_self_expose
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "solution.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("干净的一行\n所有计算均以脚本复核（见 check-answers.py）\n")
        hits = scan_self_expose(path)
    assert hits and any("check-answers" in pattern for _, pattern, _ in hits)


def test_submission_label_never_fakes_unsubmitted():
    """「交没交」的状态标签：读不到就必须说不知道，不能冒充「未提交」。

    静默把「读不到」显示成「未提交」，会让人以为还没交而重复提交 —— 比报错更糟。
    """
    from scripts.cli import submission_label

    assert submission_label({"submission": {"submitted_at": None,
                                            "workflow_state": "unsubmitted"}}) == "未提交"
    assert submission_label({"submission": {"submitted_at": "2099-10-19T02:00:00Z",
                                            "workflow_state": "submitted"}}) == "已提交 2099-10-19"
    assert submission_label({"submission": {"submitted_at": "2099-10-19T02:00:00Z",
                                            "graded_at": "2099-10-30T02:00:00Z",
                                            "workflow_state": "graded"}}) == "已评分"
    # 缺字段、类型不对、空值 —— 一律「状态未知」
    assert submission_label({}) == "状态未知"
    assert submission_label({"submission": None}) == "状态未知"
    assert submission_label({"submission": "unsubmitted"}) == "状态未知"


def test_section_stops_at_numbered_heading_when_end_missing():
    """概述段不能被拉扯成整份大纲。

    真实大纲的标题措辞常和代码里配的 `end` 对不上。这时若一路读到 limit，
    README 的「概述」会把评分占比、组队要求整段重复一遍。
    """
    syllabus = ("1. Course Description\nLearn to program.\n"
                "3. Assessment\nAssignments 30%\n"
                "5. Group Project\nForm groups of 3 to 4 members.\n")
    got = cs.section(syllabus, "Course Description", "A Heading That Does Not Exist")
    assert "Learn to program." in got
    assert "Assessment" not in got, got
    assert "Group Project" not in got, got

    # end 命中时仍按 end 截断（原行为不变）
    got2 = cs.section(syllabus, "Course Description", "Assessment")
    assert "Learn to program." in got2 and "Assignments 30%" not in got2


def test_readme_layout_contract():
    """README 的章节顺序与表头是文档/样例承诺过的形状，防止静默漂移。"""
    course = {"id": 12345, "name": "CS101 Introduction to Programming",
              "term": {"name": "2025 Fall"}}
    assignments = [{"name": "HW1", "points_possible": 100,
                    "submission_types": ["online_upload"], "due_at": "2026-01-05T00:00:00Z"}]
    readme = cs.build_readme(course, [], assignments, "1. Course Description\nLearn to program.",
                             [], [], now="2026-01-01 00:00")
    for heading in ("## 概述", "## 评分占比（考试 vs 平时分）", "## 作业（Canvas 已发布）",
                    "## 组队 / 项目要求", "## 课程资料（CourseFiles）", "## 待更新"):
        assert heading in readme, "缺少章节: %s" % heading
    # 有作业时才出表头；无作业时应显示"暂无"而不是空表
    assert "| 作业 | 分值 | 提交方式 | 截止 |" in readme
    empty = cs.build_readme(course, [], [], "1. Course Description\nLearn to program.",
                            [], [], now="2026-01-01 00:00")
    assert "（暂无已发布的 Canvas 作业）" in empty


def test_opening_description_when_no_course_description_heading():
    """很多大纲没有 "Course Description" 标题，第一行直接就是描述。

    真实实例上就有这种：概述会整个空掉。此时取第一个已知章节之前的开场文字，
    但**不能**退化成"整份大纲前 600 字"（那会把评分/组队搬进概述）。
    """
    no_heading = ("This course introduces the basic concepts of information security.\n\n"
                  "Course Intended Learning Outcomes (CILOs)\n\n"
                  "1. Identify the organizational requirements.\n")
    got = cs.opening_description(no_heading)
    assert got.startswith("This course introduces")
    assert "CILOs" not in got and "Identify the organizational" not in got

    # 开头只有一行短标题时，跳过它再取正文
    with_title = "CS101: Introduction\n\nThis course teaches programming from scratch.\n"
    assert cs.opening_description(with_title).startswith("This course teaches")

    # 实在没有可用的开场文字时返回空串，交给调用方别的兜底
    assert cs.opening_description("CS101") == ""
    assert cs.opening_description("") == ""

    # 无标题大纲走 build_readme 时，概述必须有内容且不污染
    course = {"id": 1, "name": "CS101 Introduction to Programming", "term": {"name": "2025 Fall"}}
    readme = cs.build_readme(course, [], [], no_heading, [], [], now="2026-01-01 00:00")
    overview = readme.split("## 概述")[1].split("\n## ")[0]
    assert "This course introduces" in overview, overview
    assert "CILOs" not in overview, overview


def test_setup_check_states():
    """初始化状态检测：每种「还差什么」都要能被准确识别。"""
    from scripts import setup_check as sc

    assert sc.check_setup(env={})["state"] == "missing_host"
    assert sc.check_setup(env={"CANVAS_HOST": "", "CANVAS_API_TOKEN": "x"})["state"] == "missing_host"
    assert sc.check_setup(env={"CANVAS_HOST": "https://a.edu"})["state"] == "missing_token"
    assert sc.check_setup(env={"CANVAS_HOST": "https://a.edu",
                               "CANVAS_API_TOKEN": "<在这里粘贴你的令牌>"})["state"] \
        == "token_placeholder"
    assert sc.check_setup(env={"CANVAS_HOST": "https://a.edu/api/v1",
                               "CANVAS_API_TOKEN": "a" * 40})["state"] == "host_looks_wrong"
    assert sc.check_setup(env={"CANVAS_HOST": "https://a.edu",
                               "CANVAS_API_TOKEN": "a" * 40})["state"] == "ready"

    # 文件不存在时是 no_env
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, ".env")
        status = sc.check_setup(env_path=missing)
        assert status["state"] == "no_env"
        assert status["next_steps"]


def test_init_never_overwrites_existing_env():
    """最关键的一条：init 绝不能覆盖用户已经填好的令牌。

    令牌只显示一次，被覆盖就得重新生成 —— 那是不可接受的破坏。
    """
    from scripts import setup_check as sc

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        original = 'CANVAS_HOST="https://mine.edu"\nCANVAS_API_TOKEN="my-real-token-1234567890"\n'
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(original)

        action, _, message = sc.ensure_env_file(path)
        assert action == "kept", action
        assert "未做任何改动" in message
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == original, "已存在的 .env 被改动了！"

        # 缺键时只追加，不动已有值
        partial = os.path.join(tmp, "partial.env")
        with open(partial, "w", encoding="utf-8") as fh:
            fh.write('CANVAS_TERM="2025Fall"\n')
        action2, _, msg2 = sc.ensure_env_file(partial)
        assert action2 == "completed", action2
        content = open(partial, encoding="utf-8").read()
        assert 'CANVAS_TERM="2025Fall"' in content
        assert "CANVAS_HOST" in content and "CANVAS_API_TOKEN" in content
        assert "其余内容未改动" in msg2


def test_init_creates_missing_parent_directory():
    """父目录不存在时也要能创建（曾直接抛 FileNotFoundError）。

    真机场景：多实例/多份配置时把 .env 放到子目录里，或用户指定的路径还没建。
    """
    from scripts import setup_check as sc

    with tempfile.TemporaryDirectory() as tmp:
        nested = os.path.join(tmp, "conf", "deep", ".env")
        action, path, _ = sc.ensure_env_file(nested)
        assert action == "created"
        assert os.path.isfile(nested)
        # 之后再跑必须保持不变
        action2, _, _ = sc.ensure_env_file(nested)
        assert action2 == "kept"


def test_init_creates_env_with_restrictive_permissions():
    """新建的 .env 含令牌，权限应当是 600（只有本人可读）。"""
    from scripts import setup_check as sc

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        action, _, _ = sc.ensure_env_file(path)
        assert action == "created"
        assert os.path.exists(path)
        if os.name == "posix":
            assert (os.stat(path).st_mode & 0o077) == 0, "权限过宽，别人可能读到令牌"


def test_host_problem_detection():
    from scripts import setup_check as sc

    assert sc.host_problem("https://a.edu/api/v1") is not None
    assert sc.host_problem("https://a.edu/courses/1") is not None
    assert sc.host_problem("https://a.edu/profile/settings") is not None
    assert sc.host_problem("https://a.instructure.com") is None
    assert sc.host_problem("") is None


# --------------------------------------------------------------------------- #
# 提交件预检：PDF 文本层、PDF 属性、LaTeX 日志
#   起因：只扫 .tex/.md 会漏掉「真正被老师看到的那一面」（PDF）；
#   而 Overfull 这类版面问题在 PDF 文本抽取里完全看不出来，只能查编译日志。
# --------------------------------------------------------------------------- #
def test_scan_self_expose_reads_pdf_text_layer():
    from scripts.submit import scan_self_expose
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "solution.pdf")
        with open(path, "wb") as fh:
            fh.write(b"%PDF-1.4\n")
        seen = {}

        def fake_extractor(p):
            seen["path"] = p
            return "第一页\n所有计算均以脚本复核（见 check-answers.py）\n"

        hits = scan_self_expose(path, pdf_extractor=fake_extractor)
    assert seen["path"] == path
    assert hits and any("check-answers" in pattern for _, pattern, _ in hits)


def test_scan_self_expose_pdf_without_extractor_is_not_reported_as_clean():
    """抽不出文本时返回空列表（= 没检查），空列表不等于"没问题"。

    调用方（describe）必须另行提示"这一份没覆盖"，不能静默当成通过。
    """
    from scripts.submit import scan_self_expose
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "solution.pdf")
        with open(path, "wb") as fh:
            fh.write(b"%PDF-1.4\n")
        assert scan_self_expose(path, pdf_extractor=lambda _p: "") == []


def test_extract_pdf_text_falls_back_and_never_raises():
    from scripts import submit as sm

    calls = []

    class _Proc:
        returncode = 0
        stdout = b"HELLO"

    def fake_runner(cmd, capture_output=True, timeout=0):
        calls.append(cmd[0])
        if cmd[0] == "pdftotext":
            raise RuntimeError("pdftotext 崩了")      # 提取器异常不能中断预检
        return _Proc()

    text = sm.extract_pdf_text("x.pdf", runner=fake_runner,
                               which=lambda name: "/usr/bin/" + name)
    assert text == "HELLO"
    assert calls == ["pdftotext", "gs"]


def test_extract_pdf_text_returns_empty_when_no_tool_available():
    from scripts import submit as sm
    assert sm.extract_pdf_text("x.pdf", runner=lambda *a, **k: None,
                               which=lambda name: None) == ""


def test_extract_pdf_text_ignores_gs_error_output():
    """gs 对坏 PDF 会返回 0，却把报错写进 stdout。

    不能把报错文本当成文件内容去扫 —— 否则既扫不出东西，又不会提示"这一份没覆盖"。
    """
    from scripts import submit as sm

    class _Proc:
        returncode = 0
        stdout = b"   **** Error: Couldn't initialise file.\n   No pages will be processed\n"

    text = sm.extract_pdf_text("x.pdf", runner=lambda *a, **k: _Proc(),
                               which=lambda name: "/usr/bin/" + name)
    assert text == ""


def test_pdf_metadata_flags_latex_creator_and_ignores_clean_file():
    from scripts.submit import pdf_metadata
    with tempfile.TemporaryDirectory() as tmp:
        dirty = os.path.join(tmp, "dirty.pdf")
        with open(dirty, "wb") as fh:
            fh.write(b"%PDF-1.5\n1 0 obj<</Creator (XeTeX output 2099.1.1)"
                     b"/Producer (xdvipdfmx)>>\nendobj\n")
        meta = pdf_metadata(dirty)

        clean = os.path.join(tmp, "clean.pdf")
        with open(clean, "wb") as fh:
            fh.write(b"%PDF-1.5\n1 0 obj<</Type/Catalog>>\nendobj\n")
        assert pdf_metadata(clean) == {}

    assert meta.get("Creator", "").startswith("XeTeX")
    assert "Producer" in meta


def test_scan_latex_log_catches_overfull_and_missing_char():
    from scripts.submit import scan_latex_log
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "solution.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("This is XeTeX, Version 3.141592653\n"
                     "Overfull \\hbox (238.9pt too wide) in paragraph at lines 68--69\n"
                     "Missing character: There is no ① in font nullfont!\n")
        hits = scan_latex_log(path)

    assert len(hits) == 2
    assert any("Overfull" in line for _, line in hits)
    assert scan_latex_log(os.path.join(tmp, "nope.log")) == []


def test_find_latex_logs_scans_dir_build_and_explicit():
    from scripts.submit import find_latex_logs
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, "solution.log")
        with open(top, "w", encoding="utf-8") as fh:
            fh.write("ok\n")
        build = os.path.join(tmp, "build")
        os.makedirs(build)
        with open(os.path.join(build, "solution.log"), "w", encoding="utf-8") as fh:
            fh.write("ok\n")

        found = find_latex_logs(spec_dir=tmp)
        assert len(found) == 2
        assert any(p.endswith(os.path.join("build", "solution.log")) for p in found)
        # 显式指定优先
        assert find_latex_logs(spec_dir=tmp, explicit=[top]) == [os.path.abspath(top)]
        # 只给了文件时也能从它所在目录推出来
        assert find_latex_logs(files=[os.path.join(tmp, "solution.pdf")])


def test_describe_surfaces_layout_and_metadata_warnings():
    """演练输出必须把三类风险摆到人眼前：自曝痕、PDF 属性、版面告警。"""
    import contextlib
    import io

    from scripts import submit as sm

    class _StubClient:
        def course(self, course_id, includes=None):
            return {"id": course_id, "name": "Demo Course"}

        def assignment(self, course_id, assignment_id):
            return {"name": "HW1", "due_at": "2099-01-01T00:00:00Z",
                    "submission_types": ["online_upload"]}

        def submissions(self, course_id, assignment_id):
            return {"submitted_at": None}

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "solution.pdf")
        with open(pdf, "wb") as fh:
            fh.write(b"%PDF-1.5\n1 0 obj<</Creator (XeTeX output 2099.1.1)>>\nendobj\n")
        log = os.path.join(tmp, "solution.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("Overfull \\hbox (12.0pt too wide) in paragraph at lines 1--2\n")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _, can_submit = sm.describe(_StubClient(), 12345, 67890, [pdf], latex_logs=[log])
    out = buf.getvalue()

    assert can_submit is True
    assert "Overfull" in out and "xurl" in out          # 版面告警 + 直接给出修法
    assert "PDF 属性 Creator" in out                     # 元数据告警
    assert "渲染成图片" in out                            # 人眼看版的提醒


# --------------------------------------------------------------------------- #
# 截止列表：逾期项不能从屏幕上消失
# --------------------------------------------------------------------------- #
def test_split_deadlines_reports_overdue_beyond_the_window():
    """逾期 30 天也必须报出来。

    旧实现只列 [now-1天, now+N天]：一份两周前就该交、至今没交的作业会**完全消失**，
    屏幕上什么都没有，反而让人以为没事 —— 这正是最该被提醒的一类。
    """
    from datetime import datetime, timezone

    from scripts.cli import split_deadlines

    now = datetime(2099, 1, 10, tzinfo=timezone.utc)
    items = [("Demo Course", [
        {"name": "Overdue", "due_at": "2099-01-05T00:00:00Z"},
        {"name": "Soon", "due_at": "2099-01-12T00:00:00Z"},
        {"name": "Far", "due_at": "2099-03-01T00:00:00Z"},
        {"name": "NoDue", "due_at": None},
    ])]
    upcoming, overdue = split_deadlines(items, days=7, now=now)

    assert [row[2]["name"] for row in upcoming] == ["Soon"]
    assert [row[2]["name"] for row in overdue] == ["Overdue"]


def test_cmd_deadlines_shows_overdue_unsubmitted_and_unknown_but_not_submitted():
    import contextlib
    import io

    from scripts.cli import cmd_deadlines

    class _Stub:
        def courses(self):
            return [{"id": 1, "name": "Demo Course"}]

        def assignments(self, course_id):
            return [
                {"name": "Late-Unsubmitted", "due_at": "2000-01-01T00:00:00Z",
                 "submission_types": ["online_upload"],
                 "submission": {"workflow_state": "unsubmitted", "submitted_at": None}},
                {"name": "Late-Submitted", "due_at": "2000-01-02T00:00:00Z",
                 "submission_types": ["online_upload"],
                 "submission": {"workflow_state": "submitted",
                                "submitted_at": "2000-01-02T00:00:00Z"}},
                {"name": "Late-Unknown", "due_at": "2000-01-03T00:00:00Z",
                 "submission_types": ["online_upload"]},      # 状态读不到
            ]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_deadlines(_Stub(), days=7)
    out = buf.getvalue()

    assert rc == 0
    assert "Late-Unsubmitted" in out and "逾期" in out
    assert "Late-Submitted" not in out            # 已交的不再吓人
    assert "Late-Unknown" in out and "状态未知" in out   # 读不到就照列 + 明说未知


# --------------------------------------------------------------------------- #
# 无 pytest 时的兜底 runner
# --------------------------------------------------------------------------- #
def _run_standalone():
    import inspect
    import traceback

    class _Monkey:
        def delenv(self, key, raising=True):
            os.environ.pop(key, None)

    monkey = _Monkey()
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            if "monkeypatch" in inspect.signature(fn).parameters:
                fn(monkey)
            else:
                fn()
            print("PASS %s" % name)
        except Exception:                              # noqa: BLE001
            failed += 1
            print("FAIL %s" % name)
            traceback.print_exc()
    print("\n%d/%d 通过" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_standalone())
