#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily updater for AI Skill & Project Radar.
- Fetches GitHub topic/RSS-style public pages and selected feeds.
- Appends candidate articles/videos/projects to inbox/YYYY-MM-DD.json.
- Updates public site with a daily digest section.
This script is intentionally conservative: it stores title/url/source/type/date only, no secrets.
"""
import json, re, sys, html, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data.json'
INDEX = ROOT / 'index.html'
INBOX = ROOT / 'inbox'
INBOX.mkdir(exist_ok=True)
TODAY = datetime.now().strftime('%Y-%m-%d')
UA = 'Mozilla/5.0 (compatible; AI-Skill-Radar/1.0)'

SOURCES = [
    {'name':'GitHub AI Agent topic', 'type':'project', 'url':'https://github.com/topics/ai-agent'},
    {'name':'GitHub MCP topic', 'type':'project', 'url':'https://github.com/topics/mcp'},
    {'name':'GitHub LLM Agents topic', 'type':'project', 'url':'https://github.com/topics/llm-agents'},
    {'name':'Hacker News: AI agents', 'type':'article', 'url':'https://hn.algolia.com/api/v1/search_by_date?query=AI%20agent&tags=story'},
    {'name':'Hacker News: MCP', 'type':'article', 'url':'https://hn.algolia.com/api/v1/search_by_date?query=MCP%20AI&tags=story'},
    {'name':'Hugging Face blog', 'type':'article', 'url':'https://huggingface.co/blog/feed.xml'},
    {'name':'OpenAI blog', 'type':'article', 'url':'https://openai.com/news/rss.xml'},
    {'name':'Anthropic news', 'type':'article', 'url':'https://www.anthropic.com/news/rss.xml'},
    {'name':'LangChain blog', 'type':'article', 'url':'https://blog.langchain.dev/rss/'},
    {'name':'Latent Space podcast', 'type':'video/audio', 'url':'https://www.latent.space/feed'},
]

def fetch(url, timeout=18):
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/rss+xml,application/json,*/*'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(s or '')).strip()

def slug_id(url):
    return hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]

def parse_github_topic(text, source, typ):
    out=[]
    # GitHub topic pages include repo links like /owner/repo
    for m in re.finditer(r'<h3[^>]*>\s*<a[^>]+href="/([^/]+/[^/"]+)"[^>]*>(.*?)</a>', text, re.S):
        repo = clean(re.sub('<.*?>',' ',m.group(1)))
        if not repo or repo.count('/')!=1: continue
        url = 'https://github.com/' + repo
        out.append({'id':slug_id(url),'title':repo,'url':url,'source':source,'type':typ,'note':'GitHub topic candidate'})
    if not out:
        for repo in sorted(set(re.findall(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', text)))[:20]:
            url='https://github.com/'+repo
            out.append({'id':slug_id(url),'title':repo,'url':url,'source':source,'type':typ,'note':'GitHub topic candidate'})
    return out[:12]

def parse_hn_json(text, source, typ):
    out=[]
    try: data=json.loads(text)
    except Exception: return out
    for h in data.get('hits',[])[:12]:
        title=clean(h.get('title') or h.get('story_title'))
        url=h.get('url') or ('https://news.ycombinator.com/item?id='+str(h.get('objectID')))
        if not title or not url: continue
        out.append({'id':slug_id(url),'title':title,'url':url,'source':source,'type':typ,'note':f"HN points: {h.get('points') or 0}"})
    return out

def parse_feed(text, source, typ):
    out=[]
    try:
        root=ET.fromstring(text.encode('utf-8'))
    except Exception:
        return out
    # RSS
    for item in root.findall('.//item')[:10]:
        title=clean(item.findtext('title'))
        link=clean(item.findtext('link'))
        if title and link:
            out.append({'id':slug_id(link),'title':title,'url':link,'source':source,'type':typ,'note':'RSS item'})
    # Atom
    ns='{http://www.w3.org/2005/Atom}'
    for entry in root.findall(f'.//{ns}entry')[:10]:
        title=clean(entry.findtext(f'{ns}title'))
        link=''
        for l in entry.findall(f'{ns}link'):
            link=l.attrib.get('href','')
            if link: break
        if title and link:
            out.append({'id':slug_id(link),'title':title,'url':link,'source':source,'type':typ,'note':'Atom item'})
    return out

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return default

def main():
    candidates=[]
    errors=[]
    for src in SOURCES:
        try:
            text=fetch(src['url'])
            if 'github.com/topics' in src['url']:
                found=parse_github_topic(text, src['name'], src['type'])
            elif 'hn.algolia.com' in src['url']:
                found=parse_hn_json(text, src['name'], src['type'])
            else:
                found=parse_feed(text, src['name'], src['type'])
            candidates.extend(found)
        except Exception as e:
            errors.append({'source':src['name'],'error':str(e)[:180]})
    seen=set()
    uniq=[]
    for c in candidates:
        if c['id'] in seen: continue
        seen.add(c['id']); uniq.append(c)
    daily={'date':TODAY,'generated_at':datetime.now(timezone.utc).isoformat(),'count':len(uniq),'items':uniq[:80],'errors':errors}
    (INBOX / f'{TODAY}.json').write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding='utf-8')
    # write a small latest digest json for site use
    (ROOT / 'latest-digest.json').write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"采集完成：{len(uniq)} 条候选，保存到 inbox/{TODAY}.json")
    if errors:
        print(f"部分来源失败：{len(errors)} 个")

if __name__ == '__main__':
    main()
