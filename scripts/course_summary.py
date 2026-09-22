#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课程信息汇总：把某门课（或全部课）的考核、作业、组队要求抓下来，生成 README。

用法（仓库根目录执行）：
    uv run canvas-summary 12345          # 处理一门课
    uv run canvas-summary --all          # 处理所有 active 课程
    uv run canvas-summary --index        # 重建顶层 COURSES.md

产出（写入 `CourseFiles/<课程目录>/`）：
    README.md           课程要点（概述 / 评分占比 / 作业表 / 组队要求 / 资料清单）
    syllabus.md         大纲全文
    pages/*.md          课程页面转 Markdown
    announcements/*.md  公告全文

这些都是**给你自己和 AI 助读用的快照**，不是作业提交件；不要把它交给老师。
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import canvas_client as cc

# --------------------------------------------------------------------------- #
# 可调参数：不同学校的措辞不一样，改这里就行，不用动下面的逻辑
# --------------------------------------------------------------------------- #
#: 大纲里「课程概述」段落的起止标题（找不到就用大纲开头）
SECTION_DESCRIPTION = ("Course Description", "Course Intended Learning Outcomes")

#: 从大纲里尽力抽取的课程信息字段（教师、上课时间等）
SECTION_INFO_KEYS = [
    "Instructor", "Teaching Assistant", "Lecture Time", "Tutorial Time",
    "Venue", "Medium of Instruction", "Credit Units",
]

#: 组队/项目章节的标题关键词（用于定位大纲里的段落，以及筛公告）
GROUP_KEYWORDS = r"(group|team|partner|member|contribution|组队|小组|团队|分工)"

#: 概述段的兜底停止词。很多大纲是**没有编号的段落式**（每个小标题就是一行），
#: 这时既拿不到配置的 end、也没有 `3. Assessment` 这种编号可依；
#: 若不放兜底，"概述"会把整份大纲吞进来，让 README 里评分/组队内容重复一遍。
#: 自己学校的措辞不一样就往这里加词。
DESCRIPTION_STOP_MARKERS = [
    "assessment", "grading", "intended learning outcomes", "learning outcomes",
    "group project", "course schedule", "teaching and learning", "考核", "评分", "学习成果",
]

#: 「标签 + 百分比」的识别（评分占比）。英文/中文标题都支持。
PERCENT_PATTERN = re.compile(r"([A-Za-z\u4e00-\u9fff][^\n]*?)\s*\n\s*\n?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.M)


def to_text(raw_html):
    """把 Canvas 返回的 HTML 正文压成纯文本（保留段落换行）。"""
    if not raw_html:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.S | re.I)
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def section(text, start, end=None, limit=1500):
    """截取 start..end 之间的文本；找不到 start 返回空串。

    主要用途是取「课程概述」。两个坑：

    1. 很多大纲的人话标题和程序里配的 `end` 对不上（措辞不同、干脆没有），
       这时若一路读到 `limit`，概述会把**整份大纲**吞进来 —— 评分占比、
       组队要求会在 README 里重复出现。所以 end 找不到时，退而求其次停在
       **下一个编号小标题**（`3. Assessment` 之类），这也更符合"一节"的语义。
    2. 万一连编号标题都没有，才用 `limit` 兜底，避免打印整篇。
    """
    if not text:
        return ""
    pos = text.lower().find(start.lower())
    if pos < 0:
        return ""
    body_start = pos + len(start)
    if end:
        nxt = text.lower().find(end.lower(), body_start)
        if nxt > pos:
            return text[pos:nxt].strip()
    # end 没命中：停在下一条编号小标题之前
    nxt_section = re.search(r"(?m)^\s*\d+\.\s+[A-Za-z\u4e00-\u9fff]", text[body_start:])
    if nxt_section:
        stop = body_start + nxt_section.start()
        if stop > pos:
            return text[pos:stop].strip()
    # 段落式大纲（无编号）：
    #   a) 先试已知章节名兜底
    stop = _find_first_marker(text, body_start)
    if stop is not None:
        return text[pos:stop].strip()
    #   b) 都没有就按字数截断，并在句子边界收尾
    if len(text) - pos > limit:
        cut = text.rfind(".", pos, pos + limit)
        return text[pos:cut + 1 if cut > pos else pos + limit].strip()
    return text[pos:pos + limit].strip()


def _find_first_marker(text, body_start):
    """在 text[body_start:] 里找最早的已知章节名，返回绝对位置；找不到返回 None。

    注意 min 长度限制：不能在 body_start 之前找，否则 "Assessment" 出现在
    概述正文里时会把自己截断成空串。
    """
    lowered = text.lower()
    best = None
    for marker in DESCRIPTION_STOP_MARKERS:
        idx = lowered.find(marker.lower(), body_start)
        if idx >= 0 and (best is None or idx < best):
            best = idx
    return best


def percent_pairs(text):
    """从大纲文本里抽「标签 + N%」，得到评分占比。

    兼容标题与百分比分行的情况（`Assignments\\n20%`）。
    """
    rows = []
    for label, pct in PERCENT_PATTERN.findall(text or ""):
        label = label.strip()
        if not label:
            continue
        if re.search(r"\d", label.split()[-1] if label.split() else ""):
            continue        # 形如 "2. " 的编号行，不是标签
        if len(label) > 80:
            continue
        rows.append((label, pct))
    return rows


def block_after(text, word, maxlen=1400):
    """取以 `word` 为标题的章节，边界为下一个编号章节或下一个已知章节名。

    优先匹配 `5. Group Project` 这种带编号的小标题（最稳，能避免误配正文里
    同名的词）；很多大纲是**段落式、没有编号**的，这时退回"整行就是标题"的
    匹配，并用下一个已知章节名收尾，别把整份大纲都吞进来。
    """
    if not text:
        return ""

    match = re.search(r"(?im)^\s*\d+\.\s+%s\b" % re.escape(word), text)
    if not match:
        # 段落式：标题独占一行（允许行首空白），如 "Group Project"
        match = re.search(r"(?im)^\s*%s\s*$" % re.escape(word), text)
    if not match:
        return ""

    start = match.start()
    # 若匹配到的是正文里出现的同名词而不是标题行，后面只有少量文字时不必取值
    after = text.find("\n", start)
    if after < 0:
        return text[start:start + maxlen].strip()
    after += 1
    nxt = re.search(r"(?m)^\s*\d+\.\s+[A-Za-z\u4e00-\u9fff]", text[after:])
    if nxt:
        return text[start:after + nxt.start()].strip()
    # 无编号：停在下一条已知章节名之前
    stop = _find_first_marker(text, after)
    if stop is not None:
        return text[start:stop].strip()
    return text[start:start + maxlen].strip()


def opening_description(text, limit=600, min_chars=40):
    """无 "Course Description" 标题时，取大纲开场文字作为概述。

    做法：找到第一个已知章节名（CILOs / 评分 / 组队…），取它之前的文字。
    - 开头若只有一行很短的标题（如 "CS101: Intro"），跳过它再取；
    - 取不到足够内容就返回空串，让调用方走别的兜底。
    """
    if not text:
        return ""
    stop = _find_first_marker(text, 0)
    chunk = (text[:stop] if stop is not None else text[:limit]).strip()
    if chunk:
        first, _, rest = chunk.partition("\n")
        if len(first.strip()) < min_chars and rest.strip():
            chunk = rest.strip()
    if len(chunk) < min_chars:
        return ""
    return chunk[:limit].rstrip()


def safe_slug(value, maxlen=60):
    name = re.sub(r"[^\w.-]+", "-", str(value or "item"), flags=re.UNICODE).strip("-")
    return (name or "item")[:maxlen]


def save(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# --------------------------------------------------------------------------- #
# 抓取与转换
# --------------------------------------------------------------------------- #
def dump_pages(client, course_id, dest):
    try:
        pages = client.pages(course_id)
    except cc.CanvasError as exc:
        print("  [页面拉取失败] %s" % exc)
        return []
    out = []
    for page in pages:
        slug = page.get("url") or ("page-%s" % page.get("page_id"))
        try:
            detail = client.page(course_id, slug)
        except cc.CanvasError:
            continue
        body = to_text(detail.get("body"))
        path = os.path.join(dest, "pages", safe_slug(slug) + ".md")
        save(path, "# %s\n\n> 来源: Canvas 课程页面（%s）\n\n%s\n" % (
            detail.get("title", slug), detail.get("html_url"), body))
        out.append((path, body))
    return out


def dump_announcements(client, course_id, dest):
    try:
        announcements = client.announcements(course_id)
    except cc.CanvasError as exc:
        print("  [公告拉取失败] %s" % exc)
        return []
    out = []
    for ann in announcements:
        try:
            detail = client.announcement(course_id, ann.get("id"))
        except cc.CanvasError:
            detail = ann
        title = detail.get("title") or "announcement"
        body = to_text(detail.get("message"))
        path = os.path.join(dest, "announcements", safe_slug(title) + ".md")
        save(path, "# %s\n\n> 发布时间: %s\n\n%s\n" % (
            title, str(detail.get("posted_at"))[:16], body))
        out.append((path, title, body))
    return out


def group_requirements(announcements):
    """从公告里挑出与组队/项目相关的。"""
    found = []
    for path, title, body in announcements:
        if re.search(GROUP_KEYWORDS, title, re.I) or re.search(GROUP_KEYWORDS, body, re.I):
            found.append((title, body, path))
    return found


def build_readme(course, groups, assignments, syllabus_text, announcements, files, now=None):
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    term = (course.get("term") or {}).get("name", course.get("enrollment_term_id"))
    lines = [
        "# README — %s" % course.get("name"),
        "",
        "- **课程 ID**：%s" % course.get("id"),
        "- **学期**：%s" % term,
        "- **快照时间**：%s（Canvas 当前已发布内容）" % now,
        "",
        "## 概述",
    ]

    desc = section(syllabus_text, *SECTION_DESCRIPTION)
    if not desc:
        # 很多大纲（实测有课程如此）根本没有 "Course Description" 标题，
        # 开头第一段就是描述，之后就进入 CILOs / 评分。此时取已知章节之前的开场文字，
        # 别再退回"整份大纲前 600 字"——那样会把评分和组队内容一起搬进概述。
        desc = opening_description(syllabus_text)
    desc = re.sub(r"\s*\d+\.\s*$", "", desc)
    if desc:
        lines.append(desc)
    elif syllabus_text:
        lines.append(syllabus_text[:600] + ("…" if len(syllabus_text) > 600 else ""))
    else:
        lines.append("（大纲未发布或缺少课程描述）")
    lines.append("")

    info_items = []
    for key in SECTION_INFO_KEYS:
        value = section(syllabus_text, key, limit=120)
        if value:
            rows = [row.strip() for row in value.replace(key, "").strip().splitlines() if row.strip()]
            if rows:
                info_items.append("- %s：%s" % (key, " / ".join(rows[:2])))
    if info_items:
        lines += ["## 课程信息"] + info_items + [""]

    lines += ["## 评分占比（考试 vs 平时分）"]
    pairs = percent_pairs(syllabus_text)
    if pairs:
        lines += ["- %s：%s%%" % (label, pct) for label, pct in pairs]
    else:
        weights = [(g.get("name"), g.get("group_weight")) for g in groups or []
                   if g and g.get("group_weight") not in (None, 0)]
        if weights:
            lines += ["- %s：%s%%" % (name, weight) for name, weight in weights]
        else:
            lines.append("（考核/权重未配置或未发布）")
    lines.append("")

    lines += ["## 作业（Canvas 已发布）"]
    if assignments:
        lines += ["| 作业 | 分值 | 提交方式 | 截止 |", "|---|---|---|---|"]
        for item in assignments:
            lines.append("| %s | %s | %s | %s |" % (
                item.get("name"), item.get("points_possible"),
                ",".join(item.get("submission_types") or []),
                str(item.get("due_at"))[:10]))
    else:
        lines.append("（暂无已发布的 Canvas 作业）")
    lines.append("")

    lines += ["## 组队 / 项目要求"]
    project_block = block_after(syllabus_text, "Group Project")
    requirements = group_requirements(announcements)
    if project_block and len(project_block) > 30:
        lines.append(project_block)
    if requirements:
        for title, body, path in requirements:
            lines += ["", "**公告《%s》**（已存 `%s`）" % (title, os.path.relpath(path)),
                      "> " + "\n> ".join(body.splitlines())]
    if not project_block and not requirements:
        lines.append("（未发现项目/组队信息）")
    lines.append("")

    lines += ["## 课程资料（CourseFiles）"]
    lines += ["- `%s`" % rel for rel in files] if files else ["（暂无）"]
    lines += [
        "",
        "## 待更新",
        "> 以上是 Canvas 当前快照。老师可能在学期中继续发布考核/组队细节，",
        "> 到期前重跑 `uv run canvas-summary %s` 即可刷新。" % course.get("id"),
        "",
    ]
    return "\n".join(lines)


def process_course(client, course_id):
    course = client.course_with_syllabus(course_id)
    dest = os.path.join(cc.COURSE_FILES_DIR, cc.course_dir_name(course))
    syllabus_text = to_text(course.get("syllabus_body") or "")

    groups, assignments = [], []
    try:
        groups = client.assignment_groups(course_id)
        assignments = client.assignments(course_id)
    except cc.CanvasError as exc:
        print("  [考核/作业拉取失败] %s" % exc)

    announcements = dump_announcements(client, course_id, dest)
    pages = dump_pages(client, course_id, dest)

    if syllabus_text:
        save(os.path.join(dest, "syllabus.md"),
             "# Syllabus — %s\n\n%s\n" % (course.get("name"), syllabus_text))

    files = []
    for root, _, names in os.walk(dest):
        for name in names:
            if name in ("README.md", "MANIFEST.md", "syllabus.md") or name.startswith("~$"):
                continue
            files.append(os.path.relpath(os.path.join(root, name), dest))
    files.sort()

    save(os.path.join(dest, "README.md"),
         build_readme(course, groups, assignments, syllabus_text, announcements, files))
    print("课程: %s\n  -> %s\n     大纲 %d 字 / 页面 %d / 公告 %d" % (
        course.get("name"), dest, len(syllabus_text), len(pages), len(announcements)))


def rebuild_index(client):
    """重建顶层 COURSES.md —— 课程 ID → 本地目录 → 考核要点，给 AI 与你自己当索引用。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# COURSES — 课程索引", "",
        "> 本文件由 `uv run canvas-summary --index` 自动生成：课程 ID → 本地目录 → 考核要点。",
        "> 快照时间：%s。" % now,
        "", "## 总览", "",
        "| 课程 ID | 目录 | 学期 | 考核要点 |", "|---|---|---|---|",
    ]
    for course in client.courses():
        course_id = course.get("id")
        directory = cc.course_dir_name(course)
        term = (course.get("term") or {}).get("name", course.get("enrollment_term_id"))
        try:
            detail = client.course_with_syllabus(course_id)
            pairs = percent_pairs(to_text(detail.get("syllabus_body")))
            if pairs:
                assessment = " + ".join("%s %s%%" % (label, pct) for label, pct in pairs)
            else:
                weights = [("%s %s%%" % (g.get("name"), g.get("group_weight")))
                           for g in client.assignment_groups(course_id)
                           if g.get("group_weight") not in (None, 0)]
                assessment = " + ".join(weights) if weights else "考核未发布"
        except cc.CanvasError as exc:
            assessment = "获取失败（HTTP %s）" % exc.status
        lines.append("| %s | `%s` | %s | %s |" % (course_id, directory, term, assessment))
    lines += ["", "> 详细要点见 `CourseFiles/<课程目录>/README.md`。", ""]
    save("COURSES.md", "\n".join(lines))
    print("已更新 COURSES.md")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Canvas 课程信息汇总")
    parser.add_argument("course_id", nargs="?", help="课程 ID（不知道就先用 canvas courses 列出来）")
    parser.add_argument("--all", action="store_true", help="处理所有 active 课程")
    parser.add_argument("--index", action="store_true", help="重建顶层 COURSES.md")
    args = parser.parse_args(argv)

    try:
        client = cc.CanvasClient()
    except cc.NotConfigured as exc:
        raise SystemExit(str(exc))

    try:
        if args.index:
            rebuild_index(client)
        elif args.all:
            for course in client.courses():
                print("-" * 60)
                try:
                    process_course(client, course.get("id"))
                except cc.CanvasError as exc:
                    print("  %s 出错: %s（%s）" % (course.get("name"), exc, exc.hint))
        elif args.course_id:
            process_course(client, args.course_id)
        else:
            raise SystemExit("请提供 course_id，或使用 --all / --index")
    except cc.CanvasError as exc:
        print("错误:", exc, "\n提示:", exc.hint, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
