import os, re, json, html, time, datetime, urllib.parse, requests, feedparser
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
try:
    import trafilatura
except Exception:
    trafilatura = None
검색어목록 = []
표시제목 = '데일리 브리핑'
프롬프트_심층 = '아래 최신 기사에서 더 깊이 팔 후속 검색어 {n}개를 고유명사 중심으로 만들어라. 설명 없이 JSON 문자열 배열로만 출력하라.\n\n'
프롬프트_속보 = '아래 새 기사 중 즉시 알릴 만큼 중대하고 새로운 것이 있으면 **제목** | 한 문장, 없으면 정확히 NONE 만 출력하라.\n\n'
프롬프트_키워드 = '아래 최신 기사들을 보고 자동 검색어를 정리하라. 기본 검색어(건드리지 말 것): {base}\n현재 자동 검색어: {auto}\n설명 없이 JSON으로만 출력: {{"add": [], "remove": []}}\n\n'
프롬프트_소스 = "이 주제에 유용한, 실제 존재하는 공개 RSS/Atom 피드 주소를 최대 {max}개 제안하라. 정확한 URL만. RSSHub 경로는 반드시 '{rsshub}/...' 전체 주소로. 이미 사용 중 제외: {existing}\n설명 없이 JSON 문자열 배열로만 출력하라."
추가RSS목록 = ['https://www.38north.org/feed/', 'https://www.dailynk.com/english/feed/', 'https://www.nknews.org/feed/', 'https://www.nkeconwatch.com/feed/', 'https://www.nkleadershipwatch.org/feed/', 'https://www.chosonexchange.org/our-blog?format=rss', 'https://beyondparallel.csis.org/feed/', 'https://www.armscontrolwonk.com/feed/', 'https://www.nautilus.org/feed/', 'https://www3.nhk.or.jp/rss/news/cat6.xml', 'https://www.rfa.org/arc/outboundfeeds/korean/rss', 'https://www.tongilnews.com/rss/allArticle.xml', 'https://kcnawatch.org/feed/', 'https://www.stimson.org/feed/', 'https://keia.org/feed/', 'https://sinonk.com/feed/', 'https://thediplomat.com/feed/', 'https://news.google.com/rss/search?q=site:voakorea.com&hl=ko&gl=KR&ceid=KR:ko', 'https://news.google.com/rss/search?q=site:asiapress.org&hl=ko&gl=KR&ceid=KR:ko', 'https://www.dailynk.com/feed/', 'https://news.google.com/rss/search?q=site:nkeconomy.com&hl=ko&gl=KR&ceid=KR:ko', 'https://news.google.com/rss/search?q=site:spnews.co.kr&hl=ko&gl=KR&ceid=KR:ko']
중국검색 = True
중국어검색어목록 = []
러시아검색 = True
러시아어검색어목록 = []
일본검색 = True
일본어검색어목록 = []
RSSHUB = 'https://rsshub.app'
소셜RSS목록 = []
텔레채널 = []
웨이보계정 = []
웨이보검색어 = []

def _apply_secret_config():
    raw = os.environ.get('SECRET_CONFIG', '').strip()
    if not raw:
        print('SECRET_CONFIG 없음 — 키워드 0개(주입 필요)')
        return
    try:
        cfg = json.loads(raw)
    except Exception as ex:
        print('SECRET_CONFIG 해석 실패(JSON 오류) → 기본값 사용:', ex)
        return
    g = globals()
    for key, var in [('ko', '검색어목록'), ('zh', '중국어검색어목록'), ('ru', '러시아어검색어목록'), ('ja', '일본어검색어목록'), ('sns', '소셜RSS목록'), ('tg', '텔레채널'), ('wb', '웨이보계정'), ('wb_kw', '웨이보검색어')]:
        v = cfg.get(key)
        if isinstance(v, list) and v:
            g[var] = [str(x) for x in v]
    st_ = cfg.get('san_tokens')
    if isinstance(st_, list) and st_:
        g['제재토큰'] = [str(x).lower() for x in st_]
    t = cfg.get('title')
    if isinstance(t, str) and t.strip():
        g['표시제목'] = t.strip()
    geo = cfg.get('geo')
    if isinstance(geo, list) and len(geo) >= 2:
        g['감시좌표'] = (float(geo[0]), float(geo[1]))
        if len(geo) >= 3:
            g['감시반경km'] = float(geo[2])
        if len(geo) >= 4:
            g['감시최소규모'] = float(geo[3])
    for key, var in [('p_expand', '프롬프트_심층'), ('p_breaking', '프롬프트_속보'), ('p_kw', '프롬프트_키워드'), ('p_src', '프롬프트_소스')]:
        v = cfg.get(key)
        if isinstance(v, str) and v.strip():
            g[var] = v
    p = cfg.get('prompt')
    if isinstance(p, str) and p.strip():
        g['명령'] = p
    b = cfg.get('border')
    if isinstance(b, list) and b:
        g['_BORDER_HINTS'] = [str(x).lower() for x in b]
    extra = cfg.get('rss_extra')
    if isinstance(extra, list):
        g['추가RSS목록'] = list(g['추가RSS목록']) + [str(x) for x in extra if str(x) not in g['추가RSS목록']]
    print('비밀 설정 적용 완료 (키워드·소스 주입)')
명령 = "아래 [자료]를 바탕으로 '{주제}' 관련 새 소식을 한국어로 간결히 요약하라. 출처 종류 표시를 참고해 검증 안 된 내용은 단정하지 마라.\n[자료]\n{목록}"
시간범위 = 48
최대기사수 = 100
본문까지읽기 = True
심층검색 = True
심층검색어수 = 12
심층반복 = 1
평일슬롯 = [(8, 0), (13, 30), (17, 30)]
마스터슬롯 = [(22, 0)]
주말발송 = False
주간시작 = '07:00'
주간종료 = '23:00'
검색간격시간 = 0.5
속보허용 = True
심야속보 = True
보고안내 = '평일(월~금) 08:00·13:30·17:30 KST · 중대 속보는 즉시'
키워드자동최신화 = True
자동키워드최대 = 20
키워드갱신주기시간 = 24
키워드열거 = True
소스자동발굴 = True
자동소스최대 = 40
소스갱신주기시간 = 48
소스후보수 = 12
제재감시 = True
제재갱신주기시간 = 24
제재토큰 = []
OPENSANCTIONS_BASE = 'https://data.opensanctions.org/datasets/latest'
제재데이터셋 = ['un_sc_sanctions', 'us_ofac_sdn', 'eu_fsf']
교역지표 = True
교역갱신주기시간 = 720
지진감시 = True
지진갱신주기시간 = 6
감시좌표 = None
감시반경km = 60
감시최소규모 = 2.5
요약모델 = 'gemini-2.5-pro'
보조모델 = 'gemini-2.5-flash'
폴백모델목록 = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-flash-latest']
STATE_FILE = 'seen.json'
상태암호화 = True

def _state_fernet():
    if not (상태암호화 and TG_TOKEN):
        return None
    try:
        from cryptography.fernet import Fernet
    except Exception:
        print('cryptography 미설치 → 상태 평문 저장(공개 전환 전 requirements 확인)')
        return None
    import hashlib, base64
    k = base64.urlsafe_b64encode(hashlib.sha256(('state:' + TG_TOKEN).encode()).digest())
    return Fernet(k)
