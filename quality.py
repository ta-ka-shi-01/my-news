"""Scope and temporal context from RSS headlines/snippets; no body-fetch or AI API."""
import re
import unicodedata
import datetime as dt
import urllib.parse


def text_of(article):
    return unicodedata.normalize('NFKC', article['title']+' '+article.get('summary',''))


def any_word(text, words):
    return any(word.casefold() in text.casefold() for word in words)


def adult_scope(article,config):
    text=text_of(article); q=config['quality']
    quoted=re.findall(r'[『「]([^』」]+)[』」]',article['title'])
    work_quotes=[v for v in quoted if not any_word(v,q['non_work_quotes'])]
    individual=bool(work_quotes) or any_word(text,q['individual'])
    systemic_change=bool(re.search(r'規約.{0,5}(?:変更|改定|改訂)|審査(?:方針|基準).{0,5}(?:変更|改定|改訂)|取扱方針.{0,5}(?:変更|改定)',text))
    widespread=any_word(text,q['widespread'])
    circle_actor=bool(re.search(r'(?:サークル|作者|制作元).{0,12}(?:が|の|独自).{0,16}(?:規約|取扱方針)',text))
    if circle_actor and not any_word(text,('プラットフォームの規約','DLsiteの規約','FANZAの規約')):systemic_change=False
    platform=any_word(text,('DLsite','FANZA','プラットフォーム','運営','決済会社','Visa','Mastercard','クレジットカード','クレカ'))
    try:
        host=urllib.parse.urlsplit(article.get('source_url','')).hostname or ''
        platform |= any(host==domain or host.endswith('.'+domain) for domain in ('dlsite.com','dmm.co.jp'))
    except ValueError:pass
    payment=any_word(text,q['payment']) and any_word(text,q['change'])
    regulation=any_word(text,('表現規制','新基準','審査基準','規制方針'))
    # A single work's suspension is not evidence of a platform-wide policy.
    measure=any_word(text,('販売停止','取扱停止','取扱変更','取り扱い変更','表現規制','規制措置','審査基準','規約変更','規約改定','停止措置','決済','審査方針'))
    policy=(systemic_change and platform) or (widespread and platform and measure) or (not individual and platform and (payment or regulation))
    if circle_actor and not any_word(text,('プラットフォームの規約','DLsiteの規約','FANZAの規約','運営の方針')):policy=False
    if individual and policy:scope='platform' if widespread else 'precedent' if systemic_change else 'individual'
    elif policy:scope='platform'
    elif individual:scope='individual'
    else:scope='uncertain'
    policy=policy and scope in ('platform','precedent')
    sales=bool(re.search(r'\d[\d,.]*\s*(?:万|億)\s*(?:本|部|DL|ダウンロード)|\d[\d,.]*\s*(?:本|DL|ダウンロード)(?:突破|達成|販売)|(?:販売本数|販売数|売上|累計).{0,12}(?:\d[\d,.]*\s*(?:万|億)?\s*(?:本|円|DL)|公開|分析|推移)',text,re.I))
    market=any_word(text,q['market_subject']) and any_word(text,q['analysis'])
    success=any_word(text,('販売戦略','成功要因','ヒット事例','ヒットの背景')) and (sales or market or any_word(text,('ヒット','成功','売上')))
    ai=any_word(text,q['ai']) and any_word(text,q['production'])
    recommendation=any_word(text,q['recommendation'])
    if any_word(text,('制作ツール','技術解説','ワークフロー','制作手法')) and not any_word(text,('作品ランキング','AI作品紹介','AI作品を紹介')):recommendation=False
    promotion=any_word(text,q['promotion'])
    # AI products/recommendations are not production technology coverage.
    if recommendation or (promotion and not any_word(text,('技術解説','制作手法','ワークフロー','商用利用','導入事例'))):ai=False
    if policy:kind='policy';useful=True
    elif (sales or success) and not any_word(text,('市場','ジャンル','タグ','価格帯','販売施策','全体','複数作品')):kind='sales';useful=True
    elif market:kind='market';useful=True
    elif sales or success:kind='sales';useful=True
    elif ai:kind='production_ai';useful=True
    elif individual and any_word(text,('販売停止','完全版','販売ページ','販売告知','発売','販売開始')):kind='individual_update';useful=False
    elif recommendation or promotion or any_word(text,('作品紹介','作品を紹介','ゲーム紹介','AI作品紹介')):kind='work_promotion';useful=False
    else:kind='uncertain';useful=False
    if kind=='market':scope='market'
    elif kind=='sales':scope='work_case'
    elif kind=='production_ai':scope='production'
    return {'scope':scope,'classification':kind,'policy':policy,'market':kind=='market',
            'sales':kind=='sales','production_ai':kind=='production_ai','useful':useful,'sales_announcement':promotion and sales and not (market or success),
            'evidence':{'individual_work':individual,'systemic_change':systemic_change,
                        'widespread':widespread,'payment_change':payment,'numeric_sales':sales}}


def baseball_context(article,config):
    text=text_of(article);q=config['quality']
    historical=any_word(text,q['historical'])
    year=dt.datetime.fromisoformat(article.get('published','2026-01-01T00:00:00+00:00')).year
    historical |= any(int(v)<year for v in re.findall(r'((?:19|20)\d{2})年(?:の)?(?:ドラフト|現役|入団)',text))
    retrospective_event=any_word(text,('現役時代','当時','回顧','振り返','思い出','かつて','過去の','秘話')) or any(int(v)<year for v in re.findall(r'((?:19|20)\d{2})年(?:の)?(?:ドラフト|現役|入団)',text))
    current=any_word(text,q['current_action']) and (not retrospective_event or any_word(text,q['current_time']))
    impact=any_word(text,q['new_fact']) and any_word(text,q['current_impact']) and any_word(text,q['current_time'])
    retrospective=historical and not current and not impact
    return {'historical':historical,'current_action':current,'current_impact':impact,'retrospective':retrospective}


def conference_key(article,config):
    text=unicodedata.normalize('NFKC',article['title'])
    if baseball_context(article,config)['retrospective']:return None
    actions=[('contract',('契約更改','更改会見','契約更新')),('appointment',('就任会見','就任発表','新コーチ','新監督')),('joining',('入団会見','入団発表')),('retirement',('引退会見','引退発表'))]
    action=next((key for key,words in actions if any_word(text,words)),None)
    if not action:return None
    team=next((name for name,aliases in config['ranking']['team_aliases'].items() if any_word(text,aliases)),None)
    if not team:return None
    aliases=config['ranking']['team_aliases'][team]
    prefix='(?:'+'|'.join(re.escape(x) for x in aliases)+')'
    name=r'[一-龥ぁ-んァ-ヶ]{2,10}'
    match=re.search(prefix+r'[・\s]*('+name+r')(?=[「『、\s]|が|は|の)',text)
    if not match:match=re.search(r'^('+name+r'?)(?:が|は|、|「)',text)
    if not match:return None
    person=re.sub(r'(?:選手|投手|監督|コーチ|氏)$','',match[1])
    if len(person)<2:return None
    day=dt.datetime.fromisoformat(article['published']).astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    return ('conference',team,person,action,day)
