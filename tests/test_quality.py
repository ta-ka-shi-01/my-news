import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape
from collect import (collect, run, parse_rss, clean_title, duplicate,
                     official_publisher, RULES, TOPICS, score_article)

NOW = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)
GAME, ADULT, BALL = list(TOPICS)

def feed(*titles, days=0, source='Test', source_url='https://example.org'):
    date = (NOW-dt.timedelta(days=days)).strftime('%a, %d %b %Y %H:%M:%S GMT')
    items = ''.join(f'<item><title>{escape(t)}</title><link>https://example.org/{i}</link><pubDate>{date}</pubDate><source url="{source_url}">{escape(source)}</source></item>' for i,t in enumerate(titles))
    return f'<rss><channel>{items}</channel></rss>'.encode()

def article(topic, title, days=0):
    return {'category':topic,'title':title,'source':'Test','url':'https://example.org/previous',
            'published':(NOW-dt.timedelta(days=days)).isoformat(),'priority':'通常'}

def fail(_):
    raise OSError('sample network failure')

class QualityTests(unittest.TestCase):
    def test_noise(self):
        for topic,title in [(GAME,'ゲーム攻略Wiki 最強装備'),(GAME,'ゲーム新作グッズ抽選キャンペーン'),
                            (BALL,'元プロ野球選手の熱愛と私生活'),(BALL,'DeNA選手がSNS投稿'),
                            (ADULT,'FANZA 動画ランキング'),(ADULT,'DLsite クーポンセール'),
                            (ADULT,'一般向けインディーゲーム 新作発売')]:
            with self.subTest(title=title): self.assertEqual(parse_rss(feed(title),topic,NOW),[])

    def test_important_news_survives_nuisance_words(self):
        for topic,title in [(GAME,'ゲーム会社の決算、グッズ事業と開発体制を説明'),
                            (ADULT,'DLsite 決済規約変更、セール作品も対象'),
                            (BALL,'NPBがSNS投稿に関するルール変更を発表')]:
            with self.subTest(title=title): self.assertEqual(len(parse_rss(feed(title),topic,NOW)),1)

    def test_indie_and_adult_ai(self):
        self.assertEqual(len(parse_rss(feed('インディーゲーム新作発売'),GAME,NOW)),1)
        self.assertEqual(len(parse_rss(feed('成人向けコンテンツ制作の画像生成AI技術'),ADULT,NOW)),1)

    def test_npball_not_only_dena(self):
        result=collect(fetch=lambda _:feed('DeNA 来季の補強発表','NPB ルール変更を発表','MLB ワールドシリーズ決勝'),now=NOW)
        self.assertEqual(result['diagnostics']['baseball_coverage']['dena'],1)
        self.assertEqual(result['diagnostics']['baseball_coverage']['other'],2)

    def test_title_suffix(self):
        self.assertEqual(clean_title('ゲーム - 新作 - Test - Test','Test'),'ゲーム - 新作')
        self.assertEqual(clean_title('ゲーム - 新作','Test'),'ゲーム - 新作')

    def test_dedup_and_material_differences(self):
        a=article(GAME,'ゲーム新作の発売日を発表、最新の開発情報と詳細を公開');a['url']='https://example.org/a'
        b=dict(a,title=a['title']+'！',url='https://example.org/b')
        self.assertTrue(duplicate(b,[a]))
        self.assertFalse(duplicate(dict(b,title='ゲーム新作の発売日を延期、最新の開発情報と詳細を公開'),[a]))
        self.assertFalse(duplicate(dict(b,title=a['title']+'2027'),[a]))

    def test_diagnostic_accounting(self):
        result=collect(fetch=lambda _:feed('ゲーム新作発売','ゲーム攻略Wiki'),now=NOW)
        for diag in result['diagnostics']['categories'].values():
            self.assertEqual(diag['fetched'],diag['accepted']+diag['excluded'])
            self.assertEqual(diag['excluded'],sum(diag['exclusion_reasons'].values()))
            self.assertEqual(diag['fetched'],sum(q['fetched'] for q in diag['queries']))
            for q in diag['queries']: self.assertEqual(q['fetched'],q['accepted']+q['excluded'])

    def test_three_empty_causes(self):
        for fetch,expected in [(lambda _:feed(),'A_no_results'),(fail,'B_fetch_failed'),
                               (lambda _:feed('一般向けインディーゲーム 新作発売'),'C_all_filtered')]:
            result=collect(fetch=fetch,now=NOW)
            self.assertEqual(result['diagnostics']['categories'][ADULT]['empty_reason'],expected)

    def test_malformed_rss_is_failure_not_empty(self):
        for xml in (b'<html/>', b'<rss>', b'<rss/>'):
            result=collect(fetch=lambda _:xml,now=NOW)
            self.assertTrue(result['diagnostics']['all_failed'])

    def test_old_and_future(self):
        self.assertEqual(parse_rss(feed('ゲーム新作発売',days=3),GAME,NOW),[])
        self.assertEqual(parse_rss(feed('DLsite 同人ゲーム規約変更',days=15),ADULT,NOW),[])
        self.assertEqual(parse_rss(feed('ゲーム新作発売',days=-1),GAME,NOW),[])

    def test_important_adult_retention_preserves_dates(self):
        old=article(ADULT,'DLsite 同人ゲーム規約変更',days=20)
        previous={'articles':[old]}
        result=collect(fetch=lambda _:feed(),now=NOW,previous=previous)
        self.assertEqual(result['articles'][0]['published'],old['published'])
        self.assertEqual(result['articles'][0]['first_seen_at'],old['published'])
        self.assertTrue(result['articles'][0]['retained'])
        self.assertEqual(result['diagnostics']['categories'][ADULT]['accepted'],0)
        self.assertEqual(result['diagnostics']['categories'][ADULT]['retained'],1)
        self.assertEqual(collect(fetch=lambda _:feed(),now=NOW+dt.timedelta(days=11),previous=previous)['articles'],[])

    def test_rerun_does_not_refresh_first_seen(self):
        old=article(ADULT,'DLsite 同人ゲーム規約変更')
        old['first_seen_at']=(NOW-dt.timedelta(days=1)).isoformat()
        result=collect(fetch=lambda _:feed(old['title']),now=NOW,previous={'articles':[old]})
        self.assertEqual(result['articles'][0]['first_seen_at'],old['first_seen_at'])

    def test_partial_failure_retains_and_reports(self):
        old=article(BALL,'DeNA 来季の補強発表',days=1)
        def fetch(url):
            from urllib.parse import parse_qs,urlsplit
            query=parse_qs(urlsplit(url).query)['q'][0]
            return feed() if 'MLB' in query else fail(url)
        result=collect(fetch=fetch,now=NOW,previous={'articles':[old]})
        self.assertEqual(len(result['articles']),1)
        diag=result['diagnostics']['categories'][BALL]
        self.assertEqual(diag['status'],'partial')
        self.assertEqual(diag['empty_reason'],'partial_fetch_failure')
        self.assertEqual(diag['last_success_at'],NOW.isoformat())
        self.assertIsNone(diag['last_complete_success_at'])

    def test_all_failure_preserves_exact_news_file_and_logs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder); raw=json.dumps({'articles':[article(BALL,'DeNA 補強発表',days=10)]}).encode()
            (root/'news.json').write_bytes(raw)
            self.assertEqual(run(root,fail,NOW),1)
            self.assertEqual((root/'news.json').read_bytes(),raw)
            self.assertTrue(json.loads((root/'diagnostics.json').read_text(encoding='utf-8'))['all_failed'])

    def test_fresh_install_empty_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder)
            self.assertEqual(run(root,fail,NOW),1)
            self.assertFalse((root/'news.json').exists())
            self.assertTrue((root/'diagnostics.json').exists())

    def test_normal_run_writes_compatible_news(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder)
            self.assertEqual(run(root,lambda _:feed('ゲーム新作発売'),NOW),0)
            result=json.loads((root/'news.json').read_text(encoding='utf-8'))
            self.assertTrue({'updated_at','articles','errors'}.issubset(result))
            self.assertTrue({'category','title','url','source','published','priority'}.issubset(result['articles'][0]))

    def test_last_success_kept_on_failure(self):
        result=collect(fetch=lambda _:feed(),now=NOW)
        later=collect(fetch=fail,now=NOW+dt.timedelta(hours=6),previous=result)
        self.assertEqual(later['diagnostics']['categories'][ADULT]['last_success_at'],NOW.isoformat())

    def test_official_publisher_not_claimed_as_confirmed(self):
        self.assertTrue(official_publisher('https://support.dlsite.com/hc/ja'))
        self.assertFalse(official_publisher('https://dlsite.com.evil.example'))
        a=parse_rss(feed('DLsite 同人ゲーム規約変更',source_url='https://support.dlsite.com'),ADULT,NOW)[0]
        self.assertEqual(a['official_confirmation'],'official_publisher_unverified')
        a=parse_rss(feed('DLsite 同人ゲーム規約変更'),ADULT,NOW)[0]
        self.assertEqual(a['official_confirmation'],'needs_official_review')

    def test_ascii_word_boundary(self):
        score,_,reason=score_article(article(BALL,'プロ野球選手のfan交流'),BALL)
        self.assertEqual(score,0)
        self.assertEqual(reason,'low_score')

