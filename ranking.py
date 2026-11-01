"""Explainable, free ranking and conservative event grouping (standard library only)."""
import datetime as dt
import math
import re
import unicodedata
from quality import adult_scope, baseball_context, conference_key, any_word

GAME, ADULT, BALL = 'ゲーム業界', '成人向け同人ゲーム', '野球'
UTC = dt.timezone.utc
JST = dt.timezone(dt.timedelta(hours=9))


def fold(text):
    return unicodedata.normalize('NFKC', text).casefold().replace('智辯','智弁').replace('智辨','智弁')


def has(text, words):
    text = fold(text)
    return any((bool(re.search(r'(?<![a-z0-9])'+re.escape(fold(w))+r'(?![a-z0-9])',text))
                if re.fullmatch(r'[a-z0-9 -]+',fold(w)) else fold(w) in text) for w in words)


def date(value):
    return dt.datetime.fromisoformat(value).astimezone(UTC)


def features(article, config):
    title = article['title']
    settings = config['ranking']
    flags = {name: has(title, words) for name,words in settings['signals'].items()}
    if article['category'] == GAME:
        quality=config['quality']
        flags['business'] = any_word(article['title'],quality['business_actions']) or (any_word(article['title'],quality['business_subject']) and any_word(article['title'],quality['business_change']))
        # A figure's "new release" is not a new video game announcement.
        flags['announcement']=bool(re.search(r'(?:新作|続編|リメイク|新タイトル).{0,35}(?:発表|公開|発売日.{0,6}決定)',title)) or has(title,('新作発表','発売日決定'))
        negated_release=bool(re.search(r'新作(?:発表)?(?:は|の予定は)?(?:なし|無し|ない|見送り)',title))
        if negated_release:flags['announcement']=False
        release_news=(not negated_release and flags['release'] and (not flags['merchandise'] or flags['explicit_game'])
                      and (not (flags['anniversary'] or flags['promotion']) or flags['announcement']))
        flags['substantive'] = flags['business'] or flags['update'] or release_news
    elif article['category'] == ADULT:
        scope=adult_scope(article,config)
        flags.update(policy=scope['policy'],market_change=scope['market'],sales_case=scope['sales'],ai_production=scope['production_ai'],substantive=scope['useful'])
    else:
        if flags['dena'] or (flags['roster'] and has(title,('NPB','プロ野球','ドラフト'))):
            flags['high_school']=False
        flags['retrospective']=baseball_context(article,config)['retrospective']
        if flags['retrospective']:
            flags['roster']=False;flags['major']=False;flags['international_major']=False
        flags['regional'] = flags['high_school'] and flags['regional_event']
        flags['national_major'] = flags['high_school'] and (bool(re.search(r'(?:全国|甲子園).{0,16}(?:大会.{0,3})?(?:中止|開催断念)',title)) or flags['major'] or (flags['national_event'] and not flags['regional'] and ('決勝' in title.replace('準々決勝','').replace('準決勝','') or has(title,('全国制覇','大会中止','全試合中止')))))
    return flags


