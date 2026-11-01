import unittest,datetime as dt
from collect import collect,parse_rss,RULES
from ranking import assess,rank_articles,same_story
from quality import adult_scope,baseball_context,conference_key
from test_quality import feed,NOW,GAME,ADULT,BALL
from test_ranking import a

class ScopeTests(unittest.TestCase):
    def test_single_work_not_policy(self):
        for title in ['DLsite『作品A』の販売停止を告知','FANZA 個別作品1作品の販売停止、完全版を販売','DLsite 個別サークルの販売ページ更新']:
            with self.subTest(title=title):
                item=a(ADULT,title)
                self.assertFalse(adult_scope(item,RULES[ADULT])['policy'])
                self.assertNotEqual(assess(item,RULES[ADULT])['priority'],'注目')
                self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])

    def test_scope_and_actor(self):
        for title in ['DLsite全体の販売停止・取扱方針変更','FANZAが全作品の審査基準を変更','クレジットカード決済会社による成人向けコンテンツ取扱変更','DLsite 複数作品・複数サークルの販売停止']:
            with self.subTest(title=title):
                item=a(ADULT,title)
                self.assertTrue(adult_scope(item,RULES[ADULT])['policy'])
                self.assertEqual(assess(item,RULES[ADULT])['priority'],'注目')
                self.assertTrue(parse_rss(feed(title),ADULT,NOW))

    def test_work_precedent_and_violation_different(self):
        precedent=a(ADULT,'DLsiteの規約改定により『作品A』販売停止、審査方針変更の先行事例')
        violation=a(ADULT,'DLsite『作品A』規約違反で販売停止')
        self.assertTrue(adult_scope(precedent,RULES[ADULT])['policy'])
        self.assertFalse(adult_scope(violation,RULES[ADULT])['policy'])
        self.assertTrue(parse_rss(feed(precedent['title']),ADULT,NOW))
        self.assertEqual(parse_rss(feed(violation['title']),ADULT,NOW),[])

    def test_market_sales_and_production_ai(self):
        for title in ['成人向け同人ゲームの育成・生活SLG 売れ筋ジャンルとタグの変化','DLsite 同人ゲームの価格帯と販売施策の傾向分析','FANZA同人ゲーム10万本ヒット、販売戦略と成功要因','成人向け同人ゲーム制作で活用する生成AIワークフローと商用利用']:
            with self.subTest(title=title):self.assertTrue(parse_rss(feed(title),ADULT,NOW))

    def test_recommendation_is_not_analysis(self):
        for title in ['DLsite おすすめAI作品ランキング','FANZA AI生成作品紹介','DLsite『作品B』個別作品の発売告知','DLsite おすすめ同人ゲームランキング']:
            with self.subTest(title=title):self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])
        title='DLsite おすすめ作品ランキングを分析、育成ジャンルの売上推移と価格帯の変化'
        self.assertTrue(parse_rss(feed(title),ADULT,NOW))

    def test_price_and_circle_actor_not_systemic(self):
        for title in ['DLsite『作品A』作品紹介、価格1980円','DLsiteでサークル「A」が独自の規約改定、作品販売停止']:
            item=a(ADULT,title)
            self.assertFalse(adult_scope(item,RULES[ADULT])['policy'])
            self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])

    def test_sales_case_not_aggregate_market(self):
        item=a(ADULT,'DLsite同人ゲーム10万本ヒット、販売戦略と成功要因')
        self.assertEqual(adult_scope(item,RULES[ADULT])['classification'],'sales')

    def test_wide_recommendation_not_policy(self):
        title='DLsite全作品のおすすめAI作品ランキング'
        self.assertFalse(adult_scope(a(ADULT,title),RULES[ADULT])['policy'])
        self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])
        title='DLsiteでサークル「A」が独自の規約変更、全作品販売停止'
        self.assertFalse(adult_scope(a(ADULT,title),RULES[ADULT])['policy'])

    def test_useful_recommended_tools_and_real_counts(self):
        for title in ['成人向け同人ゲーム制作におすすめの生成AI制作ツール、技術解説','DLsite同人ゲーム10000本突破、ヒットの背景']:
            with self.subTest(title=title):self.assertTrue(parse_rss(feed(title),ADULT,NOW))

    def test_generic_official_notice_has_operator_context(self):
        item=a(ADULT,'販売規約と審査基準の変更')
        item['source_url']='https://support.dlsite.com/'
        self.assertEqual(adult_scope(item,RULES[ADULT])['scope'],'platform')
        self.assertEqual(assess(item,RULES[ADULT])['priority'],'注目')

    def test_snippet_evidence(self):
        item=a(ADULT,'DLsite『作品A』販売停止')
        item['summary']='プラットフォーム全体の規約改定に伴い、複数作品に適用する新基準。'
        self.assertTrue(adult_scope(item,RULES[ADULT])['policy'])

