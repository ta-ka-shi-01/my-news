#!/usr/bin/env python3
"""Offline v0.3/v0.3.1 replay with the same feed inputs; never writes news.json."""
import argparse
import datetime as dt
import json
import runpy
import urllib.parse
from pathlib import Path
from xml.sax.saxutils import escape
from collect import collect

ROOT=Path(__file__).resolve().parent
BASELINE=runpy.run_path(str(ROOT/'tests'/'baseline_v03'/'collect.py'))

def make_feeds(articles,now):
    feeds={}
    for category in BASELINE['TOPICS']:
        items=[]
        for i,a in enumerate(articles):
            if a['category']!=category:continue
            published=a.get('published',(now-dt.timedelta(hours=a.get('hours',0))).isoformat())
            date=dt.datetime.fromisoformat(published).strftime('%a, %d %b %Y %H:%M:%S GMT')
            items.append(f'<item><title>{escape(a["title"])}</title><link>https://example.org/replay/{i}</link><pubDate>{date}</pubDate><source>{escape(a.get("source","Test"))}</source></item>')
        feeds[category]=('<rss><channel>'+''.join(items)+'</channel></rss>').encode()
    def fetch(url):
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['q'][0]
        category=next(t for t,queries in BASELINE['TOPICS'].items() if query in queries)
        return feeds[category]
    return fetch

def compare(articles,now):
    fetch=make_feeds(articles,now)
    old=BASELINE['collect'](fetch=fetch,now=now)
    new=collect(fetch=fetch,now=now)
    report={}
    for category in BASELINE['TOPICS']:
        report[category]={}
        for key,result in [('v03',old),('v031',new)]:
            picked=[a for a in result['articles'] if a['category']==category]
            report[category][key]={
                'accepted':len(picked),'notable':sum(a['priority']=='注目' for a in picked),
                'top5':[{k:a[k] for k in ['title','published','priority','importance','ranking_score'] if k in a} for a in picked[:5]],
                'same_story_grouped':result['diagnostics']['categories'][category]['exclusion_reasons'].get('same_story',0)}
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',type=Path);parser.add_argument('--output',type=Path,default=Path('ranking-comparison.json'));args=parser.parse_args()
    samples=json.loads((ROOT/'tests'/'ranking_samples.json').read_text(encoding='utf-8-sig'))
    now=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
    report={'method':'Same RSS replay, no live request. Baseline is frozen delivered v0.3. Counts include selection and grouping.',
            'sample':compare(samples,now)}
    if args.snapshot:
        snapshot=json.loads(args.snapshot.read_text(encoding='utf-8-sig'))
        report['snapshot_updated_at']=snapshot['updated_at']
        report['snapshot']=compare(snapshot['articles'],dt.datetime.fromisoformat(snapshot['updated_at']))
        report['snapshot_limitations']='The snapshot in this workspace predates v0.3 production. This is an offline replay, not a comparison of actual production v0.3 collection. No ground truth labels or raw rejected RSS entries are available.'
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Comparison saved:',args.output)

if __name__=='__main__':main()
