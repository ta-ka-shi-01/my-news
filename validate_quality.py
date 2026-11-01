#!/usr/bin/env python3
"""Offline, same-input comparison; never overwrites the feed or calls the network."""
import argparse
import datetime as dt
import json
import runpy
from pathlib import Path
from xml.sax.saxutils import escape
from collect import TOPICS, clean_title, parse_rss

ROOT = Path(__file__).resolve().parent
BASELINE = runpy.run_path(str(ROOT / 'tests' / 'baseline_v02.py'))['parse_rss']

def rss(article, now, index):
    published = article.get('published', (now-dt.timedelta(days=article.get('days', 0))).isoformat())
    date = dt.datetime.fromisoformat(published).strftime('%a, %d %b %Y %H:%M:%S GMT')
    return (f'<rss><channel><item><title>{escape(article["title"])}</title>'
            f'<link>https://example.org/{index}</link><pubDate>{date}</pubDate>'
            f'<source>{escape(article.get("source", "Test"))}</source></item></channel></rss>').encode()

def compare(articles, now, labelled):
    result = {}
    for topic in TOPICS:
        entries = [(i,a) for i,a in enumerate(articles) if a['category']==topic]
        stats = {'input':len(entries),'v02_accepted':0,'v03_accepted':0,'removed':[]}
        if labelled:
            stats.update(wanted=sum(bool(a['wanted']) for _,a in entries),v02_wanted=0,v03_wanted=0,v02_noise=0,v03_noise=0,missed=[])
        for index,article in entries:
            xml = rss(article, now, index)
            old = bool(BASELINE(xml,topic,now)); new = bool(parse_rss(xml,topic,now))
            stats['v02_accepted'] += old; stats['v03_accepted'] += new
            if old and not new: stats['removed'].append(article['title'])
            if labelled:
                suffix='wanted' if article['wanted'] else 'noise'
                stats['v02_'+suffix] += old; stats['v03_'+suffix] += new
                if article['wanted'] and not new: stats['missed'].append(article['title'])
        result[topic] = stats
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',type=Path,default=ROOT/'news.json')
    parser.add_argument('--output',type=Path,default=ROOT/'quality-report.json')
    args=parser.parse_args()
    samples=json.loads((ROOT/'tests'/'quality_samples.json').read_text(encoding='utf-8-sig'))
    now=dt.datetime(2026,11,1,12,tzinfo=dt.timezone.utc)
    snapshot=json.loads(args.snapshot.read_text(encoding='utf-8-sig'))
    report={'method':'Same input to v0.2 and v0.3 parsers, before deduplication. No live RSS request.',
            'limitations':'Constructed labelled cases do not estimate real-world precision/recall. Snapshot contains only articles already selected by v0.2; excluded RSS items and ground truth are unavailable. Query coverage is not measured.',
            'samples':compare(samples,now,True),
            'snapshot_updated_at':snapshot['updated_at'],
            'snapshot':compare(snapshot['articles'],dt.datetime.fromisoformat(snapshot['updated_at']),False)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'samples':report['samples'],'snapshot_counts':{k:{s:v for s,v in d.items() if s!='removed'} for k,d in report['snapshot'].items()}},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