class ContextTests(unittest.TestCase):
    def test_past_draft_not_current(self):
        for title in ['元DeNA選手の1998年ドラフト秘話、野球人生を振り返る','DeNA監督が現役時代のドラフトを回顧','元DeNA選手の半生と人物紹介']:
            item=a(BALL,title)
            self.assertTrue(baseball_context(item,RULES[BALL])['retrospective'])
            self.assertLessEqual(assess(item,RULES[BALL])['importance'],2)
            self.assertEqual(assess(item,RULES[BALL])['priority'],'通常')

    def test_former_player_current_role_and_current_impact(self):
        for title in ['元DeNA選手が来季の新コーチ就任を発表','元DeNA選手が監督就任を発表','元DeNA関係者の新事実で現在の球界のドラフト制度変更へ']:
            item=a(BALL,title)
            self.assertFalse(baseball_context(item,RULES[BALL])['retrospective'])
            self.assertGreaterEqual(assess(item,RULES[BALL])['importance'],8)

    def test_conference_grouping(self):
        first=a(BALL,'DeNA・山田太郎が契約更改会見「来季も挑戦」',index=1)
        second=a(BALL,'DeNA 山田太郎「優勝を目指す」契約更新インタビュー',index=2)
        self.assertEqual(conference_key(first,RULES[BALL]),conference_key(second,RULES[BALL]))
        self.assertTrue(same_story(first,second,RULES[BALL]))
        for title in ['DeNA・山田太郎が追加発表、契約更改会見の新情報','DeNA・鈴木次郎が契約更改会見']:
            self.assertFalse(same_story(first,a(BALL,title),RULES[BALL]))

class DiversityTests(unittest.TestCase):
    def test_observed_comparison_top_five(self):
        import json
        from pathlib import Path
        from evaluate_quality import compare
        rows=json.loads((Path(__file__).parent/'quality_samples_v032.json').read_text(encoding='utf-8'))
        result,diag=compare(rows,NOW)
        self.assertEqual(diag['version'],'0.3.2')
        adult=result[ADULT]['v032']['top5']
        self.assertTrue(all(row['scope']!='individual' for row in adult))
        self.assertFalse(any('おすすめ' in row['title'] for row in adult))
        self.assertTrue(any(row['info_type']=='market' for row in adult))
        self.assertGreater(len({row['info_type'] for row in result[GAME]['v032']['top5']}),1)
        self.assertFalse(any('回顧' in row['title'] or '現役時代' in row['title'] for row in result[BALL]['v032']['top5']))
        for cat,versions in result.items():
            for counts in versions.values():self.assertEqual(counts['fetched'],counts['accepted']+counts['excluded'])


    def test_game_mix_without_fixed_slots(self):
        items=[a(GAME,f'新作ゲーム『作品{i}』を発表',index=i) for i in range(6)]
        items += [a(GAME,'ゲーム企業が大規模な買収を発表',hours=24,index=20),a(GAME,'人気ゲームの大型アップデート',hours=12,index=21),a(GAME,'注目インディーゲーム発売開始',hours=6,index=22)]
        top=rank_articles(items,RULES,NOW)[:5]
        self.assertGreater(len({x['info_type'] for x in top}),1)
        self.assertTrue(any(x['info_type']=='release' for x in top))
        self.assertTrue(any(x['info_type'] in ('business','update') for x in top))
        only=rank_articles(items[:6],RULES,NOW)
        self.assertEqual(len(only),6)
        self.assertTrue(all(x['info_type']=='release' for x in only))

    def test_major_release_not_unfairly_downranked(self):
        items=[a(GAME,'大型新作ゲーム、シリーズ最新作『星の旅』を発表',index=1),a(GAME,'ゲーム企業の開発体制を紹介',index=2)]
        top=rank_articles(items,RULES,NOW)
        self.assertEqual(top[0]['url'],items[0]['url'])
        self.assertLess(assess(items[1],RULES[GAME])['importance'],7)

if __name__=='__main__':unittest.main()
