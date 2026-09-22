#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上传并提交作业到 Canvas。

**这是整个工具包里唯一会改变线上状态的操作。** 所以它默认只做演练（dry-run），
真正提交必须同时给出 `--confirm`。

用法：
    # 1) 先看要发生什么（不联网写任何东西）
    uv run canvas-submit 12345 67890 Assignments/CS101/hw1-implement-vector
    uv run canvas-submit 12345 67890 --files solution.pdf

    # 2) 确认无误后真正提交
    uv run canvas-submit 12345 67890 --files solution.pdf --confirm

背后的两步流程（Canvas 不支持直接指本地路径）：
    上传到「我的文件」→ 拿 file_id → 把 file_id 挂到 submission 上。

演练阶段会替你做三项**机械可查**的检查（细节见 docs/security.md）：
    1. 自曝痕：PDF 先抽文本层再扫（交上去的是 PDF，只扫 .tex 会漏掉真正被看到的一面）；
    2. PDF 属性：/Creator /Producer 等，LaTeX 默认写 XeTeX，等于盖章"机器排版"；
    3. 编译日志：Overfull/Underfull/缺字/未定义引用 —— 这类版面问题在文本抽取里看不见，
       只能查日志；脚本查完仍会提醒你渲染成图片人眼看一遍。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import canvas_client as cc

#: 交给老师/学校的文件必须是干净的「人写的文件」。
#: 详见 docs/security.md —— 提交件里出现仓库文件名、脚本名、生成时间戳都算自曝。
SELF_EXPOSE_PATTERNS = [
    "canvas_client", "course_summary", "check-answers", "scripts/", "MANIFEST",
    "AGENTS.md", "canvas-course-toolkit", "uv run", "skills/",
    "脚本复核", "自动化生成", "AI 生成", "agent",
]

#: 纯文本类提交件直接读文件即可；PDF 要先抽文本层。
TEXT_SUFFIXES = (".md", ".txt", ".tex", ".py", ".csv", ".json")

#: PDF 属性里最容易暴露"流水线产物"的几个键。
PDF_METADATA_KEYS = ("Creator", "Producer", "Author", "CreationDate")

#: LaTeX 日志里必须处理的告警：版面类 + 引用/字体类。
LATEX_WARNING_RE = re.compile(
    r"Overfull|Underfull|Missing character|Undefined control sequence|Citation .* undefined",
    re.I,
)


def extract_pdf_text(path, runner=None, which=None):
    """抽取 PDF 的文本层：优先 `pdftotext`，退回 ghostscript。

    两者都没有（或都失败）时返回空字符串 —— 预检绝不能因为缺工具就崩掉，
    但调用方要把"抽不出来"如实告诉用户，而不是当成"检查通过"。
    """
    runner = runner or subprocess.run
    which = which or shutil.which
    path = os.fspath(path)
    candidates = (
        ["pdftotext", "-q", path, "-"],
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dNOSAFER",
         "-sDEVICE=txtwrite", "-sOutputFile=-", path],
    )
    for cmd in candidates:
        if which(cmd[0]) is None:
            continue
        try:
            proc = runner(cmd, capture_output=True, timeout=180)
        except Exception:                      # noqa: BLE001 —— 提取器任何异常都不该阻断预检
            continue
        if getattr(proc, "returncode", 1) != 0 or not getattr(proc, "stdout", None):
            continue
        text = proc.stdout.decode("utf-8", "replace")
        # gs 遇到坏 PDF 会**返回 0 并把报错写进 stdout**（-sOutputFile=- 时）。
        # 这种"正文"其实是错误信息，必须丢掉，否则会当成文件内容去扫（还给不出"未覆盖"的提示）。
        if "**** Error" in text or "No pages will be processed" in text:
            continue
        return text
    return ""


