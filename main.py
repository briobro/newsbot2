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
프롬프트_속보 = '아래 새 기사 중 즉시 알릴 만큼 중대하고 새로운 것이 있으면 한 줄 요지와 근거 자료 번호 [n], 없으면 정확히 NONE 만 출력하라. 이전 알림과 같은 사안은 제외.\n[이전 알림]\n{이전}\n\n'
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
    tv = cfg.get('topic_vocab')
    if isinstance(tv, list) and tv:
        g['주제어휘'] = [str(x) for x in tv]
    ic = cfg.get('invite_code')
    if isinstance(ic, str) and ic.strip():
        g['초대코드'] = ic.strip()
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
    for key, var in [('p_expand', '프롬프트_심층'), ('p_breaking', '프롬프트_속보'), ('p_kw', '프롬프트_키워드'), ('p_src', '프롬프트_소스'), ('p_short', '프롬프트_단문')]:
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
평일슬롯 = [(8, 0), (14, 0), (20, 0)]
장문최대페이지 = 3
단문사람체 = True
마스터슬롯 = []
주말발송 = False
공휴일휴무 = True
양력공휴일 = ['0101', '0301', '0505', '0606', '0815', '1003', '1009', '1225']
공휴일자동 = True
_HOLI_CACHE = set()
조용한시간_무음 = True
항상무음 = True
야간시작 = 22
야간끝 = 8
주간시작 = '07:00'
주간종료 = '23:00'
검색간격시간 = 0.5
속보허용 = True
심야속보 = True
보고안내 = '평일(공휴일 제외) 08:00·14:00·20:00 KST · 중대 속보는 즉시'
키워드자동최신화 = True
자동키워드최대 = 20
키워드갱신주기시간 = 24
키워드열거 = False
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
HELP_TEXT = f"🛠 <b>명령 안내</b>\n/보고 — 지금 바로 브리핑 받기\n/요약 ○○ — 특정 주제만 찾아 정리 (예: /요약 ○○ 동향)\n/일시중지 [이틀·사흘·일주일] — 정기 알림 멈춤\n/재개 — 다시 시작\n/검색어 — 자동 추가된 검색어 보기\n/검색어삭제 ○○ — 자동 검색어에서 빼기\n/확인 — 봇 응답·상태 확인\n/수신자 — 받는 사람 명단\n/승인 ID · /거절 ID · /추가 ID · /수신삭제 ID — 수신자 관리\n/도움말 — 이 안내\n(새 사람은 봇에게 '/구독'을 보내면 승인 요청이 와요)\n\n정기 보고: {보고안내}\n※ 한글 명령(/일시중지 등)은 그대로 입력하면 동작해요. 텔레그램 자동완성 메뉴(/)에는 규칙상 영문 별칭(/report·/pause·/resume·/keywords·/help)만 떠요 — 둘 다 됩니다."
TG_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TG_TOKEN_SHORT = os.environ.get('TELEGRAM_TOKEN_SHORT', '').strip()
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
import builtins as _bi

def _redact(text):
    t = str(text)
    for v in (os.environ.get('TELEGRAM_TOKEN', ''), os.environ.get('TELEGRAM_TOKEN_SHORT', ''), os.environ.get('GEMINI_API_KEY', ''), os.environ.get('NAVER_CLIENT_ID', ''), os.environ.get('NAVER_CLIENT_SECRET', ''), os.environ.get('HOLIDAY_KEY', '')):
        if v and len(v) >= 6:
            t = t.replace(v, '***')
    t = re.sub('/bot[0-9]+:[A-Za-z0-9_-]{20,}', '/bot***', t)
    t = re.sub('([?&](?:key|serviceKey|api_key|token)=)[^&\\s]+', '\\1***', t)
    for name in ('TELEGRAM_CHAT_ID_MASTER', 'TELEGRAM_CHAT_ID_NORMAL', 'TELEGRAM_CHAT_ID_SUB'):
        for cid in re.split('[,\\uff0c;\\s]+', os.environ.get(name, '')):
            cid = re.sub('[^\\d-]', '', cid)
            if len(cid) >= 5:
                t = t.replace(cid, '…' + cid[-3:])
    return t

def print(*args, **kwargs):
    _bi.print(*[_redact(a) for a in args], **kwargs)

def _ids(name):
    raw = os.environ.get(name, '')
    out = []
    for c in re.split('[,\\uff0c;\\s]+', raw):
        c = re.sub('[^\\d-]', '', c)
        if re.fullmatch('-?\\d{3,}', c) and c not in out:
            out.append(c)
    return out
MASTERS = _ids('TELEGRAM_CHAT_ID_MASTER')
ENV_NORMALS = _ids('TELEGRAM_CHAT_ID_NORMAL')
NORMALS = list(ENV_NORMALS)
SUBS = _ids('TELEGRAM_CHAT_ID_SUB')
초대코드 = ''
주제어휘 = []
OWNER = MASTERS[0] if MASTERS else ''
TG_CHATS = MASTERS
NAVER_ID = os.environ.get('NAVER_CLIENT_ID', '').strip()
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '').strip()

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def _base_state(d):
    if isinstance(d, list):
        d = {'seen': d}
    return {'seen': d.get('seen', []), 'paused_until': d.get('paused_until', ''), 'last_update_id': d.get('last_update_id', 0), 'user_mutes': d.get('user_mutes', {}), 'holiday_cache': d.get('holiday_cache', {}), 'webhook_cleared': d.get('webhook_cleared', False), 'conflict_alerted_day': d.get('conflict_alerted_day', ''), 'last_summary': d.get('last_summary', ''), 'last_short': d.get('last_short', ''), 'short_log': d.get('short_log', []), 'alert_log': d.get('alert_log', []), 'health': d.get('health', {}), 'dyn_normals': d.get('dyn_normals', []), 'url_cache': d.get('url_cache', {}), 'url_res': d.get('url_res', {}), 'unreach_alerted': d.get('unreach_alerted', []), 'pending_subs': d.get('pending_subs', {}), 'recip_names': d.get('recip_names', {}), 'sub_notified': d.get('sub_notified', {}), 'last_search_ts': d.get('last_search_ts', ''), 'last_digest_ts': d.get('last_digest_ts', ''), 'last_digest_slot': d.get('last_digest_slot', ''), 'last_slot_all': d.get('last_slot_all', ''), 'last_slot_master': d.get('last_slot_master', ''), 'alerted': d.get('alerted', []), 'auto_keywords': d.get('auto_keywords', []), 'auto_kw_updated': d.get('auto_kw_updated', ''), 'auto_sources': d.get('auto_sources', []), 'auto_src_updated': d.get('auto_src_updated', ''), 'sanctions_seen': d.get('sanctions_seen', []), 'sanctions_checked': d.get('sanctions_checked', ''), 'comtrade_checked': d.get('comtrade_checked', ''), 'quake_seen': d.get('quake_seen', []), 'quake_checked': d.get('quake_checked', ''), 'cfg_alerted_day': d.get('cfg_alerted_day', ''), 'bot_cmds_v': d.get('bot_cmds_v', '')}

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

def _post_one(chat, text, silent=False, plain=False, urgent=False, token=None):
    if 항상무음 or (_quiet_now() and (not urgent)):
        silent = True
    url = f'https://api.telegram.org/bot{token or TG_TOKEN}/sendMessage'
    payload = {'chat_id': chat, 'text': text, 'disable_web_page_preview': True, 'disable_notification': silent}
    if not plain:
        payload['parse_mode'] = 'HTML'
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code == 400 and (not plain):
        text2 = re.sub('<[^>]+>', '', text)
        r = requests.post(url, json={'chat_id': chat, 'text': text2, 'disable_web_page_preview': True, 'disable_notification': silent}, timeout=30)
    if r.status_code >= 400:
        try:
            desc = r.json().get('description', '')
        except Exception:
            desc = r.text[:80]
        raise RuntimeError(f'{r.status_code} {desc}')