def assess(article, config):
    """Importance is independent of relation-to-category and DeNA affinity."""
    f=features(article,config)
    settings=config['ranking']
    points=settings['importance']
    reasons=[]
    if article['category']==GAME:
        if f['business']: importance=points['business']; reasons.append('企業・事業の重要動向')
        elif f['update']: importance=points['update']; reasons.append('重要アップデート')
        elif f['substantive']: importance=points['announcement'] if f['announcement'] else points['release']; reasons.append('ゲームの新作・発売')
        elif f['indie']: importance=points['indie']; reasons.append('注目インディー')
        else: importance=points['general']; reasons.append('一般情報')
        if (f['merchandise'] or f['anniversary'] or f['promotion']) and not f['substantive']:
            importance=points['promotion']; reasons.append('商品・記念日・販促を減点')
        interest=0; tier='games'
    elif article['category']==ADULT:
        if f['policy']: importance=points['policy']; reasons.append('規約・審査・決済の重要情報')
        elif f['market_change']: importance=points['market']; reasons.append('市場・販売環境の変化')
        elif f['sales_case']: importance=points['sales']; reasons.append('売上・ヒット事例')
        elif f['ai_production']: importance=points['ai']; reasons.append('制作・販売に役立つAI情報')
        else: importance=points['general']; reasons.append('一般的な作品情報')
        if adult_scope(article,config)['scope']=='precedent':
            importance=min(importance,config['quality']['precedent_importance']);reasons.append('個別措置の先行事例として評価')
        if adult_scope(article,config)['sales_announcement']:
            importance=min(importance,config['quality']['sales_announcement_importance']);reasons.append('販売実績付き告知であり分析とは区別')
        if f['promotion'] and not f['substantive']:
            importance=points['promotion']; reasons.append('単発宣伝・キャンペーンを減点')
        interest=0; tier='adult'
    else:
        if f['major'] or f['national_major']: importance=points['major']; reasons.append('球界・全国の重大ニュース')
        elif f['roster']: importance=points['roster']; reasons.append('移籍・補強・来季編成')
        elif f['international_major']: importance=points['international']; reasons.append('国際大会・MLBの重要ニュース')
        else: importance=points['general']; reasons.append('通常の試合・選手情報')
        tier='high_school' if f['high_school'] else 'dena' if f['dena'] else 'mlb' if f['mlb'] else 'npb'
        interest=settings['interest'][tier]
        reasons.append('関心度:'+tier)
        if f['roundup'] and not f['confirmed_roster'] and not f['major']:
            importance=min(importance,points['roundup']);reasons.append('一覧・回顧情報を減点')
        if f['former_player'] and f['outside_baseball']:
            importance=points['outside'];interest=0;reasons.append('元選手の競技外の話題を減点')
    if article['category']==GAME and f['substantive'] and has(article['title'],config['quality']['major_release']):
        importance+=config['quality']['major_release_bonus'];reasons.append('主要な新作発表を評価')
    if article['category']==BALL and f['retrospective']:
        importance=min(importance,config['quality']['retrospective_importance']);interest=config['quality']['retrospective_interest'];reasons.append('現在の動きではない人物紹介・回顧')
    if article['category']==GAME:
        info_type='business' if f['business'] else 'update' if f['update'] else 'indie' if f['indie'] else 'release' if f['substantive'] else 'reference'
        details={'info_type':info_type}
    elif article['category']==ADULT:
        scope=adult_scope(article,config)
        details={'info_type':scope['classification'],'scope':scope['scope'],'classification_evidence':scope['evidence']}
    else:
        details={'info_type':'retrospective' if f['retrospective'] else 'current','temporal_context':baseball_context(article,config)}
    notable = importance >= settings['notable_min']
    return {**details,'importance':importance,'importance_reasons':reasons,'interest':interest,
            'coverage_group':tier,'regional_high_school':f.get('regional',False) and not f.get('national_major',False) and not f.get('major',False),
            'priority':'注目' if notable else '通常'}


def rank_value(article,config,now):
    info=assess(article,config)
    age=max(0,(now-date(article['published'])).total_seconds()/3600)
    r=config['ranking']
    freshness=r['freshness_max']*math.pow(2,-age/r['half_life_hours'])
    age_penalty=min(r['age_penalty_max'],age/r['age_penalty_hours'])
    value=info['importance']*r['importance_weight']+info['interest']+freshness-age_penalty
    return value,info,{'freshness':round(freshness,3),'age_penalty':round(age_penalty,3)}


def _kind(article,config):
    f=features(article,config);t=article['title']
    if article['category']==GAME:
        if not f['substantive']: return ''
        if has(t,('延期','中止','撤回')): return 'delay'
        if f['business']: return 'business'
        if f['update']: return 'update'
        if has(t,('発売日','発売決定','発売予定')): return 'release_date'
        if has(t,('発売開始','配信開始','リリース','早期アクセス')): return 'launch'
        return 'announcement'
    if article['category']==ADULT:
        if not f['policy']: return ''
        subject='payment' if has(t,('決済','クレジットカード','クレカ','カード決済')) else 'ai' if has(t,('AI作品','AI生成','生成AI')) else 'review' if has(t,('審査',)) else 'terms'
        action='resume' if has(t,('再開','撤回')) else 'stop' if has(t,('停止','終了','禁止','利用不能')) else 'change'
        return subject+':'+action
    if conference_key(article,config):return 'conference'
    return 'game' if not f['roster'] and not f['major'] else ''


def competition(title):
    match=re.search(r'(?:秋季|春季)?(?:近畿|関東|東海|九州|中国|四国|東北|北信越|北海道|東京)(?:地区)?大会',title)
    if match:return match.group()
    if has(title,('甲子園','センバツ','選抜')):return '甲子園・選抜'
    return ''


def teams(title,config):
    text=unicodedata.normalize('NFKC',title)
    found=[]
    for canonical,aliases in config['ranking'].get('team_aliases',{}).items():
        if has(text,aliases):found.append(canonical)
    if len(found)>=2:return tuple(sorted(set(found)))
    name=r'[一-龥ぁ-んァ-ヶA-Za-z0-9・]{2,14}'
    match=re.search('('+name+r')\s*(?:対|vs\.?|―|－|−|×|-)\s*('+name+')',text,re.I)
    if not match:
        match=re.search('('+name+r'?)(?:が|は)('+name+r'?)(?:に|を)(?:勝|破|敗|下|逆転)',text)
    if match:return tuple(sorted(fold(name) for name in match.groups()))
    return ()


