#!/usr/bin/env python3
"""Google News RSS collector; standard library only."""
import datetime as dt
import email.utils
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOPICS = {
    'ゲーム業界': [
        'ゲーム 新作 発売 発表 when:2d',
        'ゲーム業界 企業 決算 開発 when:2d',
        'インディーゲーム 注目 新作 when:2d',
    ],
    '成人向け同人ゲーム': [
        'DLsite 同人ゲーム 規約 変更 when:14d',
        'FANZA 同人 ゲーム 規約 変更 when:14d',
        '成人向け 同人ゲーム 売上 ランキング when:14d',
        '成人向け AI生成作品 販売 規制 when:14d',
    ],
    '野球': [
        '横浜DeNA ベイスターズ when:2d',
        'プロ野球 NPB ドラフト 移籍 試合 when:2d',
        'MLB 日本人選手 大ニュース when:2d',
        '高校野球 甲子園 大会 when:2d',
    ],
}
ADULT_STRONG = ('規約', '禁止', '変更', '審査', '規制', '販売停止', '決済', 'ランキング', '売上', '生成AI', 'AI生成', 'FANZA', 'DLsite')
ADULT_RELEVANT = ('同人', '成人向け', 'アダルト', 'DLsite', 'FANZA', 'R18', 'R-18')

def parse_rss(xml_bytes, topic, now):
    root = ET.fromstring(xml_bytes)
    items = []
    for node in root.findall('./channel/item'):
        title = (node.findtext('title') or '').strip()
        link = (node.findtext('link') or '').strip()
        raw_date = node.findtext('pubDate') or ''
        source_node = node.find('source')
        source = source_node.text.strip() if source_node is not None and source_node.text else ''
        try:
            published = email.utils.parsedate_to_datetime(raw_date).astimezone(dt.timezone.utc)
        except (ValueError, TypeError):
            continue
        age = now - published
        if age.total_seconds() < -3600 or age > dt.timedelta(days=14 if topic == '成人向け同人ゲーム' else 2):
            continue
        if not title or not link.startswith('https://'):
            continue
        if topic == '成人向け同人ゲーム':
            text = title + ' ' + source
            if not any(w.casefold() in text.casefold() for w in ADULT_RELEVANT):
                continue
            if not any(w.casefold() in text.casefold() for w in ADULT_STRONG):
                continue
        items.append({'category': topic, 'title': title, 'url': link, 'source': source,
                      'published': published.isoformat(), 'priority': '注目' if topic == '成人向け同人ゲーム' else '通常'})
    return items

def collect(fetch=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if fetch is None:
        def fetch(url):
            req = urllib.request.Request(url, headers={'User-Agent': 'MyNewsFeed/0.1 (personal RSS reader)'})
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read()
    seen = set()
    results = []
    errors = []
    for topic, queries in TOPICS.items():
        for query in queries:
            url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl':'ja', 'gl':'JP', 'ceid':'JP:ja'})
            try:
                items = parse_rss(fetch(url), topic, now)
                for item in items:
                    normalized = re.sub(r'\W+', '', item['title'].split(' - ')[0]).casefold()
                    key = (topic, normalized)
                    if key not in seen:
                        seen.add(key)
                        results.append(item)
            except Exception as exc:
                errors.append({'category': topic, 'query': query, 'error': str(exc)[:160]})
    results.sort(key=lambda a: a['published'], reverse=True)
    return {'updated_at': now.isoformat(), 'articles': results, 'errors': errors}

if __name__ == '__main__':
    result = collect()
    output = ROOT / 'news.json'
    # Preserve previous successful data when all sources fail.
    if len(result['errors']) == sum(map(len, TOPICS.values())):
        raise SystemExit('All RSS sources failed; keeping previous news.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('articles:', len(result['articles']), 'errors:', len(result['errors']))