def register_commands(state):
    if state.get('bot_cmds_v') == '4':
        return
    cmds = [{'command': 'report', 'description': '지금 브리핑 받기'}, {'command': 'summary', 'description': '특정 주제 정리 (예: /summary 환율)'}, {'command': 'pause', 'description': '정기 알림 멈춤'}, {'command': 'resume', 'description': '다시 시작'}, {'command': 'keywords', 'description': '자동 검색어 보기'}, {'command': 'help', 'description': '명령 안내'}]
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/setMyCommands', json={'commands': cmds}, timeout=15)
        state['bot_cmds_v'] = '4'
    except Exception as ex:
        print('명령 메뉴 등록 실패(무시 가능):', ex)

def _quiet_now():
    if not 조용한시간_무음:
        return False
    k = now_utc() + datetime.timedelta(hours=9)
    if k.weekday() >= 5:
        return True
    if 공휴일휴무 and k.strftime('%m%d') in 양력공휴일:
        return True
    if 공휴일휴무 and k.strftime('%Y%m%d') in _HOLI_CACHE:
        return True
    h = k.hour
    if 야간시작 <= 야간끝:
        return 야간시작 <= h < 야간끝
    return h >= 야간시작 or h < 야간끝
_LAST_FAILED, _LAST_OK = ([], [])

def _remember_delivery(failed, okids):
    global _LAST_FAILED, _LAST_OK
    _LAST_FAILED, _LAST_OK = (list(failed), list(okids))

def _notify_fail_once(state, kind, err):
    already = set(state.get('unreach_alerted', []))
    for c in _LAST_OK:
        already.discard(c)
    new_fail = [c for c in _LAST_FAILED if c not in already]
    if new_fail:
        hint = " → 그 사람이 봇에게 'Start'를 안 눌렀거나 ID 오류('/수신자'로 확인). 이 ID는 다시 알리지 않아요." if 'not found' in err or '403' in err else ''
        deliver(MASTERS, f'⚠️ {kind} 전송 실패 {len(new_fail)}명({', '.join(new_fail)}): {err}{hint}', silent=True)
        already |= set(new_fail)
    state['unreach_alerted'] = sorted(already)

def deliver(targets, text, silent=False, plain=False, urgent=False, token=None):
    if len(text) > TG_LIMIT:
        text = text[:TG_LIMIT]
    if 항상무음 or (_quiet_now() and (not urgent)):
        silent = True
    fails, last_err, failed, okids = (0, '', [], [])
    for chat in targets:
        try:
            _post_one(chat, text, silent=silent, plain=plain, urgent=urgent, token=token)
            okids.append(str(chat))
        except Exception as ex:
            fails += 1
            last_err = str(ex)[:120]
            failed.append(str(chat))
            print(f'전송 실패 (받는사람 {chat}): {ex}')
    _remember_delivery(failed, okids)
    return (fails, last_err)

def _ensure_polling(state):
    if state.get('webhook_cleared'):
        return
    try:
        requests.get(f'https://api.telegram.org/bot{TG_TOKEN}/deleteWebhook', timeout=15)
    except Exception:
        pass
    state['webhook_cleared'] = True

