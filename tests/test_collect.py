import datetime as dt
import unittest
from collect import parse_rss, collect, TOPICS
NOW = dt.datetime(2026,10,29,5,0,tzinfo=dt.timezone.utc)
def feed(title, pub='Thu, 29 Oct 2026 02:00:00 GMT'):
    return f'<rss><channel><item><title>{title}</title><link>https://example.org/story</link><pubDate>{pub}</pubDate><source>Test</source></item></channel></rss>'.encode()
class Tests(unittest.TestCase):
    def test_recent(self):
        self.assertEqual(len(parse_rss(feed('ゲーム新作発表'), 'ゲーム業界', NOW)),1)
    def test_old(self):
        self.assertEqual(len(parse_rss(feed('ゲーム新作発表','Mon, 01 Jun 2026 02:00:00 GMT'), 'ゲーム業界', NOW)),0)
    def test_adult_filter(self):
        self.assertEqual(len(parse_rss(feed('一般的なインディーゲーム発表'), '成人向け同人ゲーム', NOW)),0)
        self.assertEqual(len(parse_rss(feed('DLsite 同人ゲーム規約変更'), '成人向け同人ゲーム', NOW)),1)
    def test_dedup(self):
        result=collect(fetch=lambda _:feed('ゲーム新作発表'),now=NOW)
        self.assertEqual(len([a for a in result['articles'] if a['category']=='ゲーム業界']),1)
if __name__=='__main__':unittest.main()
