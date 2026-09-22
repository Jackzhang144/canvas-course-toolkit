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