def read_commands(state, long_poll=False):
    if not MASTERS:
        return []
    try:
        resp = requests.get(f'https://api.telegram.org/bot{TG_TOKEN}/getUpdates', params={'offset': state['last_update_id'] + 1, 'timeout': 25 if long_poll else 0}, timeout=35)
        if resp.status_code == 409:
            today = (now_utc() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d')
            if state.get('conflict_alerted_day') != today:
                try:
                    _post_one(OWNER, '⚠️ 명령 수신 충돌(409): 같은 봇 토큰을 쓰는 다른 실행(옛 저장소 워크플로 등)이 명령을 가로채고 있어요. 그쪽 워크플로를 끄면 해결돼요.', silent=True)
                except Exception:
                    pass
                state['conflict_alerted_day'] = today
            print('getUpdates 409 충돌 — 다른 인스턴스가 폴링 중')
            return []
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
        frm = msg.get('from', {}) or {}
        name = (frm.get('first_name') or frm.get('username') or '')[:20]
        if chat and text and (msg.get('chat', {}).get('type', 'private') == 'private'):
            out.append((chat, text, name))
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
                p_ = it.get('pub')
                if p_ is not None and getattr(p_, 'tzinfo', None) is None:
                    p_ = p_.replace(tzinfo=datetime.timezone.utc)
                    it['pub'] = p_
                if p_ and p_ < cutoff:
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
        futs = [(j[:-1], ex.submit(j[-1])) for j in jobs]
        for meta, f in futs:
            try:
                res = f.result()
            except Exception:
                res = []
            out.append(tuple(meta) + (res,))
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
        _h(state, 'kw_added', len(added))
        _h(state, 'kw_removed', len(removed))
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
        _h(state, 'src_added', len(added))
        _h(state, 'src_dropped', len(dropped))
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
                    pub = datetime.datetime.fromisoformat(tm.group(2).replace('Z', '+00:00')).astimezone(datetime.timezone.utc)
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
                pub = parsedate_to_datetime(mb.get('created_at', '')).astimezone(datetime.timezone.utc)
            except Exception:
                pub = None
            out.append({'title': txt[:200], 'link': f'https://m.weibo.cn/status/{mid}', 'source': tag, 'pub': pub, 'seed': txt[:300]})
            if len(out) >= limit:
                break
    except Exception as ex:
        global _WB_FAILS
        _WB_FAILS = globals().get('_WB_FAILS', 0) + 1
        if _WB_FAILS <= 1:
            print('웨이보 수집 실패(차단/비JSON) — 이번 실행은 건너뜀:', str(ex)[:60])
    return out
_FEED_STATS = {}

def fetch_items(terms, regional=True, bodies=True, deep=True, auto_feeds=None):
    days = max(1, (시간범위 + 23) // 24)
    cutoff = now_utc() - datetime.timedelta(hours=시간범위)
    하드캡 = 최대기사수 * 2 if 심층검색 and deep else 최대기사수
    jobs = []
    for t in terms:
        jobs.append(('ko', lambda t=t: search_news(t, _lang_of(t), days, 출처당최대)))
    if regional:
        for rss in 추가RSS목록 + list(auto_feeds or []):
            jobs.append(('rss', rss, lambda rss=rss: _rss_items(rss, 출처당최대)))
        for s in 소셜RSS목록:
            jobs.append(('sns', s, lambda s=s: _rss_items(s, 출처당최대)))
        for ch in 텔레채널:
            jobs.append(('sns', f'tg:{ch}', lambda ch=ch: fetch_telegram(ch, 출처당최대)))
        for uid in 웨이보계정:
            jobs.append(('sns', f'wb:{uid}', lambda uid=uid: fetch_weibo(uid=uid, limit=출처당최대)))
        for kw in 웨이보검색어:
            jobs.append(('sns', f'wbkw:{kw}', lambda kw=kw: fetch_weibo(keyword=kw, limit=출처당최대)))
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
    for res in _parallel(jobs):
        bucket, lst = (res[0], res[-1])
        if len(res) == 3:
            _FEED_STATS[res[1]] = len(lst)
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
            ex_sources = [r[-1] for r in _parallel(ex_jobs)]
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

def _coverage_tags(items):

    def key(t):
        return re.sub('[^0-9A-Za-z가-힣一-鿿]', '', t or '')

    def sim(a, b):
        if len(a) < 6 or len(b) < 6:
            return 0.0
        A = {a[i:i + 2] for i in range(len(a) - 1)}
        B = {b[i:i + 2] for i in range(len(b) - 1)}
        return len(A & B) / max(1, len(A | B))
    keys = [key(it.get('title', '')) for it in items]
    cluster = [-1] * len(items)
    n = 0
    for i in range(len(items)):
        if cluster[i] != -1:
            continue
        cluster[i] = n
        for j in range(i + 1, len(items)):
            if cluster[j] == -1 and sim(keys[i], keys[j]) >= 0.5:
                cluster[j] = n
        n += 1
    outlets, ko_main = ({}, {})
    for it, c in zip(items, cluster):
        outlets.setdefault(c, set()).add((it.get('source') or _domain(it.get('link', '')) or '?').lower())
        g, _ = _provenance(it)
        if g == 'main' and re.search('[가-힣]', it.get('title', '')):
            ko_main[c] = True
    for it, c in zip(items, cluster):
        cnt = len(outlets.get(c, ()))
        it['_cov'] = (cnt, ko_main.get(c, False))
    return items

def _cov_label(it):
    cnt, ko = it.get('_cov', (0, False))
    if not cnt:
        return ''
    lab = f'보도 {cnt}곳'
    if not ko:
        lab += '·국내 미보도'
    if cnt <= 2 and (not ko):
        lab = '★선점 ' + lab
    return f' ({lab})'

def summarize(topic, items, prev_summary=''):
    items = _coverage_tags(items)
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
            tag = (f' ({it['_plabel']})' if it.get('_plabel') else '') + _cov_label(it)
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

def build_messages(topic, items, digest, stat=None, prefix='', lead=None, show_links=True, footer=True, max_pages=None, show_head=True):
    now_kst = now_utc() + datetime.timedelta(hours=9)
    status = status_line(stat) + '\n' if stat is not None else ''
    head = f'{status}{prefix}📰 <b>[{html.escape(topic)}] {now_kst.strftime('%m-%d %H:%M')} KST</b> (자료 {len(items)}건)\n\n' if show_head else prefix or ''

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
    linkblock = '\n\n📎 <b>자료</b>\n' + '\n'.join(links) if links else ''
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
    if max_pages and len(chunks) > max_pages:
        if show_links and idx > 0:
            body_chunks = []
            for p in parts[1:]:
                body_chunks.extend(_chunk(p, TG_LIMIT - 16))
            chunks = [head.rstrip() + '\n\n' + body_chunks[0]] + body_chunks[1:] if body_chunks else chunks
        chunks = chunks[:max_pages]
    n = len(chunks)
    if n > 1:
        chunks = [f'({i + 1}/{n}) ' + c for i, c in enumerate(chunks)]
    return chunks

def parse_command(text):
    raw = text.strip()
    t = raw.lstrip('/').replace(' ', '').lower()
    if t.startswith('구독') or t.startswith('subscribe') or t == 'start':
        arg = raw
        for w in ['/', '구독', 'subscribe', 'start', '신청']:
            arg = arg.replace(w, ' ')
        return ('subscribe', arg.strip() or None)
    if t.startswith('승인') or t.startswith('approve'):
        ids = re.findall('-?\\d{3,}', raw)
        return ('approve', ids or None)
    if t.startswith('거절') or t.startswith('reject'):
        ids = re.findall('-?\\d{3,}', raw)
        return ('reject', ids or None)
    if t.startswith('수신삭제') or t.startswith('수신자삭제') or t.startswith('removeuser'):
        ids = re.findall('-?\\d{3,}', raw)
        return ('rm_user', ids or None)
    if t.startswith('수신자') or t.startswith('명단') or t.startswith('members'):
        return ('members', None)
    if t.startswith('추가') or t.startswith('adduser'):
        ids = re.findall('-?\\d{3,}', raw)
        return ('add_user', ids or None)
    if any((k in t for k in ['도움말', '사용법', '명령어', 'help', 'commands'])):
        return ('help', None)
    if t in ('확인', '상태', '살아있니', '핑', 'status', 'ping', 'check', 'alive') or t.startswith('확인') or t.startswith('상태'):
        return ('status', None)
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

def _sync_recipients(state):
    dyn = [str(x) for x in state.get('dyn_normals', [])]
    merged = list(dict.fromkeys(ENV_NORMALS + dyn))
    NORMALS[:] = [c for c in merged if c not in MASTERS]

def _add_recipient(state, chat, name=''):
    dyn = [str(x) for x in state.get('dyn_normals', [])]
    if str(chat) not in dyn:
        dyn.append(str(chat))
    state['dyn_normals'] = dyn
    names = dict(state.get('recip_names', {}))
    names[str(chat)] = name or names.get(str(chat), '')
    state['recip_names'] = names
    state.setdefault('pending_subs', {}).pop(str(chat), None)
    _sync_recipients(state)

def _check_chat(chat):
    try:
        r = requests.get(f'https://api.telegram.org/bot{TG_TOKEN}/getChat', params={'chat_id': chat}, timeout=10)
        j = r.json()
        if j.get('ok'):
            res = j.get('result', {})
            nm = res.get('first_name') or res.get('title') or res.get('username') or ''
            return (True, nm)
        return (False, j.get('description', ''))
    except Exception as ex:
        return (False, str(ex)[:60])

def _members_text(state):
    names = state.get('recip_names', {})

    def fmt(c):
        ok, info = _check_chat(c)
        if ok:
            return f'✅ {c}' + (f'({info})' if info else '')
        why = 'Start 안 누름 또는 ID 오류' if 'not found' in info else info
        return f'❌ {c} — {why}'
    lines = [f'👑 마스터: {', '.join((fmt(c) for c in MASTERS)) or '-'}', f'👤 노멀(기본): {', '.join((fmt(c) for c in ENV_NORMALS)) or '-'}', f'👤 노멀(승인 추가): {', '.join((fmt(c) for c in state.get('dyn_normals', []))) or '-'}', f'📨 구독자(기본): {', '.join((fmt(c) for c in SUBS)) or '-'}']
    pend = state.get('pending_subs', {})
    if pend:
        lines.append('⏳ 승인 대기: ' + ', '.join((f'{c}({n})' if n else c for c, n in pend.items())))
    lines.append('명령: /승인 ID · /거절 ID · /추가 ID · /수신삭제 ID')
    return '\n'.join(lines)

def _status_text(state, is_master):
    k = now_utc() + datetime.timedelta(hours=9)
    base = f'✅ 봇 응답 확인 · {k.strftime('%m-%d %H:%M')} KST'
    if not is_master:
        return base + "\n명령은 '/일시중지'·'/재개'만 쓸 수 있어요."
    nxt = [f'{h:02d}:{m:02d}' for h, m in 평일슬롯 if h * 60 + m > k.hour * 60 + k.minute]
    lines = [base, f'설정: 검색어 {len(검색어목록)}개(+자동 {len(state.get('auto_keywords', []))}) · 피드 {len(추가RSS목록) + len(소셜RSS목록) + len(state.get('auto_sources', []))} · 텔레채널 {len(텔레채널)} · 웨이보 {len(웨이보계정) + len(웨이보검색어)}', f'수신: 마스터 {len(MASTERS)} · 노멀 {len(NORMALS)} · 구독 {len(SUBS)}', f'마지막 보고 슬롯: {state.get('last_slot_all') or '-'} / 마스터 {state.get('last_slot_master') or '-'}', f'다음 슬롯(오늘): {(', '.join(nxt) if nxt else '없음(내일 08:00)')}', f'정지: {('예 (' + state.get('paused_until', '')[:16] + ')' if is_paused(state) else '아니오')} · 조용한시간: {('예' if _quiet_now() else '아니오')} · 공휴일: {('예' if _is_holiday(state) else '아니오')}', f'분석 엔진: {_BRIEF_ENGINE or '-'}']
    return '\n'.join(lines)

def handle_commands(state, long_poll=False):
    on_demand = []
    report_now = False
    for chat, text, name in read_commands(state, long_poll=long_poll):
        kind, arg = parse_command(text)
        known = set(MASTERS) | set(NORMALS) | set(SUBS)
        if chat not in known:
            if kind == 'subscribe':
                if 초대코드 and arg and (arg == 초대코드):
                    _add_recipient(state, chat, name)
                    deliver([chat], "✅ 구독이 승인됐어요. 이제 요약 보고를 받게 돼요. ('/일시중지'·'/재개' 사용 가능)")
                    deliver(MASTERS, f'🙋 초대코드로 자동 승인: {name or '-'} ({chat})', silent=True)
                else:
                    state.setdefault('pending_subs', {})[chat] = name
                    deliver([chat], '🙋 구독 요청을 전달했어요. 관리자가 승인하면 알려드릴게요.')
                    today = (now_utc() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d')
                    if state.setdefault('sub_notified', {}).get(chat) != today:
                        deliver(MASTERS, f'🙋 구독 요청: {name or '-'} ({chat})\n승인: /승인 {chat}  · 거절: /거절 {chat}', silent=True)
                        state['sub_notified'][chat] = today
            continue
        if kind == 'status':
            deliver([chat], _status_text(state, chat in set(MASTERS)))
            continue
        if kind == 'subscribe':
            deliver([chat], '이미 수신 중이에요.' if chat not in set(MASTERS) else HELP_TEXT)
            continue
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
        if kind in ('approve', 'add_user'):
            targets = arg or list(state.get('pending_subs', {}).keys())
            if not targets:
                deliver([chat], "승인 대기 중인 요청이 없어요. '/추가 ID'로 직접 추가할 수도 있어요.")
                continue
            done = []
            for cid in targets:
                nm = state.get('pending_subs', {}).get(cid, '')
                _add_recipient(state, cid, nm)
                deliver([cid], "✅ 구독이 승인됐어요. 이제 요약 보고를 받게 돼요. ('/일시중지'·'/재개' 사용 가능)")
                done.append(cid)
            deliver([chat], f'✅ 등록 완료: {', '.join(done)}\n\n' + _members_text(state))
        elif kind == 'reject':
            targets = arg or list(state.get('pending_subs', {}).keys())
            for cid in targets:
                state.get('pending_subs', {}).pop(cid, None)
            deliver([chat], f'거절 처리: {', '.join(targets) or '-'}')
        elif kind == 'rm_user':
            if not arg:
                deliver([chat], '예: /수신삭제 6841230577')
                continue
            dyn = [x for x in state.get('dyn_normals', []) if x not in arg]
            state['dyn_normals'] = dyn
            _sync_recipients(state)
            fixed = [x for x in arg if x in ENV_NORMALS or x in SUBS]
            msg = f'삭제: {', '.join(arg)}'
            if fixed:
                msg += f'\n※ {', '.join(fixed)} 는 GitHub Secret에 고정된 사람이라 여기선 못 빼요.'
            deliver([chat], msg + '\n\n' + _members_text(state))
        elif kind == 'members':
            deliver([chat], _members_text(state))
        elif kind == 'help':
            deliver([OWNER], HELP_TEXT)
        elif kind == 'resume':
            state['paused_until'] = ''
            deliver([OWNER], '▶️ 다시 시작할게요. 정해진 시간에 알림을 보낼게요.')
        elif kind == 'report_now':
            deliver([OWNER], '📰 지금 브리핑을 준비할게요… 잠시만요(1~2분).')
            report_now = True
        elif kind == 'kwlist':
            auto = state.get('auto_keywords', [])
            parts = [f'🔎 <b>고정 검색어 {len(검색어목록)}개</b>\n' + ', '.join(검색어목록)]
            if 중국어검색어목록 or 러시아어검색어목록 or 일본어검색어목록:
                parts.append(f'외국어: 중 {len(중국어검색어목록)} · 러 {len(러시아어검색어목록)} · 일 {len(일본어검색어목록)}')
            parts.append(f'<b>자동 추가 {len(auto)}개</b>\n' + ', '.join(auto) if auto else '자동 추가: 아직 없음')
            parts.append("'/검색어삭제 ○○'로 자동분만 뺄 수 있어요.")
            for m in _chunk('\n\n'.join(parts), TG_LIMIT - 16):
                deliver([OWNER], m)
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

def _is_holiday(state=None):
    global _HOLI_CACHE
    if not 공휴일휴무:
        return False
    k = now_utc() + datetime.timedelta(hours=9)
    if k.strftime('%m%d') in 양력공휴일:
        return True
    if not (공휴일자동 and state is not None):
        return False
    key = os.environ.get('HOLIDAY_KEY', '').strip()
    if not key:
        return False
    ym = k.strftime('%Y%m')
    cache = state.get('holiday_cache', {})
    if cache.get('ym') != ym:
        days = []
        try:
            r = requests.get('http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo', params={'serviceKey': key, 'solYear': k.strftime('%Y'), 'solMonth': k.strftime('%m'), 'numOfRows': 50, '_type': 'json'}, timeout=20)
            items = (((r.json().get('response', {}) or {}).get('body', {}) or {}).get('items', {}) or {}).get('item', [])
            if isinstance(items, dict):
                items = [items]
            for it in items:
                if str(it.get('isHoliday', '')).upper() == 'Y':
                    days.append(str(it.get('locdate', '')))
        except Exception as ex:
            print('공휴일 조회 실패(양력만 적용):', str(ex)[:80])
            return False
        cache = {'ym': ym, 'days': days}
        state['holiday_cache'] = cache
    _HOLI_CACHE = set(cache.get('days', []))
    return k.strftime('%Y%m%d') in _HOLI_CACHE

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
프롬프트_단문 = "아래 [자료]에서 핵심 소식을 우선순위대로 5~8줄로 요약하라. 각 줄: '주체, 사건 핵심, 향후 전망 : ○○ 확인 필요' 형태. 자세한 기사가 필요한 줄 끝에는 자료 번호를 [n] 형태로 붙여라. 순수 텍스트만(굵게·링크 태그 금지). [이전 단문]과 중복 금지.\n\n[이전 단문]\n{이전}\n\n[자료]\n{목록}"

def _is_korean_item(it):
    return bool(re.search('[\\uac00-\\ud7a3]', it.get('title', '')))

def make_brief(prompt):
    return gemini(prompt, [요약모델, 보조모델] + 폴백모델목록)

def _resolve(url, state=None):
    if not url:
        return url
    cache = state.get('url_res', {}) if state is not None else {}
    if url in cache:
        return cache[url]
    out = url
    try:
        if 'bing.com/news/apiclick' in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            real = (q.get('url') or [''])[0]
            if real.startswith('http'):
                out = real
        elif 'news.google.com' in url:
            try:
                from googlenewsdecoder import gnewsdecoder
                r = gnewsdecoder(url, interval=1)
                if isinstance(r, dict) and r.get('status') and str(r.get('decoded_url', '')).startswith('http'):
                    out = r['decoded_url']
            except Exception as ex:
                print('구글뉴스 링크 해석 실패:', str(ex)[:60])
    except Exception:
        pass
    if state is not None:
        cache[url] = out
        if len(cache) > 400:
            for k in list(cache)[:150]:
                cache.pop(k, None)
        state['url_res'] = cache
    return out
_URL_CACHE = {}
_SHORTENERS = ('https://tinyurl.com/api-create.php?url=', 'https://is.gd/create.php?format=simple&url=', 'https://v.gd/create.php?format=simple&url=', 'https://da.gd/s?url=')
_DEAD_SHORTENERS = set()

def _shorten(url, state=None):
    if not url:
        return url
    url = _resolve(url, state)
    if len(url) <= 15:
        return url
    cache = state.get('url_cache', {}) if state is not None else _URL_CACHE
    if url in cache:
        return cache[url]
    out = url
    for api in _SHORTENERS:
        if api in _DEAD_SHORTENERS:
            continue
        try:
            r = requests.get(api + urllib.parse.quote(url, safe=''), timeout=8)
            t = (r.text or '').strip()
            if r.status_code == 200 and t.startswith('http') and (len(t) < 60) and (' ' not in t):
                out = t
                break
            _DEAD_SHORTENERS.add(api)
        except Exception:
            _DEAD_SHORTENERS.add(api)
            continue
    out = re.sub('^https?://(www\\.)?', '', out)
    cache[url] = out
    if state is not None:
        if len(cache) > 300:
            for k in list(cache)[:100]:
                cache.pop(k, None)
        state['url_cache'] = cache
    return out
import random as _rnd

def _humanize(text):
    url_re = re.compile('(\\S+\\.[a-z]{2,}/\\S*|https?://\\S+)')
    tail_forms = ['{x} 피료해보임', '{x}해야할듯', '{x} 필요해보임', '{x}필요', '{x} 필여', '{x} 필요함', '{x} 좀 해봐야', '{x}해봐야함', '{x} 필요할듯', '{x} 요망', '{x}해야하나', '{x} 피료', '{x}봐야할듯', '{x} 필요 있음']
    typo = {'확인': ['확이', '학인', '확인'], '파악': ['파학', '파악', '파악'], '추적': ['추젘', '추적', '추적'], '점검': ['점겅', '점검'], '검토': ['검토우', '검토'], '분석': ['분서', '분석'], '취재': ['취제', '취재'], '확보': ['확뽀', '확보'], '체크': ['체쿠', '체크'], '규모': ['규모', '규뫄'], '여부': ['여부', '여붜'], '경로': ['경로', '경뢰'], '내용': ['내용', '내욤'], '관계': ['관계', '관게']}
    marks = ['•'] * 24 + ['○', '●', '■']
    out_lines = []
    for line in text.splitlines():
        if not line.strip():
            out_lines.append(line)
            continue
        m = url_re.search(line)
        body, tail = (line[:m.start()], line[m.start():]) if m else (line, '')
        body = re.sub('^[\\-\\*\\u2022\\u25aa\\u25cf\\u30fb·▪•●■◆▶>]+\\s*', '', body).strip()
        p_drop = _rnd.choice([0.15, 0.25, 0.35])
        om = re.search('\\(원문:.*?\\)', body)
        orig = om.group(0) if om else ''
        if orig:
            body = body.replace(orig, '\x00ORIG\x00')
        body = re.sub('(?<=[가-힣0-9%)])[ ]+(?=[가-힣0-9(])', lambda m: '' if _rnd.random() < p_drop else m.group(0), body)
        if _rnd.random() < 0.25:
            body = re.sub(',[ ]+', lambda m: ',' if _rnd.random() < 0.4 else m.group(0), body)
        if _rnd.random() < 0.15:
            body = body.replace(', ', ',  ', 1)
        r = _rnd.random()
        if r < 0.2:
            body += '.'
        elif r < 0.28:
            body += '..'
        rr = _rnd.random()
        if rr < 0.05:
            mark = ''
        else:
            mark = _rnd.choice(marks) + ('' if _rnd.random() < 0.15 else ' ')
        if orig:
            body = body.replace('\x00ORIG\x00', orig)
        um2 = re.search('\\([^()]*미확인\\)', body)
        if um2 and _rnd.random() < 0.5:
            seg = um2.group(0)
            seg2 = _rnd.choice([seg.replace('미확인', '미학인'), seg.replace('미확인', '미확이'), seg.replace('등은', '등은'), seg.replace(', ', ','), seg.replace('미확인', '미확인됨')])
            body = body.replace(seg, seg2, 1)
        glue = _rnd.choice([' ', '  ', '   ', '\n', '\n', ' ', '  ']) if tail else ''
        out_lines.append((mark + body + glue + tail).rstrip())
    text = '\n'.join(out_lines)
    text = re.sub('\\n\\n', lambda m: '\n\n\n' if _rnd.random() < 0.25 else '\n\n', text)
    return text
_SHORT_REASON = ''
_OUTLET_NAMES = set()

def _core(line):
    x = re.sub('\\[\\d+\\]|https?://\\S+|[\\w.-]+\\.[a-z]{2,}/\\S*|\\([^)]*\\)', '', line)
    x = re.sub('^[\\s•○●■▪·\\-]+', '', x)
    x = re.sub('^(?:[\\w.-]+\\.[a-z]{2,}|[^,]{1,12}(?:뉴스|일보|경제|신문|방송|TV|투데이|타임스|저널|위크|미디어|통신))\\s*,\\s*', '', x)
    for nm in _OUTLET_NAMES:
        if nm and x.startswith(nm):
            x = x[len(nm):].lstrip(' ,')
    segs = [t for t in x.split(',') if t.strip()]
    x = ','.join(segs[:2])
    return re.sub('[^0-9A-Za-z가-힣一-鿿]', '', x)

def _stem_overlap(a, b):

    def st(x):
        x = re.sub('\\[\\d+\\]|https?://\\S+|[\\w.-]+\\.[a-z]{2,}/\\S*|\\([^)]*\\)', '', x)
        toks = {w[:2] for w in re.findall('[가-힣]{2,}', x)} | set(re.findall('\\d+(?:\\.\\d+)?', x))
        toks -= {'향후', '전망', '가능', '확인', '미확', '관련', '대한', '위한', '통해', '및', '등'}
        return toks
    A, B = (st(a), st(b))
    if min(len(A), len(B)) < 4:
        return 0.0
    return len(A & B) / min(len(A), len(B))

def _core_sim(a, b):
    a0, b0 = (a, b)
    a, b = (_core(a), _core(b))
    if len(a) < 6 or len(b) < 6:
        return 0.0
    A = {a[i:i + 2] for i in range(len(a) - 1)}
    B = {b[i:i + 2] for i in range(len(b) - 1)}
    sim = len(A & B) / max(1, len(A | B))
    tok = lambda x: set(re.findall("'[^']{2,}'|\\d+(?:\\.\\d+)?(?:억|만|천|배|톤|대|척|명|%)", x))
    if tok(a0) & tok(b0) and sim >= 0.25:
        return 1.0
    return sim
_RU_LOCAL_DOMAINS = ('primamedia.ru', 'dvnovosti.ru', 'newsvl.ru', 'vostokmedia.com', 'khabarovsk', 'amur', 'vl.ru', 'dvhab', 'primorye')

def _is_local_ru(it):
    t = it.get('title', '') or ''
    d = _domain(it.get('link', ''))
    src = (it.get('source', '') or '').lower()
    return bool(re.search('[\\u0400-\\u04ff]', t)) or any((k in d for k in _RU_LOCAL_DOMAINS)) or src.startswith('tg:')

def _link_text(link, state=None):
    u = _resolve(link, state)
    try:
        pr = urllib.parse.urlparse(u)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(pr.query, keep_blank_values=True) if not re.match('^(ref|utm_\\w+|fbclid|gclid|source|from|cid|oc)$', k, re.I)]
        u = urllib.parse.urlunparse(pr._replace(query=urllib.parse.urlencode(q), fragment=''))
    except Exception:
        pass
    disp = re.sub('^https?://(www\\.)?', '', u).rstrip('?&/')
    if len(disp) > 45:
        return _shorten(u, state)
    return disp

def build_short(items, state):
    items = _coverage_tags(items)

    def _micro(it):
        d = _domain(it.get('link', ''))
        src = (it.get('source', '') or '').lower()
        primary = any((d.endswith(pd) for pd in _PRIMARY_DOMAINS)) or any((k in src for k in _PRIMARY_SRC_HINTS))
        cnt, ko = it.get('_cov', (9, True))
        korean_main = bool(re.search('[가-힣]', it.get('title', ''))) and (not primary)
        return bool(it.get('social')) or _is_local_ru(it) or primary or (not korean_main and cnt <= 2 and (not ko))

    def _rank(it):
        cnt, ko = it.get('_cov', (9, True))
        return (0 if _micro(it) else 1, 0 if cnt <= 2 and (not ko) else 1, 0 if _is_korean_item(it) else 1)
    ordered = sorted(items, key=_rank)[:200]
    lst = []
    for i, it in enumerate(ordered, 1):
        tag = '(한)' if _is_korean_item(it) else ''
        if _is_local_ru(it):
            tag += '(러시아 현지)'
        if _micro(it):
            tag += '(미시)'
        snip = (it.get('seed') or it.get('body') or '')[:70].replace('\n', ' ')
        snip = f' — {snip}' if snip and snip not in it.get('title', '') else ''
        lst.append(f'[{i}] {it.get('title', '')}{snip} {tag}{_cov_label(it)} ({it.get('source', '')})')
    hist = state.get('short_log', [])[-10:]
    prev = '\n---\n'.join(hist) if hist else '(없음)'
    alerts = '\n'.join(state.get('alert_log', [])[-10:])
    if alerts:
        prev += '\n[이미 보낸 긴급 알림]\n' + alerts
    base_prompt = 프롬프트_단문.replace('{이전}', prev).replace('{목록}', '\n'.join(lst))
    out = make_brief(base_prompt).strip()
    global _SHORT_REASON
    _SHORT_REASON = ''
    if 'NO_UPDATE' in out.upper() and len(out) < 40:
        _SHORT_REASON = '새 소식 없음(NO_UPDATE)'
        return ''
    try:
        lines_now = [l for l in out.splitlines() if l.strip()]

        def _ref_item(l):
            m = re.search('\\[(\\d+)', l)
            return ordered[int(m.group(1)) - 1] if m and 0 < int(m.group(1)) <= len(ordered) else None
        local_n = sum((1 for l in lines_now if _ref_item(l) is not None and _is_local_ru(_ref_item(l))))
        need = max(0, int(len(lines_now) * 0.2 + 0.999) - local_n)
        refs = {int(x) for x in re.findall('\\[(\\d+)', out)}
        local_pool = [l for i, l in enumerate(lst, 1) if i not in refs and _is_local_ru(ordered[i - 1])]
        if need > 0 and len(local_pool) >= 2:
            q_prompt = 프롬프트_단문.replace('{이전}', prev).replace('{목록}', '\n'.join(local_pool)) + f"\n\n[이미 작성한 줄 — 반복 금지]\n{out}\n\n위 자료는 전부 '러시아 현지' 것이다. 여기서 현지 특파원이 발로 확인할 수 있는 '현장 확인형' 항목만 {need}~{need + 3}줄 추가하라(요구사항은 '어디 가서 누구에게 무엇을 확인'처럼 구체적으로). 새로 쓸 게 없으면 정확히 NONE."
            more = make_brief(q_prompt).strip()
            if more and (not more.upper().startswith('NONE')) and (len(more) > 30):
                out = out + '\n' + more
    except Exception as ex:
        print('현장형 쿼터 처리 실패:', str(ex)[:80])
    lines_now = [l for l in out.splitlines() if l.strip()]
    if len(lines_now) >= 4:
        try:
            merged = make_brief("아래 줄들 중 '같은 사건'을 다룬 줄은 하나로 합쳐라(정보가 가장 많은 한 줄만 남기고, 매체가 다르다는 이유로 따로 두지 마라). 합칠 때 [n] 번호는 남긴 줄의 것을 유지. 새 내용 추가·문장 수정 금지, 순서 유지. 결과 줄들만 출력.\n\n" + '\n'.join(lines_now)).strip()
            if merged and len([l for l in merged.splitlines() if l.strip()]) <= len(lines_now):
                out = merged
        except Exception as ex:
            print('병합 패스 실패:', str(ex)[:60])
    try:
        ls = [l for l in out.splitlines() if l.strip()]

        def _ref(l):
            m = re.search('\\[(\\d+)\\]', l)
            return ordered[int(m.group(1)) - 1] if m and 0 < int(m.group(1)) <= len(ordered) else None
        micro_ls = [l for l in ls if _ref(l) is not None and _micro(_ref(l))]
        main_ls = [l for l in ls if l not in micro_ls]
        if micro_ls and len(main_ls) > max(3, int(len(ls) * 0.4)):
            keep_main = set(main_ls[:max(3, int(len(ls) * 0.4))])
            out = '\n'.join((l for l in ls if l in micro_ls or l in keep_main))
    except Exception:
        pass
    uniq = []
    for l in out.splitlines():
        if l.strip() and any((_core_sim(l, u) >= 0.6 for u in uniq)):
            continue
        uniq.append(l)
    out = '\n'.join(uniq)
    prev_lines = [l for h in hist for l in h.splitlines() if len(l) > 15]
    kept = []
    for line in out.splitlines():
        if len(line.strip()) < 15:
            kept.append(line)
            continue
        dup = any((_core_sim(line, pl) >= 0.7 for pl in prev_lines))
        if dup and '갱신' not in line and ('급변' not in line):
            continue
        kept.append(line)
    out = '\n'.join(kept).strip()
    out = re.sub('\\s*\\((갱신|급변|update)\\)', '', out)
    if len(re.findall('[가-힣]', out)) < 12:
        _SHORT_REASON = '전부 이전 단문과 중복(진전 없음)'
        return ''

    def _key(t):
        return re.sub('[^0-9A-Za-z가-힣一-鿿]', '', t or '')

    def _bigram_sim(a, b):
        a, b = (_key(a), _key(b))
        if len(a) < 4 or len(b) < 4:
            return 0.0
        A = {a[i:i + 2] for i in range(len(a) - 1)}
        B = {b[i:i + 2] for i in range(len(b) - 1)}
        return len(A & B) / max(1, len(A | B))

    def _direct(u):
        return u and (not ('news.google.com' in u or 'bing.com' in u))

    def _is_micro(it):
        cnt, ko = it.get('_cov', (9, True))
        if _is_local_ru(it) or bool(it.get('social')):
            return True
        d = _domain(it.get('link', ''))
        src = (it.get('source', '') or '').lower()
        primary = any((d.endswith(pd) for pd in _PRIMARY_DOMAINS)) or any((k in src for k in _PRIMARY_SRC_HINTS))
        if primary:
            return True
        korean_main = bool(re.search('[가-힣]', it.get('title', ''))) and (not primary)
        if korean_main:
            return False
        return cnt <= 2 and (not ko)

    def _rep(m):
        try:
            it = ordered[int(m.group(1)) - 1]
            if not _is_micro(it):
                return ''
            line_txt = out[max(0, m.start() - 160):m.start()]
            tt = it.get('title', '') or ''
            if re.search('[가-힣]', tt):
                tks = {w for w in re.findall('[가-힣]{2,}|\\d+', tt)}
                if tks and (not any((w in line_txt for w in tks))):
                    return ''
            link = it.get('link', '')
            if not _direct(link):
                best = None
                for o in ordered:
                    if _direct(o.get('link', '')) and _bigram_sim(o.get('title', ''), it.get('title', '')) >= 0.55:
                        best = o
                        break
                if best:
                    link = best['link']
            extra = ''
            t = it.get('title', '') or ''
            if not re.search('[가-힣]', t) and re.search('[\\u0400-\\u04ff\\u4e00-\\u9fff\\u3040-\\u30ff]', t):
                extra = ' (원문: ' + t[:60].strip() + ')'
            return extra + ' ' + _link_text(link, state)
        except Exception:
            return ''

    def _rep_group(m):
        nums = [int(x) for x in re.findall('\\d+', m.group(1))]
        cands = [ordered[n - 1] for n in nums if 0 < n <= len(ordered)]
        if not cands:
            return ''
        pick = next((c for c in cands if _is_korean_item(c)), cands[0])
        return ' [' + str(ordered.index(pick) + 1) + ']'
    _CIRC = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'

    def _circ_end(m):
        return f' [{_CIRC.index(m.group(1)) + 1}]'
    out = re.sub('\\s*([①-⑳])\\s*$', _circ_end, out, flags=re.M)
    out = re.sub('^([\\s•○●■▪·\\-]*)[①-⑳㉑-㉟⑴-⒇]\\s*', '\\1', out, flags=re.M)
    out = re.sub('^([\\s•○●■▪·\\-]*)\\d{1,2}[.)]\\s+', '\\1', out, flags=re.M)
    out = re.sub('\\[(\\d+(?:\\s*[,、·/]\\s*\\d+)+)\\]', _rep_group, out)
    out = re.sub('[ \\t]*\\[(\\d+)\\]', _rep, out)
    out = re.sub('\\[[\\d,、·/\\s]*\\]', '', out)
    out = out.replace('★', '')
    out = re.sub('\\(\\s*(러시아\\s*현지|한|보도\\s*\\d+곳[^)]*|국내\\s*미보도|선점[^)]*)\\s*\\)', '', out)
    global _OUTLET_NAMES
    _OUTLET_NAMES = {str(it.get('source', '')).strip() for it in items if it.get('source')} | {_domain(it.get('link', '')) for it in items}
    _OUTLET_NAMES = {n for n in _OUTLET_NAMES if n and len(n) >= 2}

    def _strip_outlet(l):
        x = re.sub('^([\\s•○●■▪·\\-]*)', '', l)
        lead = l[:len(l) - len(x)]
        x = re.sub('^(?:[\\w.-]+\\.[a-z]{2,}|[^,]{1,14}(?:뉴스|일보|경제|신문|방송|TV|투데이|타임스|저널|위크|미디어|통신|채널A|KBS|MBC|SBS|YTN|JTBC))\\s*,\\s*', '', x)
        for nm in sorted(_OUTLET_NAMES, key=len, reverse=True):
            if x.startswith(nm + ','):
                x = x[len(nm) + 1:].lstrip()
                break
        return lead + x
    out = '\n'.join((_strip_outlet(l) for l in out.splitlines()))

    def _drop_instr(l):
        um = re.search('(?:https?://\\S+|(?<![\\w/])[\\w.-]+\\.[a-z]{2,}/\\S+)', l)
        body, tail = (l[:um.start()], l[um.start():]) if um else (l, '')
        parens = re.findall('\\([^()]*미확인[^()]*\\)', body)
        core = re.sub('\\([^()]*미확인[^()]*\\)', '\x00P\x00', body)
        core = re.sub('\\([^()]*(?:필요|봐야|체크|요망|확인)[^()]*\\)', '', core)
        segs = [t for t in core.split(',')]
        segs = [t for t in segs if not re.search('(확인|분석|평가|점검|파악|추적|검토|조사)\\s*(이|을|가)?\\s*필요|봐야할듯|봐야|체크해야|필요할듯|필요함', t)]
        core = ','.join(segs)
        kept_ph = core.count('\x00P\x00')
        for p_ in parens[:kept_ph]:
            core = core.replace('\x00P\x00', p_, 1)
        for p_ in parens[kept_ph:]:
            core = core.rstrip(' ,.') + p_
        core = core.replace('\x00P\x00', '')
        return (core.rstrip(' ,.') + (' ' + tail if tail else '')).rstrip()
    out = '\n'.join((_drop_instr(l) for l in out.splitlines()))
    cleaned = []
    for l in out.splitlines():
        um = re.search('(?:https?://\\S+|(?<![\\w/])[\\w.-]+\\.[a-z]{2,}/\\S+)', l)
        body, tail = (l[:um.start()], l[um.start():]) if um else (l, '')
        parts = re.split('\\s*[:：]\\s*', body, maxsplit=1)
        if len(parts) == 2 and re.search('(필요|확인|파악|추적|점검|봐야|체크|요망|취재|분석)', parts[1]):
            body = parts[0].rstrip(' ,.-')
        body = re.sub('\\s+-\\s+[^-(]*?(필요|확인|파악|추적|점검|봐야|체크|요망)[^-(]*$', '', body)
        cleaned.append((body.rstrip() + (' ' + tail if tail else '')).rstrip())
    out = '\n'.join(cleaned)
    vocab = {v.strip().lower() for v in 주제어휘 if v.strip()}
    if not vocab:
        vocab = {w for kw in 검색어목록 or [] for w in re.split('\\s+', kw) if len(w) >= 2}
    kept2 = []
    for l in out.splitlines():
        if not l.strip():
            continue
        low = l.lower()
        if re.search('연관성[^\\n]{0,12}(불확실|미상|불명|낮|없)', l):
            continue
        fact = re.split('향후|전망|가능성|우려', low, maxsplit=1)[0]
        if not any((v in fact for v in vocab)):
            continue
        kept2.append(l)
    out = '\n'.join(kept2)
    out = re.sub('<[^>]+>', '', out).replace('**', '').replace('__', '')
    url_re = re.compile('(?:https?://\\S+|(?<![\\w/])[\\w.-]+\\.[a-z]{2,}/\\S+)')
    fixed = []
    for l in out.splitlines():
        urls = url_re.findall(l)
        if urls:
            l = url_re.sub('', l).rstrip(' ,.:;-') + ' ' + urls[0]
        fixed.append(l)
    out = '\n'.join(fixed)
    out = '\n'.join((l for l in out.splitlines() if not re.match('^\\s*[\\[【#]', l) and '미시 신호' not in l and ('취재·조사' not in l)))
    lines = []
    for l in out.splitlines():
        l = l.strip()
        if not l:
            continue
        l = re.sub('^[\\-\\*\\u2022\\u25aa\\u25cf\\u30fb·▪•●■◆▶>]+\\s*', '', l)
        lines.append('▪ ' + l)
    out = '\n\n'.join(lines)
    if 단문사람체:
        out = _humanize(out)
    if len(out) > TG_LIMIT:
        cut = out.rfind('\n\n', 0, TG_LIMIT - 1)
        out = out[:cut] if cut > 0 else out[:TG_LIMIT]
    return out

def run_digest_tiers(state, items, stat, send_all):
    seen = set(state['seen'])
    items = [it for it in items if it['link'] not in seen]
    if not items:
        return 0
    try:
        digest = summarize(표시제목, items, prev_summary=state.get('last_summary', ''))
    except Exception as ex:
        deliver(MASTERS, f'⚠️ 장문 생성 오류: {str(ex)[:120]}', silent=True)
        raise
    if len(digest.strip()) < 40 and 'NO_UPDATE' in digest.upper():
        state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
        print('업데이트 없음 - 전송 생략')
        _h(state, 'skip')
        deliver(MASTERS, 'ℹ️ 정기 보고 생략: 이전 보고 이후 새 내용 없음', silent=True)
        return 0
    try:
        for m in build_messages(표시제목, items, digest, stat=None, lead=None, max_pages=장문최대페이지, show_head=False, footer=False):
            deliver(_active(state, MASTERS), m)
            time.sleep(0.4)
        _h(state, 'long')
        _h(state, 'pro' if 'pro' in (_BRIEF_ENGINE or '') else 'flash')
    except Exception as ex:
        print('장문 전송 오류:', str(ex)[:100])
        deliver(MASTERS, f'⚠️ 장문 전송 오류: {str(ex)[:120]}', silent=True)
    global _SHORT_REASON
    try:
        short = build_short(items, state)
    except Exception as ex:
        print('단문 생성 실패:', str(ex)[:100])
        short = ''
        _SHORT_REASON = '생성 오류: ' + str(ex)[:80]
    if short:
        fails, err = deliver(_active(state, MASTERS + NORMALS + SUBS), short, plain=True, token=TG_TOKEN_SHORT or None)
        if fails:
            _notify_fail_once(state, '단문', err)
        state['last_short'] = short[:2000]
        state['short_log'] = (state.get('short_log', []) + [short[:2500]])[-10:]
        _h(state, 'short')
    else:
        _h(state, 'skip')
        deliver(MASTERS, f'ℹ️ 단문 미발송: {_SHORT_REASON or '내용 없음'}', silent=True)
    state['seen'] = sorted(set(state['seen']) | {it['link'] for it in items})
    state['last_summary'] = digest[:3000]
    return len(items)

def _h(state, key, n=1):
    h = state.setdefault('health', {})
    h[key] = h.get(key, 0) + n

def _h_feed(state, name, count):
    z = state.setdefault('health', {}).setdefault('zero', {})
    if count > 0:
        z.pop(name, None)
    else:
        z[name] = z.get(name, 0) + 1

def _maybe_weekly_health(state, now_kst):
    h = state.get('health', {})
    wk = now_kst.strftime('%G-W%V')
    if now_kst.weekday() != 0 or h.get('sent_week') == wk:
        return
    runs, ok = (h.get('runs', 0), h.get('ok', 0))
    zero = {k: v for k, v in h.get('zero', {}).items() if v >= 6}
    lines = [f'📋 주간 점검 ({wk})', f'실행 {runs}회 · 정상 종료 {ok}회 · 비정상 {max(0, runs - ok)}회', f'보고: 장문 {h.get('long', 0)} · 단문 {h.get('short', 0)} · 긴급 {h.get('urgent', 0)} · 미발송(중복/없음) {h.get('skip', 0)}', f'분석 모델: Pro {h.get('pro', 0)}회 · Flash 등 강등 {h.get('flash', 0)}회' + (' ⚠ 한도 자주 소진' if h.get('flash', 0) > h.get('pro', 0) else ''), f'소스: 자동 추가 {h.get('src_added', 0)} · 정리 {h.get('src_dropped', 0)} · 자동 검색어 +{h.get('kw_added', 0)}/-{h.get('kw_removed', 0)}']
    if zero:
        lines.append('⚠ 계속 0건인 소스(점검 필요):')
        for k, v in sorted(zero.items(), key=lambda x: -x[1])[:8]:
            lines.append(f'  · {k} — {v}회 연속')
    else:
        lines.append('소스 상태: 이상 없음')
    try:
        deliver(MASTERS, '\n'.join(lines), silent=True)
    except Exception:
        pass
    state['health'] = {'sent_week': wk, 'zero': h.get('zero', {})}

def _due_slot(now_kst, last_key, slots, state=None):
    if now_kst.weekday() >= 5 and (not 주말발송):
        return None
    if _is_holiday(state):
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

def breaking_check(new_items, state=None):
    if not new_items:
        return None
    items = new_items[:40]
    sample = []
    for i, it in enumerate(items, 1):
        s = it.get('title', '')
        if it.get('seed'):
            s += ' — ' + it['seed'][:80]
        sample.append(f'[{i}] {s}')
    prev_lines = list((state or {}).get('alert_log', [])[-10:])
    for h in (state or {}).get('short_log', [])[-4:]:
        prev_lines += [l for l in h.splitlines() if len(l) > 15][:15]
    prev = '\n'.join(prev_lines[-40:]) or '(없음)'
    prompt = 프롬프트_속보.replace('{이전}', prev) + '\n'.join(sample)
    try:
        resp = gemini(prompt, [보조모델] + 폴백모델목록).strip()
    except Exception as ex:
        print('속보 판단 실패:', ex)
        return None
    if not resp or resp.upper().startswith('NONE') or (len(resp) < 12 and 'NONE' in resp.upper()):
        return None
    ref = None
    m = re.search('\\[(\\d+)\\]', resp)
    if m:
        try:
            ref = items[int(m.group(1)) - 1]
        except Exception:
            ref = None
        resp = re.sub('\\s*\\[\\d+\\]', '', resp).strip()
    return (resp, ref)

def main():
    if not (TG_TOKEN and GEMINI_KEY and MASTERS):
        print('비밀값(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID_MASTER / GEMINI_API_KEY)이 설정되지 않았어요.')
        return
    now_kst = now_utc() + datetime.timedelta(hours=9)
    _apply_secret_config()
    state = load_state()
    _sync_recipients(state)
    _h(state, 'runs')
    _ensure_polling(state)
    _maybe_weekly_health(state, now_kst)
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
    due_all = _due_slot(now_kst, state.get('last_slot_all', ''), 평일슬롯, state)
    due_master = _due_slot(now_kst, state.get('last_slot_master', ''), 마스터슬롯, state)
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
    for _name, _cnt in list(_FEED_STATS.items()):
        _h_feed(state, _name, _cnt)
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
            res = breaking_check(pending, state) if pending else None
            if res:
                head, ref = res
                recent = [l for h in state.get('short_log', [])[-10:] for l in h.splitlines() if len(l) > 15] + [l for l in (state.get('last_summary', '') or '').splitlines() if len(l) > 15] + list(state.get('alert_log', []))
                if '급변' not in head and any((_core_sim(head, l) >= 0.5 or _stem_overlap(head, l) >= 0.5 for l in recent)):
                    print('긴급 후보가 이미 보고된 사안 → 생략')
                    state['alerted'] = (list(alerted) + [it['link'] for it in pending])[-800:]
                    res = None
            if res:
                head, ref = res
                url = _shorten((ref or {}).get('link', ''), state)
                msg = f'[긴급] {now_kst.strftime('%m-%d %H:%M')} KST\n{re.sub('<[^>]+>', '', head)}' + (f'\n{url}' if url else '') + '\n\n자세한 내용은 다음 정기 보고에서.'
                fails, err = deliver(MASTERS + NORMALS + SUBS, msg[:TG_LIMIT], plain=True, urgent=True, token=TG_TOKEN_SHORT or None)
                if fails:
                    _notify_fail_once(state, '긴급', err)
                state['alerted'] = (list(alerted) + [it['link'] for it in pending])[-800:]
                state['alert_log'] = (state.get('alert_log', []) + [head[:120]])[-20:]
                _h(state, 'urgent')
                print('긴급 알림 전송(1통)')
            else:
                print('중대 속보 없음 - 점검만')
        else:
            print('정기 시각 아님 - 점검만')
    except Exception as ex:
        print('전송 처리 실패(다음 주기 재시도):', ex)
        state.setdefault('health', {})['ok'] = state['health'].get('ok', 0) - 1
    _h(state, 'ok')
    save_state(state)
if __name__ == '__main__':
    main()
