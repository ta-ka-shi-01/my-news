#!/usr/bin/env python3
"""Free, standard-library RSS collection with explainable scoring and diagnostics."""
import datetime as dt
import email.utils
import json
import html
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path
from quality import adult_scope
from ranking import assess, features, rank_value, rank_articles, related_to, attach_related

ROOT = Path(__file__).resolve().parent
UTC = dt.timezone.utc
RULES = json.loads((ROOT / 'scoring.json').read_text(encoding='utf-8-sig'))
TOPICS = {
    'ゲーム業界': [
        'ゲーム (新作 OR 発表 OR 発売日 OR 発売) when:2d',
        'ゲーム (大型アップデート OR 新シーズン OR 拡張パック) when:2d',
        'ゲーム (決算 OR 事業戦略 OR 開発体制) when:2d',
        'ゲーム (買収 OR 開発中止 OR レイオフ OR スタジオ閉鎖) when:2d',
        'インディーゲーム (新作 OR 発売 OR リリース) when:2d',
    ],
    '成人向け同人ゲーム': [
        'DLsite (規約 OR 審査 OR 決済) when:14d',
        'FANZA 同人 (規約 OR 審査 OR AI作品) when:14d',
        '成人向け 同人ゲーム (市場 OR 売上 OR ランキング) when:14d',
        '成人向け (生成AI OR AI技術 OR 画像生成) 制作 when:14d',
        '同人ゲーム (販売停止 OR 表現規制 OR 決済) when:14d',
        'site:dlsite.com (規約 OR 審査 OR AI作品) when:14d',
        'site:dlsite.com (決済 OR 販売停止) when:14d',
        'site:dmm.co.jp 同人 (規約 OR 審査 OR AI作品) when:14d',
    ],
    '野球': [
        '(横浜DeNA OR ベイスターズ) (試合 OR 選手 OR 勝利 OR 契約) when:2d',
        'DeNA (補強 OR ドラフト OR 監督 OR コーチ OR 来季) when:2d',
        '(NPB OR プロ野球) (移籍 OR FA OR ドラフト) when:2d',
        'プロ野球 (日本シリーズ OR 制度変更 OR 記録 OR 優勝) when:2d',
        'MLB (ワールドシリーズ OR 記録 OR 移籍 OR MVP) when:2d',
        '(高校野球 OR 甲子園) (決勝 OR 大会 OR 開幕 OR 中止) when:2d',
    ],
}
OFFICIAL_DOMAINS = ('dlsite.com', 'dmm.co.jp')
GAME_SOURCES = ('4gamer', 'ファミ通', 'game watch', 'automaton', 'gamespark', 'game*spark', '電ファミ', '電撃オンライン', 'gamebiz', 'gamebusiness', 'インサイド')
BASEBALL_SOURCES = ('full-count', 'サンスポ', 'スポニチ', '日刊スポーツ', 'baseball king', 'ベースボールチャンネル', 'バーチャル高校野球')
REASONS = {
    'invalid': 'タイトル・URL・公開日時が不正', 'future': '未来の公開日時',
    'old': '公開日時が収集対象期間外', 'unrelated': 'カテゴリとの関連性不足',
    'non_game_market': '同人ゲーム市場との関連性不足', 'low_score': '関連性・重要度スコア不足',
    'individual_update':'個別作品の販売停止・販売告知', 'work_promotion':'作品紹介・おすすめ・単なる宣伝', 'duplicate': '同一・類似記事', 'same_story': '同一の出来事（代表記事へ関連リンクを集約）',
}


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def contains(text, words):
    # ASCII words use boundaries: e.g. FA must not match "fan" or "FANZA".
    text = unicodedata.normalize('NFKC', text).casefold()
    for word in words:
        word = unicodedata.normalize('NFKC', word).casefold()
        if re.fullmatch(r'[a-z0-9 -]+', word):
            if re.search(r'(?<![a-z0-9])' + re.escape(word) + r'(?![a-z0-9])', text):
                return True
        elif word in text:
            return True
    return False


def clean_title(title, source):
    # Remove only an exact publisher suffix; never split arbitrary title hyphens.
    if not source:
        return title.strip()
    suffix = re.compile(r'\s*[-–—|｜]\s*' + re.escape(source.strip()) + r'\s*$', re.I)
    while suffix.search(title):
        title = suffix.sub('', title)
    return title.strip()