본문길이 = 1800
본문읽기최대 = 90
동시작업 = 16
출처당최대 = 30
MAX_PROMPT = 220000
링크표시최대 = 15
TG_LIMIT = 4096
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
COMMAND_HELP = '\n\n⏱ 정기 보고: {보고안내}\n🛠 명령: /보고 · /일시중지 · /재개 · /요약 ○○ · /검색어 · /도움말'.replace('{보고안내}', 보고안내)
HELP_TEXT = f'🛠 <b>명령 안내</b>\n/보고 — 지금 바로 브리핑 받기\n/요약 ○○ — 특정 주제만 찾아 정리 (예: /요약 ○○ 동향)\n/일시중지 [이틀·사흘·일주일] — 정기 알림 멈춤\n/재개 — 다시 시작\n/검색어 — 자동 추가된 검색어 보기\n/검색어삭제 ○○ — 자동 검색어에서 빼기\n/도움말 — 이 안내\n\n정기 보고: {보고안내}\n※ 한글 명령(/일시중지 등)은 그대로 입력하면 동작해요. 텔레그램 자동완성 메뉴(/)에는 규칙상 영문 별칭(/report·/pause·/resume·/keywords·/help)만 떠요 — 둘 다 됩니다.'
TG_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()

def _ids(name):
    return [c.strip() for c in os.environ.get(name, '').split(',') if c.strip()]
MASTERS = _ids('TELEGRAM_CHAT_ID_MASTER')
NORMALS = _ids('TELEGRAM_CHAT_ID_NORMAL')
SUBS = _ids('TELEGRAM_CHAT_ID_SUB')
OWNER = MASTERS[0] if MASTERS else ''
TG_CHATS = MASTERS
NAVER_ID = os.environ.get('NAVER_CLIENT_ID', '').strip()
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '').strip()

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def _base_state(d):
    if isinstance(d, list):
        d = {'seen': d}
    return {'seen': d.get('seen', []), 'paused_until': d.get('paused_until', ''), 'last_update_id': d.get('last_update_id', 0), 'user_mutes': d.get('user_mutes', {}), 'last_summary': d.get('last_summary', ''), 'last_search_ts': d.get('last_search_ts', ''), 'last_digest_ts': d.get('last_digest_ts', ''), 'last_digest_slot': d.get('last_digest_slot', ''), 'last_slot_all': d.get('last_slot_all', ''), 'last_slot_master': d.get('last_slot_master', ''), 'alerted': d.get('alerted', []), 'auto_keywords': d.get('auto_keywords', []), 'auto_kw_updated': d.get('auto_kw_updated', ''), 'auto_sources': d.get('auto_sources', []), 'auto_src_updated': d.get('auto_src_updated', ''), 'sanctions_seen': d.get('sanctions_seen', []), 'sanctions_checked': d.get('sanctions_checked', ''), 'comtrade_checked': d.get('comtrade_checked', ''), 'quake_seen': d.get('quake_seen', []), 'quake_checked': d.get('quake_checked', ''), 'cfg_alerted_day': d.get('cfg_alerted_day', ''), 'bot_cmds_v': d.get('bot_cmds_v', '')}

def load_state():
    try:
        raw = open(STATE_FILE, 'rb').read()
        try:
            return _base_state(json.loads(raw.decode('utf-8')))
        except Exception:
            f = _state_fernet()
            if not f:
                raise
            return _base_state(json.loads(f.decrypt(raw).decode('utf-8')))
    except Exception:
        return _base_state({})

def save_state(state):
    f = _state_fernet()
    data = json.dumps(state, ensure_ascii=False, indent=0)
    if f:
        open(STATE_FILE, 'wb').write(f.encrypt(data.encode('utf-8')))
    else:
        open(STATE_FILE, 'w', encoding='utf-8').write(data)

def _post_one(chat, text, silent=False):
    url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    r = requests.post(url, json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True, 'disable_notification': silent}, timeout=30)
    if r.status_code == 400:
        plain = re.sub('<[^>]+>', '', text)
        r = requests.post(url, json={'chat_id': chat, 'text': plain, 'disable_web_page_preview': True, 'disable_notification': silent}, timeout=30)
    r.raise_for_status()

def register_commands(state):
    if state.get('bot_cmds_v') == '2':
        return
    cmds = [{'command': 'report', 'description': '지금 브리핑 받기'}, {'command': 'summary', 'description': '특정 주제 정리 (예: /summary 환율)'}, {'command': 'pause', 'description': '정기 알림 멈춤'}, {'command': 'resume', 'description': '다시 시작'}, {'command': 'keywords', 'description': '자동 검색어 보기'}, {'command': 'help', 'description': '명령 안내'}]
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/setMyCommands', json={'commands': cmds}, timeout=15)
        state['bot_cmds_v'] = '2'
    except Exception as ex:
        print('명령 메뉴 등록 실패(무시 가능):', ex)

def deliver(targets, text, silent=False):
    if len(text) > TG_LIMIT:
        text = text[:TG_LIMIT]
    for chat in targets:
        try:
            _post_one(chat, text, silent=silent)
        except Exception as ex:
            print(f'전송 실패 (받는사람 {chat}): {ex}')

def read_commands(state, long_poll=False):
    known = set(MASTERS) | set(NORMALS) | set(SUBS)
    if not known:
        return []
    try:
        resp = requests.get(f'https://api.telegram.org/bot{TG_TOKEN}/getUpdates', params={'offset': state['last_update_id'] + 1, 'timeout': 25 if long_poll else 0}, timeout=35)
        resp.raise_for_status()
        updates = resp.json().get('result', [])
    except Exception as ex:
        print('명령 읽기 실패:', ex)
        return []
    out = []
    for u in updates:
        state['last_update_id'] = max(state['last_update_id'], u.get('update_id', 0))
        msg = u.get('message') or u.get('channel_post') or {}
        chat = str(msg.get('chat', {}).get('id', ''))
        text = (msg.get('text') or '').strip()
        if chat in known and text:
            out.append((chat, text))
    return out

def _clean(s):
    return ' '.join(re.sub('<[^>]+>', ' ', html.unescape(s or '')).split())

def _rss_items(url, limit):
    out = []
    try:
        entries = feedparser.parse(url).entries[:limit]
    except Exception:
        return out
    for e in entries:
        link = getattr(e, 'link', '')
        if not link:
            continue
        pub = None
        if getattr(e, 'published_parsed', None):
            pub = datetime.datetime(*e.published_parsed[:6], tzinfo=datetime.timezone.utc)
        src = ''
        if hasattr(e, 'source') and isinstance(e.source, dict):
            src = e.source.get('title', '')
        out.append({'title': getattr(e, 'title', '(제목 없음)'), 'link': link, 'source': src, 'pub': pub, 'seed': _clean(getattr(e, 'summary', ''))})
    return out

def _naver_query(term, limit):
    last = None
    for attempt in range(3):
        r = requests.get('https://openapi.naver.com/v1/search/news.json', params={'query': term, 'display': limit, 'sort': 'date'}, headers={'X-Naver-Client-Id': NAVER_ID, 'X-Naver-Client-Secret': NAVER_SECRET}, timeout=20)
        if r.status_code == 429:
            last = r
            time.sleep(0.6 * (attempt + 1))
            continue
        r.raise_for_status()
        out = []
        for it in r.json().get('items', []):
            link = it.get('originallink') or it.get('link') or ''
            if not link:
                continue
            pub = None
            try:
                pub = parsedate_to_datetime(it.get('pubDate', ''))
            except Exception:
                pub = None
            out.append({'title': _clean(it.get('title', '')), 'link': link, 'source': '네이버뉴스', 'pub': pub, 'seed': _clean(it.get('description', ''))})
        return out
    if last is not None:
        last.raise_for_status()
    raise RuntimeError('네이버 응답 없음')

def _body(seed, link):
    if len(seed) >= 400:
        return seed[:본문길이]
    if 본문까지읽기 and trafilatura and link and ('news.google.com' not in link):
        try:
            r = requests.get(link, headers=UA, timeout=12, allow_redirects=True)
            if 'news.google.com' not in r.url:
                body = _clean(trafilatura.extract(r.text) or '')
                if len(body) > len(seed):
                    return body[:본문길이]
        except Exception:
            pass
    return seed[:본문길이]