def story_signature(article,config):
    kind=_kind(article,config)
    if not kind:return None
    title=article['title']
    if article['category']==GAME:
        entities=re.findall(r'[『「]([^』」]{2,50})[』」]',title)
        if not entities:return None
        # Financial articles need more specific identification than a company quote.
        if kind=='business':return None
        return (kind,fold(entities[0]))
    if article['category']==ADULT:
        brand='dlsite' if has(title,('DLsite',)) else 'fanza' if has(title,('FANZA',)) else ''
        if not brand:return None
        return (kind,brand)
    if kind=='conference':return conference_key(article,config)
    opponents=teams(title,config)
    if len(opponents)!=2:return None
    stage=next((s for s in ('準々決勝','準決勝','決勝','1回戦','2回戦','第1試合','第2試合') if s in title),'')
    explicit=re.search(r'(\d{1,2})月(\d{1,2})日',title)
    day=f'{date(article["published"]).year}-{int(explicit[1]):02}-{int(explicit[2]):02}' if explicit else date(article['published']).astimezone(JST).date().isoformat()
    return ('game',opponents,competition(title),stage,day)


def ngrams(title):
    text=re.sub(r'[^\w]','',fold(title))
    return {text[i:i+2] for i in range(len(text)-1)}


def same_story(a,b,config):
    if a['category']!=b['category']:return False
    # Independent reporting and material updates survive event-level grouping.
    followups=config['ranking']['keep_followups']
    if a['category']==BALL:
        followups=[word for word in followups if word!='インタビュー']+['追加発表','新たな契約','新たな移籍','重要な分析']
    if has(a['title'],followups) or has(b['title'],followups):return False
    for terms in config['ranking'].get('material_terms',[]):
        left_terms={word for word in terms if has(a['title'],[word])}
        right_terms={word for word in terms if has(b['title'],[word])}
        if left_terms and right_terms and left_terms!=right_terms:return False
    if abs((date(a['published'])-date(b['published'])).total_seconds())>config['ranking']['story_window_hours']*3600:return False
    left,right=story_signature(a,config),story_signature(b,config)
    if not left or left!=right:return False
    if a['category']==BALL:return True
    if a['category']==ADULT and left[0].startswith('terms'):
        if re.findall(r'\d+',a['title']) != re.findall(r'\d+',b['title']):return False
    aa,bb=ngrams(a['title']),ngrams(b['title'])
    similarity=len(aa&bb)/max(1,len(aa|bb))
    threshold=max(0.45,config['ranking']['story_similarity']) if a['category']==ADULT and left[0].startswith('terms') else config['ranking']['story_similarity']
    return similarity>=threshold


def related_to(article,existing,config):
    return next((a for a in existing if same_story(article,a,config)),None)


def attach_related(representative,article):
    links=representative.setdefault('related_articles',[])
    if article['url']!=representative['url'] and not any(a['url']==article['url'] for a in links):
        links.append({k:article[k] for k in ('title','url','source','published') if k in article})


def rank_articles(articles,rules,now):
    """One consistent order for both tabs; soft novelty penalties, no article deletion."""
    result=[]
    for topic,config in rules.items():
        pool=[]
        for original in articles:
            if original['category']!=topic:continue
            a=dict(original)
            value,info,age=rank_value(a,config,now)
            a.update(info,ranking_score=round(value,3),ranking_reasons=age)
            pool.append(a)
        selected=[]
        topic_counts={};type_counts={};regional_count=0
        while pool:
            eligible=pool
            if topic==BALL and len(selected)<5 and regional_count>=config['ranking']['regional_top5_limit']:
                alternatives=[a for a in pool if not a['regional_high_school'] and a['importance']>=config['ranking']['diversity_min_importance']]
                if alternatives:eligible=alternatives
            def adjusted(a):
                group=competition(a['title']) if a['regional_high_school'] else story_signature(a,config)
                penalty=topic_counts.get(group,0)*config['ranking']['same_topic_penalty'] if group else 0
                type_penalty=0
                if topic==GAME:
                    q=config['quality'];count=type_counts.get(a['info_type'],0)
                    alternatives=[b for b in pool if b['info_type']!=a['info_type'] and b['importance']>=q['diversity_min_importance'] and b['ranking_score']>=a['ranking_score']-q['diversity_score_gap']]
                    if alternatives:type_penalty=min(q['diversity_max_penalty'],max(0,count-1)*q['diversity_penalty'])
                return (a['ranking_score']-penalty-type_penalty,date(a['published']),a['url'])
            winner=max(eligible,key=adjusted)
            group=competition(winner['title']) if winner['regional_high_school'] else story_signature(winner,config)
            effective=adjusted(winner)[0]
            winner['ranking_reasons']['diversity_penalty']=round(winner['ranking_score']-effective,3)
            winner['ranking_score']=round(effective,3)
            winner['display_order']=len(selected)
            selected.append(winner);pool.remove(winner)
            type_counts[winner['info_type']]=type_counts.get(winner['info_type'],0)+1
            if group:topic_counts[group]=topic_counts.get(group,0)+1
            regional_count+=bool(winner['regional_high_school'])
        result.extend(selected)
    return result