class RegressionCases(unittest.TestCase):
    def test_scoring_reasons_add_up_and_policy_is_important(self):
        score,reasons,rejected=score_article(article(ADULT,'DLsite 決済規約変更、セールも対象'),ADULT)
        self.assertIsNone(rejected)
        self.assertGreaterEqual(score,RULES[ADULT]['important'])
        self.assertEqual(score,sum(r['points'] for r in reasons))

    def test_malformed_item_url_does_not_break_other_items(self):
        xml=feed('ゲーム新作発売').replace(b'https://example.org/0',b'https://[broken')
        result=collect(fetch=lambda _:xml,now=NOW)
        self.assertFalse(result['diagnostics']['all_failed'])
        self.assertEqual(result['diagnostics']['categories'][GAME]['exclusion_reasons']['invalid'],len(TOPICS[GAME]))

    def test_official_generic_policy_title(self):
        a=parse_rss(feed('販売規約と審査基準の変更',source_url='https://support.dlsite.com'),ADULT,NOW)
        self.assertEqual(len(a),1)
        self.assertEqual(a[0]['official_confirmation'],'official_publisher_unverified')

    def test_legacy_suffix_dedup(self):
        a=article(GAME,'ゲーム新作発売 - Test')
        b=dict(a,title='ゲーム新作発売',url='https://example.org/another')
        self.assertTrue(duplicate(b,[a]))

    def test_labelled_cases(self):
        from validate_quality import compare
        samples=json.loads((Path(__file__).parent/'quality_samples.json').read_text(encoding='utf-8-sig'))
        for topic,result in compare(samples,NOW,True).items():
            with self.subTest(topic=topic):
                self.assertEqual(result['v03_noise'],0)
                self.assertEqual(result['v03_wanted'],result['wanted'])

    def test_reissued_article_is_not_new(self):
        old=article(ADULT,'DLsite 同人ゲーム規約変更',days=20)
        result=collect(fetch=lambda _:feed(old['title']),now=NOW,previous={'articles':[old]})
        self.assertEqual(len(result['articles']),1)
        self.assertEqual(result['articles'][0]['published'],old['published'])
        self.assertTrue(result['articles'][0]['retained'])
        self.assertEqual(result['diagnostics']['categories'][ADULT]['accepted'],0)

    def test_old_regular_article_does_not_resurface(self):
        old=article(GAME,'ゲーム新作発売',days=10)
        result=collect(fetch=lambda _:feed(old['title']),now=NOW,previous={'articles':[old]})
        self.assertEqual(result['articles'],[])

if __name__=='__main__': unittest.main()


