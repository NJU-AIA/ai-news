#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import random
import re
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core import query_reviewed

BASE_URL = "https://news.nju-aia.com"
SECTION_ORDER = ("要闻", "模型发布", "开发生态", "前瞻传闻")
SECTION_ICON = {"要闻": "🔴", "模型发布": "🔵", "开发生态": "🟢", "前瞻传闻": "🟡"}
MAX_ITEMS = 9
ARCHIVE_LIMIT = 3
TARGET_TOTAL_ITEMS = 9
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def md(text: str) -> str:
    return str(text or "").replace("[", "［").replace("]", "］").strip()


def compact(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rstrip("，、：:；;。 ")
    # Avoid ending in the middle of an English token.
    if cut and cut[-1].isascii() and cut[-1].isalnum():
        boundary = max(cut.rfind(" "), cut.rfind("-"), cut.rfind("/"))
        if boundary >= max(8, len(cut) - 14):
            cut = cut[:boundary].rstrip("，、：:；;。 ")
    return cut + "…"


def brief_text(text: str, limit: int = 112) -> str:
    value = compact(text, limit)
    if value and value[-1] not in "。！？!?；;…":
        value = value.rstrip("，、：: ") + "…"
    return value


def edition_window(edition: str) -> tuple[datetime, datetime]:
    # The editorial policy moved the daily cutoff from 07:00 to 08:15.
    # 2026-08-07 is the one-time bridge edition: start at the previous
    # production cutoff (07:00 on Aug 6) so the migration creates no gap.
    edition_day = datetime.fromisoformat(edition).replace(
        hour=8, minute=15, second=0, microsecond=0, tzinfo=BEIJING_TZ
    )
    window_start = edition_day - timedelta(days=1)
    if edition == "2026-08-07":
        window_start = (edition_day - timedelta(days=1)).replace(hour=7, minute=0)
    return window_start, edition_day


def parse_item_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(BEIJING_TZ)


def select(date: str | None) -> tuple[str, list[dict[str, Any]], int]:
    all_items = query_reviewed(limit=1000, days=3650)
    if not all_items:
        raise RuntimeError("没有可发布的已审阅内容")
    edition = date or datetime.now(BEIJING_TZ).date().isoformat()
    window_start, window_end = edition_window(edition)
    items = []
    for item in all_items:
        if item.get("category") == "其他":
            continue
        published_at = parse_item_time(item.get("published_at"))
        if published_at is not None and window_start <= published_at < window_end:
            items.append(item)
    total = len(items)
    items = sorted(items, key=importance, reverse=True)[:MAX_ITEMS]
    items.sort(key=lambda x: (
        SECTION_ORDER.index(x.get("brief_section", "要闻")) if x.get("brief_section", "要闻") in SECTION_ORDER else len(SECTION_ORDER),
        -int(bool(x.get("is_shock"))), -int(bool(x.get("is_featured"))), -int(x.get("quality_score") or 0),
    ))
    return edition, items, total


def importance(item: dict[str, Any]) -> tuple[int, int, int]:
    return (int(bool(item.get("is_shock"))), int(bool(item.get("is_featured"))), int(item.get("quality_score") or 0))


def title_for(edition: str, items: list[dict[str, Any]], archive_items: list[dict[str, Any]]) -> str:
    if items:
        top = sorted(items, key=importance, reverse=True)[0]
        subject = re.split(r"[：:]", str(top["title_zh"]), maxsplit=1)[0].strip()
        return f"AIA AI 日报｜{edition}：{compact(subject, 36)}"
    if archive_items:
        return f"AIA AI 日报｜{edition}：本期无新增，回顾近期精选"
    return f"AIA AI 日报｜{edition}：本期无新增"


def select_archive_picks(edition: str, current_ids: set[int], current_count: int) -> list[dict[str, Any]]:
    needed = min(ARCHIVE_LIMIT, max(0, TARGET_TOTAL_ITEMS - current_count))
    if needed == 0:
        return []
    candidates = [
        x for x in query_reviewed(limit=1000, days=30)
        if x.get("editorial_date", "") < edition
        and x.get("category") != "其他"
        and x.get("is_featured")
        and int(x["item_id"]) not in current_ids
    ]
    # Stable randomness: rerunning the same edition yields the same archive picks.
    rng = random.Random(f"AIA-archive-{edition}")
    rng.shuffle(candidates)
    return candidates[:needed]


def build(edition: str, items: list[dict[str, Any]], total: int, archive_items: list[dict[str, Any]]) -> str:
    featured = sum(bool(x.get("is_featured")) for x in items)
    shock = sum(bool(x.get("is_shock")) for x in items)
    ranked = sorted(items, key=importance, reverse=True)
    lines = [f"# AIA AI 日报｜{edition}", ""]
    if items:
        lines.extend([
            f"> 本帖压缩呈现 **{len(items)}** 条 AI 进展（站内本期共 {total} 条）：**{featured}** 条精选，**{shock}** 条进入「震惊瘫坐」。",
            "", "## 30 秒结论", "",
        ])
        for idx, item in enumerate(ranked[:3], 1):
            lines.append(f"{idx}. {md(brief_text(item.get('brief_zh') or item.get('summary_zh'), 108))}")
    else:
        lines.append(
            f"> 本期北京时间 08:15–08:15 窗口内 **今日新增 0 条**。"
            + (f"以下仅回顾 **{len(archive_items)}** 条往期精选，且不计入今日新增。" if archive_items else "")
        )
    number = 1
    for section in SECTION_ORDER:
        section_items = [x for x in items if x.get("brief_section", "要闻") == section]
        if not section_items:
            continue
        lines.extend(["", f"## {SECTION_ICON[section]} {section}", ""])
        for item in section_items:
            badges = ("⭐" if item.get("is_featured") else "") + ("🤯" if item.get("is_shock") else "")
            prefix = f"{badges} " if badges else ""
            detail = f"{BASE_URL}/article/{item['item_id']}"
            lines.extend([
                f"**{number}. {prefix}[{md(item['title_zh'])}]({detail})**  ",
                md(brief_text(item.get("brief_zh") or item.get("summary_zh"), 112)), "",
            ])
            number += 1
    if archive_items:
        lines.extend([
            "", "## 📚 往期精选", "",
            "> 以下内容来自近 30 天的精选回顾，不计入今日新增，也不会冒充当日新闻。", "",
        ])
        for item in archive_items:
            detail = f"{BASE_URL}/article/{item['item_id']}"
            lines.extend([
                f"**[⭐ {md(item['title_zh'])}]({detail})**  ",
                md(brief_text(item.get("brief_zh") or item.get("summary_zh"), 112)), "",
            ])
    lines.extend([
        "---", "",
        f"🔎 [查看完整方法、关键结果、局限与原始来源]({BASE_URL}/)", "",
        "欢迎直接回复编号，讨论你认为最值得关注的进展。", "",
        "<small>⭐ = 精选；🤯 = 震惊瘫坐。内容由 AIA 新闻情报站完成事件去重、中文化与编辑审阅。</small>",
    ])
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    edition, items, total = select(args.date)
    current_ids = {int(x["item_id"]) for x in items}
    archive_items = select_archive_picks(edition, current_ids, len(items))
    payload = {
        "edition": edition,
        "title": title_for(edition, items, archive_items),
        "raw": build(edition, items, total, archive_items),
        "current_item_ids": sorted(current_ids),
        "archive_item_ids": [int(x["item_id"]) for x in archive_items],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"edition": edition, "items": len(items), "archive_items": len(archive_items), "available": total, "title": payload["title"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