def score_article(article, topic):
    config = RULES[topic]
    title = article['title']
    context = contains(title, config['context'])
    if topic == 'ゲーム業界':
        context |= contains(article.get('source', ''), GAME_SOURCES)
        # Keep general indie titles out of adult-only coverage, and vice versa.
        if contains(title, ('成人向け', 'アダルト', 'R18', 'R-18', 'エロゲ')):
            return 0, [], 'unrelated'
    if topic == '成人向け同人ゲーム':
        context |= official_publisher(article.get('source_url', ''))
    if topic == '野球':
        context |= contains(article.get('source', ''), BASEBALL_SOURCES)
    if not context:
        return 0, [], 'unrelated'
    matches = [r for r in config['rules'] if contains(title, r['words'])]
    if topic == '成人向け同人ゲーム':
        # Platform names alone do not make a product advert useful to a creator.
        names = {r['name'] for r in matches}
        if names == {'市場・ヒット'} and not contains(title, ('ゲーム', '同人', '制作', 'クリエイター')) and not adult_scope(article,config)['useful']:
            return 0, [], 'non_game_market'
    score = sum(r['weight'] for r in matches)
    if re.search(r'[＜<]?画像\s*\d+\s*/', title):
        score -= 8
        matches.append({'name': '画像ページ', 'weight': -8})
    reasons = [{'rule': r['name'], 'points': r['weight']} for r in matches]
    signals=features(article,config)
    # Anniversary/goods words must not discard an actual new game announcement.
    if topic == '成人向け同人ゲーム':
        classification=adult_scope(article,config)
        if classification['classification'] in ('individual_update','work_promotion'):
            return score,reasons,classification['classification']
        if classification['useful'] and score < config['threshold']:
            reasons.append({'rule':'影響範囲・分析・制作情報の評価','points':config['threshold']-score})
            score=config['threshold']
    if topic == 'ゲーム業界' and signals['substantive'] and score < config['threshold']:
        reasons.append({'rule':'実質的なゲームニュースの保護','points':config['threshold']-score})
        score=config['threshold']
    protected=any(r['name'] in config.get('protected_rules', []) for r in matches)
    if topic == '成人向け同人ゲーム' and not signals['policy']:
        protected=False
    # Protection affects acceptance, not the independent importance assessment.
    if protected:
        floor = config['important']
        if score < floor:
            reasons.append({'rule': '重要事項の保護', 'points': floor-score})
            score = floor
    return score, reasons, None if score >= config['threshold'] else 'low_score'


def official_publisher(source_url):
    try:
        host = (urllib.parse.urlsplit(source_url).hostname or '').lower()
    except ValueError:
        return False
    return any(host == domain or host.endswith('.' + domain) for domain in OFFICIAL_DOMAINS)


def valid_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return parsed.scheme == 'https' and bool(parsed.hostname)
    except ValueError:
        return False


def read_rss(xml_bytes, topic, now):
    root = ET.fromstring(xml_bytes)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('RSS channel missing')
    records = []
    for node in root.findall('./channel/item'):
        source = (node.findtext('source') or '').strip()
        source_node = node.find('source')
        article = {'category': topic, 'title': clean_title(node.findtext('title') or '', source),
                   'url': (node.findtext('link') or '').strip(), 'source': source,
                   'source_url': source_node.get('url', '') if source_node is not None else '',
                   'summary': html.unescape(re.sub(r'<[^>]+>',' ',node.findtext('description') or ''))[:1000]}
        try:
            published = email.utils.parsedate_to_datetime(node.findtext('pubDate') or '')
            if published.tzinfo is None:
                raise ValueError('Timezone missing')
            published = published.astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            records.append((article, 'invalid'))
            continue
        article['published'] = published.isoformat()
        age = now - published
        score, reasons, rejected = score_article(article, topic)
        article.update(score=score, score_reasons=reasons,
                       priority=assess(article,RULES[topic])['priority'])
        if not article['title'] or not valid_url(article['url']):
            rejected = 'invalid'
        elif age.total_seconds() < -3600:
            rejected = 'future'
        elif age > dt.timedelta(days=RULES[topic]['days']):
            rejected = 'old'
        if topic == '成人向け同人ゲーム' and any(r['rule'] == '規約・審査・決済' for r in reasons):
            # RSS publisher metadata is a lead, not proof that a policy changed.
            article['official_confirmation'] = 'official_publisher_unverified' if official_publisher(article['source_url']) else 'needs_official_review'
        records.append((article, rejected))
    return records


def parse_rss(xml_bytes, topic, now):
    """Backward-compatible interface used by the v0.2 tests."""
    return [a for a, reason in read_rss(xml_bytes, topic, now) if not reason]


def normalized(title):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', title).casefold())


