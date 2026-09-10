from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from .core import (
    init_db,
    query_items,
    query_reviewed,
    query_reviewed_item,
    review_stats,
    source_status,
    stats,
)

app = FastAPI(title="AIA 新闻情报站", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": "aia-news-intelligence"}


@app.get("/api/items")
def api_items(
    limit: int = Query(30, ge=1, le=500),
    source: str | None = None,
    topic: str | None = None,
    days: int | None = Query(None, ge=1, le=3650),
):
    """Raw collector output. The homepage does not expose these items before review."""
    return query_items(limit=limit, source_id=source, topic=topic, days=days)


@app.get("/api/reviewed")
def api_reviewed(
    limit: int = Query(300, ge=1, le=1000),
    category: str | None = None,
    days: int | None = Query(30, ge=1, le=3650),
):
    return query_reviewed(limit=limit, category=category, days=days)


@app.get("/api/sources")
def api_sources():
    return source_status()


@app.get("/api/stats")
def api_stats():
    return {"collector": stats(), "editorial": review_stats()}


@app.get("/feed.xml")
def feed():
    items = query_reviewed(limit=100, days=60)
    body = []
    for item in items:
        pub = item.get("published_at") or item.get("discovered_at")
        try:
            dt = datetime.fromisoformat(pub).astimezone(timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        description = f"30 秒速览：{item.get('brief_zh') or item['summary_zh']}\n\n完整摘要：{item['summary_zh']}\n\n为什么值得看：{item['why_zh']}"
        body.append(
            f"""<item><title>{html.escape(item['title_zh'])}</title>
            <link>https://news.nju-aia.com/article/{item['item_id']}</link>
            <guid isPermaLink="false">review:{item['item_id']}</guid>
            <pubDate>{format_datetime(dt)}</pubDate>
            <description>{html.escape(description)}</description>
            <category>{html.escape(item['category'])}</category>
            <source>{html.escape(item.get('display_source_name') or item['source_name'])}</source></item>"""
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        '<title>AIA 新闻情报站</title><link>https://news.nju-aia.com/</link>'
        '<description>经 GPT 审阅、中文化与分类的 AI 每日情报</description>'
        + "".join(body)
        + "</channel></rss>"
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIA 新闻情报站</title>
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f7f3ec" id="themeColor">
<script>
(()=>{const key='aia-news-theme-v1';let pref='system';try{pref=localStorage.getItem(key)||'system'}catch(e){}if(!['system','light','dark'].includes(pref))pref='system';const dark=pref==='dark'||(pref==='system'&&window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.dataset.themePreference=pref;const meta=document.getElementById('themeColor');if(meta)meta.content=dark?'#111216':'#f7f3ec'})();
</script>
<style>
:root{--bg:#f7f3ec;--card:#fffdfa;--text:#17171a;--muted:#74717a;--line:#e5dfd6;--purple:#6f4cff;--blue:#2f8ff7;--orange:#ff7a45;--surface:rgba(255,255,255,.72);--surface-soft:rgba(255,255,255,.58);--button-active:#17171a;--button-active-text:#fff;--summary:#64616a;--why:#48464d;--tag-bg:#fff;--tag-text:#6a6670;--hover-line:#bcb5aa;--shadow:rgba(45,35,22,.07);--orb-purple:#f0eaff;--orb-blue:#eaf3fd;--orb-orange:#fff0e7;--modal:#fffdfa;--panel:#fff;--panel-method:#f7f4ff;--panel-method-line:#e4dcff;--panel-findings:#f2f8ff;--panel-findings-line:#d9ebff;--callout:#f4f0ff;--callout-line:#dfd4ff;--limits:#fff9ea;--limits-line:#f0dfad;--shock-bg:#fff0ed;--shock-line:#ffd1ca;--featured-badge-bg:#fff0b8;--featured-badge-text:#805800;--featured-badge-line:#f2d56d;--shock-badge-bg:#ffe1dd;--shock-badge-text:#a63026;--shock-badge-line:#ffb7ad;--limits-title:#8b6500;--overlay:rgba(10,10,13,.38);color-scheme:light}
html[data-theme="dark"]{--bg:#111216;--card:#191b21;--text:#f2f0ec;--muted:#aaa6b0;--line:#34363f;--purple:#ae92ff;--blue:#77baff;--orange:#ff9d75;--surface:rgba(31,33,40,.84);--surface-soft:rgba(31,33,40,.66);--button-active:#f2f0ec;--button-active-text:#16171b;--summary:#c5c1ca;--why:#ddd8e1;--tag-bg:#22242b;--tag-text:#beb9c5;--hover-line:#646876;--shadow:rgba(0,0,0,.34);--orb-purple:#352b4b;--orb-blue:#21364c;--orb-orange:#472f26;--modal:#191b21;--panel:#22242b;--panel-method:#26213a;--panel-method-line:#4b416b;--panel-findings:#1d2b39;--panel-findings-line:#36536d;--callout:#27213b;--callout-line:#4d426d;--limits:#312a1b;--limits-line:#635227;--shock-bg:#3c2526;--shock-line:#704043;--featured-badge-bg:#423817;--featured-badge-text:#ffdc73;--featured-badge-line:#715e25;--shock-badge-bg:#4a292b;--shock-badge-text:#ffaaa1;--shock-badge-line:#81474a;--limits-title:#e7bd56;--overlay:rgba(0,0,0,.64);color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);transition:background-color .18s ease,color .18s ease;font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif}
a{color:inherit}.page{max-width:1420px;margin:auto;padding:24px 30px 52px}
.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:22px}.brand-kicker{font-size:11px;letter-spacing:.14em;color:var(--muted);font-weight:700}.brand h1{font-size:31px;margin:3px 0 0;letter-spacing:-.03em}.brand p{margin:0;color:var(--muted);font-size:14px}
.actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.theme-control{display:flex;align-items:center;gap:5px;padding:3px 8px 3px 10px;border:1px solid var(--line);background:var(--surface-soft);border-radius:999px}.theme-icon{font-size:13px;color:var(--muted);line-height:1}.theme-select{border:0;background:transparent;color:var(--text);font:inherit;font-size:13px;padding:4px 1px;cursor:pointer;outline:none}.theme-select option{background:var(--card);color:var(--text)}.ghost,.primary,.tab,.layout-button,.page-nav,.page-number{border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:999px;padding:8px 13px;font:inherit;cursor:pointer}.primary{background:var(--button-active);color:var(--button-active-text);border-color:var(--button-active)}.ghost:hover,.tab:hover,.layout-button:hover,.page-nav:hover:not(:disabled),.page-number:hover{border-color:var(--hover-line)}.pref-count{font-size:12px;opacity:.72}.layout-control{display:flex;align-items:center;gap:3px;padding:3px;border:1px solid var(--line);background:var(--surface-soft);border-radius:999px}.layout-label{font-size:12px;color:var(--muted);padding:0 6px}.layout-button{border:0;padding:5px 9px;background:transparent;font-size:13px}.layout-button.active{background:var(--button-active);color:var(--button-active-text)}
.metrics{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.metric{background:var(--surface);border:1px solid var(--line);padding:7px 12px;border-radius:11px;min-width:105px}.metric b{display:block;font-size:18px;line-height:1.3}.metric span{color:var(--muted);font-size:12px}
.quick{margin:18px 0 24px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px}.quick-head{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:12px}.quick-head h2{margin:0;font-size:22px;letter-spacing:-.02em}.quick-head span{color:var(--muted);font-size:12px}.quick-sections{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 22px}.quick-section{min-width:0}.quick-section h3{display:flex;align-items:center;gap:7px;margin:0 0 3px;font-size:14px}.quick-section h3:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--purple)}.quick-section[data-section="模型发布"] h3:before{background:#2f8ff7}.quick-section[data-section="开发生态"] h3:before{background:#22a559}.quick-section[data-section="前瞻传闻"] h3:before{background:#e49a25}.quick-section[data-section="近期精选"] h3:before{background:#d6a51d}.quick-list{display:flex;flex-direction:column}.quick-item{display:grid;grid-template-columns:27px minmax(0,1fr) auto;gap:9px;align-items:start;padding:8px 0;border-top:1px solid var(--line);text-decoration:none}.quick-item:first-child{border-top:0}.quick-num{font-size:12px;font-weight:900;color:var(--purple);padding-top:2px}.quick-copy b{display:block;font-size:14px;line-height:1.45}.quick-copy small{display:block;color:var(--muted);font-size:12px;line-height:1.5;margin-top:2px}.quick-flags{display:flex;gap:5px;align-items:center;padding-top:2px}.quick-empty{padding:15px 0;color:var(--muted)}
.section-head{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-top:18px}.eyebrow{font-size:12px;color:var(--muted);font-weight:700}.section-head h2{font-size:27px;margin:2px 0 0;letter-spacing:-.025em}.edition{color:var(--purple);font-weight:700;font-size:13px}
.tabs{display:flex;gap:7px;overflow:auto;padding:15px 0 10px}.tab{white-space:nowrap}.tab.active{background:var(--button-active);color:var(--button-active-text);border-color:var(--button-active)}.tab sup{font-size:10px;margin-left:4px;opacity:.65}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}.card{position:relative;display:flex;flex-direction:column;min-height:350px;padding:19px 20px 17px;border:1px solid var(--line);border-radius:19px;background:var(--card);text-decoration:none;overflow:hidden;transition:transform .15s,box-shadow .15s}.card:hover{transform:translateY(-2px);box-shadow:0 12px 28px var(--shadow)}.card:before{content:"";position:absolute;width:105px;height:105px;border-radius:50%;right:-34px;top:-36px;background:var(--orb-purple)}.card:nth-child(3n+2):before{background:var(--orb-blue)}.card:nth-child(3n):before{background:var(--orb-orange)}
.card-top{position:relative;display:flex;justify-content:space-between;gap:10px;font-size:12px}.card-labels{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.type{color:var(--purple);font-weight:800}.read{color:var(--muted);white-space:nowrap}.badge{display:inline-flex;align-items:center;border-radius:999px;padding:2px 7px;font-size:10px;font-weight:800;line-height:1.4}.badge.featured{background:var(--featured-badge-bg);color:var(--featured-badge-text);border:1px solid var(--featured-badge-line)}.badge.shock{background:var(--shock-badge-bg);color:var(--shock-badge-text);border:1px solid var(--shock-badge-line)}.card h3{position:relative;font-size:20px;line-height:1.34;letter-spacing:-.02em;margin:17px 0 10px}.summary{color:var(--summary);font-size:14px;line-height:1.58;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;overflow:hidden}.why{border-top:1px solid var(--line);margin-top:14px;padding-top:11px}.why b{display:block;color:var(--blue);font-size:12px;margin-bottom:3px}.why p{margin:0;color:var(--why);font-size:13px;line-height:1.55;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}.card-foot{margin-top:auto;padding-top:13px;display:flex;align-items:end;justify-content:space-between;gap:10px}.tags{display:flex;gap:5px;flex-wrap:wrap}.tag{border:1px solid var(--line);border-radius:6px;padding:2px 6px;color:var(--tag-text);font-size:11px;background:var(--tag-bg)}.arrow{font-size:23px;color:var(--purple);line-height:1}.source{font-size:11px;color:var(--muted);margin-top:7px}
.empty{grid-column:1/-1;padding:60px;text-align:center;border:1px dashed var(--line);border-radius:24px;color:var(--muted);background:var(--surface-soft)}.pagination-slot:empty{display:none}.pagination{display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap}.pagination-bottom .pagination{margin:24px 0 6px}.page-nav,.page-number{min-height:38px}.page-nav:disabled{opacity:.38;cursor:not-allowed}.page-numbers{display:flex;align-items:center;gap:5px}.page-number{min-width:38px;padding:7px 10px}.page-number.active{background:var(--button-active);color:var(--button-active-text);border-color:var(--button-active)}.page-ellipsis{color:var(--muted);padding:0 2px}.page-status{color:var(--muted);font-size:12px;margin:0 3px}.hidden{display:none!important}
details.ops{margin-top:28px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted)}details.ops summary{cursor:pointer;font-weight:700;color:#5f5b64}table{width:100%;border-collapse:collapse;background:var(--surface);margin-top:14px;border-radius:14px;overflow:hidden}th,td{padding:10px 13px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:#e1a72e}.dot.ok{background:#22a559}.footer{margin-top:22px;color:var(--muted);font-size:13px}
.modal-backdrop{position:fixed;inset:0;background:var(--overlay);display:flex;align-items:center;justify-content:center;padding:18px;z-index:10}.modal{width:min(670px,100%);max-height:88vh;overflow:auto;background:var(--modal);border-radius:24px;padding:27px;box-shadow:0 25px 90px rgba(0,0,0,.25)}.modal-head{display:flex;justify-content:space-between;gap:20px}.modal h2{margin:0;font-size:25px}.modal p{color:var(--muted)}.close{border:0;background:none;color:var(--text);font-size:25px;cursor:pointer}.pref-tags{display:flex;gap:9px;flex-wrap:wrap;margin:20px 0}.pref-tag{border:1px solid var(--line);border-radius:999px;padding:8px 13px;background:var(--tag-bg);color:var(--text);cursor:pointer}.pref-tag.selected{background:var(--button-active);color:var(--button-active-text);border-color:var(--button-active)}.modal-actions{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:22px}.error{color:#c43b32;font-size:13px}
@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.quick-sections{grid-template-columns:1fr}}@media(max-width:680px){.page{padding:18px 12px 45px}.topbar{flex-direction:column}.actions{width:100%;justify-content:flex-start}.grid{grid-template-columns:1fr}.card{min-height:320px}.section-head{align-items:flex-start;flex-direction:column}.brand h1{font-size:27px}.layout-label{display:none}.quick{padding:15px 14px}.quick-head{align-items:flex-start;flex-direction:column;gap:2px}.quick-item{grid-template-columns:25px minmax(0,1fr)}.quick-flags{grid-column:2}.pagination{gap:6px}.page-status{order:3;width:100%;text-align:center}.page-nav{padding:7px 11px}.page-number{min-width:36px}}
</style>
</head>
<body>
<div class="page">
  <div class="topbar">
    <div class="brand"><div class="brand-kicker">NJU AIA · DAILY INTELLIGENCE</div><h1>AIA 新闻情报站</h1><p>抓取程序负责发现，GPT 负责阅读、中文化、分类与解释。</p></div>
    <div class="actions"><label class="theme-control" title="页面主题"><span class="theme-icon" id="themeIcon" aria-hidden="true">◐</span><select class="theme-select" id="themeSelect" aria-label="页面主题"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></label><div class="layout-control" aria-label="每页显示数量"><span class="layout-label">每页</span><button class="layout-button" data-layout="3">3</button><button class="layout-button" data-layout="6">6</button><button class="layout-button" data-layout="9">9</button></div><button class="ghost" id="prefOpen">选择阅读偏好 <span class="pref-count" id="prefCount"></span></button><a class="primary" href="/feed.xml">订阅 RSS</a></div>
  </div>
  <div class="metrics">
    <div class="metric"><b>__ROLLING__</b><span>最近 24 小时</span></div>
    <div class="metric"><b>__PUBLISHED__</b><span>累计发布</span></div>
    <div class="metric"><b>__PENDING__</b><span>候选池待审</span></div>
  </div>
  <section class="quick"><div class="quick-head"><h2>重点速览</h2><span>滚动 24 小时更新；不足时补充近 30 天精选 · __LATEST__</span></div><div class="quick-sections">__QUICK_BRIEF__</div></section>
  <div class="section-head"><div><div class="eyebrow">你的阅读入口</div><h2 id="sectionTitle">为你推荐</h2></div><div class="edition" id="editionText">本期 __LATEST__</div></div>
  <div class="tabs" id="tabs"></div><div class="eyebrow" id="recommendationNote">推荐优先展示「精选」，约 70% 来自你的偏好、30% 用于探索其他 AI 方向；“其他”不参与推荐。</div>
  <main class="grid" id="grid"></main>
  <div class="pagination-slot pagination-bottom" id="paginationBottom"></div>
  <details class="ops"><summary>来源运行状态与采集诊断</summary><table><thead><tr><th>来源</th><th>适配器</th><th>本轮新增</th><th>状态</th></tr></thead><tbody>__SOURCE_ROWS__</tbody></table></details>
  <div class="footer">精选 RSS：<a href="/feed.xml">/feed.xml</a> · 已审阅 API：<a href="/api/reviewed">/api/reviewed</a> · 原始候选不会在首页直接发布。</div>
</div>
<div class="modal-backdrop hidden" id="modalBackdrop"><div class="modal"><div class="modal-head"><div><h2>选择你的阅读偏好</h2><p>从 8 个稳定研究方向中至少选择 3 个。偏好长期保存在当前浏览器中，新增新闻不会要求重选。推荐约 70% 匹配偏好，30% 为每日稳定探索。</p></div><button class="close" id="prefClose">×</button></div><div class="pref-tags" id="prefTags"></div><div class="modal-actions"><span class="error" id="prefError"></span><button class="primary" id="prefSave">保存偏好</button></div></div></div>
<script>
const themeKey='aia-news-theme-v1';
const themeMedia=window.matchMedia('(prefers-color-scheme: dark)');
function storedTheme(){try{const value=localStorage.getItem(themeKey)||'system';return ['system','light','dark'].includes(value)?value:'system'}catch(e){return 'system'}}
function applyTheme(preference){const dark=preference==='dark'||(preference==='system'&&themeMedia.matches);document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.dataset.themePreference=preference;const meta=document.getElementById('themeColor');if(meta)meta.content=dark?'#111216':'#f7f3ec';const select=document.getElementById('themeSelect');if(select)select.value=preference;const icon=document.getElementById('themeIcon');if(icon)icon.textContent=preference==='system'?'◐':(preference==='dark'?'☾':'☀')}
const initialTheme=storedTheme();applyTheme(initialTheme);
document.getElementById('themeSelect').onchange=e=>{const preference=e.target.value;try{localStorage.setItem(themeKey,preference)}catch(err){}applyTheme(preference)};
themeMedia.addEventListener?.('change',()=>{if(storedTheme()==='system')applyTheme('system')});
const items=__ITEMS__;
const preferenceCategories=['模型与推理','训练与对齐','Agent','多模态','具身智能','系统与基础设施','AI4Science','产业与产品'];
const categories=[...preferenceCategories,'其他'];
const specialFilters=['精选','震惊瘫坐'];
const prefKey='aia-news-preferences-v3';
const previousPrefKeys=['aia-news-preferences-v2','aia-news-preferences-v1'];
const migratePreference={
  '模型与算法':['模型与推理','训练与对齐'],
  'Agent 与应用':['Agent'],
  '多模态与具身':['多模态','具身智能'],
  '系统与基础设施':['系统与基础设施'],
  'AI4Science':['AI4Science'],
  '产业与产品':['产业与产品'],
  '推理':['模型与推理'],'NLP':['模型与推理'],'记忆':['模型与推理'],'RAG':['模型与推理'],'模型开放':['模型与推理'],
  '强化学习':['训练与对齐'],'模型训练':['训练与对齐'],'蒸馏':['训练与对齐'],'AI安全':['训练与对齐'],
  'Agent':['Agent'],'GUI Agent':['Agent'],
  '具身':['具身智能'],'世界模型':['具身智能'],'多模态':['多模态'],
  '系统':['系统与基础设施'],'推理加速':['系统与基础设施'],'GPU':['系统与基础设施'],
  '产业':['产业与产品']
};
let preferences=[];
try{
  preferences=JSON.parse(localStorage.getItem(prefKey)||'[]').filter(x=>preferenceCategories.includes(x));
  if(!preferences.length){
    for(const key of previousPrefKeys){
      const old=JSON.parse(localStorage.getItem(key)||'[]');
      const migrated=[...new Set(old.flatMap(x=>migratePreference[x]||[]))].filter(x=>preferenceCategories.includes(x));
      if(migrated.length){preferences=migrated;localStorage.setItem(prefKey,JSON.stringify(preferences));break}
    }
  }
}catch(e){preferences=[]}
const layoutKey='aia-news-layout-v1';
let layoutMode=localStorage.getItem(layoutKey)||'9';if(layoutMode==='all')layoutMode='9';if(!['3','6','9'].includes(layoutMode))layoutMode='9';localStorage.setItem(layoutKey,layoutMode);
const initialParams=new URLSearchParams(location.search);
let active=initialParams.get('tab')||'推荐',draftPreferences=[...preferences];
let currentPage=Math.max(1,parseInt(initialParams.get('page')||'1',10)||1);
const grid=document.getElementById('grid'),tabs=document.getElementById('tabs'),paginationBottom=document.getElementById('paginationBottom');
function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function timestamp(x){return String(x.published_at||x.discovered_at||'')}
function latestFirst(xs){return [...xs].sort((a,b)=>timestamp(b).localeCompare(timestamp(a)))}
function featuredFirst(xs){return [...xs].sort((a,b)=>Number(b.is_featured)-Number(a.is_featured)||(b.quality_score||0)-(a.quality_score||0)||timestamp(b).localeCompare(timestamp(a)))}
function hashSeed(text){let h=2166136261;for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function rng(seed){return function(){seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296}}
function stableShuffle(xs,salt){const out=[...xs],random=rng(hashSeed(salt));for(let i=out.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[out[i],out[j]]=[out[j],out[i]]}return out}
function featuredStableShuffle(xs,salt){const featured=stableShuffle(xs.filter(x=>x.is_featured),`featured|${salt}`);const normal=stableShuffle(xs.filter(x=>!x.is_featured),`normal|${salt}`);return [...featured,...normal]}
function roundRobinByPreference(xs,limit){const buckets=preferences.map(c=>featuredFirst(xs.filter(x=>x.category===c)));const out=[];let cursor=0;while(out.length<limit&&buckets.some(b=>b.length)){const bucket=buckets[cursor%buckets.length];if(bucket.length)out.push(bucket.shift());cursor++}return out}
const currentEdition=items.reduce((latest,x)=>String(x.editorial_date||'')>latest?String(x.editorial_date):latest,'');
function mixRecommendations(eligible,target){
  if(!target)return [];
  const seed=`${currentEdition}|${[...preferences].sort().join('|')}|${target}`;
  if(preferences.length<3){
    const recent=eligible.slice(0,Math.max(target*3,target));
    return featuredStableShuffle(recent,`cold-start|${seed}`).slice(0,target);
  }
  const matched=eligible.filter(x=>preferences.includes(x.category));
  const unmatched=eligible.filter(x=>!preferences.includes(x.category));
  const desiredExplore=Math.min(Math.round(target*.3),unmatched.length);
  const desiredExploit=Math.min(target-desiredExplore,matched.length);
  const exploit=roundRobinByPreference(matched,desiredExploit);
  const explore=featuredStableShuffle(unmatched,`epsilon|${seed}`).slice(0,desiredExplore);
  const out=[];let pi=0,ei=0;
  while(out.length<target&&(pi<exploit.length||ei<explore.length)){
    if(pi<exploit.length)out.push(exploit[pi++]);
    if(pi<exploit.length&&out.length<target)out.push(exploit[pi++]);
    if(ei<explore.length&&out.length<target)out.push(explore[ei++]);
  }
  const used=new Set(out.map(x=>x.item_id));
  const fallback=featuredFirst(eligible.filter(x=>!used.has(x.item_id)));
  out.push(...fallback.slice(0,target-out.length));
  return out;
}
function recommendationItems(){
  const eligible=latestFirst(items.filter(x=>x.category!=='其他'));
  return mixRecommendations(eligible,eligible.length);
}
function selectedItems(){
  if(active==='推荐')return recommendationItems();
  if(active==='精选')return featuredFirst(items.filter(x=>x.is_featured));
  if(active==='震惊瘫坐')return featuredFirst(items.filter(x=>x.is_shock&&x.editorial_date===currentEdition));
  return latestFirst(items.filter(x=>x.category===active));
}
function sourceLine(x){return x.source_language==='en'?'AIA 中文整理':esc(x.display_source_name||x.source_name)}
function card(x){const badges=`${x.is_featured?'<span class="badge featured" title="GPT 判断为高价值精选">精选</span>':''}${x.is_shock?'<span class="badge shock" title="今日行业突破或重要进展">震惊瘫坐</span>':''}`;return `<a class="card" href="/article/${x.item_id}"><div class="card-top"><div class="card-labels"><span class="type">${esc(x.content_type)} · ${esc(x.category)}</span>${badges}</div><span class="read">${x.read_minutes} 分钟</span></div><h3>${esc(x.title_zh)}</h3><div class="summary">${esc(x.summary_zh)}</div><div class="why"><b>为什么值得看</b><p>${esc(x.why_zh)}</p></div><div class="card-foot"><div><div class="tags">${(x.tags||[]).slice(0,6).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div><div class="source">${sourceLine(x)} · ${esc(timestamp(x).slice(0,10))}</div></div><span class="arrow">→</span></div></a>`}
function pageTokens(total,current){
  if(total<=7)return Array.from({length:total},(_,i)=>i+1);
  const keep=new Set([1,total,current-1,current,current+1]);
  const pages=[...keep].filter(x=>x>=1&&x<=total).sort((a,b)=>a-b),out=[];
  for(let i=0;i<pages.length;i++){if(i&&pages[i]-pages[i-1]>1)out.push('…');out.push(pages[i])}
  return out;
}
function updateUrlState(){const u=new URL(location.href);active==='推荐'?u.searchParams.delete('tab'):u.searchParams.set('tab',active);currentPage===1?u.searchParams.delete('page'):u.searchParams.set('page',String(currentPage));history.replaceState(null,'',u)}
function goToPage(page,scroll=true){currentPage=Math.max(1,page);render();if(scroll)document.querySelector('.section-head').scrollIntoView({behavior:'smooth',block:'start'})}
function renderPager(root,totalItems,totalPages){
  if(totalPages<=1){root.innerHTML='';return}
  const start=(currentPage-1)*Number(layoutMode)+1,end=Math.min(currentPage*Number(layoutMode),totalItems);
  const numbers=pageTokens(totalPages,currentPage).map(token=>token==='…'?'<span class="page-ellipsis">…</span>':`<button class="page-number ${token===currentPage?'active':''}" type="button" data-page="${token}" aria-label="第 ${token} 页" ${token===currentPage?'aria-current="page"':''}>${token}</button>`).join('');
  root.innerHTML=`<nav class="pagination" aria-label="卡片分页"><button class="page-nav" data-action="prev" type="button" ${currentPage<=1?'disabled':''}>← 上一页</button><div class="page-numbers">${numbers}</div><span class="page-status">第 ${currentPage}/${totalPages} 页 · ${start}–${end} / ${totalItems}</span><button class="page-nav" data-action="next" type="button" ${currentPage>=totalPages?'disabled':''}>下一页 →</button></nav>`;
  root.querySelector('[data-action="prev"]').onclick=()=>goToPage(currentPage-1);
  root.querySelector('[data-action="next"]').onclick=()=>goToPage(currentPage+1);
  root.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>goToPage(Number(button.dataset.page)));
}
function renderPagination(totalItems,totalPages){
  renderPager(paginationBottom,totalItems,totalPages);
}
function render(){
  const validTabs=new Set(['推荐',...specialFilters,...categories]);if(!validTabs.has(active))active='推荐';
  [...tabs.children].forEach(b=>b.classList.toggle('active',b.dataset.category===active));
  document.querySelectorAll('.layout-button').forEach(b=>b.classList.toggle('active',b.dataset.layout===layoutMode));
  document.getElementById('sectionTitle').textContent=active==='推荐'?'为你推荐':active;
  const xs=selectedItems(),pageSize=Number(layoutMode),totalPages=Math.max(1,Math.ceil(xs.length/pageSize));
  currentPage=Math.min(Math.max(1,currentPage),totalPages);
  const shown=xs.slice((currentPage-1)*pageSize,currentPage*pageSize);
  grid.innerHTML=shown.length?shown.map(card).join(''):'<div class="empty">这个栏目当前没有符合编辑标准的内容。</div>';
  renderPagination(xs.length,totalPages);updateUrlState();
  document.getElementById('recommendationNote').classList.toggle('hidden',active!=='推荐');
}
function filterCount(c){if(c==='推荐')return items.filter(x=>x.category!=='其他').length;if(c==='精选')return items.filter(x=>x.is_featured).length;if(c==='震惊瘫坐')return items.filter(x=>x.is_shock&&x.editorial_date===currentEdition).length;return items.filter(x=>x.category===c).length}
function buildTabs(){const defs=['推荐',...specialFilters,...categories];const visible=[];for(const c of defs){const count=filterCount(c);if(c!=='推荐'&&count===0)continue;visible.push(c);const b=document.createElement('button');b.className='tab';b.dataset.category=c;b.innerHTML=`${esc(c)}${c==='推荐'?'':`<sup>${count}</sup>`}`;b.onclick=()=>{active=c;currentPage=1;render()};tabs.appendChild(b)}if(!visible.includes(active))active='推荐';render()}
function updatePrefCount(){document.getElementById('prefCount').textContent=preferences.length?`${preferences.length} 个大类`:'至少 3 个'}
function renderPrefTags(){const box=document.getElementById('prefTags');box.innerHTML=preferenceCategories.map(t=>`<button class="pref-tag ${draftPreferences.includes(t)?'selected':''}" data-tag="${esc(t)}">${esc(t)}</button>`).join('');box.querySelectorAll('button').forEach(b=>b.onclick=()=>{const t=b.dataset.tag;draftPreferences=draftPreferences.includes(t)?draftPreferences.filter(x=>x!==t):[...draftPreferences,t];renderPrefTags()})}
document.getElementById('prefOpen').onclick=()=>{draftPreferences=[...preferences];renderPrefTags();document.getElementById('prefError').textContent='';document.getElementById('modalBackdrop').classList.remove('hidden')};document.getElementById('prefClose').onclick=()=>document.getElementById('modalBackdrop').classList.add('hidden');document.getElementById('modalBackdrop').onclick=e=>{if(e.target.id==='modalBackdrop')e.currentTarget.classList.add('hidden')};document.getElementById('prefSave').onclick=()=>{if(draftPreferences.length<3){document.getElementById('prefError').textContent='请至少选择 3 个大类。';return}preferences=[...draftPreferences];localStorage.setItem(prefKey,JSON.stringify(preferences));updatePrefCount();document.getElementById('modalBackdrop').classList.add('hidden');currentPage=1;render()};document.querySelectorAll('.layout-button').forEach(b=>b.onclick=()=>{layoutMode=b.dataset.layout;localStorage.setItem(layoutKey,layoutMode);currentPage=1;render()});window.addEventListener('popstate',()=>{const params=new URLSearchParams(location.search);active=params.get('tab')||'推荐';currentPage=Math.max(1,parseInt(params.get('page')||'1',10)||1);render()});
updatePrefCount();buildTabs();
</script>
</body></html>'''


DETAIL_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · AIA 新闻情报站</title>
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f7f3ec" id="themeColor">
<script>
(()=>{const key='aia-news-theme-v1';let pref='system';try{pref=localStorage.getItem(key)||'system'}catch(e){}if(!['system','light','dark'].includes(pref))pref='system';const dark=pref==='dark'||(pref==='system'&&window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.dataset.themePreference=pref;const meta=document.getElementById('themeColor');if(meta)meta.content=dark?'#111216':'#f7f3ec'})();
</script>
<style>
:root{--bg:#f7f3ec;--card:#fffdfa;--text:#17171a;--muted:#74717a;--line:#e5dfd6;--purple:#6f4cff;--blue:#2f8ff7;--orange:#ff7a45;--surface:rgba(255,255,255,.72);--surface-soft:rgba(255,255,255,.58);--button-active:#17171a;--button-active-text:#fff;--summary:#64616a;--why:#48464d;--tag-bg:#fff;--tag-text:#6a6670;--hover-line:#bcb5aa;--shadow:rgba(45,35,22,.07);--orb-purple:#f0eaff;--orb-blue:#eaf3fd;--orb-orange:#fff0e7;--modal:#fffdfa;--panel:#fff;--panel-method:#f7f4ff;--panel-method-line:#e4dcff;--panel-findings:#f2f8ff;--panel-findings-line:#d9ebff;--callout:#f4f0ff;--callout-line:#dfd4ff;--limits:#fff9ea;--limits-line:#f0dfad;--shock-bg:#fff0ed;--shock-line:#ffd1ca;--featured-badge-bg:#fff0b8;--featured-badge-text:#805800;--featured-badge-line:#f2d56d;--shock-badge-bg:#ffe1dd;--shock-badge-text:#a63026;--shock-badge-line:#ffb7ad;--limits-title:#8b6500;--overlay:rgba(10,10,13,.38);color-scheme:light}
html[data-theme="dark"]{--bg:#111216;--card:#191b21;--text:#f2f0ec;--muted:#aaa6b0;--line:#34363f;--purple:#ae92ff;--blue:#77baff;--orange:#ff9d75;--surface:rgba(31,33,40,.84);--surface-soft:rgba(31,33,40,.66);--button-active:#f2f0ec;--button-active-text:#16171b;--summary:#c5c1ca;--why:#ddd8e1;--tag-bg:#22242b;--tag-text:#beb9c5;--hover-line:#646876;--shadow:rgba(0,0,0,.34);--orb-purple:#352b4b;--orb-blue:#21364c;--orb-orange:#472f26;--modal:#191b21;--panel:#22242b;--panel-method:#26213a;--panel-method-line:#4b416b;--panel-findings:#1d2b39;--panel-findings-line:#36536d;--callout:#27213b;--callout-line:#4d426d;--limits:#312a1b;--limits-line:#635227;--shock-bg:#3c2526;--shock-line:#704043;--featured-badge-bg:#423817;--featured-badge-text:#ffdc73;--featured-badge-line:#715e25;--shock-badge-bg:#4a292b;--shock-badge-text:#ffaaa1;--shock-badge-line:#81474a;--limits-title:#e7bd56;--overlay:rgba(0,0,0,.64);color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);transition:background-color .18s ease,color .18s ease;font:16px/1.8 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif}a{color:inherit}.page{max-width:900px;margin:auto;padding:30px 24px 70px}.nav{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:38px}.nav-actions{display:flex;align-items:center;gap:12px}.theme-control{display:flex;align-items:center;gap:5px;padding:3px 8px 3px 10px;border:1px solid var(--line);background:var(--surface-soft);border-radius:999px}.theme-icon{font-size:13px;color:var(--muted);line-height:1}.theme-select{border:0;background:transparent;color:var(--text);font:inherit;font-size:13px;padding:4px 1px;cursor:pointer;outline:none}.theme-select option{background:var(--card);color:var(--text)}.back{text-decoration:none;color:var(--muted);font-weight:700}.brand{text-decoration:none;font-weight:900}.article{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:38px 42px}.kicker{display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:var(--purple);font-size:13px;font-weight:800}.badge{border-radius:999px;padding:2px 8px;font-size:11px}.featured{background:var(--featured-badge-bg);color:var(--featured-badge-text);border:1px solid var(--featured-badge-line)}.shock{background:var(--shock-badge-bg);color:var(--shock-badge-text);border:1px solid var(--shock-badge-line)}h1{font-size:38px;line-height:1.3;letter-spacing:-.035em;margin:18px 0 12px}.meta{color:var(--muted);font-size:13px;border-bottom:1px solid var(--line);padding-bottom:23px}.section{margin-top:30px}.section h2{font-size:18px;margin:0 0 8px}.section p{margin:0;color:var(--why);white-space:pre-wrap}.analysis-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:30px}.analysis-grid .section{margin-top:0}.panel{padding:20px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}.panel.method{background:var(--panel-method);border-color:var(--panel-method-line)}.panel.findings{background:var(--panel-findings);border-color:var(--panel-findings-line)}.why h2{color:var(--blue)}.callout{padding:18px 20px;border-radius:14px;background:var(--callout);border:1px solid var(--callout-line)}.limits{background:var(--limits);border-color:var(--limits-line)}.limits h2{color:var(--limits-title)}.shock-callout{background:var(--shock-bg);border-color:var(--shock-line)}.tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:28px}.tag{border:1px solid var(--line);background:var(--tag-bg);border-radius:8px;padding:4px 9px;font-size:12px;color:var(--tag-text)}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:34px}.button{display:inline-flex;text-decoration:none;border-radius:999px;padding:10px 17px;border:1px solid var(--line);font-weight:800}.button.primary{background:var(--button-active);color:var(--button-active-text);border-color:var(--button-active)}.original{margin-top:36px;padding-top:22px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}.original b{color:var(--why)}@media(max-width:650px){.page{padding:20px 12px 50px}.article{padding:26px 20px;border-radius:18px}h1{font-size:29px}.nav{margin-bottom:22px;align-items:flex-start}.nav-actions{flex-direction:column;align-items:flex-end;gap:7px}.brand{font-size:13px}.analysis-grid{grid-template-columns:1fr}}
</style></head>
<body><div class="page"><nav class="nav"><a class="back" href="/">← 返回情报站</a><div class="nav-actions"><a class="brand" href="/">AIA 新闻情报站</a><label class="theme-control" title="页面主题"><span class="theme-icon" id="themeIcon" aria-hidden="true">◐</span><select class="theme-select" id="themeSelect" aria-label="页面主题"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></label></div></nav>
<article class="article"><div class="kicker">__KICKER__</div><h1>__TITLE__</h1><div class="meta">__META__</div>
<section class="section callout"><h2>30 秒速览</h2><p>__BRIEF__</p></section>
<section class="section"><h2>完整摘要</h2><p>__SUMMARY__</p></section>
<div class="analysis-grid">
<section class="section panel method"><h2>怎么做的 / 核心机制</h2><p>__METHODOLOGY__</p></section>
<section class="section panel findings"><h2>关键结果 / 已披露进展</h2><p>__FINDINGS__</p></section>
</div>
<section class="section why"><h2>为什么值得看</h2><p>__WHY__</p></section>
<section class="section callout limits"><h2>局限与判断</h2><p>__LIMITATIONS__</p></section>
__FEATURE_SECTION____SHOCK_SECTION__
<div class="tags">__TAGS__</div>
<section class="section"><h2>资料与核验</h2><p class="evidence-note">正文已由 AIA 完整中文整理；以下链接仅用于查看中文报道或核对一手材料。</p><div class="actions">__SOURCE_ACTIONS__</div></section>
<div class="actions"><a class="button primary" href="/">返回首页</a></div>
<div class="original"><b>原始标题：</b>__ORIGINAL_TITLE__<br><b>编辑：</b>GPT · __EDITORIAL_DATE__ · 质量评分 __QUALITY__/100</div>
</article></div><script>
const themeKey='aia-news-theme-v1';
const themeMedia=window.matchMedia('(prefers-color-scheme: dark)');
function storedTheme(){try{const value=localStorage.getItem(themeKey)||'system';return ['system','light','dark'].includes(value)?value:'system'}catch(e){return 'system'}}
function applyTheme(preference){const dark=preference==='dark'||(preference==='system'&&themeMedia.matches);document.documentElement.dataset.theme=dark?'dark':'light';document.documentElement.dataset.themePreference=preference;const meta=document.getElementById('themeColor');if(meta)meta.content=dark?'#111216':'#f7f3ec';const select=document.getElementById('themeSelect');if(select)select.value=preference;const icon=document.getElementById('themeIcon');if(icon)icon.textContent=preference==='system'?'◐':(preference==='dark'?'☾':'☀')}
const initialTheme=storedTheme();applyTheme(initialTheme);
document.getElementById('themeSelect').onchange=e=>{const preference=e.target.value;try{localStorage.setItem(themeKey,preference)}catch(err){}applyTheme(preference)};
themeMedia.addEventListener?.('change',()=>{if(storedTheme()==='system')applyTheme('system')});
</script></body></html>'''


@app.get("/article/{item_id}", response_class=HTMLResponse)
def article_detail(item_id: int):
    item = query_reviewed_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="未找到已发布的编辑条目")
    badges = []
    if item.get("is_featured"):
        badges.append('<span class="badge featured">精选</span>')
    if item.get("is_shock"):
        badges.append('<span class="badge shock">震惊瘫坐</span>')
    kicker = html.escape(f"{item['content_type']} · {item['category']}") + "".join(badges)
    pub = (item.get("published_at") or item.get("discovered_at") or "")[:10]
    source_label = item.get("display_source_name") or item["source_name"]
    if item.get("source_language") == "en":
        source_label = "AIA 中文整理"
    meta = html.escape(f"{source_label} · {pub} · 预计阅读 {item['read_minutes']} 分钟")
    tags = "".join(f'<span class="tag">{html.escape(str(tag))}</span>' for tag in item.get("tags", []))
    feature_section = ""
    if item.get("is_featured") and item.get("feature_reason"):
        feature_section = f'<section class="section callout"><h2>精选理由</h2><p>{html.escape(item["feature_reason"])}</p></section>'
    shock_section = ""
    if item.get("is_shock") and item.get("shock_reason"):
        shock_section = f'<section class="section callout shock-callout"><h2>为什么进入「震惊瘫坐」</h2><p>{html.escape(item["shock_reason"])}</p></section>'
    source_actions = []
    if item.get("source_language") == "zh":
        source_actions.append(f'<a class="button" href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noopener">阅读中文报道 ↗</a>')
    else:
        source_actions.append(f'<a class="button" href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noopener">查看官方原文 ↗</a>')
    seen_urls = {item["url"]}
    for link in item.get("evidence_links", []):
        url = str(link.get("url") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        label = html.escape(str(link.get("label") or "一手资料"))
        source_actions.append(f'<a class="button" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{label} ↗</a>')
    return HTMLResponse(
        DETAIL_TEMPLATE.replace("__TITLE__", html.escape(item["title_zh"]))
        .replace("__KICKER__", kicker)
        .replace("__META__", meta)
        .replace("__BRIEF__", html.escape(item.get("brief_zh") or item["summary_zh"]))
        .replace("__SUMMARY__", html.escape(item["summary_zh"]))
        .replace("__METHODOLOGY__", html.escape(item["methodology_zh"]))
        .replace("__FINDINGS__", html.escape(item["findings_zh"]))
        .replace("__WHY__", html.escape(item["why_zh"]))
        .replace("__LIMITATIONS__", html.escape(item["limitations_zh"]))
        .replace("__FEATURE_SECTION__", feature_section)
        .replace("__SHOCK_SECTION__", shock_section)
        .replace("__TAGS__", tags)
        .replace("__SOURCE_ACTIONS__", "".join(source_actions))
        .replace("__ORIGINAL_TITLE__", html.escape(item["original_title"]))
        .replace("__EDITORIAL_DATE__", html.escape(item["editorial_date"]))
        .replace("__QUALITY__", str(item.get("quality_score", 0)))
    )


@app.get("/", response_class=HTMLResponse)
def home():
    collector = stats()
    editorial = review_stats()
    sources = source_status()
    items = query_reviewed(limit=500, days=45)
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    source_rows = "".join(
        f'''<tr><td><span class="dot {'ok' if x.get('last_success') and not x.get('last_error') else ''}"></span>{html.escape(x['name'])}</td>
        <td>{html.escape(x['kind'])}</td><td>{x.get('last_new_count',0)}</td><td>{html.escape((x.get('last_error') or '正常')[:80])}</td></tr>'''
        for x in sources
    )
    latest = editorial.get("latest_editorial_date") or "等待首期"
    now = datetime.now(timezone.utc)
    rolling_cutoff = now - timedelta(hours=24)
    archive_cutoff = now - timedelta(days=30)

    def item_time(item):
        raw = item.get("published_at") or item.get("discovered_at")
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    fresh_items = [
        x for x in items
        if x.get("category") != "其他" and item_time(x) >= rolling_cutoff
    ]
    fresh_items.sort(key=lambda x: (
        item_time(x), int(bool(x.get("is_shock"))), int(bool(x.get("is_featured"))),
        int(x.get("quality_score") or 0)
    ), reverse=True)
    fresh_items = fresh_items[:10]
    fresh_ids = {int(x["item_id"]) for x in fresh_items}
    archive_items = [
        x for x in items
        if x.get("category") != "其他"
        and x.get("is_featured")
        and int(x["item_id"]) not in fresh_ids
        and item_time(x) >= archive_cutoff
    ]
    archive_items.sort(key=lambda x: (
        int(x.get("quality_score") or 0), item_time(x)
    ), reverse=True)
    archive_items = archive_items[:max(0, 10-len(fresh_items))]
    rolling_count = len([
        x for x in items if x.get("category") != "其他" and item_time(x) >= rolling_cutoff
    ])

    quick_sections = []
    sequence = 0
    for section in ("要闻", "模型发布", "开发生态", "前瞻传闻"):
        section_items = [x for x in fresh_items if (x.get("brief_section") or "要闻") == section]
        if not section_items:
            continue
        rows = []
        for item in section_items:
            sequence += 1
            flags = ""
            if item.get("is_featured"):
                flags += '<span class="badge featured">精选</span>'
            if item.get("is_shock"):
                flags += '<span class="badge shock">震惊瘫坐</span>'
            rows.append(
                f'<a class="quick-item" href="/article/{item["item_id"]}">'
                f'<span class="quick-num">{sequence:02d}</span><span class="quick-copy">'
                f'<b>{html.escape(item["title_zh"])}</b>'
                f'<small>{html.escape(item.get("brief_zh") or item["summary_zh"][:90])}</small></span>'
                f'<span class="quick-flags">{flags}</span></a>'
            )
        quick_sections.append(
            f'<section class="quick-section" data-section="{html.escape(section)}">'
            f'<h3>{html.escape(section)}</h3><div class="quick-list">{"".join(rows)}</div></section>'
        )
    if archive_items:
        rows = []
        for item in archive_items:
            sequence += 1
            rows.append(
                f'<a class="quick-item" href="/article/{item["item_id"]}">'
                f'<span class="quick-num">{sequence:02d}</span><span class="quick-copy">'
                f'<b>{html.escape(item["title_zh"])}</b>'
                f'<small>{html.escape(item.get("brief_zh") or item["summary_zh"][:90])}</small></span>'
                f'<span class="quick-flags"><span class="badge featured">近期精选</span></span></a>'
            )
        quick_sections.append(
            f'<section class="quick-section" data-section="近期精选">'
            f'<h3>近期精选</h3><div class="quick-list">{"".join(rows)}</div></section>'
        )
    quick_brief = "".join(quick_sections) or '<div class="quick-empty">正在等待下一轮小时更新。</div>'
    return HTMLResponse(
        content=HTML_TEMPLATE.replace("__ITEMS__", payload)
        .replace("__SOURCE_ROWS__", source_rows)
        .replace("__QUICK_BRIEF__", quick_brief)
        .replace("__ROLLING__", str(rolling_count))
        .replace("__PUBLISHED__", str(editorial.get("published_total", 0)))
        .replace("__PENDING__", str(editorial.get("pending_total", collector.get("total", 0))))
        .replace("__LATEST__", html.escape(latest)),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )
