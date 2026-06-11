import os, re, json, html, time, datetime, urllib.parse, requests, feedparser
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor

try:
    import trafilatura
except Exception:
    trafilatura = None

# =======================================================
#                  여기만 고치면 돼요
# =======================================================

# 1) 검색할 주제 (구글 뉴스 + (키 넣으면)네이버). 한반도 정세 = 북한 + 미·중·러·일.
검색어목록 = []   # ※ 전부 SECRET_CONFIG로 주입(공개 코드에 키워드 없음)

# 화면(메시지)에 표시할 제목
표시제목 = "한반도·동북아 정세"

# 2) 뉴스가 아닌 다른 출처(분석기관·내부망·경제·제재추적)의 RSS. 한 줄에 하나씩.
#    ※ 일부(NK News 등)는 유료라 본문 대신 제목·요약만 들어올 수 있어요(그래도 신호는 잡힘).
추가RSS목록 = [
    "https://www.38north.org/feed/",            # 38 North: 위성·핵·미사일 전문 분석
    "https://www.dailynk.com/english/feed/",    # Daily NK: 북한 내부 소식통(장마당 물가·접경·단속 등 내밀)
    "https://www.nknews.org/feed/",             # NK News: 제재 위반·러시아 관계 등 탐사
    "https://www.nkeconwatch.com/feed/",        # NK Economy Watch: 북한 경제지표·교역
    "https://www.nkleadershipwatch.org/feed/",  # NK Leadership Watch: 권력층·기관 인사
    # 러시아 극동(연해주) 지역지 — 국경검문소·세관·북한 노동자/사건 등 현지 미시 동향 (직접 RSS, 안정적)
    # 대북 사업/기업 생태계
    "https://www.chosonexchange.org/our-blog?format=rss",       # Choson Exchange: 북한 내 최대 비즈니스 네트워크 NGO 블로그
    # 전문 분석·1차 성향 매체 (영어)
    "https://beyondparallel.csis.org/feed/",                    # CSIS Beyond Parallel: 위성·접경 분석
    "https://www.armscontrolwonk.com/feed/",                    # Arms Control Wonk: 핵·미사일 전문
    "https://www.nautilus.org/feed/",                           # Nautilus(NAPSNet): 동북아 안보 정책
    # 일본발 북한 전문 (북한 내부 취재·방위성 환적 정보)
    "https://www3.nhk.or.jp/rss/news/cat6.xml",                 # NHK 국제뉴스
    # 한국어 1차·대북 전문 (탈북민·내부 소식통 강함)
    "https://www.rfa.org/arc/outboundfeeds/korean/rss",         # RFA 자유아시아방송 한국어(대북 보도 강함)
    "https://www.tongilnews.com/rss/allArticle.xml",            # 통일뉴스(남북·대북 전문)
    # 북한 국가매체 원본 (체제 메시지 변화 감지)
    "https://kcnawatch.org/feed/",                              # KCNA Watch: 조선중앙통신 등 북한 관영매체 집성
    # 싱크탱크·전문 분석 (영어)
    "https://www.stimson.org/feed/",                            # Stimson Center(38N 모회)
    "https://keia.org/feed/",                                   # KEI 한미경제연구소
    "https://sinonk.com/feed/",                                 # Sino-NK: 북중 관계 전문
    "https://thediplomat.com/feed/",                            # The Diplomat: 아태 안보
    # 추가 북한 전문(미 정부발·내부소식통·니치) — 구글뉴스 site: RSS로 안정 수신
    "https://news.google.com/rss/search?q=site:voakorea.com&hl=ko&gl=KR&ceid=KR:ko",    # VOA 한국어(미국 정부발 대북 단독 많음)
    "https://news.google.com/rss/search?q=site:asiapress.org&hl=ko&gl=KR&ceid=KR:ko",   # 아시아프레스/임진강(북한 내부 취재망)
    "https://www.dailynk.com/feed/",                                                    # Daily NK 한국어판(영문판과 별도 기사)
    "https://news.google.com/rss/search?q=site:nkeconomy.com&hl=ko&gl=KR&ceid=KR:ko",   # NK경제(북 IT·산업·기업 니치)
    "https://news.google.com/rss/search?q=site:spnews.co.kr&hl=ko&gl=KR&ceid=KR:ko",    # 서울평양뉴스(남북 경협·교류 전문)
    # 전 세계 65개 언어 뉴스 그물 (무료, 키 없음) — 변방 매체까지 훑음
]

# 2-b) 중국쪽 검색 (가입 불필요). 검색어를 '중국어'로 넣어야 중국·중화권 매체가 잡혀요.
#      구글뉴스 중국어판 + 빙뉴스 중국어로 긁어옵니다. 끄려면 False.
중국검색 = True
중국어검색어목록 = []   # ※ 전부 SECRET_CONFIG로 주입(공개 코드에 키워드 없음)

# 2-c) 러시아쪽 검색 (가입 불필요). 검색어를 '러시아어'로. RIA·TASS·Kommersant 등이 잡혀요.
러시아검색 = True
러시아어검색어목록 = []   # ※ 전부 SECRET_CONFIG로 주입(공개 코드에 키워드 없음)

# 2-c2) 일본어 검색 (북한 보도가 두껍고, 일본 방위성의 '瀬取り'(환적) 적발 등 독자 정보)
일본검색 = True
일본어검색어목록 = []   # ※ 전부 SECRET_CONFIG로 주입(공개 코드에 키워드 없음)

# 2-d) 소셜·포럼 소스 (뉴스에 안 나오는 자잘한 첩보용) — 웨이보·바이두 톄바·텔레그램 채널·VK 등.
#   이런 곳은 RSS가 없어서 'RSSHub'(무료 오픈소스)가 만들어 주는 주소로 끌어옵니다.
#   ※ 여기서 온 항목은 자동으로 '(SNS·미확인)'로 표시되고, 사실이 아니라 '취재 단서'로만 쓰여요.
#   ※ 공개 RSSHub 서버(rsshub.app)는 텔레그램·웨이보 경로가 자주 끊겨요(불안정).
#     안정적으로 쓰려면 RSSHub를 직접 띄우세요(무료 Railway/Cloudflare, PC 불필요) → 아래 주소만 내 서버로 교체.
RSSHUB = "https://rsshub.app"     # 내 RSSHub 서버가 있으면 그 주소로 교체(예: https://rsshub.내도메인)

소셜RSS목록 = []   # ※ 실제 목록은 SECRET_CONFIG의 "sns"로 주입(웨이보·톄바·텔레그램 채널 비공개 유지)


# ── 비밀 설정(공개 저장소 대비): GitHub secret 'SECRET_CONFIG'(JSON)가 민감 목록을 주입 ──
def _apply_secret_config():
    raw = os.environ.get("SECRET_CONFIG", "").strip()
    if not raw:
        print("SECRET_CONFIG 없음 — 키워드 0개(주입 필요)"); return
    try:
        cfg = json.loads(raw)
    except Exception as ex:
        print("SECRET_CONFIG 해석 실패(JSON 오류) → 기본값 사용:", ex); return
    g = globals()
    for key, var in [("ko", "검색어목록"), ("zh", "중국어검색어목록"),
                     ("ru", "러시아어검색어목록"), ("ja", "일본어검색어목록"),
                     ("sns", "소셜RSS목록")]:
        v = cfg.get(key)
        if isinstance(v, list) and v:
            g[var] = [str(x) for x in v]
    p = cfg.get("prompt")
    if isinstance(p, str) and p.strip():
        g["명령"] = p
    b = cfg.get("border")
    if isinstance(b, list) and b:
        g["_BORDER_HINTS"] = [str(x).lower() for x in b]
    extra = cfg.get("rss_extra")
    if isinstance(extra, list):
        g["추가RSS목록"] = list(g["추가RSS목록"]) + [str(x) for x in extra if str(x) not in g["추가RSS목록"]]
    print("비밀 설정 적용 완료 (키워드·소스 주입)")


# 3) 인공지능한테 시킬 명령(요약 방식). {주제}, {목록} 글자는 그대로 두세요.
명령 = """아래 [자료]를 바탕으로 '{주제}' 관련 새 소식을 한국어로 간결히 요약하라. 출처 종류 표시를 참고해 검증 안 된 내용은 단정하지 마라.
[자료]
{목록}"""   # ※ 실제 프롬프트는 SECRET_CONFIG "prompt"로 주입

# 4) 최근 몇 시간 이내 자료만 볼지 (숫자만)
시간범위 = 48

# 5) 한 번에 다룰 최대 자료 수
최대기사수 = 100

# 6) 기사 본문까지 읽어 더 깊게 요약할지. 끄려면 False
본문까지읽기 = True

