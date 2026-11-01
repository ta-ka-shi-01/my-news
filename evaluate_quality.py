#!/usr/bin/env python3
"""Same-input comparison of delivered v0.3.1 and v0.3.2; never updates news.json."""
import argparse,datetime as dt,json,runpy,sys,types,urllib.parse
from pathlib import Path
from xml.sax.saxutils import escape
from collect import collect,TOPICS
ROOT=Path(__file__).resolve().parent

def baseline():
    folder=ROOT/'tests'/'baseline_v031'
    module=types.ModuleType('ranking');module.__dict__.update(runpy.run_path(str(folder/'ranking.py')))
    current=sys.modules.get('ranking');sys.modules['ranking']=module
    try:return runpy.run_path(str(folder/'collect.py'))
    finally:
        if current is None:sys.modules.pop('ranking',None)
        else:sys.modules['ranking']=current

BASELINE=baseline()

def make_feeds(articles,now):
    feeds={}
    for category in TOPICS:
        parts=[]
        for i,a in enumerate(articles):
            if a['category']!=category:continue
            published=a.get('published',(now-dt.timedelta(hours=a.get('hours',0))).isoformat())
            date=dt.datetime.fromisoformat(published).strftime('%a, %d %b %Y %H:%M:%S GMT')
            parts.append(f'<item><title>{escape(a["title"])}</title><link>https://example.org/replay/{i}</link><pubDate>{date}</pubDate><source>{escape(a.get("source","Test"))}</source><description>{escape(a.get("summary",""))}</description></item>')
        feeds[category]=('<rss><channel>'+''.join(parts)+'</channel></rss>').encode()
    def fetch(url):
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['q'][0]
        return feeds[next(t for t,queries in TOPICS.items() if query in queries)]
    return fetch

def compare(articles,now):
    fetch=make_feeds(articles,now)
    before=BASELINE['collect'](fetch=fetch,now=now);after=collect(fetch=fetch,now=now)
    result={}
    for cat in TOPICS:
        result[cat]={}
        for version,data in [('v031',before),('v032',after)]:
            diag=data['diagnostics']['categories'][cat]
            result[cat][version]={key:diag[key] for key in ('fetched','accepted','excluded','retained','exclusion_reasons')}
            picked=[a for a in data['articles'] if a['category']==cat]
            keys=('title','published','priority','importance','ranking_score','info_type','scope','temporal_context')
            result[cat][version]['top5']=[{k:a[k] for k in keys if k in a} for a in picked[:5]]
    return result,after['diagnostics']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,default=ROOT/'tests/quality_samples_v032.json');parser.add_argument('--output-dir',type=Path,default=Path('quality-evaluation'));args=parser.parse_args()
    raw=json.loads(args.input.read_text(encoding='utf-8-sig'))
    articles=raw['articles'] if isinstance(raw,dict) else raw
    now=dt.datetime.fromisoformat(raw['updated_at']) if isinstance(raw,dict) else dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
    comparison,diagnostics=compare(articles,now)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    report={'input':str(args.input),'input_count':len(articles),'evaluation_time':now.isoformat(),
            'method':'Same RSS replay per category and query. Input labelled sample or saved feed; not new RSS collection. Counts include cross-query duplicates.',
            'categories':comparison}
    (args.output_dir/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (args.output_dir/'diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved comparison.json and diagnostics.json to',args.output_dir)

if __name__=='__main__':main()
