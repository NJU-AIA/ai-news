#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core import review_candidates, review_stats, save_reviews


def main() -> None:
    parser = argparse.ArgumentParser(description="AIA 新闻情报站 GPT 编辑工具")
    sub = parser.add_subparsers(dest="command", required=True)

    candidates = sub.add_parser("candidates", help="导出尚未审阅的近期候选")
    candidates.add_argument("--limit", type=int, default=80)
    candidates.add_argument("--days", type=int, default=4)

    apply_cmd = sub.add_parser("apply", help="导入 GPT 审阅 JSON")
    apply_cmd.add_argument("path", type=Path)

    sub.add_parser("stats", help="查看编辑层状态")
    args = parser.parse_args()

    if args.command == "candidates":
        print(json.dumps(review_candidates(args.limit, args.days), ensure_ascii=False, indent=2))
    elif args.command == "apply":
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        reviews = payload["reviews"] if isinstance(payload, dict) else payload
        print(json.dumps(save_reviews(reviews), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(review_stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