# 7) 심층검색: 1차 검색 결과에서 새 인물·지명·사건을 AI가 뽑아 '후속 검색어'를 만들고
#    한 번 더 검색해 깊이 파고듭니다. (시간이 더 걸리지만 새 취재 방향에 유리)
심층검색 = True
심층검색어수 = 12        # 후속으로 자동 생성·검색할 키워드 개수
심층반복 = 1            # 심층검색을 몇 겹 반복할지 (1=한 번 더, 2=두 번 더). 2면 더 깊지만 더 느림

# 8) 정기 보고를 보낼 시각(KST, 24시간). 봇은 자주 깨어 명령을 확인하지만, 정기 보고는 이 시각에만.
# 8) 정기 보고 시각 (KST, 24시간). 기본은 하루 4회. 검색은 매시간 점검.
발송시각 = [8, 11, 15, 21]   # 오전 8시, 오전 11시, 오후 3시, 밤 9시
주간시작 = "07:00"          # 이 시간대 안에서만 '중대 속보'를 즉시 전체보고. 밖(심야)이면 무음 1건.
주간종료 = "23:00"
검색간격시간 = 0.5          # 뉴스 검색(점검) 간격(시간). 0.5 = 30분마다
속보허용 = True            # 점검 중 '중대·새 소식'이면 정기 시각을 기다리지 않고 즉시 발송
심야속보 = True            # 발송시간 밖(심야·새벽)엔 중대 속보를 메시지 1개로(무음) 알림
보고안내 = "하루 4회 · 08·11·15·21시 (KST) · 중대 속보는 즉시"  # 하단 표시용

# 9) 검색어 자동 최신화: 봇이 최신 기사를 보고 '새 기관명·새 인물·새 사건'을 스스로 검색어에 보강.
#    (예: 보위성→국가정보국 같은 개칭을 기사에서 감지해 자동 추가) 텔레그램에 "검색어목록"으로 확인 가능.
키워드자동최신화 = True
자동키워드최대 = 20        # 자동으로 보관·사용할 보강 검색어 최대 개수
키워드갱신주기시간 = 24    # 몇 시간마다 검색어를 점검·보강할지
키워드열거 = True          # 정기 보고 첫 메시지에 '이번에 쓴 검색 키워드'를 고정/변동으로 나눠 보여줄지

# 9-b) 소스(RSS) 자동 발굴: 봇이 주기적으로 새 소스 후보를 뽑아 '실제로 열어 검증'한 뒤,
#     피드가 살아있고 최근 글이 있는 것만 자동 추가하고, 죽은 자동소스는 자동으로 정리합니다.
소스자동발굴 = True
자동소스최대 = 20          # 자동으로 보관·사용할 보강 소스 최대 개수
소스갱신주기시간 = 168     # 며칠마다 소스를 발굴·점검할지 (168 = 1주)

# 9-c) 제재·교역 지표 — 뉴스가 아니라 '1차 데이터'. 키 없이 동작(OpenSanctions 공개 데이터).
제재감시 = True            # 유엔·미국·EU 대북 제재 신규 지정을 감시해 알림
제재갱신주기시간 = 24      # 며칠마다 제재 명단을 점검할지 (24 = 하루)
OPENSANCTIONS_BASE = "https://data.opensanctions.org/datasets/latest"
제재데이터셋 = ["un_sc_sanctions", "us_ofac_sdn", "eu_fsf"]   # 유엔·미국 OFAC·EU
# (선택) UN Comtrade 북중 월간 교역액 — 무료 API 키가 있을 때만 동작. 키는 GitHub secret 'COMTRADE_KEY'에 넣으세요.
교역지표 = True
교역갱신주기시간 = 720     # 약 30일마다 (월간 데이터라)

# 9-d) 핵실험 조기 신호 — 풍계리(길주) 인근 지진을 USGS에서 감시(키 불필요). 인공지진이면 핵실험 가능성.
지진감시 = True
지진갱신주기시간 = 6
풍계리좌표 = (41.28, 129.08)   # 길주군 풍계리 핵실험장
지진반경km = 60
지진최소규모 = 2.5

# 10) AI 모델 (하이브리드). 가장 중요한 '최종 브리핑'은 똑똑한 Pro로, 잦은 잡일은 빠른 Flash로.
요약모델 = "gemini-2.5-pro"      # 최종 정세 브리핑·취재 지침 생성 (추론 품질 ↑)
보조모델 = "gemini-2.5-flash"    # 후속 검색어 생성, 검색어 자동 정리 등 (빠르고 한도 여유)
# 위 모델이 '한도 소진'되거나 구글이 모델명을 바꿔 안 될 때, 아래 순서로 자동으로 갈아탑니다.
# (예: Pro 하루 한도 소진 → Flash → Flash-Lite). 새 모델이 나오면 여기에 이름만 추가하면 돼요.
폴백모델목록 = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]

# =======================================================
#         아래부터는 건드리지 않으셔도 돼요
# =======================================================

STATE_FILE = "seen.json"
상태암호화 = True   # 공개 저장소 대비: 과거 브리핑·검색 상태를 암호화해 저장(키는 봇 토큰에서 유도)


def _state_fernet():
    if not (상태암호화 and TG_TOKEN):
        return None
    try:
        from cryptography.fernet import Fernet
    except Exception:
        print("cryptography 미설치 → 상태 평문 저장(공개 전환 전 requirements 확인)"); return None
    import hashlib, base64
    k = base64.urlsafe_b64encode(hashlib.sha256(("state:" + TG_TOKEN).encode()).digest())
    return Fernet(k)
본문길이 = 1800
본문읽기최대 = 90
동시작업 = 16
출처당최대 = 30           # 검색어(출처) 하나당 최대 몇 개까지 가져올지
MAX_PROMPT = 220000
링크표시최대 = 15
TG_LIMIT = 4096
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
COMMAND_HELP = ('\n\n⏱ 정기 보고: {보고안내}\n🛠 명령: /보고 · /일시중지 · /재개 · /요약 ○○ · /검색어 · /도움말'
                ).replace("{보고안내}", 보고안내)

HELP_TEXT = (
    "🛠 <b>명령 안내</b>\n"
    "/보고 — 지금 바로 정세 브리핑 받기\n"
    "/요약 ○○ — 특정 주제만 찾아 정리 (예: /요약 북러 무기거래)\n"
    "/일시중지 [이틀·사흘·일주일] — 정기 알림 멈춤\n"
    "/재개 — 다시 시작\n"
    "/검색어 — 자동 추가된 검색어 보기\n"
    "/검색어삭제 ○○ — 자동 검색어에서 빼기\n"
    "/도움말 — 이 안내\n\n"
    f"정기 보고: {보고안내}\n"
    "※ 한글 명령(/일시중지 등)은 그대로 입력하면 동작해요. 텔레그램 자동완성 메뉴(/)에는 "
    "규칙상 영문 별칭(/report·/pause·/resume·/keywords·/help)만 떠요 — 둘 다 됩니다."
)

TG_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "").strip()
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "").strip()
TG_CHATS     = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
OWNER = TG_CHATS[0] if TG_CHATS else ""
NAVER_ID     = os.environ.get("NAVER_CLIENT_ID", "").strip()
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "").strip()


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


# ---------- 상태 ----------
def _base_state(d):
    if isinstance(d, list):
        d = {"seen": d}
    return {"seen": d.get("seen", []),
            "paused_until": d.get("paused_until", ""),
            "last_update_id": d.get("last_update_id", 0),
            "last_summary": d.get("last_summary", ""),
            "last_search_ts": d.get("last_search_ts", ""),
            "last_digest_ts": d.get("last_digest_ts", ""),
            "last_digest_slot": d.get("last_digest_slot", ""),
            "alerted": d.get("alerted", []),
            "auto_keywords": d.get("auto_keywords", []),
            "auto_kw_updated": d.get("auto_kw_updated", ""),
            "auto_sources": d.get("auto_sources", []),
            "auto_src_updated": d.get("auto_src_updated", ""),
            "sanctions_seen": d.get("sanctions_seen", []),
            "sanctions_checked": d.get("sanctions_checked", ""),
            "comtrade_checked": d.get("comtrade_checked", ""),
            "quake_seen": d.get("quake_seen", []),
            "quake_checked": d.get("quake_checked", ""),
            "cfg_alerted_day": d.get("cfg_alerted_day", ""),
            "bot_cmds_v": d.get("bot_cmds_v", "")}


def load_state():
    try:
        raw = open(STATE_FILE, "rb").read()
        try:
            return _base_state(json.loads(raw.decode("utf-8")))      # 예전 평문 상태도 그대로 읽힘
        except Exception:
            f = _state_fernet()
            if not f:
                raise
            return _base_state(json.loads(f.decrypt(raw).decode("utf-8")))
    except Exception:
        return _base_state({})


def save_state(state):
    f = _state_fernet()
    data = json.dumps(state, ensure_ascii=False, indent=0)
    if f:
        open(STATE_FILE, "wb").write(f.encrypt(data.encode("utf-8")))   # 공개 저장소에서도 내용 안 보임
    else:
        open(STATE_FILE, "w", encoding="utf-8").write(data)


