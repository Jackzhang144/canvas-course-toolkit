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
"""
from __future__ import annotations

import argparse
import os
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


def scan_self_expose(path):
    """粗查提交件里有没有「这是机器生成」的痕迹。

    只对纯文本类文件做检查（.md/.txt/.tex/.py/.csv/.json）。PDF/图片会跳过，
    PDF 请用 `pdftotext solution.pdf -` 抽文本后自行过一遍末页。
    """
    if os.path.splitext(path)[1].lower() not in (".md", ".txt", ".tex", ".py", ".csv", ".json"):
        return []
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                for pattern in SELF_EXPOSE_PATTERNS:
                    if pattern.lower() in line.lower():
                        hits.append((lineno, pattern, line.strip()[:100]))
    except OSError:
        return []
    return hits


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


def describe(client, course_id, assignment_id, files):
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
    for path in files:
        size = os.path.getsize(path)
        print("   - %s  (%.1f KB)" % (path, size / 1024.0))
        for lineno, pattern, snippet in scan_self_expose(path):
            print("     ⚠ 第 %d 行命中「%s」：%s" % (lineno, pattern, snippet))
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
    parser.add_argument("--confirm", action="store_true", help="确认执行（不加则只演练）")
    args = parser.parse_args(argv)

    try:
        client = cc.CanvasClient()
    except cc.NotConfigured as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        files = collect_files(args.course_id, args.assignment_id, args.dir, args.files)
        _, can_submit = describe(client, args.course_id, args.assignment_id, files)
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