_GNEWS = {'ko': ('ko', 'KR', 'KR:ko'), 'zh': ('zh-CN', 'CN', 'CN:zh-Hans'), 'ru': ('ru', 'RU', 'RU:ru'), 'ja': ('ja', 'JP', 'JP:ja'), 'en': ('en-US', 'US', 'US:en')}
_BING = {'ko': ('ko', 'KR'), 'zh': ('zh-hans', 'CN'), 'ru': ('ru', 'RU'), 'ja': ('ja', 'JP'), 'en': ('en', 'US')}

def _lang_of(q):
    if re.search('[\\uac00-\\ud7a3]', q):
        return 'ko'
    if re.search('[\\u0400-\\u04ff]', q):
        return 'ru'
    if re.search('[\\u3040-\\u30ff]', q):
        return 'ja'
    if re.search('[\\u4e00-\\u9fff]', q):
        return 'zh'
    return 'ko'

def search_news(q, lang, days, limit, use_bing=None):
    if use_bing is None:
        use_bing = lang != 'ko'
    hl, gl, ceid = _GNEWS.get(lang, _GNEWS['ko'])
    g = f'https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:{days}d&hl={hl}&gl={gl}&ceid={ceid}'
    out = _rss_items(g, limit)
    if use_bing:
        sl, cc = _BING.get(lang, _BING['ko'])
        b = f'https://www.bing.com/news/search?q={urllib.parse.quote(q)}&format=RSS&setlang={sl}&cc={cc}'
        out = out + _rss_items(b, limit)
    return out

def _roundrobin(sources, cutoff, cap):
    items, seen, i = ([], set(), 0)
    while len(items) < cap and any((i < len(s) for s in sources)):
        for s in sources:
            if i < len(s):
                it = s[i]
                if it['link'] in seen:
                    continue
                if it.get('pub') and it['pub'] < cutoff:
                    continue
                seen.add(it['link'])
                items.append(it)
                if len(items) >= cap:
                    break
        i += 1
    return items

def _parallel(jobs):
    out = []
    with ThreadPoolExecutor(max_workers=동시작업) as ex:
        futs = [(b, ex.submit(fn)) for b, fn in jobs]
        for b, f in futs:
            try:
                out.append((b, f.result()))
            except Exception:
                out.append((b, []))
    return out

def expand_queries(items, n):
    sample = []
    for it in items[:30]:
        s = it.get('title', '')
        if it.get('seed'):
            s += ' — ' + it['seed'][:140]
        sample.append('- ' + s)
    prompt = 프롬프트_심층.replace('{n}', str(n)) + '\n'.join(sample)
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub('^```(json)?', '', raw)
        raw = re.sub('```$', '', raw).strip()
        arr = json.loads(raw)
        seen, out = (set(), [])
        for x in arr:
            x = str(x).strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out[:n]
    except Exception as ex:
        print('심층 검색어 생성 실패:', ex)
        return []

def refresh_keywords(items, base, current_auto):
    sample = []
    for it in items[:40]:
        s = it.get('title', '')
        if it.get('seed'):
            s += ' — ' + it['seed'][:100]
        sample.append('- ' + s)
    prompt = 프롬프트_키워드.replace('{base}', ', '.join(base)).replace('{auto}', ', '.join(current_auto) or '(없음)') + '\n'.join(sample)
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub('^```(json)?', '', raw)
        raw = re.sub('```$', '', raw).strip()
        obj = json.loads(raw)
        add = [str(x).strip() for x in obj.get('add', []) if str(x).strip()]
        remove = [str(x).strip() for x in obj.get('remove', []) if str(x).strip()]
    except Exception as ex:
        print('검색어 자동 정리 실패:', ex)
        return (list(current_auto), [], [])
    base_set = set(base)
    remset = set(remove)
    cur = [k for k in current_auto if k not in remset]
    used = base_set | set(cur)
    newly = []
    for x in add:
        if x and x not in used:
            cur.append(x)
            used.add(x)
            newly.append(x)
    cur = cur[-자동키워드최대:]
    removed = [r for r in remove if r in set(current_auto)]
    return (cur, newly, removed)

def _maybe_learn_keywords(state, items):
    if not (키워드자동최신화 and state is not None and items):
        return
    last = state.get('auto_kw_updated', '')
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=키워드갱신주기시간):
                return
        except Exception:
            pass
    merged, added, removed = refresh_keywords(items, 검색어목록, state.get('auto_keywords', []))
    state['auto_keywords'] = merged
    state['auto_kw_updated'] = now_utc().isoformat()
    if added or removed:
        print(f'검색어 자동 추가 {len(added)}건 / 삭제 {len(removed)}건')
        parts = []
        if added:
            parts.append('➕ 추가: ' + ', '.join(added))
        if removed:
            parts.append('➖ 정리: ' + ', '.join(removed))
        try:
            deliver([OWNER], '🆕 검색어 업데이트\n' + '\n'.join(parts))
        except Exception:
            pass

def _validate_feed(url):
    try:
        return len(_rss_items(url, 5))
    except Exception:
        return 0

def discover_sources(existing):
    prompt = 프롬프트_소스.replace('{max}', str(소스후보수)).replace('{rsshub}', RSSHUB).replace('{existing}', ', '.join(list(existing)[:80]))
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub('^```(json)?', '', raw)
        raw = re.sub('```$', '', raw).strip()
        return [str(x).strip() for x in json.loads(raw) if str(x).strip().lower().startswith('http')]
    except Exception as ex:
        print('소스 후보 생성 실패:', ex)
        return []

def _maybe_learn_sources(state):
    if not (소스자동발굴 and state is not None):
        return
    last = state.get('auto_src_updated', '')
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=소스갱신주기시간):
                return
        except Exception:
            pass
    state['auto_src_updated'] = now_utc().isoformat()
    fixed = set(추가RSS목록) | set(소셜RSS목록) | {f'tg:{c}' for c in 텔레채널} | {f'wb:{u}' for u in 웨이보계정}
    auto = list(state.get('auto_sources', []))
    alive, dropped = ([], [])
    for u in auto:
        (alive if _validate_feed(u) > 0 else dropped).append(u)
    added = []
    for u in discover_sources(fixed | set(alive)):
        if u in fixed or u in alive:
            continue
        if _validate_feed(u) > 0:
            alive.append(u)
            added.append(u)
            if len(alive) >= 자동소스최대:
                break
    state['auto_sources'] = alive[-자동소스최대:]
    if added or dropped:
        print(f'소스 자동 추가 {len(added)}건 / 정리 {len(dropped)}건')
        parts = []
        if added:
            parts.append('➕ 검증 통과한 새 소스:\n' + '\n'.join(added))
        if dropped:
            parts.append('➖ 응답 없어 정리한 소스:\n' + '\n'.join(dropped))
        try:
            deliver([OWNER], '🛰 소스 업데이트\n' + '\n'.join(parts))
        except Exception:
            pass