# ---------- 텔레그램 ----------
def _post_one(chat, text, silent=False):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": chat, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True, "disable_notification": silent},
        timeout=30,
    )
    if r.status_code == 400:   # 보통 HTML 태그 문제 → 태그 빼고 평문으로 재전송(전달은 보장)
        plain = re.sub(r"<[^>]+>", "", text)
        r = requests.post(
            url,
            json={"chat_id": chat, "text": plain,
                  "disable_web_page_preview": True, "disable_notification": silent},
            timeout=30,
        )
    r.raise_for_status()


def register_commands(state):
    """텔레그램 자동완성 메뉴(/) 등록. 텔레그램 규칙상 명령명은 영문/숫자만 → 영문 별칭으로 등록.
       한글 명령(/보고·/일시중지 등)은 메뉴엔 안 떠도 그대로 입력하면 동작함."""
    if state.get("bot_cmds_v") == "2":
        return
    cmds = [
        {"command": "report",   "description": "지금 정세 브리핑 받기"},
        {"command": "summary",  "description": "특정 주제 정리 (예: /summary 북러 무기)"},
        {"command": "pause",    "description": "정기 알림 멈춤"},
        {"command": "resume",   "description": "다시 시작"},
        {"command": "keywords", "description": "자동 검색어 보기"},
        {"command": "help",     "description": "명령 안내"},
    ]
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/setMyCommands",
                      json={"commands": cmds}, timeout=15)
        state["bot_cmds_v"] = "2"
    except Exception as ex:
        print("명령 메뉴 등록 실패(무시 가능):", ex)


def deliver(targets, text, silent=False):
    if len(text) > TG_LIMIT:
        text = text[:TG_LIMIT]
    for chat in targets:
        try:
            _post_one(chat, text, silent=silent)
        except Exception as ex:
            print(f"전송 실패 (받는사람 {chat}): {ex}")


def read_commands(state):
    if not OWNER:
        return []
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"offset": state["last_update_id"] + 1, "timeout": 0},
            timeout=30,
        )
        resp.raise_for_status()
        updates = resp.json().get("result", [])
    except Exception as ex:
        print("명령 읽기 실패:", ex)
        return []
    texts = []
    for u in updates:
        state["last_update_id"] = max(state["last_update_id"], u.get("update_id", 0))
        msg = u.get("message") or u.get("channel_post") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if chat == str(OWNER) and text:
            texts.append(text)
    return texts


# ---------- 수집 ----------
def _clean(s):
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(s or "")).split())


def _rss_items(url, limit):
    out = []
    try:
        entries = feedparser.parse(url).entries[:limit]
    except Exception:
        return out
    for e in entries:
        link = getattr(e, "link", "")
        if not link:
            continue
        pub = None
        if getattr(e, "published_parsed", None):
            pub = datetime.datetime(*e.published_parsed[:6], tzinfo=datetime.timezone.utc)
        src = ""
        if hasattr(e, "source") and isinstance(e.source, dict):
            src = e.source.get("title", "")
        out.append({"title": getattr(e, "title", "(제목 없음)"), "link": link,
                    "source": src, "pub": pub, "seed": _clean(getattr(e, "summary", ""))})
    return out


def _naver_query(term, limit):
    # 오류가 나면 예외를 던진다 (호출부에서 실패로 표시). 429(순간 한도)는 잠깐 쉬고 재시도.
    last = None
    for attempt in range(3):
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": term, "display": limit, "sort": "date"},
            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
            timeout=20,
        )
        if r.status_code == 429:
            last = r; time.sleep(0.6 * (attempt + 1)); continue
        r.raise_for_status()
        out = []
        for it in r.json().get("items", []):
            link = it.get("originallink") or it.get("link") or ""
            if not link:
                continue
            pub = None
            try:
                pub = parsedate_to_datetime(it.get("pubDate", ""))
            except Exception:
                pub = None
            out.append({"title": _clean(it.get("title", "")), "link": link,
                        "source": "네이버뉴스", "pub": pub, "seed": _clean(it.get("description", ""))})
        return out
    if last is not None:
        last.raise_for_status()   # 끝까지 429면 예외로
    raise RuntimeError("네이버 응답 없음")


def _body(seed, link):
    if len(seed) >= 400:
        return seed[:본문길이]
    if 본문까지읽기 and trafilatura and link and "news.google.com" not in link:
        try:
            r = requests.get(link, headers=UA, timeout=12, allow_redirects=True)
            if "news.google.com" not in r.url:
                body = _clean(trafilatura.extract(r.text) or "")
                if len(body) > len(seed):
                    return body[:본문길이]
        except Exception:
            pass
    return seed[:본문길이]


# ---------- 다국어 검색 + 심층검색 ----------
_GNEWS = {"ko": ("ko", "KR", "KR:ko"), "zh": ("zh-CN", "CN", "CN:zh-Hans"),
          "ru": ("ru", "RU", "RU:ru"), "ja": ("ja", "JP", "JP:ja"), "en": ("en-US", "US", "US:en")}
_BING = {"ko": ("ko", "KR"), "zh": ("zh-hans", "CN"), "ru": ("ru", "RU"), "ja": ("ja", "JP"), "en": ("en", "US")}


def _lang_of(q):
    if re.search(r"[\uac00-\ud7a3]", q):                  # 한글
        return "ko"
    if re.search(r"[\u0400-\u04ff]", q):                  # 키릴(러시아어)
        return "ru"
    if re.search(r"[\u3040-\u30ff]", q):                  # 히라가나·가타카나(일본어)
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", q):                  # 한자(중국어)
        return "zh"
    return "ko"


def search_news(q, lang, days, limit, use_bing=None):
    if use_bing is None:
        use_bing = (lang != "ko")   # 한국어는 구글+네이버로 충분 → 빙 생략(부하↓)
    hl, gl, ceid = _GNEWS.get(lang, _GNEWS["ko"])
    g = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
         f"+when:{days}d&hl={hl}&gl={gl}&ceid={ceid}")
    out = _rss_items(g, limit)
    if use_bing:
        sl, cc = _BING.get(lang, _BING["ko"])
        b = (f"https://www.bing.com/news/search?q={urllib.parse.quote(q)}"
             f"&format=RSS&setlang={sl}&cc={cc}")
        out = out + _rss_items(b, limit)
    return out


def _roundrobin(sources, cutoff, cap):
    items, seen, i = [], set(), 0
    while len(items) < cap and any(i < len(s) for s in sources):
        for s in sources:
            if i < len(s):
                it = s[i]
                if it["link"] in seen:
                    continue
                if it.get("pub") and it["pub"] < cutoff:
                    continue
                seen.add(it["link"]); items.append(it)
                if len(items) >= cap:
                    break
        i += 1
    return items


def _parallel(jobs):
    # jobs: [(bucket, fn)] -> [(bucket, list)]
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
        s = it.get("title", "")
        if it.get("seed"):
            s += " — " + it["seed"][:140]
        sample.append("- " + s)
    prompt = ("아래는 한반도·동북아 관련 최신 기사 제목/발췌다. 표면 보도를 넘어 더 깊이 파고들 가치가 있는 "
              f"후속 '검색어' {n}개를 만들어라. 새로 등장한 인물명·지명·부대/기관명·사건명·기업·선박명 등 "
              "고유명사와 구체적 사안 중심으로(흔한 일반어 금지). 해당 지역 매체가 더 자세하므로 "
              "한국어·중국어·러시아어를 사안에 맞게 섞어 써라. "
              "단, 한반도·동북아 '안보 정세'(북한·핵미사일·미중러일·동맹·제재·접경)와 직접 관련된 것만. "
              "국내 정당·선거, 일반 IT/AI/반도체/에너지 사업, 중동 등 타 지역, 역사·문화 주제는 만들지 마라. "
              "설명·번호 없이 JSON 문자열 배열로만 출력하라.\n\n"
              + "\n".join(sample))
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub(r"^```(json)?", "", raw)
        raw = re.sub(r"```$", "", raw).strip()
        arr = json.loads(raw)
        seen, out = set(), []
        for x in arr:
            x = str(x).strip()
            if x and x not in seen:
                seen.add(x); out.append(x)
        return out[:n]
    except Exception as ex:
        print("심층 검색어 생성 실패:", ex)
        return []


