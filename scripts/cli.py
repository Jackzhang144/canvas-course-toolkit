#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canvas 命令行工具（其他 skills / 脚本都复用这里的子命令）。

    uv run canvas doctor            自检：凭据、连通性、权限
    uv run canvas whoami            我是谁
    uv run canvas courses           我的课程（自动翻页）
    uv run canvas files 12345       某门课的可下载文件清单
    uv run canvas download 12345    下载到 CourseFiles/<课程目录>/（幂等，可重跑）
    uv run canvas manifest --all    为所有课程写/更新 MANIFEST.md
    uv run canvas deadlines         近期截止的作业 / 考试

不带子命令运行会打印上面的帮助。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import canvas_client as cc


def human_size(num):
    if num in (None, ""):
        return "-"
    try:
        num = float(num)
    except (TypeError, ValueError):
        return str(num)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return "%.0f%s" % (num, unit) if unit == "B" else "%.1f%s" % (num, unit)
        num /= 1024.0
    return str(num)


def cmd_doctor(client):
    """一路自检，把「能不能用」这件事一次说清楚。"""
    print("主机        :", cc.host_label(client.host))
    print("凭据来源    :", ".env" if os.path.exists(client.env_path) else "环境变量")
    me = client.whoami()
    print("身份        : %s (id=%s)" % (me.get("name"), me.get("id")))

    courses = client.courses()
    print("在读课程    : %d 门" % len(courses))
    for course in courses:
        print("   %8s  %-44s  %s" % (
            course.get("id"), (course.get("name") or "")[:44],
            (course.get("term") or {}).get("name", "")))

    if not courses:
        print("提示: 没有 active 课程。换学期了可以用 `canvas courses --all-terms` 看看历史课。")
        return 0

    print("权限抽查    : 课 %s" % courses[0].get("id"))
    for label, fn in (("页面", lambda: len(client.pages(courses[0]["id"]))),
                      ("作业", lambda: len(client.assignments(courses[0]["id"]))),
                      ("公告", lambda: len(client.announcements(courses[0]["id"])))):
        try:
            print("   %s: %d 条" % (label, fn()))
        except cc.CanvasError as exc:
            print("   %s: HTTP %s（%s）" % (label, exc.status, exc.hint))
    try:
        files, note = client.list_course_files(courses[0]["id"])
        print("   文件: %d 个 %s" % (len(files), ("[%s]" % note) if note else ""))
    except cc.CanvasError as exc:
        print("   文件: HTTP %s（%s）" % (exc.status, exc.hint))

    print("\n自检结束。下一步: uv run canvas download <course_id>")
    return 0


def cmd_whoami(client):
    me = client.whoami()
    print("姓名:", me.get("name"))
    print("id  :", me.get("id"))
    print("主机:", cc.host_label(client.host))
    return 0


def cmd_courses(client, all_terms=False):
    courses = client.courses(enrollment_state=None if all_terms else "active")
    if not courses:
        print("（没有课程）")
        return 0
    print("%8s  %-46s  %-22s  %s" % ("课程 ID", "课程名", "学期", "本地目录"))
    for course in courses:
        print("%8s  %-46s  %-22s  %s" % (
            course.get("id"), (course.get("name") or "")[:46],
            ((course.get("term") or {}).get("name") or "")[:22],
            cc.course_dir_name(course)))
    return 0


def cmd_files(client, course_id):
    files, note = client.list_course_files(course_id)
    if note:
        print("注意:", note)
    print("共 %d 个文件：" % len(files))
    for item in files:
        print("  %10s  %9s  %s" % (item.get("id"), human_size(item.get("size")),
                                   item.get("_rel") or item.get("display_name")))
    return 0


def cmd_download(client, course_id, dest=None, dry_run=False, term_prefix=False):
    course = client.course(course_id, includes=("term",))
    if dest is None:
        dest = os.path.join(cc.COURSE_FILES_DIR,
                            cc.course_dir_name(course, prefix_term=term_prefix))
    print("课程: %s\n  -> 目录: %s" % (course.get("name"), dest))

    files, note = client.list_course_files(course_id)
    if note:
        print("注意:", note)
    if not files:
        print("这门课没有可同步的文件。")
        return 0

    downloaded = skipped = failed = 0
    failures = []
    for item in files:
        rel = item.get("_rel") or cc.sanitize(item.get("display_name"))
        subdir = os.path.dirname(cc.safe_join(dest, rel))
        try:
            if dry_run:
                print("  会下载: %s" % rel)
                continue
            ok, _ = client.download_file(item.get("id"), subdir)
            if ok:
                downloaded += 1
                print("  已下载: %s" % rel)
            else:
                skipped += 1
        except Exception as exc:                      # noqa: BLE001 - 单个文件失败不该中断整门课
            failed += 1
            failures.append((item.get("id"), item.get("display_name"), str(exc)))
            print("  失败  : %s -> %s" % (rel, exc))

    if dry_run:
        print("dry-run 结束，未下载任何文件。去掉 --dry-run 真正执行。")
        return 0

    print("完成：新下载 %d，已存在跳过 %d，失败 %d" % (downloaded, skipped, failed))
    for fid, name, err in failures:
        print("  失败文件: %s (%s) -> %s" % (fid, name, err))
    # 页面数也写进清单，让 `canvas download` 与 `canvas manifest` 产出同一种形状
    try:
        page_count = len(client.pages(course_id))
    except cc.CanvasError:
        page_count = None
    manifest = cc.write_manifest(course, files, dest,
                                 note=("失败 %d 个" % failed) if failed else "",
                                 page_count=page_count)
    print("清单已更新:", manifest)
    return 1 if failed else 0