def duplicate(article, existing):
    key = normalized(clean_title(article['title'], article.get('source', '')))
    for other in existing:
        if other['category'] != article['category']:
            continue
        if article['url'] == other['url']:
            return True
        previous = normalized(clean_title(other['title'], other.get('source', '')))
        if key == previous:
            return True
        # Conservative: preserve dates/numbers and changed event language.
        events = ('延期', '中止', '発売', '発表', '勝利', '敗戦', '変更', '撤回', '停止', '再開')
        if (min(len(key), len(previous)) >= 24
                and re.findall(r'\d+', key) == re.findall(r'\d+', previous)
                and [w for w in events if w in key] == [w for w in events if w in previous]
                and SequenceMatcher(None, key, previous, autojunk=False).ratio() >= .94):
            return True
    return False


def default_fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'MyNewsFeed/0.3.2 (personal RSS reader)'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def collect(fetch=None, now=None, previous=None, previous_diagnostics=None):
    now = now or dt.datetime.now(UTC)
    fetch = fetch or default_fetch
    previous = previous or {}
    previous_diagnostics = previous_diagnostics or previous.get('diagnostics', {})
    errors, output, candidates = [], [], []
    diagnostics = {'version': '0.3.2', 'attempted_at': now.isoformat(), 'categories': {}, 'reason_labels': REASONS, 'scoring': RULES}
    for topic, queries in TOPICS.items():
        old = previous_diagnostics.get('categories', {}).get(topic, {})
        diag = {'fetched': 0, 'accepted': 0, 'excluded': 0, 'retained': 0,
                'exclusion_reasons': {}, 'queries': [], 'decisions': [],
                'last_success_at': old.get('last_success_at'),
                'last_complete_success_at': old.get('last_complete_success_at')}
        diagnostics['categories'][topic] = diag
        for query in queries:
            q = {'query': query, 'status': 'ok', 'fetched': 0, 'accepted': 0, 'excluded': 0, 'exclusion_reasons': {}}
            diag['queries'].append(q)
            url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl': 'ja', 'gl': 'JP', 'ceid': 'JP:ja'})
            try:
                records = read_rss(fetch(url), topic, now)
            except Exception as exc:
                q.update(status='failed', error=str(exc)[:160])
                errors.append({'category': topic, 'query': query, 'error': q['error']})
                continue
            diag['last_success_at'] = now.isoformat()
            for article, reason in records:
                q['fetched'] += 1
                diag['fetched'] += 1
                decision = {'title': article['title'], 'url': article['url'],
                            'score': article.get('score'), 'score_reasons': article.get('score_reasons', []),
                            'reason': reason, 'query': query}
                decision.update({key:article.get(key) for key in ('category','published','source','source_url','summary')})
                decision['classification']=assess(article,RULES[topic])
                if article.get('official_confirmation'):
                    decision.update(official_confirmation=article['official_confirmation'], source_url=article['source_url'])
                diag['decisions'].append(decision)
                if reason:
                    reject(diag, q, decision, reason)
                else:
                    candidates.append((article, diag, q, decision))
        success = sum(q['status'] == 'ok' for q in diag['queries'])
        diag['status'] = 'failed' if success == 0 else 'partial' if success < len(queries) else 'ok'
        if diag['status'] == 'ok':
            diag['last_complete_success_at'] = now.isoformat()
    # Choose the strongest representative before grouping the same event.
    for article, diag, q, decision in sorted(candidates, key=lambda c: (rank_value(c[0],RULES[c[0]['category']],now)[0],c[0]['published']), reverse=True):
        old = next((a for a in previous.get('articles', [])
                    if a.get('category') == article['category'] and a.get('title') and a.get('url')
                    and timestamp(a.get('published')) and duplicate(article, [a])), None)
        if old:
            article['first_seen_at'] = old.get('first_seen_at', old['published'])
            if timestamp(old['published']) < timestamp(article['published']):
                article['published'] = old['published']
            if now - timestamp(article['published']) > dt.timedelta(days=RULES[article['category']]['days']):
                reject(diag, q, decision, 'old')
                continue
        if duplicate(article, output):
            reject(diag, q, decision, 'duplicate')
        elif (representative := related_to(article,output,RULES[article['category']])) is not None:
            attach_related(representative,article)
            decision['grouped_into']=representative['url']
            reject(diag,q,decision,'same_story')
        else:
            article.setdefault('first_seen_at', now.isoformat())
            output.append(article)
            diag['accepted'] += 1
            q['accepted'] += 1
            decision['reason'] = 'accepted'
    for article in previous.get('articles', []):
        topic = article.get('category')
        if topic not in RULES or not timestamp(article.get('published')):
            continue
        diag = diagnostics['categories'][topic]
        fresh = next((a for a in output if a['category'] == topic and duplicate(article, [a])), None)
        if fresh:
            fresh['first_seen_at'] = article.get('first_seen_at', article['published'])
            continue
        representative=related_to(article,output,RULES[topic])
        if representative is not None:
            attach_related(representative,article)
            continue
        score, reasons, rejected = score_article(article, topic)
        important_adult = topic == '成人向け同人ゲーム' and score >= RULES[topic]['important'] and features(article,RULES[topic])['substantive']
        days = RULES[topic].get('retain_days', RULES[topic]['days']) if important_adult else RULES[topic]['days']
        age = now - timestamp(article['published'])
        failed = diag['status'] in ('partial', 'failed')
        if (failed or important_adult) and not rejected and dt.timedelta(hours=-1) <= age <= dt.timedelta(days=days):
            saved = dict(article, title=clean_title(article['title'], article.get('source', '')),
                         score=score, score_reasons=reasons,
                         priority=assess(article,RULES[topic])['priority'],
                         retained=True, retained_reason='fetch_failure' if failed else 'important_adult',
                         first_seen_at=article.get('first_seen_at', article['published']))
            if not duplicate(saved, output):
                output.append(saved)
                diag['retained'] += 1
    for diag in diagnostics['categories'].values():
        diag['displayed'] = diag['accepted'] + diag['retained']
        diag['empty_reason'] = ('B_fetch_failed' if diag['status'] == 'failed' else
                                'partial_fetch_failure' if diag['status'] == 'partial' else
                                'has_articles' if diag['accepted'] else
                                'A_no_results' if diag['fetched'] == 0 else 'C_all_filtered')
    output=rank_articles(output,RULES,now)
    for topic,diag in diagnostics['categories'].items():
        ranked=[a for a in output if a['category']==topic]
        diag['top5']=[{'title':a['title'],'importance':a['importance'],'ranking_score':a['ranking_score'],
                       'priority':a['priority'],'interest':a['interest'],'reasons':a['importance_reasons'],
                       'ranking_reasons':a['ranking_reasons'],'info_type':a['info_type'],
                       'scope':a.get('scope'),'context':a.get('temporal_context')} for a in ranked[:5]]
    baseball = [a for a in output if a['category'] == '野球']
    diagnostics['baseball_coverage'] = {
        'dena': sum(contains(a['title'], ('DeNA', 'ベイスターズ')) for a in baseball),
        'other': sum(not contains(a['title'], ('DeNA', 'ベイスターズ')) for a in baseball),
        'note': 'DeNA以外も独立クエリで検索。件数の水増しや固定枠は設けません。',
    }
    diagnostics['all_failed'] = all(d['status'] == 'failed' for d in diagnostics['categories'].values())
    return {'updated_at': now.isoformat(), 'articles': output, 'errors': errors, 'diagnostics': diagnostics}