def refresh_keywords(items, base, current_auto):
    """최신 기사 기준으로 자동 검색어를 정리: 가치 있는 새 검색어는 추가, 철 지난·추상적·무관한 것은 삭제."""
    sample = []
    for it in items[:40]:
        s = it.get("title", "")
        if it.get("seed"):
            s += " — " + it["seed"][:100]
        sample.append("- " + s)
    prompt = ("너는 한반도·동북아 취재 데스크의 '검색어 관리자'다. 아래 최신 기사들을 보고 '자동 검색어'를 정세에 맞게 정리하라.\n"
              "[추가 기준] 앞으로도 계속 추적할 가치가 있는 것만. ① 기관·부서·직책 명칭이 바뀐 정황이 보이면 '새 명칭' "
              "② 지금 활동 중인 핵심 인물·부대·기관·작전·합의·진행 중 사건의 '구체적 고유명사' "
              "③ 북중·북러 접경의 구체 지명·통상구·노선(예: 세관/구안 이름, 다리·철도, 파견지) 등 미시 동향 단서.\n"
              "[추가 금지] 추상적 개념어(예: 다극 세계), 흔한 일반어, 한 번 쓰고 끝날 단발 사건명, "
              "이미 현직이 아닌 인물(교체된 당국자·전직), 본 주제와 거리가 먼 역사적 용어.\n"
              "[삭제 기준] '현재 자동 검색어' 중 추상적·일반적이거나, 더 이상 정세와 관련 없거나, 현직이 아닌 인물·철 지난 사안인 것. "
              "또한 한반도·동북아 안보와 무관한 것(국내 정당·선거, 일반 IT/AI/반도체/에너지 사업, 중동 등 타 지역, 역사·문화)은 삭제하라.\n"
              f"기본 검색어(절대 건드리지 말 것): {', '.join(base)}\n"
              f"현재 자동 검색어(여기서만 추가/삭제 판단): {', '.join(current_auto) or '(없음)'}\n"
              '설명 없이 JSON으로만 출력: {"add": ["새 검색어"], "remove": ["뺄 자동 검색어"]}\n\n'
              + "\n".join(sample))
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub(r"^```(json)?", "", raw)
        raw = re.sub(r"```$", "", raw).strip()
        obj = json.loads(raw)
        add = [str(x).strip() for x in obj.get("add", []) if str(x).strip()]
        remove = [str(x).strip() for x in obj.get("remove", []) if str(x).strip()]
    except Exception as ex:
        print("검색어 자동 정리 실패:", ex)
        return list(current_auto), [], []

    base_set = set(base)
    remset = set(remove)
    cur = [k for k in current_auto if k not in remset]          # 삭제 반영
    used = base_set | set(cur)
    newly = []
    for x in add:                                               # 추가 반영(기본·기존 중복 제외)
        if x and x not in used:
            cur.append(x); used.add(x); newly.append(x)
    cur = cur[-자동키워드최대:]
    removed = [r for r in remove if r in set(current_auto)]
    return cur, newly, removed


def _maybe_learn_keywords(state, items):
    if not (키워드자동최신화 and state is not None and items):
        return
    last = state.get("auto_kw_updated", "")
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=키워드갱신주기시간):
                return
        except Exception:
            pass
    merged, added, removed = refresh_keywords(items, 검색어목록, state.get("auto_keywords", []))
    state["auto_keywords"] = merged
    state["auto_kw_updated"] = now_utc().isoformat()
    if added or removed:
        print(f"검색어 자동 추가 {len(added)}건 / 삭제 {len(removed)}건")
        parts = []
        if added:
            parts.append("➕ 추가: " + ", ".join(added))
        if removed:
            parts.append("➖ 정리: " + ", ".join(removed))
        try:
            deliver([OWNER], "🆕 정세 반영 검색어 업데이트\n" + "\n".join(parts))
        except Exception:
            pass


def _validate_feed(url):
    """실제로 열어보고 '파싱되는 피드 + 항목 있음'이면 항목 수를, 아니면 0을 반환."""
    try:
        return len(_rss_items(url, 5))
    except Exception:
        return 0


def discover_sources(existing):
    """이 주제에 유용한 '실제 존재하는 공개 RSS 피드' 후보를 AI가 제안(검증은 호출부에서)."""
    prompt = ("너는 한반도·동북아(특히 북중·북러 접경·무역·제재·노동자 파견) 취재를 돕는 'OSINT 소스 발굴가'다. "
              "이 주제에 꾸준히 유용한, 실제로 존재하는 '공개 RSS/Atom 피드 주소'를 최대 8개 제안하라. "
              "전문 분석기관·전문매체·중/러 접경 지역지·연구소·공공기관 위주. "
              "정확한 피드 URL만(http로 시작, 보통 .xml 또는 /feed/ 또는 /rss 로 끝남). "
              f"RSSHub 경로를 제안하려면 반드시 '{RSSHUB}/...' 전체 주소로 써라. 존재하지 않을 법한 추측성 URL은 절대 만들지 마라.\n"
              "이미 쓰고 있으니 제외: " + ", ".join(list(existing)[:50]) + "\n"
              "설명·주석 없이 JSON 문자열 배열로만 출력하라.")
    try:
        raw = gemini(prompt, [보조모델] + 폴백모델목록).strip()
        raw = re.sub(r"^```(json)?", "", raw); raw = re.sub(r"```$", "", raw).strip()
        return [str(x).strip() for x in json.loads(raw) if str(x).strip().lower().startswith("http")]
    except Exception as ex:
        print("소스 후보 생성 실패:", ex)
        return []


def _maybe_learn_sources(state):
    if not (소스자동발굴 and state is not None):
        return
    last = state.get("auto_src_updated", "")
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=소스갱신주기시간):
                return
        except Exception:
            pass
    state["auto_src_updated"] = now_utc().isoformat()
    fixed = set(추가RSS목록) | set(소셜RSS목록)
    auto = list(state.get("auto_sources", []))

    # 1) 기존 자동소스 재검증 — 죽은 것 정리
    alive, dropped = [], []
    for u in auto:
        (alive if _validate_feed(u) > 0 else dropped).append(u)

    # 2) 새 후보 발굴 → '실제로 열어' 검증된 것만 추가
    added = []
    for u in discover_sources(fixed | set(alive)):
        if u in fixed or u in alive:
            continue
        if _validate_feed(u) > 0:
            alive.append(u); added.append(u)
            if len(alive) >= 자동소스최대:
                break

    state["auto_sources"] = alive[-자동소스최대:]
    if added or dropped:
        print(f"소스 자동 추가 {len(added)}건 / 정리 {len(dropped)}건")
        parts = []
        if added:
            parts.append("➕ 검증 통과한 새 소스:\n" + "\n".join(added))
        if dropped:
            parts.append("➖ 응답 없어 정리한 소스:\n" + "\n".join(dropped))
        try:
            deliver([OWNER], "🛰 자동 소스 업데이트\n" + "\n".join(parts))
        except Exception:
            pass


def _maybe_check_sanctions(state):
    """유엔·미국 OFAC·EU 대북 제재 명단(OpenSanctions 공개 CSV)에서 '신규 지정'만 골라 알림. 키 불필요."""
    if not (제재감시 and state is not None):
        return
    last = state.get("sanctions_checked", "")
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=제재갱신주기시간):
                return
        except Exception:
            pass
    state["sanctions_checked"] = now_utc().isoformat()

    import csv, io
    toks = ("kpi.", "kpe.", "dprk", "north korea", "korea, north", "democratic people's republic of korea")
    cur = {}
    for ds in 제재데이터셋:
        try:
            r = requests.get(f"{OPENSANCTIONS_BASE}/{ds}/targets.simple.csv", timeout=90)
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.text)))
        except Exception as ex:
            print(f"제재 명단 다운로드 실패({ds}):", ex); continue
        for row in rows:
            blob = " ".join(str(v) for v in row.values()).lower()
            if any(t in blob for t in toks):
                rid = ds + ":" + (row.get("id") or blob[:50])
                cur[rid] = (row.get("name") or rid, ds)
    if not cur:
        print("제재 명단에서 대북 항목을 못 찾음(형식 변경 가능)"); return

    seen = set(state.get("sanctions_seen", []))
    new = [(i, v) for i, v in cur.items() if i not in seen]
    state["sanctions_seen"] = list(cur.keys())
    if not seen:
        print("제재 기준선 설정:", len(cur), "건 (첫 실행은 알림 없음)"); return
    if new:
        label = {"un_sc_sanctions": "유엔", "us_ofac_sdn": "미국 OFAC", "eu_fsf": "EU"}
        lines = [f"• [{label.get(ds, ds)}] {html.escape(nm)}" for _, (nm, ds) in new[:30]]
        msg = (f"🚫 <b>신규 대북 제재 지정</b> ({len(new)}건)\n" + "\n".join(lines) + "\n\n"
               "→ 이 기업·선박·개인의 거래망(중·러 연결, 환적, 위장회사)을 추적해 보세요 — 취재 단서.")
        try:
            deliver(TG_CHATS, msg)
        except Exception:
            pass
        print("신규 제재 지정 알림:", len(new))