def cmd_manifest(client, course_id=None, all_courses=False):
    targets = [client.course(c["id"], includes=("term",)) for c in client.courses()] \
        if all_courses else [client.course(course_id, includes=("term",))]
    for course in targets:
        dest = os.path.join(cc.COURSE_FILES_DIR, cc.course_dir_name(course))
        try:
            files, note = client.list_course_files(course["id"])
        except cc.CanvasError as exc:
            files, note = None, "文件列表不可用 (HTTP %s)" % exc.status
        out = cc.write_manifest(course, files, dest, note=note)
        print("课程: %s\n  -> %s" % (course.get("name"), out))
    return 0


def submission_label(item):
    """从作业自带的 submission 字段给出「交没交」的状态标签。

    `canvas assignments` 请求时带了 `include[]=submission`，所以正常情况下
    这里能拿到状态，不必再逐条多发一个请求。

    **读不到状态时明确标记，绝不当成「未提交」**——这类静默误判会让人误以为
    还没交而重复提交，比直接报错更糟。
    """
    submission = item.get("submission")
    if not isinstance(submission, dict):
        return "状态未知"
    state = submission.get("workflow_state")
    if submission.get("submitted_at"):
        stamp = str(submission["submitted_at"])[:10]
        return "已评分" if submission.get("graded_at") else "已提交 %s" % stamp
    if state == "graded":
        return "已评分"
    if state == "unsubmitted" or state is None:
        return "未提交"
    return str(state)


def cmd_deadlines(client, days=14):
    """近 N 天要交的东西：作业 / 考试（Canvas 里考试也是 assignment）。"""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    rows = []
    for course in client.courses():
        try:
            assignments = client.assignments(course["id"])
        except cc.CanvasError as exc:
            print("  [跳过] %s: HTTP %s" % (course.get("name"), exc.status))
            continue
        for item in assignments:
            due = item.get("due_at")
            if not due:
                continue
            try:
                when = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
            except ValueError:
                continue
            if now - timedelta(days=1) <= when <= horizon:
                rows.append((when, course.get("name"), item))

    rows.sort(key=lambda row: row[0])
    if not rows:
        print("未来 %d 天内没有截止的作业（以 Canvas 已发布的 due_at 为准）。" % days)
        return 0

    print("未来 %d 天内要交的（共 %d 项）：" % (days, len(rows)))
    print("%-17s  %-28s  %-30s  %-10s  %s" % (
        "截止(本地时间)", "课程", "作业", "状态", "提交方式"))
    for when, course_name, item in rows:
        local = when.astimezone().strftime("%m-%d %a %H:%M")
        print("%-17s  %-28s  %-30s  %-10s  %s" % (
            local, (course_name or "")[:28], (item.get("name") or "")[:30],
            submission_label(item), ",".join(item.get("submission_types") or [])))
    print("\n状态来自 Canvas 的 submission 字段（未提交/已提交/已评分）；"
          "读取失败会明确标出，不会静默当成未提交。")
    print("提交前务必再核对 Canvas 页面：due_at 可能被老师改过，"
          "有些作业是线下交或通过邮件交。")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="canvas", description="Canvas 命令行工具（凭据见 .env / 环境变量）")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="自检凭据、连通性与权限")
    sub.add_parser("whoami", help="打印当前账号")

    p_courses = sub.add_parser("courses", help="列出我的课程")
    p_courses.add_argument("--all-terms", action="store_true", help="包含已结束学期的课程")

    p_files = sub.add_parser("files", help="列出某门课的可下载文件")
    p_files.add_argument("course_id")

    p_down = sub.add_parser("download", help="下载某门课的课程资料")
    p_down.add_argument("course_id")
    p_down.add_argument("--dest", default=None, help="自定义保存目录")
    p_down.add_argument("--dry-run", action="store_true", help="只列出将下载的文件，不落盘")
    p_down.add_argument("--term-prefix", action="store_true", help="目录名前缀加学期")

    p_man = sub.add_parser("manifest", help="写/更新 MANIFEST.md 增量清单")
    p_man.add_argument("course_id", nargs="?")
    p_man.add_argument("--all", action="store_true", help="所有 active 课程")

    p_due = sub.add_parser("deadlines", help="列出近期截止的作业")
    p_due.add_argument("--days", type=int, default=14, help="往后看多少天（默认 14）")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    try:
        client = cc.CanvasClient()
    except cc.NotConfigured as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if args.cmd == "doctor":
            return cmd_doctor(client)
        if args.cmd == "whoami":
            return cmd_whoami(client)
        if args.cmd == "courses":
            return cmd_courses(client, all_terms=args.all_terms)
        if args.cmd == "files":
            return cmd_files(client, args.course_id)
        if args.cmd == "download":
            return cmd_download(client, args.course_id, args.dest,
                                dry_run=args.dry_run, term_prefix=args.term_prefix)
        if args.cmd == "manifest":
            if not args.all and not args.course_id:
                parser.error("manifest 需要 course_id 或 --all")
            return cmd_manifest(client, args.course_id, all_courses=args.all)
        if args.cmd == "deadlines":
            return cmd_deadlines(client, days=args.days)
    except cc.CanvasError as exc:
        print("错误:", exc, "\n提示:", exc.hint, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