def reject(diag, query, decision, reason):
    decision['reason'] = reason
    for target in (diag, query):
        target['excluded'] += 1
        counts = target['exclusion_reasons']
        counts[reason] = counts.get(reason, 0) + 1


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}


def write_json(path, value):
    # Replace only a complete serialized file; an interruption cannot truncate news.json.
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run(root=ROOT, fetch=None, now=None):
    output = root / 'news.json'
    previous = read_json(output)
    result = collect(fetch, now, previous, read_json(root / 'diagnostics.json'))
    if result['diagnostics']['all_failed']:
        # The unchanged file, including old articles, is the actual display source.
        for topic, diag in result['diagnostics']['categories'].items():
            diag['retained'] = sum(a.get('category') == topic for a in previous.get('articles', []))
            diag['displayed'] = diag['retained']
            diag['top5']=[{key:a[key] for key in ('title','published','priority','importance','ranking_score') if key in a} for a in previous.get('articles',[]) if a.get('category')==topic][:5]
            diag['top5_source']='preserved_previous_feed'
    write_json(root / 'diagnostics.json', result['diagnostics'])
    if not result['diagnostics']['all_failed']:
        write_json(output, result)
    for topic, diag in result['diagnostics']['categories'].items():
        print(topic, diag['status'], 'fetched:', diag['fetched'], 'accepted:', diag['accepted'],
              'excluded:', diag['excluded'], 'retained:', diag['retained'], diag['empty_reason'])
        print('  最終取得成功:', diag['last_success_at'] or '未確認',
              '全検索成功:', diag['last_complete_success_at'] or '未確認')
        print('  主な除外理由:', ', '.join(f'{REASONS.get(k,k)} {v}件' for k,v in sorted(diag['exclusion_reasons'].items(),key=lambda x:x[1],reverse=True)[:3]) or 'なし')
        for query in diag['queries']:
            print('  検索:', query['status'], query['fetched'], '件 / 採用', query['accepted'],
                  query['query'], query.get('error', ''))
    return 1 if result['diagnostics']['all_failed'] else 0


if __name__ == '__main__':
    raise SystemExit(run())