def _maybe_check_quake(state):
    """풍계리 핵실험장 인근 지진을 USGS에서 감시. 인공지진(핵실험) 조기 신호. 키 불필요."""
    if not (지진감시 and state is not None):
        return
    last = state.get("quake_checked", "")
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=지진갱신주기시간):
                return
        except Exception:
            pass
    state["quake_checked"] = now_utc().isoformat()
    try:
        lat, lon = 풍계리좌표
        start = (now_utc() - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        r = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query",
                         params={"format": "geojson", "latitude": lat, "longitude": lon,
                                 "maxradiuskm": 지진반경km, "starttime": start,
                                 "minmagnitude": 지진최소규모}, timeout=30)
        r.raise_for_status()
        feats = r.json().get("features", [])
    except Exception as ex:
        print("지진 조회 실패:", ex); return

    seen = set(state.get("quake_seen", []))
    new = [f for f in feats if f.get("id") and f.get("id") not in seen]
    state["quake_seen"] = ([f.get("id") for f in feats if f.get("id")] + list(seen))[:200]
    if not seen:
        print("지진 기준선 설정:", len(feats), "건"); return
    for f in new:
        p = f.get("properties", {}); mag = p.get("mag"); place = p.get("place", "")
        when = ""
        try:
            when = datetime.datetime.utcfromtimestamp(p.get("time", 0) / 1000.0 + 9 * 3600).strftime("%m-%d %H:%M")
        except Exception:
            pass
        msg = (f"⚠️ <b>풍계리 인근 지진 감지</b> M{mag} ({when} KST)\n{html.escape(place)}\n\n"
               "→ 자연지진인지 인공지진(핵실험)인지 즉시 확인 필요. USGS·기상청·CTBTO·38N 교차 점검.")
        try:
            deliver(TG_CHATS, msg)
        except Exception:
            pass
    if new:
        print("풍계리 인근 지진 알림:", len(new))


def _maybe_comtrade(state):
    """(선택) UN Comtrade로 북중 월간 교역액을 보고에 붙임. GitHub secret 'COMTRADE_KEY' 있을 때만."""
    key = os.environ.get("COMTRADE_KEY", "").strip()
    if not (교역지표 and key and state is not None):
        return
    last = state.get("comtrade_checked", "")
    if last:
        try:
            if now_utc() - datetime.datetime.fromisoformat(last) < datetime.timedelta(hours=교역갱신주기시간):
                return
        except Exception:
            pass
    state["comtrade_checked"] = now_utc().isoformat()
    try:
        now = now_utc()
        for back in range(2, 6):   # 데이터는 1~3개월 시차 → 직전 달부터 역으로 탐색
            y, m = now.year, now.month - back
            while m <= 0:
                m += 12; y -= 1
            period = f"{y}{m:02d}"
            r = requests.get("https://comtradeapi.un.org/data/v1/get/C/M/HS",
                             params={"reporterCode": 156, "partnerCode": 408, "period": period,
                                     "flowCode": "M,X", "cmdCode": "TOTAL"},
                             headers={"Ocp-Apim-Subscription-Key": key}, timeout=40)
            if r.status_code != 200:
                continue
            data = r.json().get("data", [])
            if not data:
                continue
            exp = sum(d.get("primaryValue", 0) or 0 for d in data if d.get("flowCode") == "X")  # 중국→북한
            imp = sum(d.get("primaryValue", 0) or 0 for d in data if d.get("flowCode") == "M")  # 북한→중국
            msg = (f"📊 <b>북중 교역 지표</b> ({y}-{m:02d}, UN Comtrade)\n"
                   f"중국→북한 수출 ${exp/1e6:,.1f}M · 북한→중국 ${imp/1e6:,.1f}M")
            try:
                deliver(TG_CHATS, msg)
            except Exception:
                pass
            return
        print("Comtrade: 최근 가용 월 데이터를 못 찾음")
    except Exception as ex:
        print("Comtrade 조회 실패:", ex)


