from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

BASE_DIR = Path(os.getenv("AI_NEWS_BASE_DIR", "/opt/ai-news"))
DATA_DIR = Path(os.getenv("AI_NEWS_DATA_DIR", "/var/lib/ai-news"))
DB_PATH = Path(os.getenv("AI_NEWS_DB", str(DATA_DIR / "news.db")))
CONFIG_PATH = Path(os.getenv("AI_NEWS_SOURCES", str(BASE_DIR / "config/sources.json")))
USER_AGENT = "NJU-AIA-AI-News/0.1 (+https://news.nju-aia.com)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})

TOPIC_RULES = {
    "推理": ["reasoning", "推理", "数学", "theorem", "lean", "proof", "rlvr", "grpo"],
    "Agent": ["agent", "智能体", "tool use", "computer use", "browser", "multi-agent"],
    "具身": ["robot", "robotics", "机器人", "具身", "embodied", "world model"],
    "记忆": ["memory", "记忆", "long context", "context window", "rag", "retrieval"],
    "NLP": ["nlp", "language model", "llm", "自然语言", "语言模型", "token", "transformer"],
    "多模态": ["multimodal", "多模态", "vision-language", "video", "audio", "图像", "视频"],
    "AI4Science": ["ai for science", "scienceai", "科学", "biology", "chemistry", "physics", "material"],
    "系统": ["system", "systems", "mlsys", "inference", "serving", "compiler", "gpu", "npu", "distributed", "分布式", "推理加速", "芯片", "存储", "网络"],
}

TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "from", "source"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc)
    text = str(value).strip()
    for fn in (dateparser.parse, parsedate_to_datetime):
        try:
            dt = fn(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def clean_text(value: str | None, limit: int = 500) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text[:limit]


def canonical_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(html.unescape(url.strip()))
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
    return urlunsplit((p.scheme or "https", p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(query, doseq=True), ""))


def classify(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    tags = [topic for topic, words in TOPIC_RULES.items() if any(word.lower() in text for word in words)]
    return tags or ["综合"]


def load_sources() -> list[dict[str, Any]]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["sources"]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS sources (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          kind TEXT NOT NULL,
          url TEXT,
          enabled INTEGER NOT NULL DEFAULT 1,
          verified INTEGER NOT NULL DEFAULT 0,
          notes TEXT,
          last_attempt TEXT,
          last_success TEXT,
          last_error TEXT,
          last_fetched_count INTEGER NOT NULL DEFAULT 0,
          last_new_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_id TEXT NOT NULL REFERENCES sources(id),
          external_id TEXT NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          summary TEXT,
          author TEXT,
          published_at TEXT,
          discovered_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          topics TEXT NOT NULL,
          raw_json TEXT,
          UNIQUE(source_id, external_id)
        );
        CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id, published_at DESC);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          success_count INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0,
          new_count INTEGER NOT NULL DEFAULT 0,
          detail_json TEXT
        );
        CREATE TABLE IF NOT EXISTS reviews (
          item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
          title_zh TEXT NOT NULL,
          category TEXT NOT NULL,
          content_type TEXT NOT NULL,
          summary_zh TEXT NOT NULL,
          methodology_zh TEXT NOT NULL DEFAULT '',
          findings_zh TEXT NOT NULL DEFAULT '',
          limitations_zh TEXT NOT NULL DEFAULT '',
          brief_zh TEXT NOT NULL DEFAULT '',
          brief_section TEXT NOT NULL DEFAULT '要闻',
          why_zh TEXT NOT NULL,
          read_minutes INTEGER NOT NULL DEFAULT 3,
          tags TEXT NOT NULL,
          relevance TEXT NOT NULL DEFAULT 'high',
          quality_score INTEGER NOT NULL DEFAULT 0,
          is_featured INTEGER NOT NULL DEFAULT 0,
          feature_reason TEXT NOT NULL DEFAULT '',
          is_shock INTEGER NOT NULL DEFAULT 0,
          shock_reason TEXT NOT NULL DEFAULT '',
          evidence_links TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL DEFAULT 'published',
          editorial_date TEXT NOT NULL,
          reviewed_at TEXT NOT NULL,
          reviewer TEXT NOT NULL DEFAULT 'GPT'
        );
        CREATE INDEX IF NOT EXISTS idx_reviews_editorial_date ON reviews(editorial_date DESC);
        CREATE INDEX IF NOT EXISTS idx_reviews_category ON reviews(category, editorial_date DESC);
        CREATE TABLE IF NOT EXISTS publications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          edition_date TEXT NOT NULL,
          channel TEXT NOT NULL,
          title TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          remote_topic_id INTEGER,
          remote_post_id INTEGER,
          remote_url TEXT,
          status TEXT NOT NULL DEFAULT 'published',
          created_at TEXT NOT NULL,
          error TEXT,
          UNIQUE(edition_date, channel)
        );
        ''')
        review_columns = {row["name"] for row in db.execute("PRAGMA table_info(reviews)")}
        review_migrations = {
            "methodology_zh": "TEXT NOT NULL DEFAULT ''",
            "findings_zh": "TEXT NOT NULL DEFAULT ''",
            "limitations_zh": "TEXT NOT NULL DEFAULT ''",
            "brief_zh": "TEXT NOT NULL DEFAULT ''",
            "brief_section": "TEXT NOT NULL DEFAULT '要闻'",
            "quality_score": "INTEGER NOT NULL DEFAULT 0",
            "is_featured": "INTEGER NOT NULL DEFAULT 0",
            "feature_reason": "TEXT NOT NULL DEFAULT ''",
            "is_shock": "INTEGER NOT NULL DEFAULT 0",
            "shock_reason": "TEXT NOT NULL DEFAULT ''",
            "evidence_links": "TEXT NOT NULL DEFAULT '[]'",
        }
        for column, definition in review_migrations.items():
            if column not in review_columns:
                db.execute(f"ALTER TABLE reviews ADD COLUMN {column} {definition}")
        for s in load_sources():
            db.execute('''INSERT INTO sources(id,name,kind,url,enabled,verified,notes)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,url=excluded.url,
                enabled=excluded.enabled,verified=excluded.verified,notes=excluded.notes''',
                (s["id"], s["name"], s["kind"], s.get("url"), int(s.get("enabled", True)), int(s.get("verified", False)), s.get("notes", "")))


def fetch_url(url: str, *, timeout: int = 35, headers: dict[str, str] | None = None, verify: bool = True) -> requests.Response:
    merged = dict(SESSION.headers)
    if headers:
        merged.update(headers)
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = SESSION.get(url, headers=merged, timeout=timeout, verify=verify)
            if r.status_code in {429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def fetch_rss(source: dict[str, Any]) -> list[dict[str, Any]]:
    r = fetch_url(source["url"], headers={"Accept": "application/rss+xml, application/atom+xml, text/xml, */*"})
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries[: source.get("max_items", 80)]:
        link = e.get("link", "")
        title = clean_text(e.get("title", ""), 300)
        if not title or not link:
            continue
        published = parse_dt(e.get("published_parsed") or e.get("updated_parsed") or e.get("published") or e.get("updated"))
        summary = clean_text(e.get("summary") or e.get("description") or "")
        out.append({"external_id": str(e.get("id") or link), "title": title, "url": link, "summary": summary,
                    "author": clean_text(e.get("author", ""), 120), "published_at": published, "raw": {"feed_id": e.get("id")}})
    return out



def _meta_value(soup: BeautifulSoup, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for meta in soup.find_all("meta"):
        key = str(meta.get("property") or meta.get("name") or "").lower()
        if key in wanted:
            value = meta.get("content")
            if value:
                return clean_text(str(value), 1500)
    return ""


def _detail_metadata(url: str, *, fallback_title: str = "", fallback_date: Any = None) -> dict[str, Any]:
    """Extract normalized metadata from a first-party article page."""
    response = fetch_url(url)
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = response.apparent_encoding or "utf-8"
    page = response.text
    soup = BeautifulSoup(page, "html.parser")
    title = _meta_value(soup, "og:title", "twitter:title")
    if not title:
        heading = soup.find("h1")
        title = clean_text(heading.get_text(" ", strip=True) if heading else "", 300)
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True), 300)
    title = title or fallback_title
    summary = _meta_value(soup, "og:description", "twitter:description", "description")
    if not summary or clean_text(summary, 300).lower() == clean_text(title, 300).lower():
        for node in soup.find_all("p"):
            candidate = clean_text(node.get_text(" ", strip=True), 900)
            if len(candidate) >= 80 and candidate.lower() != clean_text(title, 300).lower():
                summary = candidate
                break
    author = _meta_value(soup, "author", "article:author")
    canonical_tag = soup.find("link", rel=lambda x: x and "canonical" in x)
    canonical = canonical_tag.get("href") if canonical_tag and canonical_tag.get("href") else url
    date_text = _meta_value(
        soup, "article:published_time", "date", "datepublished", "publishdate",
        "publication_date", "dc.date", "dc.date.issued"
    )
    if not date_text:
        time_tag = soup.find("time")
        if time_tag:
            date_text = str(time_tag.get("datetime") or time_tag.get_text(" ", strip=True) or "")
    if not date_text:
        patterns = [
            r'"(?:datePublished|publishedAt|publishDate|published_at|date)"\s*:\s*"([^"\\]+)"',
            r'(20\d{2}[/-]\d{2}[/-]\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, page, re.I)
            if match:
                date_text = match.group(1)
                break
    inferred_date = None
    path = urlsplit(url).path.rstrip("/")
    deepseek_match = re.search(r"/news/news(\d{6}|\d{4})$", path, re.I)
    if deepseek_match:
        digits = deepseek_match.group(1)
        if len(digits) == 6:
            inferred_date = parse_dt(f"20{digits[:2]}-{digits[2:4]}-{digits[4:6]}")
        else:
            inferred_date = parse_dt(f"2024-{digits[:2]}-{digits[2:4]}")
    return {
        "title": title,
        "summary": summary,
        "author": author,
        "url": urljoin(url, str(canonical)),
        "published_at": inferred_date or parse_dt(date_text) or parse_dt(fallback_date),
    }


def _read_sitemap(url: str, *, depth: int = 0) -> list[tuple[str, str]]:
    if depth > 3:
        return []
    root = ET.fromstring(fetch_url(url, headers={"Accept": "application/xml,text/xml,*/*"}).content)
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    if root.tag.endswith("sitemapindex"):
        out: list[tuple[str, str]] = []
        for loc in root.findall(f".//{namespace}loc"):
            if loc.text:
                out.extend(_read_sitemap(loc.text.strip(), depth=depth + 1))
        return out
    out = []
    for node in root.findall(f"{namespace}url"):
        loc = node.find(f"{namespace}loc")
        lastmod = node.find(f"{namespace}lastmod")
        if loc is not None and loc.text:
            out.append((loc.text.strip(), lastmod.text.strip() if lastmod is not None and lastmod.text else ""))
    return out


def fetch_sitemap_articles(source: dict[str, Any]) -> list[dict[str, Any]]:
    include = re.compile(source.get("include_regex") or r".", re.I)
    exclude = re.compile(source.get("exclude_regex") or r"$^", re.I)
    rows = [(u, d) for u, d in _read_sitemap(source["url"]) if include.search(u) and not exclude.search(u)]
    rows.sort(key=lambda x: x[1], reverse=True)
    out = []
    for url, lastmod in rows[: source.get("max_items", 40)]:
        try:
            meta = _detail_metadata(url, fallback_date=lastmod)
        except Exception:
            meta = {"title": "", "summary": "", "author": "", "url": url, "published_at": parse_dt(lastmod)}
        if not meta.get("title"):
            continue
        if source.get("require_canonical_match") and not include.search(meta.get("url") or ""):
            continue
        external = urlsplit(meta["url"]).path.strip("/") or hashlib.sha256(meta["url"].encode()).hexdigest()[:24]
        out.append({
            "external_id": external,
            "title": clean_text(meta["title"], 300),
            "url": meta["url"],
            "summary": clean_text(meta.get("summary"), 1500),
            "author": clean_text(meta.get("author") or source["name"], 160),
            "published_at": meta.get("published_at"),
            "raw": {"sitemap_lastmod": lastmod},
        })
    return out


def fetch_html_blog(source: dict[str, Any]) -> list[dict[str, Any]]:
    page = fetch_url(source["url"]).text
    soup = BeautifulSoup(page, "html.parser")
    pattern = re.compile(source.get("article_regex") or r"/blog/[^/?#]+/?$", re.I)
    seen: set[str] = set()
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = canonical_url(urljoin(source["url"], anchor.get("href", "")))
        if url in seen or not pattern.search(url):
            continue
        seen.add(url)
        links.append(url)
    out = []
    for url in links[: source.get("max_items", 40)]:
        try:
            meta = _detail_metadata(url)
        except Exception:
            continue
        if not meta.get("title"):
            continue
        external = urlsplit(meta["url"]).path.strip("/") or hashlib.sha256(meta["url"].encode()).hexdigest()[:24]
        out.append({
            "external_id": external,
            "title": clean_text(meta["title"], 300),
            "url": meta["url"],
            "summary": clean_text(meta.get("summary"), 1500),
            "author": clean_text(meta.get("author") or source["name"], 160),
            "published_at": meta.get("published_at"),
            "raw": {},
        })
    out.sort(key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out[: source.get("max_items", 40)]


def fetch_qwen_api(source: dict[str, Any]) -> list[dict[str, Any]]:
    language = source.get("api_language", "zh-CN")
    separator = "&" if "?" in source["url"] else "?"
    url = source["url"] + separator + urlencode({"language": language, "type": "qwen_ai"})
    data = fetch_url(url, headers={"Accept": "application/json", "X-Request-Id": hashlib.sha256(str(time.time()).encode()).hexdigest()[:32]}).json()
    articles = ((data.get("data") or {}).get("articles") or [])
    out = []
    for article in articles:
        extra = article.get("extra") or {}
        path = str(article.get("path") or article.get("id") or "").strip()
        title = clean_text(article.get("title"), 300)
        if not path or not title:
            continue
        summary = clean_text(extra.get("introduction") or extra.get("description") or "", 1500)
        out.append({
            "external_id": path,
            "title": title,
            "url": "https://qwen.ai/blog?" + urlencode({"id": article.get("id")}),
            "summary": summary,
            "author": clean_text(extra.get("author") or "Qwen Team", 160),
            "published_at": parse_dt(extra.get("date")),
            "raw": {
                "path": path,
                "tags": extra.get("tags") or [],
                "read_time": extra.get("readTime"),
                "word_count": extra.get("wordCount"),
            },
        })
    out.sort(key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out[: source.get("max_items", 60)]

def fetch_qbitai_wp(source: dict[str, Any]) -> list[dict[str, Any]]:
    # QbitAI's CDN intermittently resets large WordPress responses.  Fetch the
    # same 100-post discovery window with only the metadata needed by the
    # candidate queue (~60 KB instead of multi-megabyte full-content JSON).
    parts = urlsplit(source["url"])
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["_fields"] = "id,date,date_gmt,link,slug,title,excerpt"
    compact_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))
    headers = {
        "Accept": "application/json",
        "Referer": "https://www.qbitai.com/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    }
    try:
        r = fetch_url(compact_url, headers=headers)
        data = r.json()
    except Exception as api_error:
        # RSS is a deliberately smaller emergency discovery window.  A working
        # fallback is preferable to silently losing all Chinese-media coverage.
        rss_source = dict(source)
        rss_source["url"] = source.get("fallback_url", "https://www.qbitai.com/feed")
        rss_source["max_items"] = min(int(source.get("max_items", 100)), 20)
        try:
            return fetch_rss(rss_source)
        except Exception as rss_error:
            raise RuntimeError(
                f"QbitAI compact API and RSS fallback both failed: API={api_error}; RSS={rss_error}"
            ) from rss_error

    out = []
    for post in data[: source.get("max_items", 100)]:
        pid = post.get("id")
        title = clean_text((post.get("title") or {}).get("rendered", ""), 300)
        link = post.get("link") or ""
        if not pid or not title or not link:
            continue
        excerpt = clean_text((post.get("excerpt") or {}).get("rendered", ""), 1500)
        published = parse_dt(post.get("date_gmt") or post.get("date"))
        out.append({
            "external_id": str(pid), "title": title, "url": link, "summary": excerpt,
            "author": "量子位", "published_at": published,
            "raw": {"slug": post.get("slug"), "excerpt": excerpt, "fetch_mode": "compact_wp"},
        })
    return out


def fetch_jiqizhixin(source: dict[str, Any]) -> list[dict[str, Any]]:
    r = fetch_url(source["url"], headers={"Accept": "application/json", "Referer": "https://www.jiqizhixin.com/articles/"}, verify=bool(source.get("tls_verify", True)))
    data = r.json()
    out = []
    for a in data.get("articles", []):
        slug = a.get("slug")
        if not slug:
            continue
        published_raw = a.get("publishedAt")
        published_at = None
        if published_raw:
            try:
                parsed = dateparser.parse(str(published_raw))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                published_at = parsed.astimezone(timezone.utc)
            except Exception:
                published_at = parse_dt(published_raw)
        out.append({"external_id": a.get("id") or slug, "title": clean_text(a.get("title"), 300),
                    "url": f"https://www.jiqizhixin.com/articles/{slug}", "summary": clean_text(a.get("content"), 500),
                    "author": a.get("author") or a.get("source") or "机器之心", "published_at": published_at,
                    "raw": {"category": a.get("category"), "tags": a.get("tagList", []), "publishedAt": published_raw}})
    return out


def fetch_hf(source: dict[str, Any]) -> list[dict[str, Any]]:
    data = fetch_url(source["url"], headers={"Accept": "application/json"}).json()
    out = []
    for row in data[: source.get("max_items", 80)]:
        p = row.get("paper", row)
        pid = p.get("id") or p.get("paperId")
        title = clean_text(p.get("title"), 300)
        if not pid or not title:
            continue
        summary = clean_text(p.get("summary") or p.get("abstract") or "", 700)
        published = parse_dt(row.get("publishedAt") or row.get("submittedOnDailyAt") or p.get("publishedAt"))
        out.append({"external_id": str(pid), "title": title, "url": f"https://huggingface.co/papers/{pid}",
                    "summary": summary, "author": ", ".join((x.get("name") or x.get("user", {}).get("fullname", "")) for x in p.get("authors", [])[:5]),
                    "published_at": published, "raw": {"upvotes": row.get("upvotes"), "githubRepo": p.get("githubRepo")}})
    return out


def fetch_thinking_machines(source: dict[str, Any]) -> list[dict[str, Any]]:
    page = fetch_url(source["url"]).text
    soup = BeautifulSoup(page, "html.parser")
    posts: list[dict[str, Any]] = []
    seen = set()
    for a in soup.select('a.post-item-link[href^="/blog/"]'):
        href = urljoin(source["url"], a.get("href", ""))
        if href in seen:
            continue
        seen.add(href)
        title_tag = a.select_one(".post-title")
        author_tag = a.select_one(".author-date")
        time_tag = a.find("time")
        posts.append({
            "href": href,
            "title": clean_text(title_tag.get_text(" ", strip=True) if title_tag else a.get_text(" ", strip=True), 300),
            "author": clean_text(author_tag.get_text(" ", strip=True) if author_tag else "Thinking Machines Lab", 160),
            "published_at": parse_dt(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)) if time_tag else None,
        })
    out = []
    for post in posts[: source.get("max_items", 30)]:
        href = post["href"]
        desc = ""
        try:
            detail = BeautifulSoup(fetch_url(href).text, "html.parser")
            desc_tag = detail.find("meta", property="og:description") or detail.find("meta", attrs={"name": "description"})
            desc = clean_text(desc_tag.get("content") if desc_tag else "", 700)
        except Exception:
            pass
        out.append({"external_id": href.rstrip("/").split("/")[-1], "title": post["title"], "url": href,
                    "summary": desc, "author": post["author"], "published_at": post["published_at"], "raw": {}})
    return out


def fetch_anthropic(source: dict[str, Any]) -> list[dict[str, Any]]:
    page = fetch_url(source["url"]).text
    soup = BeautifulSoup(page, "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/news/"]'):
        href = urljoin(source["url"], a.get("href", ""))
        if not href or href in seen:
            continue
        seen.add(href)
        title_tag = a.find(["h1", "h2", "h3"]) or a.select_one('[class*="title"]')
        title = clean_text(title_tag.get_text(" ", strip=True) if title_tag else "", 300)
        time_tag = a.find("time")
        published = parse_dt(time_tag.get("datetime") or time_tag.get_text(" ", strip=True)) if time_tag else None
        summary_tag = a.find("p")
        summary = clean_text(summary_tag.get_text(" ", strip=True) if summary_tag else "", 700)
        subject_tag = a.select_one('[class*="subject"]')
        subject = clean_text(subject_tag.get_text(" ", strip=True) if subject_tag else "", 120)
        if not title:
            continue
        out.append({
            "external_id": href.rstrip("/").split("/")[-1],
            "title": title,
            "url": href,
            "summary": summary,
            "author": "Anthropic" + (f" · {subject}" if subject else ""),
            "published_at": published,
            "raw": {"subject": subject},
        })
        if len(out) >= source.get("max_items", 80):
            break
    return out


def decode_sogou_link(session: requests.Session, sogou_url: str) -> str:
    try:
        text = session.get(sogou_url, timeout=20).text
        parts = re.findall(r"url \+= '([^']*)'", text)
        if parts:
            return "".join(parts).replace("@", "")
    except Exception:
        pass
    return sogou_url


def fetch_wechat_sogou(source: dict[str, Any]) -> list[dict[str, Any]]:
    query = source.get("query") or source["name"]
    aliases = set(source.get("account_aliases") or [source["name"]])
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"})
    search_url = "https://weixin.sogou.com/weixin?type=2&query=" + quote(query)
    text = s.get(search_url, timeout=25).text
    if "请输入验证码" in text:
        raise RuntimeError("Sogou captcha")
    blocks = re.findall(r'<li id="sogou_vr_11002601_box_[^"]+".*?</li>', text, re.S)
    out = []
    for b in blocks:
        account_m = re.search(r'<div class="s-p">\s*<span class="all-time-y2">(.*?)</span>', b, re.S)
        title_m = re.search(r'<h3>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        summary_m = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', b, re.S)
        ts_m = re.search(r"timeConvert\('([0-9]+)'\)", b)
        account = clean_text(account_m.group(1) if account_m else "", 120)
        if account not in aliases or not title_m:
            continue
        title = clean_text(title_m.group(2), 300)
        summary = clean_text(summary_m.group(1) if summary_m else "", 600)
        sogou_link = urljoin("https://weixin.sogou.com", html.unescape(title_m.group(1)))
        signed = decode_sogou_link(s, sogou_link)
        ts = int(ts_m.group(1)) if ts_m else None
        ext = hashlib.sha256(f"{account}|{title}|{ts or ''}".encode()).hexdigest()[:24]
        out.append({"external_id": ext, "title": title, "url": signed, "summary": summary, "author": account,
                    "published_at": parse_dt(ts), "raw": {"search_url": search_url, "sogou_url": sogou_link}})
    return out


FETCHERS = {"rss": fetch_rss, "qbitai_wp": fetch_qbitai_wp,
            "jiqizhixin_api": fetch_jiqizhixin, "huggingface_api": fetch_hf,
            "thinking_machines_html": fetch_thinking_machines, "anthropic_html": fetch_anthropic,
            "wechat_sogou": fetch_wechat_sogou, "sitemap_articles": fetch_sitemap_articles,
            "html_blog": fetch_html_blog, "qwen_api": fetch_qwen_api}


def upsert_items(source: dict[str, Any], items: list[dict[str, Any]]) -> tuple[int, int]:
    now = iso(utcnow())
    new_count = 0
    with connect() as db:
        for item in items:
            if not item.get("title") or not item.get("url"):
                continue
            canon = canonical_url(item["url"])
            topics = classify(item["title"], item.get("summary", ""))
            before = db.total_changes
            db.execute('''INSERT INTO items(source_id,external_id,title,url,canonical_url,summary,author,published_at,discovered_at,updated_at,topics,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id,external_id) DO UPDATE SET title=excluded.title,url=excluded.url,canonical_url=excluded.canonical_url,
                summary=excluded.summary,author=excluded.author,published_at=COALESCE(excluded.published_at,items.published_at),updated_at=excluded.updated_at,
                topics=excluded.topics,raw_json=excluded.raw_json''',
                (source["id"], str(item["external_id"]), item["title"], item["url"], canon, item.get("summary", ""), item.get("author", ""),
                 iso(item.get("published_at")), now, now, json.dumps(topics, ensure_ascii=False), json.dumps(item.get("raw", {}), ensure_ascii=False)))
            if db.total_changes > before:
                exists = db.execute("SELECT discovered_at FROM items WHERE source_id=? AND external_id=?", (source["id"], str(item["external_id"]))).fetchone()
                if exists and exists["discovered_at"] == now:
                    new_count += 1
        return len(items), new_count


def ingest_all() -> dict[str, Any]:
    init_db()
    started = iso(utcnow())
    details = []
    total_new = success = failed = 0
    for source in load_sources():
        if not source.get("enabled", True):
            details.append({"id": source["id"], "status": "disabled", "new": 0, "fetched": 0})
            continue
        attempt = iso(utcnow())
        try:
            fetcher = FETCHERS[source["kind"]]
            items = fetcher(source)
            fetched, new = upsert_items(source, items)
            with connect() as db:
                db.execute("UPDATE sources SET last_attempt=?,last_success=?,last_error=NULL,last_fetched_count=?,last_new_count=? WHERE id=?",
                           (attempt, iso(utcnow()), fetched, new, source["id"]))
            details.append({"id": source["id"], "status": "ok", "fetched": fetched, "new": new})
            total_new += new; success += 1
        except Exception as e:
            with connect() as db:
                db.execute("UPDATE sources SET last_attempt=?,last_error=?,last_fetched_count=0,last_new_count=0 WHERE id=?",
                           (attempt, str(e)[:600], source["id"]))
            details.append({"id": source["id"], "status": "failed", "error": str(e)[:600], "fetched": 0, "new": 0})
            failed += 1
    with connect() as db:
        db.execute("INSERT INTO runs(started_at,finished_at,success_count,failed_count,new_count,detail_json) VALUES(?,?,?,?,?,?)",
                   (started, iso(utcnow()), success, failed, total_new, json.dumps(details, ensure_ascii=False)))
    return {"started_at": started, "finished_at": iso(utcnow()), "success": success, "failed": failed, "new": total_new, "sources": details}


def query_items(limit: int = 100, source_id: str | None = None, topic: str | None = None, days: int | None = None) -> list[dict[str, Any]]:
    init_db()
    sql = '''SELECT i.*,s.name source_name,s.verified source_verified FROM items i JOIN sources s ON s.id=i.source_id WHERE 1=1'''
    args: list[Any] = []
    if source_id:
        sql += " AND i.source_id=?"; args.append(source_id)
    if topic:
        sql += " AND i.topics LIKE ?"; args.append(f'%"{topic}"%')
    if days is not None:
        cutoff = iso(utcnow() - timedelta(days=days))
        sql += " AND COALESCE(i.published_at,i.discovered_at)>=?"; args.append(cutoff)
    sql += " ORDER BY COALESCE(i.published_at,i.discovered_at) DESC LIMIT ?"; args.append(min(max(limit,1),500))
    with connect() as db:
        rows = db.execute(sql,args).fetchall()
    source_meta = {s["id"]: s for s in load_sources()}
    out=[]
    for r in rows:
        x=dict(r)
        x["topics"]=json.loads(x["topics"])
        x.pop("raw_json",None)
        meta=source_meta.get(x["source_id"], {})
        x["source_role"]=meta.get("role", "editorial")
        x["source_priority"]=int(meta.get("priority", 50))
        out.append(x)
    return out


def source_status() -> list[dict[str, Any]]:
    init_db()
    with connect() as db:
        rows=db.execute("SELECT * FROM sources ORDER BY verified DESC,name").fetchall()
    return [dict(r) for r in rows]


def stats() -> dict[str, Any]:
    init_db()
    now=utcnow()
    source_meta={s["id"]:s for s in load_sources()}
    cutoff=iso(now-timedelta(days=14))
    with connect() as db:
        total=db.execute("SELECT COUNT(*) n FROM items").fetchone()["n"]
        recent=db.execute('''SELECT source_id,substr(COALESCE(published_at,discovered_at),1,10) d,COUNT(*) n FROM items
            WHERE COALESCE(published_at,discovered_at)>=? GROUP BY source_id,d''',(cutoff,)).fetchall()
        by_source=db.execute('''SELECT s.id,s.name,COUNT(i.id) total,
            SUM(CASE WHEN COALESCE(i.published_at,i.discovered_at)>=? THEN 1 ELSE 0 END) recent7
            FROM sources s LEFT JOIN items i ON i.source_id=s.id GROUP BY s.id ORDER BY recent7 DESC''',(iso(now-timedelta(days=7)),)).fetchall()
    all_day=defaultdict(int); editorial_day=defaultdict(int)
    for r in recent:
        all_day[r["d"]]+=r["n"]
        if source_meta.get(r["source_id"],{}).get("role","editorial")=="editorial":
            editorial_day[r["d"]]+=r["n"]
    days=[(now-timedelta(days=i)).date().isoformat() for i in range(6,-1,-1)]
    counts=[all_day.get(d,0) for d in days]
    editorial_counts=[editorial_day.get(d,0) for d in days]
    sources=[]
    for r in by_source:
        x=dict(r); meta=source_meta.get(x["id"],{}); x["role"]=meta.get("role","editorial"); x["priority"]=meta.get("priority",50); sources.append(x)
    return {"total":total,"last7_total":sum(counts),"last7_daily_average":round(sum(counts)/7,2),
            "editorial_last7_total":sum(editorial_counts),"editorial_last7_daily_average":round(sum(editorial_counts)/7,2),
            "days":[{"date":d,"count":n,"editorial_count":e} for d,n,e in zip(days,counts,editorial_counts)],"sources":sources}


REVIEW_CATEGORIES = {"模型与推理", "训练与对齐", "Agent", "多模态", "具身智能", "系统与基础设施", "AI4Science", "产业与产品", "其他"}
BRIEF_SECTIONS = {"要闻", "模型发布", "开发生态", "前瞻传闻"}


def review_candidates(limit: int = 80, days: int = 4) -> list[dict[str, Any]]:
    """Return recent unreviewed candidates for the daily GPT editorial pass."""
    init_db()
    cutoff = iso(utcnow() - timedelta(days=max(1, days)))
    with connect() as db:
        rows = db.execute("""SELECT i.*,s.name source_name,s.verified source_verified
            FROM items i JOIN sources s ON s.id=i.source_id
            LEFT JOIN reviews r ON r.item_id=i.id
            WHERE r.item_id IS NULL AND COALESCE(i.published_at,i.discovered_at)>=?
            ORDER BY COALESCE(i.published_at,i.discovered_at) DESC LIMIT ?""",
            (cutoff, min(max(limit, 1), 300))).fetchall()
    source_meta = {x["id"]: x for x in load_sources()}
    result=[]
    for row in rows:
        item=dict(row)
        item["topics"]=json.loads(item["topics"])
        item["raw"]=json.loads(item.pop("raw_json") or "{}")
        meta=source_meta.get(item["source_id"], {})
        item["source_role"]=meta.get("role", "editorial")
        item["source_priority"]=int(meta.get("priority", 50))
        item["source_language"]=meta.get("language", "unknown")
        item["source_event_role"]=meta.get("event_role", "unknown")
        item["source_public_priority"]=int(meta.get("public_priority", meta.get("priority", 50)))
        result.append(item)
    return result


def save_reviews(reviews: list[dict[str, Any]], reviewer: str = "GPT") -> dict[str, int]:
    """Validate and upsert editorial reviews produced by the daily GPT task."""
    init_db()
    now = iso(utcnow())
    saved = hidden = featured = shock = 0
    with connect() as db:
        for review in reviews:
            item_id = int(review["item_id"])
            item_row = db.execute("SELECT source_id,title,published_at FROM items WHERE id=?", (item_id,)).fetchone()
            if not item_row:
                raise ValueError(f"unknown item_id: {item_id}")
            category = str(review.get("category") or "其他")
            if category not in REVIEW_CATEGORIES:
                raise ValueError(f"invalid category for item {item_id}: {category}")
            status = str(review.get("status") or "published")
            if status not in {"published", "hidden"}:
                raise ValueError(f"invalid status for item {item_id}: {status}")
            requested_editorial_date = str(review.get("editorial_date") or utcnow().date().isoformat())
            if status == "published":
                source_published_at = item_row["published_at"]
                if not source_published_at:
                    raise ValueError(f"published item {item_id} has no reliable source publication time")
                try:
                    source_dt = datetime.fromisoformat(str(source_published_at).replace("Z", "+00:00"))
                    if source_dt.tzinfo is None:
                        raise ValueError("naive timestamp")
                    source_dt = source_dt.astimezone(ZoneInfo("Asia/Shanghai"))
                except Exception as exc:
                    raise ValueError(f"invalid publication time for item {item_id}: {source_published_at}") from exc
                source_date = source_dt.date().isoformat()
                if requested_editorial_date != source_date:
                    raise ValueError(
                        f"item {item_id} was published on Beijing date {source_date} "
                        f"but editorial_date is {requested_editorial_date}"
                    )
            existing_review = db.execute(
                "SELECT status,editorial_date FROM reviews WHERE item_id=?", (item_id,)
            ).fetchone()
            if (
                existing_review
                and existing_review["status"] == "published"
                and status == "published"
                and existing_review["editorial_date"] != requested_editorial_date
            ):
                raise ValueError(
                    f"published item {item_id} is already assigned to edition "
                    f"{existing_review['editorial_date']} and cannot be moved to {requested_editorial_date}"
                )
            tags = review.get("tags") or (["未入选"] if status == "hidden" else [])
            if not isinstance(tags, list) or not tags:
                raise ValueError(f"published item {item_id} requires at least one tag")
            title_zh = str(review.get("title_zh") or item_row["title"]).strip()
            summary_zh = str(review.get("summary_zh") or ("未进入本期精选。" if status == "hidden" else "")).strip()
            methodology_zh = str(review.get("methodology_zh") or "").strip()
            findings_zh = str(review.get("findings_zh") or "").strip()
            limitations_zh = str(review.get("limitations_zh") or "").strip()
            brief_zh = str(review.get("brief_zh") or (summary_zh[:80] if status == "published" else "")).strip()
            brief_section = str(review.get("brief_section") or "要闻").strip()
            if status == "published" and brief_section not in BRIEF_SECTIONS:
                raise ValueError(f"invalid brief_section for item {item_id}: {brief_section}")
            why_zh = str(review.get("why_zh") or review.get("rejection_reason") or ("价值、时效性或证据不足。" if status == "hidden" else "")).strip()
            if status == "published" and (not title_zh or not summary_zh or not methodology_zh or not findings_zh or not limitations_zh or not brief_zh or not why_zh):
                raise ValueError(
                    f"published item {item_id} requires title_zh, summary_zh, methodology_zh, "
                    "findings_zh, limitations_zh, brief_zh and why_zh"
                )
            if len(brief_zh) > 120:
                raise ValueError(f"brief_zh too long for item {item_id}: {len(brief_zh)}")
            quality_score = max(0, min(int(review.get("quality_score", 0)), 100))
            is_featured = int(bool(review.get("is_featured", False)))
            feature_reason = str(review.get("feature_reason") or "").strip()
            is_shock = int(bool(review.get("is_shock", False)))
            shock_reason = str(review.get("shock_reason") or "").strip()
            if brief_section == "前瞻传闻" and (is_featured or is_shock):
                raise ValueError(f"forward-looking rumor item {item_id} cannot be featured or shock")
            if is_featured and not feature_reason:
                raise ValueError(f"featured item {item_id} requires feature_reason")
            if is_shock:
                if item_row["source_id"] not in {"jiqizhixin", "qbitai"}:
                    raise ValueError(f"shock item {item_id} must come from 机器之心 or 量子位")
                if category == "其他":
                    raise ValueError(f"shock item {item_id} cannot be categorized as 其他")
                if not shock_reason:
                    raise ValueError(f"shock item {item_id} requires shock_reason")
            evidence_links_raw = review.get("evidence_links") or []
            if not isinstance(evidence_links_raw, list):
                raise ValueError(f"evidence_links for item {item_id} must be a list")
            evidence_links = []
            for link in evidence_links_raw:
                if isinstance(link, str):
                    link = {"label": "一手资料", "url": link, "type": "primary"}
                if not isinstance(link, dict) or not str(link.get("url") or "").startswith(("http://", "https://")):
                    raise ValueError(f"invalid evidence link for item {item_id}: {link!r}")
                evidence_links.append({
                    "label": str(link.get("label") or "一手资料").strip(),
                    "url": str(link["url"]).strip(),
                    "type": str(link.get("type") or "primary").strip(),
                })
            editorial_date = requested_editorial_date
            db.execute("""INSERT INTO reviews(
                    item_id,title_zh,category,content_type,summary_zh,methodology_zh,findings_zh,limitations_zh,
                    brief_zh,brief_section,why_zh,read_minutes,tags,relevance,
                    quality_score,is_featured,feature_reason,is_shock,shock_reason,evidence_links,
                    status,editorial_date,reviewed_at,reviewer)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET title_zh=excluded.title_zh,category=excluded.category,
                content_type=excluded.content_type,summary_zh=excluded.summary_zh,
                methodology_zh=excluded.methodology_zh,findings_zh=excluded.findings_zh,
                limitations_zh=excluded.limitations_zh,brief_zh=excluded.brief_zh,
                brief_section=excluded.brief_section,why_zh=excluded.why_zh,
                read_minutes=excluded.read_minutes,tags=excluded.tags,relevance=excluded.relevance,
                quality_score=excluded.quality_score,is_featured=excluded.is_featured,
                feature_reason=excluded.feature_reason,is_shock=excluded.is_shock,
                shock_reason=excluded.shock_reason,evidence_links=excluded.evidence_links,status=excluded.status,
                editorial_date=excluded.editorial_date,reviewed_at=excluded.reviewed_at,
                reviewer=excluded.reviewer""",
                (item_id, title_zh, category,
                 str(review.get("content_type") or ("未入选" if status == "hidden" else "资讯")).strip(),
                 summary_zh, methodology_zh, findings_zh, limitations_zh,
                 brief_zh, brief_section, why_zh,
                 max(1, min(int(review.get("read_minutes", 3)), 60)),
                 json.dumps(tags, ensure_ascii=False), str(review.get("relevance") or "high"),
                 quality_score, is_featured, feature_reason, is_shock, shock_reason,
                 json.dumps(evidence_links, ensure_ascii=False),
                 status, editorial_date, now, str(review.get("reviewer") or reviewer)))
            saved += 1
            hidden += int(status == "hidden")
            featured += int(bool(is_featured) and status == "published")
            shock += int(bool(is_shock) and status == "published")
    return {"saved": saved, "hidden": hidden, "published": saved-hidden,
            "featured": featured, "shock": shock}


def query_reviewed(limit: int = 500, days: int | None = 30, category: str | None = None) -> list[dict[str, Any]]:
    init_db()
    sql = """SELECT i.id item_id,i.source_id,i.external_id,i.title original_title,i.url,i.author,i.published_at,
        i.discovered_at,s.name source_name,r.title_zh,r.category,r.content_type,r.summary_zh,
        r.methodology_zh,r.findings_zh,r.limitations_zh,r.brief_zh,r.brief_section,r.why_zh,
        r.read_minutes,r.tags,r.relevance,r.quality_score,r.is_featured,r.feature_reason,
        r.is_shock,r.shock_reason,r.evidence_links,r.editorial_date,r.reviewed_at,r.reviewer
        FROM reviews r JOIN items i ON i.id=r.item_id JOIN sources s ON s.id=i.source_id
        WHERE r.status='published' """
    args = []
    if days is not None:
        sql += " AND r.editorial_date>=?"
        args.append((utcnow()-timedelta(days=max(1, days))).date().isoformat())
    if category:
        sql += " AND r.category=?"
        args.append(category)
    sql += " ORDER BY r.editorial_date DESC,r.is_featured DESC,r.quality_score DESC,COALESCE(i.published_at,i.discovered_at) DESC,r.item_id DESC LIMIT ?"
    args.append(min(max(limit, 1), 1000))
    with connect() as db:
        rows = db.execute(sql, args).fetchall()
    source_meta = {x["id"]: x for x in load_sources()}
    out = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        item["is_featured"] = bool(item["is_featured"])
        item["is_shock"] = bool(item["is_shock"])
        item["evidence_links"] = json.loads(item.get("evidence_links") or "[]")
        meta = source_meta.get(item["source_id"], {})
        item["source_priority"] = int(meta.get("priority", 50))
        item["source_language"] = meta.get("language", "unknown")
        item["source_event_role"] = meta.get("event_role", "unknown")
        item["display_source_name"] = item["source_name"] if item["source_language"] == "zh" else "AIA 中文整理"
        out.append(item)
    return out



def query_reviewed_item(item_id: int) -> dict[str, Any] | None:
    """Return one published editorial item for the internal detail page."""
    init_db()
    sql = """SELECT i.id item_id,i.source_id,i.external_id,i.title original_title,i.url,i.author,i.published_at,
        i.discovered_at,s.name source_name,r.title_zh,r.category,r.content_type,r.summary_zh,
        r.methodology_zh,r.findings_zh,r.limitations_zh,r.brief_zh,r.brief_section,r.why_zh,
        r.read_minutes,r.tags,r.relevance,r.quality_score,r.is_featured,r.feature_reason,
        r.is_shock,r.shock_reason,r.evidence_links,r.editorial_date,r.reviewed_at,r.reviewer
        FROM reviews r JOIN items i ON i.id=r.item_id JOIN sources s ON s.id=i.source_id
        WHERE r.status='published' AND i.id=?"""
    with connect() as db:
        row = db.execute(sql, (int(item_id),)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["tags"] = json.loads(item["tags"])
    item["is_featured"] = bool(item["is_featured"])
    item["is_shock"] = bool(item["is_shock"])
    item["evidence_links"] = json.loads(item.get("evidence_links") or "[]")
    meta = {x["id"]: x for x in load_sources()}.get(item["source_id"], {})
    item["source_priority"] = int(meta.get("priority", 50))
    item["source_language"] = meta.get("language", "unknown")
    item["source_event_role"] = meta.get("event_role", "unknown")
    item["display_source_name"] = item["source_name"] if item["source_language"] == "zh" else "AIA 中文整理"
    return item

def review_stats() -> dict[str, Any]:
    init_db()
    today=utcnow().date().isoformat()
    with connect() as db:
        total=db.execute("SELECT COUNT(*) n FROM reviews WHERE status='published'").fetchone()["n"]
        today_count=db.execute("SELECT COUNT(*) n FROM reviews WHERE status='published' AND editorial_date=?",(today,)).fetchone()["n"]
        pending=db.execute("SELECT COUNT(*) n FROM items i LEFT JOIN reviews r ON r.item_id=i.id WHERE r.item_id IS NULL").fetchone()["n"]
        latest=db.execute("SELECT MAX(editorial_date) d FROM reviews WHERE status='published'").fetchone()["d"]
        featured=db.execute("SELECT COUNT(*) n FROM reviews WHERE status='published' AND is_featured=1").fetchone()["n"]
        shock=db.execute("SELECT COUNT(*) n FROM reviews WHERE status='published' AND is_shock=1 AND editorial_date=?",(latest,)).fetchone()["n"] if latest else 0
    return {"published_total":total,"today_count":today_count,"pending_total":pending,
            "latest_editorial_date":latest,"featured_total":featured,"latest_shock_count":shock}
