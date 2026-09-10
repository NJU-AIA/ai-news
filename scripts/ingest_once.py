#!/usr/bin/env python3
import json
from app.core import ingest_all
print(json.dumps(ingest_all(),ensure_ascii=False,indent=2))