def _maybe_check_sanctions(state):
    if not (제재감시 and state is not None):
        return
    last = state.get('sanctions_checked', '')
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=제재갱신주기시간):
                return
        except Exception:
            pass
    state['sanctions_checked'] = now_utc().isoformat()
    import csv, io
    toks = tuple(제재토큰)
    if not toks:
        print('제재 필터 토큰 미주입 → 건너뜀')
        return
    cur = {}
    for ds in 제재데이터셋:
        try:
            r = requests.get(f'{OPENSANCTIONS_BASE}/{ds}/targets.simple.csv', timeout=90)
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.text)))
        except Exception as ex:
            print(f'제재 명단 다운로드 실패({ds}):', ex)
            continue
        for row in rows:
            blob = ' '.join((str(v) for v in row.values())).lower()
            if any((t in blob for t in toks)):
                rid = ds + ':' + (row.get('id') or blob[:50])
                cur[rid] = (row.get('name') or rid, ds)
    if not cur:
        print('제재 명단에서 대상 항목을 못 찾음(형식 변경 가능)')
        return
    seen = set(state.get('sanctions_seen', []))
    new = [(i, v) for i, v in cur.items() if i not in seen]
    state['sanctions_seen'] = list(cur.keys())
    if not seen:
        print('제재 기준선 설정:', len(cur), '건 (첫 실행은 알림 없음)')
        return
    if new:
        label = {'un_sc_sanctions': '유엔', 'us_ofac_sdn': '미국 OFAC', 'eu_fsf': 'EU'}
        lines = [f'• [{label.get(ds, ds)}] {html.escape(nm)}' for _, (nm, ds) in new[:30]]
        msg = f'🚫 <b>신규 제재 지정 감지</b> ({len(new)}건)\n' + '\n'.join(lines) + '\n\n→ 신규 지정 대상의 거래망·소유구조를 추적해 보세요 — 취재 단서.'
        try:
            deliver(TG_CHATS, msg)
        except Exception:
            pass
        print('신규 제재 지정 알림:', len(new))

def _maybe_check_quake(state):
    if not (지진감시 and 감시좌표 and (state is not None)):
        return
    last = state.get('quake_checked', '')
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=지진갱신주기시간):
                return
        except Exception:
            pass
    state['quake_checked'] = now_utc().isoformat()
    try:
        lat, lon = 감시좌표
        start = (now_utc() - datetime.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S')
        r = requests.get('https://earthquake.usgs.gov/fdsnws/event/1/query', params={'format': 'geojson', 'latitude': lat, 'longitude': lon, 'maxradiuskm': 감시반경km, 'starttime': start, 'minmagnitude': 감시최소규모}, timeout=30)
        r.raise_for_status()
        feats = r.json().get('features', [])
    except Exception as ex:
        print('지진 조회 실패:', ex)
        return
    seen = set(state.get('quake_seen', []))
    new = [f for f in feats if f.get('id') and f.get('id') not in seen]
    state['quake_seen'] = ([f.get('id') for f in feats if f.get('id')] + list(seen))[:200]
    if not seen:
        print('지진 기준선:', len(feats), '건')
        return
    for f in new:
        p = f.get('properties', {})
        mag = p.get('mag')
        place = p.get('place', '')
        when = ''
        try:
            when = datetime.datetime.utcfromtimestamp(p.get('time', 0) / 1000.0 + 9 * 3600).strftime('%m-%d %H:%M')
        except Exception:
            pass
        msg = f'⚠️ <b>감시지점 인근 지진 감지</b> M{mag} ({when} KST)\n{html.escape(place)}\n\n→ 자연·인공 여부 즉시 교차 확인(USGS·기상청·CTBTO).'
        try:
            deliver(TG_CHATS, msg)
        except Exception:
            pass
    if new:
        print('감시지점 인근 지진 알림:', len(new))

def _maybe_comtrade(state):
    key = os.environ.get('COMTRADE_KEY', '').strip()
    if not (교역지표 and key and (state is not None)):
        return
    last = state.get('comtrade_checked', '')
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=교역갱신주기시간):
                return
        except Exception:
            pass
    state['comtrade_checked'] = now_utc().isoformat()
    try:
        now = now_utc()
        for back in range(2, 6):
            y, m = (now.year, now.month - back)
            while m <= 0:
                m += 12
                y -= 1
            period = f'{y}{m:02d}'
            r = requests.get('https://comtradeapi.un.org/data/v1/get/C/M/HS', params={'reporterCode': 156, 'partnerCode': 408, 'period': period, 'flowCode': 'M,X', 'cmdCode': 'TOTAL'}, headers={'Ocp-Apim-Subscription-Key': key}, timeout=40)
            if r.status_code != 200:
                continue
            data = r.json().get('data', [])
            if not data:
                continue
            exp = sum((d.get('primaryValue', 0) or 0 for d in data if d.get('flowCode') == 'X'))
            imp = sum((d.get('primaryValue', 0) or 0 for d in data if d.get('flowCode') == 'M'))
            msg = f'📊 <b>교역 지표</b> ({y}-{m:02d}, UN Comtrade)\n상대→대상 수출 ${exp / 1000000.0:,.1f}M · 대상→상대 ${imp / 1000000.0:,.1f}M'
            try:
                deliver(TG_CHATS, msg)
            except Exception:
                pass
            return
        print('Comtrade: 최근 가용 월 데이터를 못 찾음')
    except Exception as ex:
        print('Comtrade 조회 실패:', ex)
