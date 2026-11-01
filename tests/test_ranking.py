import datetime as dt
import unittest
from collect import collect,parse_rss,RULES,TOPICS,score_article
from ranking import rank_articles,assess,same_story,story_signature,rank_value
from test_quality import feed,NOW,GAME,ADULT,BALL


def a(category,title,hours=0,index=0):
    return {'category':category,'title':title,'published':(NOW-dt.timedelta(hours=hours)).isoformat(),
            'url':f'https://example.org/{index}','source':'Test','score':8}

class RankingTests(unittest.TestCase):
    def test_goods_and_anniversary(self):
        news=a(GAME,'ゲーム新作『星の旅』を発表',hours=3)
        for title in ['ゲーム新作フィギュア発売','ゲーム機の発売記念日、30周年を振り返る','人気ゲームの抽選キャンペーン']:
            with self.subTest(title=title):
                low=a(GAME,title)
                self.assertLess(rank_value(low,RULES[GAME],NOW)[0],rank_value(news,RULES[GAME],NOW)[0])
                self.assertEqual(assess(low,RULES[GAME])['priority'],'通常')

    def test_anniversary_announcement_survives(self):
        title='ゲーム30周年記念、新作ゲーム『星の旅』を発表、グッズも発売'
        self.assertEqual(len(parse_rss(feed(title),GAME,NOW)),1)
        self.assertEqual(assess(a(GAME,title),RULES[GAME])['priority'],'注目')

    def test_negated_announcement_not_notable(self):
        item=a(GAME,'ピクミン5などの新作発表はなし、シリーズ情報を配信')
        self.assertEqual(assess(item,RULES[GAME])['priority'],'通常')
        self.assertLess(assess(item,RULES[GAME])['importance'],6)

    def test_former_player_other_career_and_roundup(self):
        news=a(BALL,'DeNA 来季の補強を発表',hours=6,index=1)
        for title in ['元DeNA投手がゴルファーへ転身、コーチ退任','プロ野球 FA移籍の注目選手一覧']:
            low=a(BALL,title,index=2)
            self.assertLess(rank_value(low,RULES[BALL],NOW)[0],rank_value(news,RULES[BALL],NOW)[0])
            self.assertEqual(assess(low,RULES[BALL])['priority'],'通常')

    def test_figure_announcement_is_not_a_game(self):
        title='ゲーム『星の旅』のフィギュア新作発表、発売決定'
        self.assertEqual(assess(a(GAME,title),RULES[GAME])['importance'],0)

    def test_adult_promotion_and_policy(self):
        promo=a(ADULT,'DLsite AI生成同人ゲーム新作発売、売上ランキング記念キャンペーン')
        policy=a(ADULT,'DLsite クレカ決済停止と規約変更',hours=24)
        self.assertLess(rank_value(promo,RULES[ADULT],NOW)[0],rank_value(policy,RULES[ADULT],NOW)[0])
        self.assertEqual(assess(promo,RULES[ADULT])['priority'],'通常')
        self.assertEqual(assess(policy,RULES[ADULT])['priority'],'注目')
        self.assertEqual(len(parse_rss(feed(policy['title']),ADULT,NOW)),1)

    def test_payment_campaign_is_not_policy_news(self):
        title='DLsite 決済キャンペーン、プレゼント開催'
        self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])
        self.assertEqual(assess(a(ADULT,title),RULES[ADULT])['priority'],'通常')

    def test_credit_card_promo_not_important_policy(self):
        title='FANZA クレジットカード決済でプレゼントキャンペーン'
        self.assertEqual(assess(a(ADULT,title),RULES[ADULT])['priority'],'通常')
        self.assertEqual(parse_rss(feed(title),ADULT,NOW),[])
        title='DLsite クレジットカード決済障害、キャンペーンにも影響'
        self.assertEqual(assess(a(ADULT,title),RULES[ADULT])['priority'],'注目')
        self.assertEqual(len(parse_rss(feed(title),ADULT,NOW)),1)

    def test_sales_milestone_campaign_not_hit_analysis(self):
        title='DLsite AI生成同人ゲーム10万本記念プレゼントキャンペーン'
        self.assertEqual(assess(a(ADULT,title),RULES[ADULT])['priority'],'通常')

    def test_roster_and_professional_priorities(self):
        items=[a(BALL,'高校野球 秋季近畿大会 大阪桐蔭対智弁和歌山 決勝結果',index=1),
               a(BALL,'DeNA 来季の補強とコーチ人事',hours=6,index=2),
               a(BALL,'NPB ドラフトと大型移籍',hours=3,index=3)]
        ordered=rank_articles(items,RULES,NOW)
        self.assertNotEqual(ordered[0]['coverage_group'],'high_school')
        self.assertEqual(ordered[-1]['coverage_group'],'high_school')

    def test_dena_not_fixed_first(self):
        items=[a(BALL,'DeNA 試合に勝利',index=1),a(BALL,'MLB 世界記録を更新、史上初の快挙',index=2)]
        self.assertEqual(rank_articles(items,RULES,NOW)[0]['url'],items[1]['url'])

    def test_national_high_school_major_kept(self):
        major=a(BALL,'高校野球 全国大会が中止、全試合中止を発表',index=1)
        routine=a(BALL,'DeNA 試合に勝利',index=2)
        self.assertEqual(assess(major,RULES[BALL])['priority'],'注目')
        self.assertEqual(rank_articles([major,routine],RULES,NOW)[0]['url'],major['url'])
        self.assertEqual(len(parse_rss(feed(major['title']),BALL,NOW)),1)

    def test_regional_results_not_notable(self):
        for title in ['高校野球 秋季近畿大会 決勝結果','高校野球 秋季関東大会 組み合わせ決定','DeNA 試合に勝利']:
            with self.subTest(title=title):self.assertEqual(assess(a(BALL,title),RULES[BALL])['priority'],'通常')

    def test_no_regional_monopoly_when_alternatives_exist(self):
        items=[a(BALL,f'高校野球 秋季近畿大会 第{i}試合の決勝結果',index=i) for i in range(6)]
        items += [a(BALL,'DeNA 補強発表',hours=12,index=20),a(BALL,'NPB 契約と移籍',hours=12,index=21),
                  a(BALL,'MLB ワールドシリーズ決勝',hours=12,index=22),a(BALL,'プロ野球ルール変更',hours=12,index=23)]
        top=rank_articles(items,RULES,NOW)[:5]
        self.assertLessEqual(sum(x['regional_high_school'] for x in top),1)
        self.assertEqual(len(rank_articles(items,RULES,NOW)),len(items))

    def test_no_fabricated_diversity(self):
        items=[a(BALL,f'高校野球 秋季近畿大会 第{i}試合の結果',index=i) for i in range(6)]
        self.assertEqual(len(rank_articles(items,RULES,NOW)),6)

    def test_age_decay_and_original_dates(self):
        old=a(ADULT,'DLsite 規約変更',hours=24*20,index=1)
        new=a(ADULT,'成人向け同人ゲーム市場の売上動向',index=2)
        ordered=rank_articles([old,new],RULES,NOW)
        self.assertEqual(ordered[0]['url'],new['url'])
        self.assertEqual(ordered[1]['published'],old['published'])

    def test_rank_order_is_contiguous_per_category(self):
        items=[a(BALL,'DeNA 補強',index=1),a(GAME,'ゲーム新作発表',index=2),a(BALL,'NPB 移籍',index=3)]
        ranked=rank_articles(items,RULES,NOW)
        self.assertEqual([x['display_order'] for x in ranked if x['category']==BALL],[0,1])

class StoryTests(unittest.TestCase):
    def test_replay_top_five(self):
        import json
        from pathlib import Path
        from compare_ranking import compare
        samples=json.loads((Path(__file__).parent/'ranking_samples.json').read_text(encoding='utf-8-sig'))
        results=compare(samples,NOW)
        before=results[BALL]['v03']['top5'];after=results[BALL]['v031']['top5']
        self.assertEqual(sum('秋季' in x['title'] for x in before),5)
        self.assertLessEqual(sum('秋季' in x['title'] for x in after),1)
        self.assertTrue(any('DeNA' in x['title'] for x in after))
        self.assertTrue(any('NPB' in x['title'] for x in after))
        self.assertTrue(any('全国大会' in x['title'] for x in after))
        self.assertFalse(any('フィギュア' in x['title'] or '発売記念日' in x['title'] for x in results[GAME]['v031']['top5']))
        self.assertFalse(any('キャンペーン' in x['title'] for x in results[ADULT]['v031']['top5']))


    def test_same_match_different_headlines(self):
        first=a(BALL,'高校野球 秋季近畿大会 大阪桐蔭対智弁和歌山 決勝速報',index=1)
        second=a(BALL,'秋季近畿大会決勝 大阪桐蔭が智弁和歌山に勝利 試合結果',index=2)
        self.assertTrue(same_story(first,second,RULES[BALL]),(story_signature(first,RULES[BALL]),story_signature(second,RULES[BALL])))

    def test_different_matches_and_days(self):
        first=a(BALL,'高校野球 秋季近畿大会 大阪桐蔭対智弁和歌山 決勝速報')
        for second in [a(BALL,'高校野球 秋季近畿大会 履正社対報徳学園 決勝速報'),
                       a(BALL,first['title'],hours=24)]:
            self.assertFalse(same_story(first,second,RULES[BALL]))

    def test_same_game_announcement(self):
        first=a(GAME,'新作ゲーム『星の旅』発表、Steamに登場',index=1)
        second=a(GAME,'『星の旅』新作発表！ゲームの映像を公開',index=2)
        self.assertTrue(same_story(first,second,RULES[GAME]))
        self.assertFalse(same_story(first,a(GAME,'新作ゲーム『海の旅』発表、Steamに登場'),RULES[GAME]))

    def test_same_policy_different_headlines(self):
        first=a(ADULT,'DLsite クレジットカード決済停止を発表',index=1)
        second=a(ADULT,'DLsite クレカ決済が利用不能に、販売者へ告知',index=2)
        self.assertTrue(same_story(first,second,RULES[ADULT]))

    def test_material_platform_difference_not_grouped(self):
        first=a(GAME,'新作ゲーム『星の旅』発表、PS5に登場')
        second=a(GAME,'新作ゲーム『星の旅』発表、Switch 2に登場')
        self.assertFalse(same_story(first,second,RULES[GAME]))

    def test_interviews_followups_and_action_changes_survive(self):
        first=a(ADULT,'DLsite クレジットカード決済停止を発表')
        for title in ['DLsite クレカ決済停止、独自取材で影響を確認','DLsite クレカ決済再開を発表','DLsite クレカ決済停止、補償の詳細判明']:
            self.assertFalse(same_story(first,a(ADULT,title),RULES[ADULT]))
        first=a(GAME,'新作ゲーム『星の旅』発表')
        self.assertFalse(same_story(first,a(GAME,'新作ゲーム『星の旅』開発者インタビュー'),RULES[GAME]))

    def test_grouping_preserves_related_links_and_diagnostics(self):
        titles=['高校野球 秋季近畿大会 大阪桐蔭対智弁和歌山 決勝速報',
                '秋季近畿大会決勝 大阪桐蔭が智弁和歌山に勝利 試合結果',
                'DeNA 補強とドラフト発表']
        result=collect(fetch=lambda _:feed(*titles),now=NOW)
        baseball=[x for x in result['articles'] if x['category']==BALL]
        self.assertEqual(len(baseball),2)
        self.assertTrue(any(x.get('related_articles') for x in baseball))
        diag=result['diagnostics']['categories'][BALL]
        self.assertGreater(diag['exclusion_reasons'].get('same_story',0),0)
        self.assertEqual(diag['fetched'],diag['accepted']+diag['excluded'])

if __name__=='__main__':unittest.main()