def pdf_metadata(path):
    """读 PDF 里明文可见的 /Creator /Producer /Author /CreationDate。

    LaTeX 默认会写 `Creator: XeTeX`；用 `\\hypersetup{pdfcreator={},pdfproducer={}}`
    置空。这里只做启发式扫描（不解析完整 PDF），够用来提示"要不要抹掉"。
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return {}
    text = raw.decode("latin-1", "replace")
    found = {}
    for key in PDF_METADATA_KEYS:
        match = re.search(r"/%s\s*\(((?:[^()\\]|\\.)*)\)" % key, text)
        if match:
            value = match.group(1).strip()
            if value:
                found[key] = value[:80]
    return found


def scan_self_expose(path, pdf_extractor=None):
    """粗查提交件里有没有「这是机器生成」的痕迹。

    文本类文件（.md/.txt/.tex/.py/.csv/.json）直接读；
    **PDF 会先抽文本层**（`pdftotext` 或 `gs`），因为作业交上去的通常正是 PDF ——
    只扫 .tex 源码会漏掉"真正被老师看到的那一面"。
    抽不出文本时返回空列表，由调用方另行提示"未能检查"。
    """
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".pdf":
        extractor = pdf_extractor or extract_pdf_text
        content = extractor(path)
        if not content:
            return []
        lines = content.splitlines()
    elif suffix in TEXT_SUFFIXES:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return []
    else:
        return []

    hits = []
    for lineno, line in enumerate(lines, 1):
        for pattern in SELF_EXPOSE_PATTERNS:
            if pattern.lower() in line.lower():
                hits.append((lineno, pattern, line.strip()[:100]))
    return hits


def scan_latex_log(path):
    """扫 LaTeX 编译日志里的告警，返回 [(行号, 原始行)]。

    为什么必须看日志：`Overfull` 表示内容**冲出了版心**（最常见是长 URL、宽表格），
    而它在 PDF 文本抽取里完全看不出来 —— 抽出来的 URL 照样是正常换行。
    """
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if LATEX_WARNING_RE.search(line):
                    hits.append((lineno, line.strip()[:120]))
    except OSError:
        return []
    return hits


def find_latex_logs(spec_dir=None, explicit=None, files=None):
    """找 LaTeX 编译日志：显式指定优先，否则在作业目录与其 build/ 下找 *.log。"""
    if explicit:
        return [os.path.abspath(p) for p in explicit if os.path.isfile(p)]
    if not spec_dir and files:
        spec_dir = os.path.dirname(os.path.abspath(files[0]))
    if not spec_dir or not os.path.isdir(spec_dir):
        return []
    found = []
    for base in (spec_dir, os.path.join(spec_dir, "build")):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.endswith(".log"):
                found.append(os.path.join(base, name))
    return found


def collect_files(course_id, assignment_id, spec_dir, explicit):
    """确定要提交哪些文件：显式 `--files` 优先，否则取目录里的提交件。"""
    if explicit:
        return [os.path.abspath(p) for p in explicit]
    if not spec_dir:
        raise SystemExit("请用 --files 指定文件，或给出一个作业目录")
    if not os.path.isdir(spec_dir):
        raise SystemExit("作业目录不存在: %s" % spec_dir)
    skip_names = {"README.md", "MANIFEST.md", "sources", "check-answers.py", ".DS_Store"}
    picked = []
    for name in sorted(os.listdir(spec_dir)):
        full = os.path.join(spec_dir, name)
        if name in skip_names or name.startswith(".") or name.endswith((".aux", ".log", ".part")):
            continue
        if os.path.isfile(full):
            picked.append(full)
    if not picked:
        raise SystemExit("目录里没有可提交的文件: %s" % spec_dir)
    return picked


def describe(client, course_id, assignment_id, files, latex_logs=()):
    """提交前把「要发生什么」原原本本打印出来，让用户能核对。"""
    course = client.course(course_id, includes=("term",))
    assignment = client.assignment(course_id, assignment_id)
    submission_types = assignment.get("submission_types") or []

    print("=" * 66)
    print("即将提交")
    print("=" * 66)
    print("课程      : %s (id=%s)" % (course.get("name"), course_id))
    print("作业      : %s (id=%s)" % (assignment.get("name"), assignment_id))
    print("截止时间  : %s UTC" % (assignment.get("due_at") or "未设置"))
    print("允许方式  : %s" % (",".join(submission_types) or "未声明"))
    print("当前时间  : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("待提交文件:")
    has_pdf = False
    for path in files:
        size = os.path.getsize(path)
        print("   - %s  (%.1f KB)" % (path, size / 1024.0))

        # 1) 自曝痕（PDF 会先抽文本层，见 scan_self_expose）
        hits = scan_self_expose(path)
        for lineno, pattern, snippet in hits:
            print("     ⚠ 第 %d 行命中「%s」：%s" % (lineno, pattern, snippet))
        if os.path.splitext(path)[1].lower() == ".pdf":
            has_pdf = True
            if not extract_pdf_text(path) and not hits:
                print("     ℹ 没能抽出 PDF 文本层（文件读不了，或本机没有 pdftotext/gs），"
                      "自曝检查未覆盖这一份，请自己翻一遍末页。")

            # 2) PDF 属性：LaTeX 默认写 Creator/Producer，等于盖章"机器排版"
            meta = pdf_metadata(path)
            for key, value in sorted(meta.items()):
                print("     ⚠ PDF 属性 %s = %s（想抹掉：\\hypersetup{pdfcreator={},pdfproducer={}}）"
                      % (key, value))

    # 3) 版面检查：Overfull/Underfull/缺字只能从编译日志看出来
    for log_path in latex_logs:
        warnings = scan_latex_log(log_path)
        if warnings:
            print("   ⚠ 编译日志有 %d 条告警：%s" % (len(warnings), log_path))
            for lineno, line in warnings[:8]:
                print("       第 %d 行: %s" % (lineno, line))
            if len(warnings) > 8:
                print("       …… 还有 %d 条" % (len(warnings) - 8))
            print("     Overfull = 内容冲出页边距（长 URL 加 \\usepackage{xurl}，宽表格用 tabularx）。")
        else:
            print("   ✓ 编译日志无版面/引用告警：%s" % log_path)
    if has_pdf:
        print("   ℹ 版面还要人眼看一遍：文本抽取看不出越界，"
              "请渲染成图片逐页看（首页、带表格/公式页、末页）：")
        print("     gs -q -dNOPAUSE -dBATCH -dNOSAFER -sDEVICE=png16m -r120 \\\n"
              "        -dFirstPage=1 -dLastPage=1 -sOutputFile=/tmp/p1.png solution.pdf")
    print("-" * 66)

    if "online_upload" not in submission_types:
        print("⚠ 该作业不支持 online_upload（可能是纸面提交、外部工具或仅打分项）。")
        print("  不要硬传，先看作业说明确认提交方式。")
        return assignment, False

    try:
        current = client.submissions(course_id, assignment_id)
        if current.get("submitted_at"):
            print("⚠ 你已提交过：%s（尝试 %s 次），当前状态 %s，分数 %s" % (
                current.get("submitted_at"), current.get("attempt"), 
                current.get("workflow_state"), current.get("score")))
            print("  重新提交会覆盖上一次的提交记录，请确认这是你要的。")
    except cc.CanvasError as exc:
        print("（读取已有提交失败，忽略: HTTP %s）" % exc.status)
    return assignment, True


def main(argv=None):
    parser = argparse.ArgumentParser(description="上传并提交作业到 Canvas（默认 dry-run）")
    parser.add_argument("course_id")
    parser.add_argument("assignment_id")
    parser.add_argument("dir", nargs="?", help="作业目录（自动挑里面的提交件）")
    parser.add_argument("--files", nargs="*", default=None, help="显式指定要提交的文件")
    parser.add_argument("--folder", default="submissions", help="Canvas 个人文件区里的目标目录")
    parser.add_argument("--latex-log", nargs="*", default=None,
                        help="要检查的 LaTeX 编译日志（默认自动找作业目录及其 build/ 下的 *.log）")
    parser.add_argument("--confirm", action="store_true", help="确认执行（不加则只演练）")
    args = parser.parse_args(argv)

    try:
        client = cc.CanvasClient()
    except cc.NotConfigured as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        files = collect_files(args.course_id, args.assignment_id, args.dir, args.files)
        latex_logs = find_latex_logs(args.dir, args.latex_log, files=files)
        _, can_submit = describe(client, args.course_id, args.assignment_id, files,
                                 latex_logs=latex_logs)
    except cc.CanvasError as exc:
        print("错误:", exc, "\n提示:", exc.hint, file=sys.stderr)
        return 1

    if not can_submit:
        return 1

    if not args.confirm:
        print("这是演练（dry-run）。确认无误后，在命令末尾加上 --confirm 真正提交：")
        print("  uv run canvas-submit %s %s %s --confirm" % (
            args.course_id, args.assignment_id,
            (" ".join(args.files) if args.files else (args.dir or "--files <文件>"))))
        return 0

    # ---- 真正提交：上传 → 挂 file_id ----
    file_ids = []
    for path in files:
        print("上传中: %s ..." % os.path.basename(path))
        try:
            info = client.upload_file(path, parent_folder_path=args.folder)
        except Exception as exc:                       # noqa: BLE001
            print("上传失败，已中止，未产生任何提交: %s" % exc, file=sys.stderr)
            return 1
        file_ids.append(info.get("id"))
        print("  -> file_id=%s" % info.get("id"))

    try:
        result = client.submit_online_upload(args.course_id, args.assignment_id, file_ids)
    except cc.CanvasError as exc:
        print("提交失败: %s\n提示: %s" % (exc, exc.hint), file=sys.stderr)
        return 1

    submission = (result or {}).get("submission", result) or {}
    print("已提交: submitted_at=%s attempt=%s 状态=%s" % (
        submission.get("submitted_at"), submission.get("attempt"),
        submission.get("workflow_state")))
    print("请到 Canvas 页面再确认一次提交状态与文件是否正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