_TG_WRAP = re.compile('<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|<div class="tgme_channel_history)', re.S)
_TG_BUBBLE = re.compile('tgme_widget_message_bubble.*', re.S)
_TG_TEXT = re.compile('<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\\s*(?:<div class="tgme_widget_message_(?:footer|info|reply)|$)', re.S)
_TG_TEXT_SIMPLE = re.compile('<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TG_TIME = re.compile('<a class="tgme_widget_message_date"[^>]*href="([^"]+)".*?datetime="([^"]+)"', re.S)

def fetch_telegram(channel, limit):
    out = []
    try:
        url = f'https://t.me/s/{channel.lstrip('@')}'
        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return out
        wraps = _TG_WRAP.findall(r.text)
        for w in wraps[-limit:]:
            bub = _TG_BUBBLE.search(w)
            seg = bub.group(0) if bub else w
            m = _TG_TEXT.search(seg) or _TG_TEXT_SIMPLE.search(seg)
            if not m:
                continue
            txt = _clean(m.group(1))
            if not txt or len(txt) < 4:
                continue
            link, pub = (url, None)
            tm = _TG_TIME.search(w)
            if tm:
                link = tm.group(1)
                try:
                    pub = datetime.datetime.fromisoformat(tm.group(2).replace('Z', '+00:00')).astimezone(datetime.timezone.utc).replace(tzinfo=None)
                except Exception:
                    pub = None
            out.append({'title': txt[:200], 'link': link, 'source': f'TG:{channel}', 'pub': pub, 'seed': txt[:300]})
    except Exception as ex:
        print(f'텔레그램 수집 실패({channel}):', str(ex)[:80])
    return out

def fetch_weibo(uid=None, keyword=None, limit=10):
    out = []
    try:
        h = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)', 'Referer': 'https://m.weibo.cn/'}
        if keyword:
            url = 'https://m.weibo.cn/api/container/getIndex'
            params = {'containerid': f'100103type=1&q={keyword}', 'page_type': 'searchall'}
        else:
            url = 'https://m.weibo.cn/api/container/getIndex'
            params = {'type': 'uid', 'value': uid, 'containerid': f'107603{uid}'}
        r = requests.get(url, params=params, headers=h, timeout=20)
        cards = (r.json().get('data', {}) or {}).get('cards', []) or []
        for c in cards:
            mb = c.get('mblog') or (c.get('card_group', [{}])[0].get('mblog') if c.get('card_group') else None)
            if not mb:
                continue
            txt = _clean(mb.get('text', ''))
            if not txt:
                continue
            mid = mb.get('id', '')
            tag = f'WB:{keyword}' if keyword else f'WB:{uid}'
            pub = None
            try:
                pub = parsedate_to_datetime(mb.get('created_at', '')).astimezone(datetime.timezone.utc).replace(tzinfo=None)
            except Exception:
                pub = None
            out.append({'title': txt[:200], 'link': f'https://m.weibo.cn/status/{mid}', 'source': tag, 'pub': pub, 'seed': txt[:300]})
            if len(out) >= limit:
                break
    except Exception as ex:
        print(f'웨이보 수집 실패({uid or keyword}):', str(ex)[:80])
    return out

def fetch_items(terms, regional=True, bodies=True, deep=True, auto_feeds=None):
    days = max(1, (시간범위 + 23) // 24)
    cutoff = now_utc() - datetime.timedelta(hours=시간범위)
    하드캡 = 최대기사수 * 2 if 심층검색 and deep else 최대기사수
    jobs = []
    for t in terms:
        jobs.append(('ko', lambda t=t: search_news(t, _lang_of(t), days, 출처당최대)))
    if regional:
        for rss in 추가RSS목록 + list(auto_feeds or []):
            jobs.append(('rss', lambda rss=rss: _rss_items(rss, 출처당최대)))
        for s in 소셜RSS목록:
            jobs.append(('sns', lambda s=s: _rss_items(s, 출처당최대)))
        for ch in 텔레채널:
            jobs.append(('sns', lambda ch=ch: fetch_telegram(ch, 출처당최대)))
        for uid in 웨이보계정:
            jobs.append(('sns', lambda uid=uid: fetch_weibo(uid=uid, limit=출처당최대)))
        for kw in 웨이보검색어:
            jobs.append(('sns', lambda kw=kw: fetch_weibo(keyword=kw, limit=출처당최대)))
        if 중국검색:
            for t in 중국어검색어목록:
                jobs.append(('zh', lambda t=t: search_news(t, 'zh', days, 출처당최대)))
        if 러시아검색:
            for t in 러시아어검색어목록:
                jobs.append(('ru', lambda t=t: search_news(t, 'ru', days, 출처당최대)))
        if 일본검색:
            for t in 일본어검색어목록:
                jobs.append(('ja', lambda t=t: search_news(t, 'ja', days, 출처당최대)))
    counts = {'ko': 0, 'zh': 0, 'ru': 0, 'ja': 0, 'rss': 0, 'sns': 0, 'naver': 0, 'expand': 0}
    sources = []
    for bucket, lst in _parallel(jobs):
        counts[bucket] += len(lst)
        if bucket == 'sns':
            for it in lst:
                it['social'] = True
        sources.append(lst)
    네이버상태 = 'off'
    네이버오류 = ''
    if NAVER_ID and NAVER_SECRET:
        네이버상태 = 'ok'
        err = False
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(lambda t=t: _naver_query(t, 출처당최대)) for t in terms]
            for f in futs:
                try:
                    lst = f.result()
                except Exception as ex2:
                    print('네이버 검색 실패:', ex2)
                    err = True
                    lst = []
                    code = getattr(getattr(ex2, 'response', None), 'status_code', None)
                    if code and (not 네이버오류):
                        네이버오류 = str(code)
                        hint = {'401': "키 오류 또는 '검색' API 미설정/공백 포함", '403': "권한 없음(앱에 '검색' API 미추가)", '429': '하루 호출 한도 초과'}.get(str(code), '')
                        if hint:
                            print('  ↳ 네이버 점검:', hint)
                counts['naver'] += len(lst)
                sources.append(lst)
        if err:
            네이버상태 = 'err'
    items = _roundrobin(sources, cutoff, 최대기사수)
    if 심층검색 and deep and items:
        pool = list(items)
        for _ in range(max(1, 심층반복)):
            queries = expand_queries(pool, 심층검색어수)
            if not queries:
                break
            counts['expand'] += len(queries)
            ex_jobs = [('x', lambda q=q: search_news(q, _lang_of(q), days, 출처당최대)) for q in queries]
            ex_sources = [lst for _, lst in _parallel(ex_jobs)]
            more = _roundrobin(ex_sources, cutoff, 하드캡)
            have = {it['link'] for it in items}
            added = []
            for it in more:
                if it['link'] not in have:
                    items.append(it)
                    have.add(it['link'])
                    added.append(it)
                    if len(items) >= 하드캡:
                        break
            if not added or len(items) >= 하드캡:
                break
            pool = added
    deep_list = items[:본문읽기최대]
    if 본문까지읽기 and bodies and deep_list:
        with ThreadPoolExecutor(max_workers=동시작업) as ex:
            read = list(ex.map(lambda it: _body(it.get('seed', ''), it['link']), deep_list))
        for it, b in zip(deep_list, read):
            it['body'] = b
    for it in items:
        it.setdefault('body', (it.get('seed', '') or '')[:본문길이])
    stat = {'ko': counts['ko'], 'zh': counts['zh'], 'ru': counts['ru'], 'ja': counts['ja'], 'rss': counts['rss'], 'sns': counts['sns'], 'naver': counts['naver'], 'naver_state': 네이버상태, 'naver_err': 네이버오류, 'expand': counts['expand']}
    return (items, stat)

def _gemini(prompt, model=보조모델):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    err = ''
    for attempt in range(4):
        try:
            r = requests.post(url, headers={'x-goog-api-key': GEMINI_KEY, 'Content-Type': 'application/json'}, json={'contents': [{'parts': [{'text': prompt}]}]}, timeout=180)
            if r.status_code in (400, 404):
                raise RuntimeError(f"모델 '{model}' 사용 불가({r.status_code})")
            if r.status_code in (429, 500, 502, 503, 504):
                err = f'{r.status_code} (한도 또는 일시 오류)'
                print(f'Gemini[{model}] {err} - {6 * (attempt + 1)}초 후 재시도 ({attempt + 1}/4)')
                time.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()['candidates'][0]['content']['parts'][0]['text']
        except requests.exceptions.RequestException as ex:
            err = str(ex)
            time.sleep(6 * (attempt + 1))
    raise RuntimeError(f'Gemini[{model}] 호출 실패(재시도 후): ' + err)
_BRIEF_ENGINE = ''

def gemini(prompt, models):
    global _BRIEF_ENGINE
    seen, chain = (set(), [])
    for m in models:
        if m and m not in seen:
            seen.add(m)
            chain.append(m)
    last = ''
    for m in chain:
        try:
            out = _gemini(prompt, model=m)
            _BRIEF_ENGINE = m
            return out
        except Exception as ex:
            last = str(ex)
            print(f'모델 {m} 실패 → 다음 모델로 폴백: {last[:120]}')
    raise RuntimeError('모든 모델 폴백 실패: ' + last)
_BORDER_HINTS = []

def _is_border(it):
    blob = (it.get('title', '') + ' ' + it.get('seed', '') + ' ' + (it.get('body', '') or '')).lower()
    return any((h in blob for h in _BORDER_HINTS))
_PRIMARY_DOMAINS = ('rfa.org', 'kcnawatch.org', '38north.org', 'dailynk.com', 'nknews.org', 'nkeconwatch.com', 'nkleadershipwatch.org', 'beyondparallel.csis.org', 'armscontrolwonk.com', 'nautilus.org', 'sinonk.com', 'stimson.org', 'keia.org', 'thediplomat.com', 'tongilnews.com', 'primamedia.ru', 'chosonexchange.org', 'asiapress.org')
_PRIMARY_SRC_HINTS = ('rfa', '자유아시아', 'daily nk', '데일리nk', 'nk news', '38 north', 'kcna', '조선중앙', 'beyond parallel', 'stimson', 'diplomat', '통일뉴스', 'nautilus', 'nk pro', '아시아프레스', 'rimjin', '임진강')

def _domain(u):
    try:
        return urllib.parse.urlparse(u).netloc.lower().replace('www.', '')
    except Exception:
        return ''

def _provenance(it):
    t = it.get('title', '')
    d = _domain(it.get('link', ''))
    src = (it.get('source', '') or '').lower()
    primary = any((d.endswith(pd) for pd in _PRIMARY_DOMAINS)) or any((k in src for k in _PRIMARY_SRC_HINTS))
    if re.search('[\\u0400-\\u04ff]', t):
        lang = '러'
    elif re.search('[\\u3040-\\u30ff]', t):
        lang = '일'
    elif re.search('[\\u4e00-\\u9fff]', t):
        lang = '중'
    else:
        lang = ''
    if it.get('social'):
        return ('sns', 'SNS·미확인')
    if _is_border(it):
        return ('border', '지역신호·1차' if primary else '지역신호')
    if primary:
        return ('primary', '1차·전문')
    if lang:
        return ('foreign', '외신·' + lang)
    return ('main', '주류')

def summarize(topic, items, prev_summary=''):
    groups = {'border': [], 'sns': [], 'primary': [], 'foreign': [], 'main': []}
    seen_titles = set()
    for it in items:
        g, label = _provenance(it)
        if g == 'main':
            key = re.sub('\\W+', '', it.get('title', ''))[:16]
            if key and key in seen_titles:
                continue
            seen_titles.add(key)
        it['_plabel'] = label
        groups[g].append(it)
    order = ['border', 'sns', 'primary', 'foreign', 'main']
    main_cap = int(MAX_PROMPT * 0.3)
    blocks, total, main_used = ([], 0, 0)
    for g in order:
        for it in groups[g]:
            tag = f' ({it['_plabel']})' if it.get('_plabel') else ''
            b = f'[{len(blocks) + 1}] {it['title']}{tag} ({it.get('source', '')})'
            if it.get('body'):
                b += f'\n발췌: {it['body']}'
            if total + len(b) > MAX_PROMPT:
                if g != 'main':
                    continue
                break
            if g == 'main' and main_used + len(b) > main_cap:
                break
            blocks.append(b)
            total += len(b)
            if g == 'main':
                main_used += len(b)
    base = 명령.replace('{주제}', topic).replace('{목록}', '\n\n'.join(blocks))
    if prev_summary:
        base = f"아래 [이전 보고]는 직전에 이미 보낸 브리핑이다. 반드시 지켜라:\n1) 이전 보고에서 이미 다룬 사안은 ★원칙적으로 생략★하라. 중대한 새 전개가 있을 때만 맨 끝에 '(갱신)' 표시로 딱 한 줄. 두 줄 이상 쓰면 실패다.\n2) 지면은 이전 보고 '이후' 새로 등장한 것에만 써라. 같은 사건 재정리 금지.\n3) 이전과 견줘 의미 있는 새 내용이 사실상 없으면, 설명 없이 정확히 'NO_UPDATE' 한 단어만 출력하라.\n\n[이전 보고]\n{prev_summary}\n\n--------\n\n" + base
    return gemini(base, [요약모델, 보조모델] + 폴백모델목록)

def status_line(stat):
    ko = stat.get('ko', 0)
    zh = stat.get('zh', 0)
    ru = stat.get('ru', 0)
    ja = stat.get('ja', 0)
    rs = stat.get('rss', 0)
    ns = stat.get('naver_state', 'off')
    nv = stat.get('naver', 0)
    sn = stat.get('sns', 0)
    xp = stat.get('expand', 0)
    if ns == 'off':
        nav = '네이버 –'
    elif ns == 'err':
        code = stat.get('naver_err', '')
        nav = f'네이버 ✗({code})' if code else '네이버 ✗'
    else:
        nav = f'네이버 {nv}'
    ok = ko + zh + ru + ja + rs + nv > 0 and ns != 'err'
    head = '✅ 동작 정상' if ok else '⚠️ 점검 필요'
    deep = f' | 심층 +{xp}' if xp else ''
    sns = f'·SNS {sn}' if sn else ''
    jap = f'·일본 {ja}' if ja else ''
    eng = f' | 분석 {_BRIEF_ENGINE}' if _BRIEF_ENGINE else ''
    return f'{head} | 검색: 한국 {ko}·{nav}·중국 {zh}·러시아 {ru}{jap}·RSS {rs}{sns}{deep}{eng} | 요약 ✓'

def _chunk(text, limit):
    out, cur = ([], '')
    for line in text.split('\n'):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ''
            out.append(line[:limit])
            line = line[limit:]
        add = '\n' + line if cur else line
        if len(cur) + len(add) <= limit:
            cur += add
        else:
            out.append(cur)
            cur = line
    if cur:
        out.append(cur)
    return out

def _fmt(text):
    t = html.escape(text)
    t = re.sub('\\*\\*(.+?)\\*\\*', '<b>\\1</b>', t)
    t = re.sub('__(.+?)__', '<i>\\1</i>', t)
    return t

def keyword_message(auto):
    L = ['🔑 <b>검색 키워드</b>']
    L.append(f'[고정·한국어 {len(검색어목록)}] ' + html.escape(', '.join(검색어목록)))
    if 중국검색 and 중국어검색어목록:
        L.append(f'[고정·중국어 {len(중국어검색어목록)}] ' + html.escape(', '.join(중국어검색어목록)))
    if 러시아검색 and 러시아어검색어목록:
        L.append(f'[고정·러시아어 {len(러시아어검색어목록)}] ' + html.escape(', '.join(러시아어검색어목록)))
    rss = 추가RSS목록 + 소셜RSS목록
    if rss:
        L.append(f'[고정·RSS {len(rss)}] ' + html.escape(', '.join(rss)))
    if auto:
        L.append(f'[변동·자동 {len(auto)}] ' + html.escape(', '.join(auto)))
    else:
        L.append('[변동·자동 0] 아직 없음 — 상황 따라 자동 추가·삭제돼요')
    return '\n'.join(L)

def build_messages(topic, items, digest, stat=None, prefix='', lead=None, show_links=True, footer=True):
    now_kst = now_utc() + datetime.timedelta(hours=9)
    status = status_line(stat) + '\n' if stat is not None else ''
    head = f'{status}{prefix}📰 <b>[{html.escape(topic)}] {now_kst.strftime('%m-%d %H:%M')} KST</b> (자료 {len(items)}건)\n\n'

    def line(i, it):
        t = html.escape(it['title'])
        u = html.escape(it['link'], quote=True)
        s = html.escape(it.get('source', ''))
        pub = it.get('pub')
        when = ''
        if pub:
            try:
                when = '(' + (pub + datetime.timedelta(hours=9)).strftime('%m-%d %H:%M') + ') '
            except Exception:
                when = ''
        return f'{i + 1}. {when}<a href="{u}">{t}</a>' + (f' - {s}' if s else '')
    links = [line(i, it) for i, it in enumerate(items)][:링크표시최대]
    linkblock = '\n\n📎 <b>주요 최신 자료</b> (괄호=보도 시각, KST)\n' + '\n'.join(links) if links else ''
    tail = COMMAND_HELP if footer else ''
    idx = digest.find('[취재')
    if idx > 0:
        body_pre, body_post = (_fmt(digest[:idx].rstrip()), _fmt(digest[idx:].strip()) + tail)
        if show_links:
            parts = [head + (linkblock.lstrip('\n') if linkblock else '(링크 없음)'), body_pre, body_post]
        else:
            parts = [head + body_pre, body_post]
    elif show_links:
        parts = [head + (linkblock.lstrip('\n') if linkblock else ''), _fmt(digest) + tail]
    else:
        parts = [head + _fmt(digest) + tail]
    chunks = []
    for L in lead or []:
        chunks.extend(_chunk(L, TG_LIMIT - 16))
    for p in parts:
        chunks.extend(_chunk(p, TG_LIMIT - 16))
    n = len(chunks)
    if n > 1:
        chunks = [f'({i + 1}/{n}) ' + c for i, c in enumerate(chunks)]
    return chunks

def parse_command(text):
    raw = text.strip()
    t = raw.lstrip('/').replace(' ', '').lower()
    if any((k in t for k in ['도움말', '사용법', '명령어', 'help', 'start', 'commands'])):
        return ('help', None)
    if '검색어' in t or '키워드' in t or 'keyword' in t:
        if any((k in t for k in ['초기화', '리셋', '전부삭제', '모두삭제', 'reset', 'clear'])):
            return ('kwreset', None)
        if any((k in t for k in ['빼', '삭제', '제거', '지워', '지우', 'remove', 'del'])):
            r = raw
            for w in ['/', '검색어', '키워드', 'keyword', '목록', '에서', '좀', '줘', '빼줘', '빼기', '빼', '삭제해', '삭제', '제거해', '제거', '지워줘', '지워', '지우기', '지우', 'remove', 'del']:
                r = r.replace(w, ' ')
            terms = [x.strip() for x in r.split(',') if x.strip()] if ',' in r else [r.strip()] if r.strip() else []
            return ('kwremove', terms)
        return ('kwlist', None)
    if any((k in t for k in ['재개', '다시보내', '다시시작', 'resume', '켜'])):
        return ('resume', None)
    if any((k in t for k in ['일시중지', '정지', '그만', '멈춰', '멈춤', '중지', '쉬어', '쉴게', 'pause', 'stop'])):
        hours = 24
        if '이틀' in t or '2일' in t:
            hours = 48
        elif '사흘' in t or '3일' in t:
            hours = 72
        elif '일주일' in t or '7일' in t or '한주' in t or ('week' in t):
            hours = 168
        return ('pause', hours)
    if '요약' in raw or '정리' in raw or t.startswith('summary') or t.startswith('요약'):
        topic = raw
        for w in ['/', '요약해서 알려줘', '요약해줘', '요약해', '요약', '정리해줘', '정리해', '정리', 'summary', '관련 기사', '관련기사', '에 대해', '에 대한', '알려줘', '최신', '관련', '기사', '해서']:
            topic = topic.replace(w, ' ')
        topic = ' '.join(topic.split()).strip()
        if topic:
            return ('digest', topic)
        return ('report_now', None)
    if t in ('보고', '브리핑', '지금보고', 'report', 'brief', 'now') or t.startswith('보고') or t.startswith('브리핑') or t.startswith('report') or t.startswith('brief'):
        return ('report_now', None)
    return (None, None)

def handle_commands(state, long_poll=False):
    on_demand = []
    report_now = False
    for chat, text in read_commands(state, long_poll=long_poll):
        kind, arg = parse_command(text)
        if chat not in set(MASTERS):
            if kind == 'pause':
                _user_pause(state, chat, arg)
                deliver([chat], f"⏸️ 약 {arg}시간 동안 알림을 멈출게요. ('/재개'로 다시 받기.)")
            elif kind == 'resume':
                _user_pause(state, chat, 0, clear=True)
                deliver([chat], '▶️ 알림을 다시 받을게요.')
            else:
                deliver([chat], "이 봇은 '/일시중지'와 '/재개'만 사용할 수 있어요.")
            continue
        if kind == 'help':
            deliver([OWNER], HELP_TEXT)
        elif kind == 'resume':
            state['paused_until'] = ''
            deliver([OWNER], '▶️ 다시 시작할게요. 정해진 시간에 알림을 보낼게요.')
        elif kind == 'report_now':
            deliver([OWNER], '📰 지금 브리핑을 준비할게요… 잠시만요(1~2분).')
            report_now = True
        elif kind == 'kwlist':
            auto = state.get('auto_keywords', [])
            msg = f'🔎 자동 추가된 검색어 {len(auto)}개:\n' + ', '.join(auto) if auto else '🔎 아직 자동 추가된 검색어가 없어요. (다음 정기 보고 때 다음 보고 때 보강해요.)'
            deliver([OWNER], msg + f"\n\n기본 검색어는 {len(검색어목록)}개 고정. '/검색어삭제 ○○'로 자동분만 뺄 수 있어요.")
        elif kind == 'kwreset':
            state['auto_keywords'] = []
            state['auto_kw_updated'] = ''
            deliver([OWNER], '🧹 자동 추가 검색어를 모두 비웠어요. 다음 보고 때 다시 학습해요.')
        elif kind == 'kwremove':
            auto = state.get('auto_keywords', [])
            tgts = [t.replace(' ', '') for t in arg or [] if t.strip()]
            removed, keep = ([], [])
            for kw in auto:
                norm = kw.replace(' ', '')
                if tgts and any((tt and tt in norm for tt in tgts)):
                    removed.append(kw)
                else:
                    keep.append(kw)
            state['auto_keywords'] = keep
            if removed:
                deliver([OWNER], '🗑 검색어에서 제거: ' + ', '.join(removed))
            else:
                deliver([OWNER], "그 검색어를 자동 목록에서 못 찾았어요. '/검색어'로 확인해 주세요.")
        elif kind == 'pause':
            state['paused_until'] = (now_utc() + datetime.timedelta(hours=arg)).isoformat()
            deliver([OWNER], f"⏸️ 약 {arg}시간 동안 정기 알림을 멈출게요. ('/재개'로 다시 시작.)")
        elif kind == 'digest':
            deliver([OWNER], f"🔎 '{arg}' 자료를 모으는 중이에요… 잠시만요(1~2분).")
            on_demand.append(arg)
    return (on_demand, report_now)

def _user_pause(state, chat, hours, clear=False):
    m = dict(state.get('user_mutes', {}))
    if clear:
        m.pop(str(chat), None)
    else:
        m[str(chat)] = (now_utc() + datetime.timedelta(hours=hours)).isoformat()
    state['user_mutes'] = m

def _active(state, ids):
    m = state.get('user_mutes', {})
    out = []
    for c in ids:
        u = m.get(str(c), '')
        if u:
            try:
                if now_utc() < datetime.datetime.fromisoformat(u):
                    continue
            except Exception:
                pass
        out.append(c)
    return out

def is_paused(state):
    if not state.get('paused_until'):
        return False
    try:
        return now_utc() < datetime.datetime.fromisoformat(state['paused_until'])
    except Exception:
        return False

def run_topic(topic, terms, targets, state=None, mark_seen=True, prefix='', gate=False, regional=True, learn=False, prefetched=None):
    items, stat = prefetched if prefetched is not None else fetch_items(terms, regional=regional)
    if learn:
        _maybe_learn_keywords(state, items)
    if state is not None and mark_seen:
        seen = set(state['seen'])
        items = [it for it in items if it['link'] not in seen]
    if not items:
        return 0
    prev = state.get('last_summary', '') if state and gate else ''
    digest = summarize(topic, items, prev_summary=prev)
    if gate and len(digest.strip()) < 40 and ('NO_UPDATE' in digest.upper()):
        if state is not None and mark_seen:
            state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
        print('업데이트 없음 - 전송 생략')
        return 0
    lead = None
    if 키워드열거 and regional:
        auto = state.get('auto_keywords', []) if state else []
        lead = [keyword_message(auto)]
    msgs = build_messages(topic, items, digest, stat=stat, prefix=prefix, lead=lead)
    for m in msgs:
        deliver(targets, m)
        time.sleep(0.4)
    if state is not None and mark_seen:
        state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
        state['last_summary'] = digest[:3000]
    return len(items)

def _hhmm(s):
    h, m = s.split(':')
    return int(h) * 60 + int(m)

def _in_window(now_kst):
    cur = now_kst.hour * 60 + now_kst.minute
    return _hhmm(주간시작) <= cur < _hhmm(주간종료)

def _trim_for_normal(digest):
    keep = []
    for ln in digest.splitlines():
        if '(어떻게' in ln or '(단서' in ln:
            continue
        keep.append(ln)
    return '\n'.join(keep)

def _single_for_sub(topic, digest, now_kst):
    body = digest.split('[취재')[0].strip()
    head = f'📰 <b>[{html.escape(topic)}] {now_kst.strftime('%m-%d %H:%M')} KST</b>\n\n'
    return _chunk(head + _fmt(body), TG_LIMIT - 16)[0]

def run_digest_tiers(state, items, stat, send_all):
    seen = set(state['seen'])
    items = [it for it in items if it['link'] not in seen]
    if not items:
        return 0
    digest = summarize(표시제목, items, prev_summary=state.get('last_summary', ''))
    if len(digest.strip()) < 40 and 'NO_UPDATE' in digest.upper():
        state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
        print('업데이트 없음 - 전송 생략')
        return 0
    now_kst = now_utc() + datetime.timedelta(hours=9)
    lead = [keyword_message(state.get('auto_keywords', []))] if 키워드열거 else None
    for m in build_messages(표시제목, items, digest, stat=stat, lead=lead):
        deliver(_active(state, MASTERS), m)
        time.sleep(0.4)
    if send_all:
        if NORMALS:
            for m in build_messages(표시제목, items, _trim_for_normal(digest), stat=None, lead=None, show_links=True, footer=False):
                deliver(_active(state, NORMALS), m)
                time.sleep(0.4)
        sub_t = _active(state, SUBS)
        if sub_t:
            deliver(sub_t, _single_for_sub(표시제목, digest, now_kst))
    state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
    state['last_summary'] = digest[:3000]
    return len(items)

def _due_slot(now_kst, last_key, slots):
    if now_kst.weekday() >= 5 and (not 주말발송):
        return None
    cur = now_kst.hour * 60 + now_kst.minute
    passed = [hm for hm in slots if hm[0] * 60 + hm[1] <= cur]
    if not passed:
        return None
    h, m = max(passed, key=lambda x: x[0] * 60 + x[1])
    key = now_kst.strftime('%Y-%m-%d-') + f'{h:02d}{m:02d}'
    return key if key != last_key else None

def _due(state, key, hours, default=True):
    last = state.get(key, '')
    if not last:
        return default
    try:
        return now_utc() - datetime.datetime.fromisoformat(last) >= datetime.timedelta(hours=hours) - datetime.timedelta(minutes=10)
    except Exception:
        return default

def breaking_check(new_items):
    if not new_items:
        return None
    sample = []
    for it in new_items[:40]:
        s = it.get('title', '')
        if it.get('seed'):
            s += ' — ' + it['seed'][:80]
        sample.append('- ' + s)
    prompt = 프롬프트_속보 + '\n'.join(sample)
    try:
        resp = gemini(prompt, [보조모델] + 폴백모델목록).strip()
    except Exception as ex:
        print('속보 판단 실패:', ex)
        return None
    if not resp or resp.upper().startswith('NONE') or (len(resp) < 12 and 'NONE' in resp.upper()):
        return None
    return resp

def main():
    if not (TG_TOKEN and GEMINI_KEY and MASTERS):
        print('비밀값(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID_MASTER / GEMINI_API_KEY)이 설정되지 않았어요.')
        return
    _apply_secret_config()
    state = load_state()
    if not 검색어목록:
        today = now_kst.strftime('%Y-%m-%d')
        if state.get('cfg_alerted_day') != today:
            try:
                _post_one(OWNER, '⚠️ SECRET_CONFIG 미설정 — 검색어가 비어 있어 보고를 만들 수 없어요. GitHub Secrets에 SECRET_CONFIG를 넣어주세요.', silent=True)
            except Exception:
                pass
            state['cfg_alerted_day'] = today
        save_state(state)
        print('SECRET_CONFIG 없음 → 실행 종료')
        return
    register_commands(state)
    on_demand, report_now = handle_commands(state, long_poll=True)
    for topic in on_demand:
        try:
            n = run_topic(topic, [topic], [OWNER], state=None, mark_seen=False, prefix='🙋 요청하신 ', regional=False)
            if n == 0:
                deliver([OWNER], f"🙋 '{topic}' 관련 최근 자료를 찾지 못했어요.")
        except Exception as ex:
            print('요청 처리 실패:', ex)
            deliver([OWNER], f"⚠️ '{topic}' 처리 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")
    if report_now:
        try:
            eff = 검색어목록 + state.get('auto_keywords', [])
            n = run_topic(표시제목, eff, [OWNER], state=state, mark_seen=False, gate=False, regional=True)
            if n == 0:
                deliver([OWNER], '지금은 새로 모을 자료가 거의 없어요. 잠시 후 다시 시도해 주세요.')
        except Exception as ex:
            print('즉시 보고 실패:', ex)
            deliver([OWNER], '⚠️ 브리핑 생성 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.')
    if is_paused(state):
        print('정지 기간 - 정기/속보 생략')
        save_state(state)
        return
    now_kst = now_utc() + datetime.timedelta(hours=9)
    force = os.environ.get('FORCE_DIGEST', '') == '1'
    if not force and (not _due(state, 'last_search_ts', 검색간격시간)):
        print('검색 주기 아님 - 대기')
        save_state(state)
        return
    due_all = _due_slot(now_kst, state.get('last_slot_all', ''), 평일슬롯)
    due_master = _due_slot(now_kst, state.get('last_slot_master', ''), 마스터슬롯)
    due_slot = due_all or due_master
    inwin = _in_window(now_kst)
    is_digest = bool(force or due_slot)
    if is_digest:
        sk = due_slot.split('-')[-1] if due_slot else ''
        tag = f'{sk[:2]}:{sk[2:]} 정기 보고' if due_slot else '수동 보고' if force else '보고'
        tag += ' (마스터 전용)' if due_master and (not due_all) and (not force) else ''
        try:
            _post_one(OWNER, f'🟢 작업 시작 · {now_kst.strftime('%m-%d %H:%M')} KST · {tag}', silent=True)
        except Exception:
            pass
    effective_terms = 검색어목록 + state.get('auto_keywords', [])
    try:
        items, stat = fetch_items(effective_terms, regional=True, bodies=is_digest, deep=is_digest, auto_feeds=state.get('auto_sources', []))
    except Exception as ex:
        print('검색 실패(다음 주기 재시도):', ex)
        save_state(state)
        return
    state['last_search_ts'] = now_utc().isoformat()
    if is_digest:
        _maybe_learn_keywords(state, items)
        _maybe_learn_sources(state)
        _maybe_check_sanctions(state)
        _maybe_check_quake(state)
        _maybe_comtrade(state)
    seen = set(state.get('seen', []))
    new_items = [it for it in items if it['link'] not in seen]
    try:
        if is_digest:
            n = run_digest_tiers(state, items, stat, send_all=bool(due_all or force))
            if due_all:
                state['last_slot_all'] = due_all
            if due_master:
                state['last_slot_master'] = due_master
            print(f'정기 보고 전송: {n}건 (all={due_all}, master={due_master}, force={force})')
        elif 속보허용 and new_items:
            alerted = set(state.get('alerted', []))
            pending = [it for it in new_items if it['link'] not in alerted]
            head = breaking_check(pending) if pending else None
            if head and inwin:
                deep_items, deep_stat = fetch_items(effective_terms, regional=True)
                n = run_digest_tiers(state, deep_items, deep_stat, send_all=True)
                print(f'속보 즉시 보고: {n}건')
            elif head and 심야속보:
                msg = f'🌙🚨 <b>심야 속보</b> ({now_kst.strftime('%m-%d %H:%M')} KST)\n' + _fmt(head) + '\n\n자세한 내용은 다음 정기 보고에 정리해 드릴게요.'
                deliver(MASTERS + NORMALS + SUBS, msg, silent=True)
                state['alerted'] = (list(alerted) + [it['link'] for it in pending])[-800:]
                print('심야 속보 무음 전송')
            else:
                print('중대 속보 없음 - 점검만')
        else:
            print('정기 시각 아님 - 점검만')
    except Exception as ex:
        print('전송 처리 실패(다음 주기 재시도):', ex)
    save_state(state)
if __name__ == '__main__':
    main()