def fetch_items(terms, regional=True, bodies=True, deep=True, auto_feeds=None):
    days = max(1, (시간범위 + 23) // 24)
    cutoff = now_utc() - datetime.timedelta(hours=시간범위)
    하드캡 = 최대기사수 * 2 if (심층검색 and deep) else 최대기사수

    # ---- 1차 검색 (전부 병렬) ----
    jobs = []
    for t in terms:
        jobs.append(("ko", lambda t=t: search_news(t, _lang_of(t), days, 출처당최대)))
    if regional:
        for rss in 추가RSS목록 + list(auto_feeds or []):
            jobs.append(("rss", lambda rss=rss: _rss_items(rss, 출처당최대)))
        for s in 소셜RSS목록:
            jobs.append(("sns", lambda s=s: _rss_items(s, 출처당최대)))   # 웨이보·톄바·텔레그램 등(RSSHub)
        if 중국검색:
            for t in 중국어검색어목록:
                jobs.append(("zh", lambda t=t: search_news(t, "zh", days, 출처당최대)))
        if 러시아검색:
            for t in 러시아어검색어목록:
                jobs.append(("ru", lambda t=t: search_news(t, "ru", days, 출처당최대)))
        if 일본검색:
            for t in 일본어검색어목록:
                jobs.append(("ja", lambda t=t: search_news(t, "ja", days, 출처당최대)))

    counts = {"ko": 0, "zh": 0, "ru": 0, "ja": 0, "rss": 0, "sns": 0, "naver": 0, "expand": 0}
    sources = []
    for bucket, lst in _parallel(jobs):
        counts[bucket] += len(lst)
        if bucket == "sns":
            for it in lst:
                it["social"] = True   # 소셜·포럼 출처 → '미확인 첩보'로 표시·취급
        sources.append(lst)

    네이버상태 = "off"; 네이버오류 = ""
    if NAVER_ID and NAVER_SECRET:
        네이버상태 = "ok"; err = False
        with ThreadPoolExecutor(max_workers=2) as ex:   # 네이버는 순간 호출 한도가 있어 동시 2개로 제한
            futs = [ex.submit(lambda t=t: _naver_query(t, 출처당최대)) for t in terms]
            for f in futs:
                try:
                    lst = f.result()
                except Exception as ex2:
                    print("네이버 검색 실패:", ex2); err = True; lst = []
                    code = getattr(getattr(ex2, "response", None), "status_code", None)
                    if code and not 네이버오류:
                        네이버오류 = str(code)
                        hint = {"401": "키 오류 또는 '검색' API 미설정/공백 포함",
                                "403": "권한 없음(앱에 '검색' API 미추가)",
                                "429": "하루 호출 한도 초과"}.get(str(code), "")
                        if hint:
                            print("  ↳ 네이버 점검:", hint)
                counts["naver"] += len(lst); sources.append(lst)
        if err:
            네이버상태 = "err"

    items = _roundrobin(sources, cutoff, 최대기사수)

    # ---- 심층검색: 결과에서 후속 검색어를 뽑아 한 번 더(또는 여러 겹) 파고든다 ----
    if 심층검색 and deep and items:
        pool = list(items)
        for _ in range(max(1, 심층반복)):
            queries = expand_queries(pool, 심층검색어수)
            if not queries:
                break
            counts["expand"] += len(queries)
            ex_jobs = [("x", lambda q=q: search_news(q, _lang_of(q), days, 출처당최대)) for q in queries]
            ex_sources = [lst for _, lst in _parallel(ex_jobs)]
            more = _roundrobin(ex_sources, cutoff, 하드캡)
            have = {it["link"] for it in items}
            added = []
            for it in more:
                if it["link"] not in have:
                    items.append(it); have.add(it["link"]); added.append(it)
                    if len(items) >= 하드캡:
                        break
            if not added or len(items) >= 하드캡:
                break
            pool = added

    # ---- 본문 읽기 (깊게) — 가벼운 점검(bodies=False)일 땐 건너뜀 ----
    deep_list = items[:본문읽기최대]
    if 본문까지읽기 and bodies and deep_list:
        with ThreadPoolExecutor(max_workers=동시작업) as ex:
            read = list(ex.map(lambda it: _body(it.get("seed", ""), it["link"]), deep_list))
        for it, b in zip(deep_list, read):
            it["body"] = b
    for it in items:
        it.setdefault("body", (it.get("seed", "") or "")[:본문길이])

    stat = {"ko": counts["ko"], "zh": counts["zh"], "ru": counts["ru"], "ja": counts["ja"],
            "rss": counts["rss"], "sns": counts["sns"], "naver": counts["naver"],
            "naver_state": 네이버상태, "naver_err": 네이버오류, "expand": counts["expand"]}
    return items, stat


# ---------- 요약 ----------
def _gemini(prompt, model=보조모델):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    err = ""
    for attempt in range(4):
        try:
            r = requests.post(
                url,
                headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=180,
            )
            # 모델명이 없거나 잘못됨(404/400) → 재시도 무의미, 즉시 알려서 다음 모델로 넘기게
            if r.status_code in (400, 404):
                raise RuntimeError(f"모델 '{model}' 사용 불가({r.status_code})")
            if r.status_code in (429, 500, 502, 503, 504):
                err = f"{r.status_code} (한도 또는 일시 오류)"
                print(f"Gemini[{model}] {err} - {6*(attempt+1)}초 후 재시도 ({attempt+1}/4)")
                time.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.exceptions.RequestException as ex:
            err = str(ex)
            time.sleep(6 * (attempt + 1))
    raise RuntimeError(f"Gemini[{model}] 호출 실패(재시도 후): " + err)


_BRIEF_ENGINE = ""   # 마지막 브리핑을 실제로 만든 엔진/모델 (상태줄 표시용)


def gemini(prompt, models):
    """모델 우선순위 리스트를 앞에서부터 시도. 한도 소진/모델 폐기 시 다음 모델로 자동 폴백."""
    global _BRIEF_ENGINE
    seen, chain = set(), []
    for m in models:
        if m and m not in seen:
            seen.add(m); chain.append(m)
    last = ""
    for m in chain:
        try:
            out = _gemini(prompt, model=m)
            _BRIEF_ENGINE = m
            return out
        except Exception as ex:
            last = str(ex)
            print(f"모델 {m} 실패 → 다음 모델로 폴백: {last[:120]}")
    raise RuntimeError("모든 모델 폴백 실패: " + last)


_BORDER_HINTS = []   # ※ SECRET_CONFIG "border"로 주입


def _is_border(it):
    blob = (it.get("title", "") + " " + it.get("seed", "") + " " + (it.get("body", "") or "")).lower()
    return any(h in blob for h in _BORDER_HINTS)


# 출처 등급 — 남들이 잘 안 보는 1차·전문·현지어·소셜을 우대하고, 주류 한국 언론은 상한을 둠
_PRIMARY_DOMAINS = (
    "rfa.org", "kcnawatch.org", "38north.org", "dailynk.com", "nknews.org",
    "nkeconwatch.com", "nkleadershipwatch.org", "beyondparallel.csis.org",
    "armscontrolwonk.com", "nautilus.org", "sinonk.com", "stimson.org",
    "keia.org", "thediplomat.com", "tongilnews.com", "primamedia.ru",
    "chosonexchange.org", "asiapress.org",
)
_PRIMARY_SRC_HINTS = ("rfa", "자유아시아", "daily nk", "데일리nk", "nk news", "38 north",
                      "kcna", "조선중앙", "beyond parallel", "stimson", "diplomat",
                      "통일뉴스", "nautilus", "nk pro", "아시아프레스", "rimjin", "임진강")


def _domain(u):
    try:
        return urllib.parse.urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _provenance(it):
    """(그룹, 표시라벨). 그룹 우선순위: border>sns>primary>foreign>main"""
    t = it.get("title", "")
    d = _domain(it.get("link", ""))
    src = (it.get("source", "") or "").lower()
    primary = any(d.endswith(pd) for pd in _PRIMARY_DOMAINS) or any(k in src for k in _PRIMARY_SRC_HINTS)
    if re.search(r"[\u0400-\u04ff]", t):
        lang = "러"
    elif re.search(r"[\u3040-\u30ff]", t):
        lang = "일"
    elif re.search(r"[\u4e00-\u9fff]", t):
        lang = "중"
    else:
        lang = ""
    if it.get("social"):
        return "sns", "SNS·미확인"
    if _is_border(it):
        return "border", ("접경신호·1차" if primary else "접경신호")
    if primary:
        return "primary", "1차·전문"
    if lang:
        return "foreign", "외신·" + lang
    return "main", "주류"


def summarize(topic, items, prev_summary=""):
    # 1) 출처 등급별로 분류 (+ 주류는 비슷한 제목끼리 한 번만 — 같은 사건 수십 건이 예산 먹는 것 방지)
    groups = {"border": [], "sns": [], "primary": [], "foreign": [], "main": []}
    seen_titles = set()
    for it in items:
        g, label = _provenance(it)
        if g == "main":
            key = re.sub(r"\W+", "", it.get("title", ""))[:16]
            if key and key in seen_titles:
                continue
            seen_titles.add(key)
        it["_plabel"] = label
        groups[g].append(it)

    # 2) 희귀·고가치 그룹(접경·소셜·1차·외신)을 먼저 다 채우고, 주류는 전체 예산의 30%까지만
    order = ["border", "sns", "primary", "foreign", "main"]
    main_cap = int(MAX_PROMPT * 0.30)
    blocks, total, main_used = [], 0, 0
    for g in order:
        for it in groups[g]:
            tag = f" ({it['_plabel']})" if it.get("_plabel") else ""
            b = f"[{len(blocks)+1}] {it['title']}{tag} ({it.get('source','')})"
            if it.get("body"):
                b += f"\n발췌: {it['body']}"
            if total + len(b) > MAX_PROMPT:
                if g != "main":
                    continue          # 희귀 그룹은 한 건이 너무 길면 건너뛰고 다음(짧은) 건을 시도
                break
            if g == "main" and main_used + len(b) > main_cap:
                break
            blocks.append(b); total += len(b)
            if g == "main":
                main_used += len(b)

    base = 명령.replace("{주제}", topic).replace("{목록}", "\n\n".join(blocks))
    if prev_summary:
        base = ("아래 [이전 보고]는 직전에 이미 보낸 브리핑이다. 반드시 지켜라:\n"
                "1) 이전 보고에서 이미 다룬 사안은 ★원칙적으로 생략★하라. 중대한 새 전개가 있을 때만 맨 끝에 '(갱신)' 표시로 딱 한 줄. 두 줄 이상 쓰면 실패다.\n"
                "2) 지면은 이전 보고 '이후' 새로 등장한 것에만 써라. 같은 사건 재정리 금지.\n"
                "3) 이전과 견줘 의미 있는 새 내용이 사실상 없으면, 설명 없이 정확히 'NO_UPDATE' 한 단어만 출력하라.\n\n"
                f"[이전 보고]\n{prev_summary}\n\n--------\n\n" + base)
    # 강한 모델(2.5 Pro)부터, 한도/실패면 Gemini가 알아서 낮은 모델로 자동 강등
    return gemini(base, [요약모델, 보조모델] + 폴백모델목록)


def status_line(stat):
    ko = stat.get("ko", 0); zh = stat.get("zh", 0); ru = stat.get("ru", 0)
    ja = stat.get("ja", 0)
    rs = stat.get("rss", 0); ns = stat.get("naver_state", "off"); nv = stat.get("naver", 0)
    sn = stat.get("sns", 0)
    xp = stat.get("expand", 0)
    if ns == "off":
        nav = "네이버 –"          # 미설정
    elif ns == "err":
        code = stat.get("naver_err", "")
        nav = f"네이버 ✗({code})" if code else "네이버 ✗"   # API 오류(코드)
    else:
        nav = f"네이버 {nv}"
    ok = (ko + zh + ru + ja + rs + nv > 0) and ns != "err"
    head = "✅ 동작 정상" if ok else "⚠️ 점검 필요"
    deep = f" | 심층 +{xp}" if xp else ""
    sns = f"·SNS {sn}" if sn else ""
    jap = f"·일본 {ja}" if ja else ""
    eng = f" | 분석 {_BRIEF_ENGINE}" if _BRIEF_ENGINE else ""
    return f"{head} | 검색: 한국 {ko}·{nav}·중국 {zh}·러시아 {ru}{jap}·RSS {rs}{sns}{deep}{eng} | 요약 ✓"


def _chunk(text, limit):
    """줄 경계로 잘라 각 조각이 limit 이하가 되게. (HTML 태그는 한 줄 안에 있으므로 안전)"""
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                       # 한 줄이 너무 길면 강제 분할
            if cur:
                out.append(cur); cur = ""
            out.append(line[:limit]); line = line[limit:]
        add = ("\n" + line) if cur else line
        if len(cur) + len(add) <= limit:
            cur += add
        else:
            out.append(cur); cur = line
    if cur:
        out.append(cur)
    return out


def _fmt(text):
    """본문을 안전하게 escape한 뒤, AI가 표시한 강조만 텔레그램 HTML 태그로 변환.
       **굵게** → <b>, __기울임__ → <i>. (줄을 넘는 강조는 변환 안 함 → 메시지 분할 시 태그 안 깨짐)"""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<i>\1</i>", t)
    return t


def keyword_message(auto):
    """검색 키워드를 고정/변동으로 나눠 한 메시지로."""
    L = ["🔑 <b>검색 키워드</b>"]
    L.append(f"[고정·한국어 {len(검색어목록)}] " + html.escape(", ".join(검색어목록)))
    if 중국검색 and 중국어검색어목록:
        L.append(f"[고정·중국어 {len(중국어검색어목록)}] " + html.escape(", ".join(중국어검색어목록)))
    if 러시아검색 and 러시아어검색어목록:
        L.append(f"[고정·러시아어 {len(러시아어검색어목록)}] " + html.escape(", ".join(러시아어검색어목록)))
    rss = 추가RSS목록 + 소셜RSS목록
    if rss:
        L.append(f"[고정·RSS {len(rss)}] " + html.escape(", ".join(rss)))
    if auto:
        L.append(f"[변동·자동 {len(auto)}] " + html.escape(", ".join(auto)))
    else:
        L.append("[변동·자동 0] 아직 없음 — 정세 따라 자동 추가/삭제돼요")
    return "\n".join(L)


def build_messages(topic, items, digest, stat=None, prefix="", lead=None):
    """길면 여러 메시지로 나눠 보냄. '취재·조사 지침'은 앞부분과 분리해서 보냄."""
    now_kst = now_utc() + datetime.timedelta(hours=9)
    status = (status_line(stat) + "\n") if stat is not None else ""
    head = (f"{status}{prefix}📰 <b>[{html.escape(topic)}] "
            f"{now_kst.strftime('%m-%d %H:%M')} KST</b> (자료 {len(items)}건)\n\n")

    def line(i, it):
        t = html.escape(it["title"]); u = html.escape(it["link"], quote=True)
        s = html.escape(it.get("source", ""))
        pub = it.get("pub"); when = ""
        if pub:
            try:
                when = "(" + (pub + datetime.timedelta(hours=9)).strftime("%m-%d %H:%M") + ") "
            except Exception:
                when = ""
        return f'{i+1}. {when}<a href="{u}">{t}</a>' + (f" - {s}" if s else "")
    links = [line(i, it) for i, it in enumerate(items)][:링크표시최대]
    linkblock = ("\n\n📎 <b>주요 최신 자료</b> (괄호=보도 시각, KST)\n" + "\n".join(links)) if links else ""

    # 순서: 자료(링크) 먼저 → 단신·접경 → [취재지침]을 맨 마지막에 (텔레그램에선 마지막 메시지가 바로 보임)
    idx = digest.find("[취재")
    if idx > 0:
        parts = [head + (linkblock.lstrip("\n") if linkblock else "(링크 없음)"),
                 _fmt(digest[:idx].rstrip()),
                 _fmt(digest[idx:].strip()) + COMMAND_HELP]
    else:
        parts = [head + (linkblock.lstrip("\n") if linkblock else ""),
                 _fmt(digest) + COMMAND_HELP]

    chunks = []
    for L in (lead or []):           # 맨 앞에 붙일 메시지(예: 키워드 목록)
        chunks.extend(_chunk(L, TG_LIMIT - 16))
    for p in parts:
        chunks.extend(_chunk(p, TG_LIMIT - 16))
    n = len(chunks)
    if n > 1:
        chunks = [f"({i+1}/{n}) " + c for i, c in enumerate(chunks)]
    return chunks


# ---------- 명령 ----------
def parse_command(text):
    raw = text.strip()
    t = raw.lstrip("/").replace(" ", "").lower()
    if any(k in t for k in ["도움말", "사용법", "명령어", "help", "start", "commands"]):
        return ("help", None)
    if "검색어" in t or "키워드" in t or "keyword" in t:
        if any(k in t for k in ["초기화", "리셋", "전부삭제", "모두삭제", "reset", "clear"]):
            return ("kwreset", None)
        if any(k in t for k in ["빼", "삭제", "제거", "지워", "지우", "remove", "del"]):
            r = raw
            for w in ["/", "검색어", "키워드", "keyword", "목록", "에서", "좀", "줘",
                      "빼줘", "빼기", "빼", "삭제해", "삭제", "제거해", "제거", "지워줘", "지워", "지우기", "지우", "remove", "del"]:
                r = r.replace(w, " ")
            terms = [x.strip() for x in r.split(",") if x.strip()] if "," in r else ([r.strip()] if r.strip() else [])
            return ("kwremove", terms)
        return ("kwlist", None)
    if any(k in t for k in ["재개", "다시보내", "다시시작", "resume", "켜"]):
        return ("resume", None)
    if any(k in t for k in ["일시중지", "정지", "그만", "멈춰", "멈춤", "중지", "쉬어", "쉴게", "pause", "stop"]):
        hours = 24
        if "이틀" in t or "2일" in t:
            hours = 48
        elif "사흘" in t or "3일" in t:
            hours = 72
        elif "일주일" in t or "7일" in t or "한주" in t or "week" in t:
            hours = 168
        return ("pause", hours)
    # 주제 요약: "/요약 <주제>" 또는 "○○ 요약해줘"
    if "요약" in raw or "정리" in raw or t.startswith("summary") or t.startswith("요약"):
        topic = raw
        for w in ["/", "요약해서 알려줘", "요약해줘", "요약해", "요약", "정리해줘", "정리해", "정리",
                  "summary", "관련 기사", "관련기사", "에 대해", "에 대한", "알려줘", "최신", "관련", "기사", "해서"]:
            topic = topic.replace(w, " ")
        topic = " ".join(topic.split()).strip()
        if topic:
            return ("digest", topic)
        return ("report_now", None)   # "/요약"만 → 전체 브리핑
    if t in ("보고", "브리핑", "지금보고", "report", "brief", "now") or t.startswith("보고") or t.startswith("브리핑") or t.startswith("report") or t.startswith("brief"):
        return ("report_now", None)
    return (None, None)


def handle_commands(state):
    on_demand = []; report_now = False
    for text in read_commands(state):
        kind, arg = parse_command(text)
        if kind == "help":
            deliver([OWNER], HELP_TEXT)
        elif kind == "resume":
            state["paused_until"] = ""
            deliver([OWNER], "▶️ 다시 시작할게요. 정해진 시간에 알림을 보낼게요.")
        elif kind == "report_now":
            deliver([OWNER], "📰 지금 정세 브리핑을 준비할게요… 잠시만요(1~2분).")
            report_now = True
        elif kind == "kwlist":
            auto = state.get("auto_keywords", [])
            msg = (f"🔎 자동 추가된 검색어 {len(auto)}개:\n" + ", ".join(auto)) if auto \
                  else "🔎 아직 자동 추가된 검색어가 없어요. (다음 정기 보고 때 정세를 보고 보강해요.)"
            deliver([OWNER], msg + f"\n\n기본 검색어는 {len(검색어목록)}개 고정. '/검색어삭제 ○○'로 자동분만 뺄 수 있어요.")
        elif kind == "kwreset":
            state["auto_keywords"] = []; state["auto_kw_updated"] = ""
            deliver([OWNER], "🧹 자동 추가 검색어를 모두 비웠어요. 다음 보고 때 다시 학습해요.")
        elif kind == "kwremove":
            auto = state.get("auto_keywords", [])
            tgts = [t.replace(" ", "") for t in (arg or []) if t.strip()]
            removed, keep = [], []
            for kw in auto:
                norm = kw.replace(" ", "")
                if tgts and any(tt and tt in norm for tt in tgts):
                    removed.append(kw)
                else:
                    keep.append(kw)
            state["auto_keywords"] = keep
            if removed:
                deliver([OWNER], "🗑 검색어에서 제거: " + ", ".join(removed))
            else:
                deliver([OWNER], "그 검색어를 자동 목록에서 못 찾았어요. '/검색어'로 확인해 주세요.")
        elif kind == "pause":
            state["paused_until"] = (now_utc() + datetime.timedelta(hours=arg)).isoformat()
            deliver([OWNER], f"⏸️ 약 {arg}시간 동안 정기 알림을 멈출게요. ('/재개'로 다시 시작.)")
        elif kind == "digest":
            deliver([OWNER], f"🔎 '{arg}' 자료를 모으는 중이에요… 잠시만요(1~2분).")
            on_demand.append(arg)
    return on_demand, report_now


def is_paused(state):
    if not state.get("paused_until"):
        return False
    try:
        return now_utc() < datetime.datetime.fromisoformat(state["paused_until"])
    except Exception:
        return False


# ---------- 메인 ----------
def run_topic(topic, terms, targets, state=None, mark_seen=True, prefix="", gate=False, regional=True, learn=False, prefetched=None):
    items, stat = prefetched if prefetched is not None else fetch_items(terms, regional=regional)
    if learn:
        _maybe_learn_keywords(state, items)   # 거른 것 말고 '수집한 전체'로 학습
    if state is not None and mark_seen:
        seen = set(state["seen"])
        items = [it for it in items if it["link"] not in seen]
    if not items:
        return 0
    prev = state.get("last_summary", "") if (state and gate) else ""
    digest = summarize(topic, items, prev_summary=prev)

    if gate and len(digest.strip()) < 40 and "NO_UPDATE" in digest.upper():
        if state is not None and mark_seen:
            state["seen"] = sorted(set(state["seen"]) | {it["link"] for it in items})
        print("업데이트 없음 - 전송 생략")
        return 0

    lead = None
    if 키워드열거 and regional:
        auto = state.get("auto_keywords", []) if state else []
        lead = [keyword_message(auto)]
    msgs = build_messages(topic, items, digest, stat=stat, prefix=prefix, lead=lead)
    for m in msgs:
        deliver(targets, m)
        time.sleep(0.4)   # 순서 보장용 약간의 간격
    if state is not None and mark_seen:
        state["seen"] = sorted(set(state["seen"]) | {it["link"] for it in items})
        state["last_summary"] = digest[:3000]
    return len(items)


def _hhmm(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def _in_window(now_kst):
    cur = now_kst.hour * 60 + now_kst.minute
    return _hhmm(주간시작) <= cur < _hhmm(주간종료)


def _due_slot(now_kst, last_slot):
    """오늘 지나간 발송시각 중 아직 안 보낸 가장 최근 슬롯을 반환(크론 지연/누락에도 따라잡기). 없으면 None."""
    passed = [h for h in 발송시각 if h <= now_kst.hour]
    if not passed:
        return None
    slot = now_kst.strftime("%Y-%m-%d-") + str(max(passed))
    return slot if slot != last_slot else None


def _due(state, key, hours, default=True):
    last = state.get(key, "")
    if not last:
        return default
    try:
        return (now_utc() - datetime.datetime.fromisoformat(last)) >= datetime.timedelta(hours=hours) - datetime.timedelta(minutes=10)
    except Exception:
        return default


def breaking_check(new_items):
    """새로 들어온 기사 중 '지금 즉시 알릴 중대·새 속보'가 있는지 판단. 있으면 한 줄, 없으면 None."""
    if not new_items:
        return None
    sample = []
    for it in new_items[:40]:
        s = it.get("title", "")
        if it.get("seed"):
            s += " — " + it["seed"][:80]
        sample.append("- " + s)
    prompt = ("아래는 직전 보고 이후 '새로' 들어온 한반도·동북아 기사다. 정기 보고를 기다리지 않고 지금 즉시 "
              "알릴 만한 '중대하고 새로운' 속보가 있는가? 기준: 핵실험·미사일 발사·정상회담 개최나 취소·고위급 "
              "사망/숙청·무력 충돌·대형 합의·중대한 접경 사건 등. 평범한 논평·해설·반복·후속 보도는 제외. "
              "있으면 **제목** | 한 문장 요지 형식으로 가장 중대한 한 건만, 없으면 정확히 NONE 만 출력.\n\n"
              + "\n".join(sample))
    try:
        resp = gemini(prompt, [보조모델] + 폴백모델목록).strip()
    except Exception as ex:
        print("속보 판단 실패:", ex); return None
    if not resp or resp.upper().startswith("NONE") or (len(resp) < 12 and "NONE" in resp.upper()):
        return None
    return resp


def main():
    if not (TG_TOKEN and GEMINI_KEY and TG_CHATS):
        print("비밀값(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID / GEMINI_API_KEY)이 설정되지 않았어요.")
        return
    _apply_secret_config()   # 모든 기본 정의가 끝난 뒤 주입(덮어쓰기 방지)

    state = load_state()

    if not 검색어목록:   # SECRET_CONFIG 미주입 → 검색 불가. 주인에게 알리고 종료(하루 1회만 알림)
        today = now_kst.strftime("%Y-%m-%d")
        if state.get("cfg_alerted_day") != today:
            try:
                _post_one(OWNER, "⚠️ SECRET_CONFIG 미설정 — 검색어가 비어 있어 보고를 만들 수 없어요. GitHub Secrets에 SECRET_CONFIG를 넣어주세요.", silent=True)
            except Exception:
                pass
            state["cfg_alerted_day"] = today
        save_state(state)
        print("SECRET_CONFIG 없음 → 실행 종료"); return
    register_commands(state)

    # 1) 명령은 매번 확인하고 즉시 처리
    on_demand, report_now = handle_commands(state)
    for topic in on_demand:
        try:
            n = run_topic(topic, [topic], [OWNER], state=None, mark_seen=False,
                          prefix="🙋 요청하신 ", regional=False)
            if n == 0:
                deliver([OWNER], f"🙋 '{topic}' 관련 최근 자료를 찾지 못했어요.")
        except Exception as ex:
            print("요청 처리 실패:", ex)
            deliver([OWNER], f"⚠️ '{topic}' 처리 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")

    if report_now:   # /보고 → 지금 즉시 전체 브리핑(요청자에게만, 정기 일정엔 영향 없음)
        try:
            eff = 검색어목록 + state.get("auto_keywords", [])
            n = run_topic(표시제목, eff, [OWNER], state=state, mark_seen=False,
                          gate=False, regional=True)
            if n == 0:
                deliver([OWNER], "지금은 새로 모을 자료가 거의 없어요. 잠시 후 다시 시도해 주세요.")
        except Exception as ex:
            print("즉시 보고 실패:", ex)
            deliver([OWNER], "⚠️ 브리핑 생성 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")

    if is_paused(state):
        print("정지 기간 - 정기/속보 생략")
        save_state(state); return

    now_kst = now_utc() + datetime.timedelta(hours=9)
    force = os.environ.get("FORCE_DIGEST", "") == "1"

    # 2) 검색(점검) 주기가 아니면 대기 (명령만 처리하고 끝)
    if not force and not _due(state, "last_search_ts", 검색간격시간):
        print("검색 주기 아님 - 대기"); save_state(state); return

    due_slot = _due_slot(now_kst, state.get("last_digest_slot", ""))
    inwin = _in_window(now_kst)
    is_digest = bool(force or due_slot)   # 이번 실행이 '정기 보고'인가

    # 보고 작업 시작 기록(무음, 첫 번째 봇=OWNER에게만). 실제 실행 시각을 남겨 스케줄 동작을 눈으로 확인.
    if is_digest:
        slot_h = due_slot.split("-")[-1] if due_slot else ""
        tag = (f"{slot_h}시 정기 보고" if due_slot else ("수동 보고" if force else "보고"))
        try:
            _post_one(OWNER, f"🟢 작업 시작 · {now_kst.strftime('%m-%d %H:%M')} KST · {tag}", silent=True)
        except Exception:
            pass

    # 3) 뉴스 검색 1회. 정기 보고면 깊게, 평소 점검이면 가볍게(본문·심층 생략 → 빠르고 저렴)
    effective_terms = 검색어목록 + state.get("auto_keywords", [])
    try:
        items, stat = fetch_items(effective_terms, regional=True,
                                  bodies=is_digest, deep=is_digest,
                                  auto_feeds=state.get("auto_sources", []))
    except Exception as ex:
        print("검색 실패(다음 주기 재시도):", ex); save_state(state); return
    state["last_search_ts"] = now_utc().isoformat()
    if is_digest:
        _maybe_learn_keywords(state, items)   # 키워드 자동 정리는 정기 보고 때만
        _maybe_learn_sources(state)           # 소스 자동 발굴·검증(주 1회)
        _maybe_check_sanctions(state)         # 유엔·미국·EU 대북 제재 신규 지정 감시(하루 1회)
        _maybe_check_quake(state)             # 풍계리 인근 지진(핵실험 조기 신호, 6시간마다)
        _maybe_comtrade(state)                # (키 있으면) 북중 월간 교역액
    seen = set(state.get("seen", []))
    new_items = [it for it in items if it["link"] not in seen]

    try:
        if is_digest:
            # 정기 보고 (08·11·15·21시 중 아직 안 보낸 슬롯), 또는 수동 실행
            n = run_topic(표시제목, effective_terms, TG_CHATS, state=state, mark_seen=True,
                          gate=True, regional=True, prefetched=(items, stat))
            if due_slot:
                state["last_digest_slot"] = due_slot
            print(f"정기 보고 전송: {n}건 (slot={due_slot})")
        elif 속보허용 and new_items:
            alerted = set(state.get("alerted", []))
            pending = [it for it in new_items if it["link"] not in alerted]
            head = breaking_check(pending) if pending else None
            if head and inwin:
                # 주간 + 중대 속보 → 정기 시각 안 기다리고 즉시 전체 보고(이번엔 깊게 다시 수집)
                deep_items, deep_stat = fetch_items(effective_terms, regional=True)
                n = run_topic(표시제목, effective_terms, TG_CHATS, state=state, mark_seen=True,
                              gate=True, regional=True, prefetched=(deep_items, deep_stat))
                print(f"속보 즉시 보고: {n}건")
            elif head and 심야속보:
                # 창 밖(심야·새벽) + 중대 속보 → 메시지 1개, 무음
                msg = (f"🌙🚨 <b>심야 속보</b> ({now_kst.strftime('%m-%d %H:%M')} KST)\n"
                       + _fmt(head) + "\n\n자세한 내용은 다음 정기 보고에 정리해 드릴게요.")
                deliver(TG_CHATS, msg, silent=True)
                state["alerted"] = (list(alerted) + [it["link"] for it in pending])[-800:]
                print("심야 속보 무음 전송")
            else:
                print("중대 속보 없음 - 점검만")
        else:
            print("정기 시각 아님 - 점검만")
    except Exception as ex:
        print("전송 처리 실패(다음 주기 재시도):", ex)
    save_state(state)


if __name__ == "__main__":
    main()
