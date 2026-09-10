#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core import connect, init_db

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--payload",type=Path,required=True)
    p.add_argument("--result",type=Path,required=True)
    args=p.parse_args()
    payload=json.loads(args.payload.read_text(encoding="utf-8"))
    result=json.loads(args.result.read_text(encoding="utf-8"))
    edition=str(payload["edition"])
    if result.get("edition") != edition:
        raise SystemExit("payload/result edition mismatch")
    if result.get("status") not in {"published","already_published","updated"}:
        raise SystemExit(f"publication not successful: {result.get('status')}")
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode("utf-8")
    init_db()
    with connect() as db:
        db.execute("""INSERT INTO publications(
            edition_date,channel,title,payload_hash,remote_topic_id,remote_post_id,
            remote_url,status,created_at,error
        ) VALUES(?,?,?,?,?,?,?,?,?,NULL)
        ON CONFLICT(edition_date,channel) DO UPDATE SET
            title=excluded.title,payload_hash=excluded.payload_hash,
            remote_topic_id=excluded.remote_topic_id,remote_post_id=excluded.remote_post_id,
            remote_url=excluded.remote_url,status=excluded.status,error=NULL""",
            (edition,"discourse",str(payload["title"]),hashlib.sha256(raw).hexdigest(),
             result.get("topic_id"),result.get("post_id"),result.get("url"),"published",
             datetime.now(timezone.utc).isoformat()))
    print(json.dumps({"recorded":True,"edition":edition,"topic_id":result.get("topic_id")},ensure_ascii=False))

if __name__=="__main__":
    main()
