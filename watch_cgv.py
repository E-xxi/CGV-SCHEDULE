"""
CGV 센텀시티 IMAX '오디세이' 예매 오픈 감시 스크립트 (신 사이트 cgv.co.kr 기준)

■ 왜 새로 썼나
  CGV가 구 예매 사이트(ticket.cgv.co.kr/CGV2011/...)를 완전히 폐기했습니다.
  이제 모든 요청은 이벤트/점검 페이지로 리다이렉트되고, 예매 기능은
  새 사이트(https://cgv.co.kr/cnm/movieBook/cinema)로 옮겨갔습니다.

■ 동작 방식
  1) Playwright(헤드리스 크롬)로 "극장별 상영시간표" 페이지를 연다.
  2) 페이지가 내부적으로 호출하는 비공개 API(searchMovScnInfo) 의 JSON 응답을
     네트워크 레벨에서 가로챈다. (스크립트가 직접 API를 때리는 게 아니라,
     브라우저가 알아서 호출한 응답을 주워 담는 방식 → Cloudflare 쿠키/서명 불필요)
  3) 응답 안에서 영화명에 '오디세이'가 포함되고, 상영일이 TARGET_PLAY_YMD 이며,
     특별관 등급이 IMAX('03')인 회차가 있는지 찾는다.
  4) 처음 발견되는 순간(state.json 에 아직 notified 가 안 찍혀 있을 때)
     디스코드로 알림을 보낸다 (봇 DM 또는 웹훅).

■ 중요한 제약
  cgv.co.kr 은 Cloudflare 뒤에 있어서 한국 외 IP / 데이터센터 IP 는 403 으로 막힙니다.
  즉 GitHub Actions(미국 러너)에서는 동작하지 않습니다. 한국 IP(집/서버)에서 실행하세요.

■ 참고
  - https://github.com/0w0i0n0g0/cgv-open-push (구 사이트용, AGPL-3.0)
  - https://github.com/DongminL/movie_reservation_notification
    (신 사이트 searchMovScnInfo 응답 스키마 / IMAX 등급코드 '03' 확인에 참고)
  - CGV 공식 API 가 아니라 웹 예매 페이지가 내부적으로 호출하는 비공개 API 입니다.
    CGV 가 사이트를 또 개편하면 이 스크립트도 함께 깨질 수 있습니다.

■ 사용법
  python watch_cgv.py               # 예매 오픈 여부 확인 + (열렸으면) 디스코드 알림
  python watch_cgv.py --debug       # 가로챈 회차/응답을 자세히 출력 (알림 안 보냄)
  python watch_cgv.py --list-theaters  # 극장명 -> siteNo 목록을 덤프 (siteNo 를 모를 때)
  python watch_cgv.py --test-notify # 디스코드 알림 설정이 되는지 테스트 메시지 1건 발송
  python watch_cgv.py --headed      # 브라우저 창을 띄워서 눈으로 확인 (디버깅용)

  환경변수로 대상 변경 가능:
    CGV_SITE_NO       극장 코드 (기본값 아래 SITE_NO, 센텀시티 추정치)
    CGV_SITE_NM       극장명 (기본 '센텀시티')
    CGV_MOVIE_KEYWORD 영화명 키워드 (기본 '오디세이')
    CGV_PLAY_YMD      상영일 YYYYMMDD (기본 '20260916')
    CGV_SCREEN_GRADE_CD  특별관 등급코드 (기본 '03'=IMAX, 빈 값이면 등급 상관없이)

  디스코드 알림 (둘 중 하나 설정):
    ① 봇 DM  — 내 계정으로 봇이 개인 메시지를 보냄
       DISCORD_BOT_TOKEN   디스코드 개발자 포털에서 만든 봇 토큰
       DISCORD_USER_ID     내 디스코드 유저 ID (개발자 모드 → 프로필 우클릭 → ID 복사)
       * 봇과 내가 같은 서버에 있어야 하고, 그 서버의 "서버 멤버가 보내는 DM 허용"이 켜져 있어야 함
    ② 웹훅 — 특정 채널로 보냄 (더 간단)
       DISCORD_WEBHOOK_URL 채널 설정 → 연동 → 웹후크 → 새 웹후크
"""

import os
import sys
import json

import requests
from playwright.sync_api import sync_playwright

STATE_FILE = "state.json"

CINEMA_URL = "https://cgv.co.kr/cnm/movieBook/cinema"

# 페이지가 상영 회차를 불러올 때 호출하는 비공개 API 의 URL 조각
API_MARKER = "searchMovScnInfo"

# 센텀시티 극장 코드 (신 사이트 기준, searchAllRegionAndSite 로 확인: "0089").
# 다른 극장을 보려면 --list-theaters 로 코드를 찾아 환경변수 CGV_SITE_NO 로 넘기세요.
# (참고: 왕십리 = '0074')
SITE_NO = os.environ.get("CGV_SITE_NO", "0089")
SITE_NM = os.environ.get("CGV_SITE_NM", "센텀시티")

TARGET_MOVIE_KEYWORD = os.environ.get("CGV_MOVIE_KEYWORD", "오디세이")
TARGET_PLAY_YMD = os.environ.get("CGV_PLAY_YMD", "20260916")  # YYYYMMDD

# 특별관 등급코드: '03' = IMAX (참고 프로젝트에서 확인). 빈 문자열이면 등급 필터 미적용.
SCREEN_GRADE_CD = os.environ.get("CGV_SCREEN_GRADE_CD", "03")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

GOTO_TIMEOUT_MS = 40000
RESPONSE_TIMEOUT_MS = 25000


# ────────────────────────────────────────────────────────────────────────────
# 브라우저로 상영 회차(JSON row) 가로채기
# ────────────────────────────────────────────────────────────────────────────
def _collect_json(url: str, marker: str, headed: bool, debug: bool):
    """
    url 로 이동한 뒤, 그 페이지가 호출하는 XHR 중 marker 를 포함하는 응답들의
    JSON body 를 모아서 (rows, seen_json_urls) 로 반환한다.
    marker 가 빈 문자열이면 cgv.co.kr 로 가는 모든 JSON 응답을 rows 대신
    seen_json_urls 로만 수집한다(--list-theaters 용).
    """
    rows = []
    seen_json_urls = []
    raw_bodies = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=USER_AGENT,
            viewport={"width": 1360, "height": 900},
        )
        page = context.new_page()

        def on_response(resp):
            r_url = resp.url
            if "cgv.co.kr" not in r_url:
                return
            ctype = (resp.headers or {}).get("content-type", "")
            if "json" not in ctype.lower():
                return
            seen_json_urls.append(r_url)
            if marker and marker in r_url:
                try:
                    body = resp.json()
                except Exception:
                    return
                raw_bodies.append((r_url, body))
                data = None
                if isinstance(body, dict):
                    data = body.get("data") or body.get("Data") or body.get("list")
                if isinstance(data, list):
                    rows.extend(x for x in data if isinstance(x, dict))

        page.on("response", on_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        except Exception as e:
            print(f"[경고] 페이지 이동 중 예외(계속 진행): {e}", file=sys.stderr)

        # marker 응답이 도착할 때까지(또는 타임아웃까지) 폴링.
        # wait_for_response 와 달리 goto 이전/도중에 이미 온 응답도 잡힌다.
        waited = 0
        step = 500
        while marker and not raw_bodies and waited < RESPONSE_TIMEOUT_MS:
            page.wait_for_timeout(step)
            waited += step
        # 여러 날짜/여러 XHR 가 이어서 올 수 있으니 잠깐 더 기다린다
        page.wait_for_timeout(2500)
        if marker and not raw_bodies:
            print(
                f"[경고] '{marker}' 응답을 {RESPONSE_TIMEOUT_MS/1000:.0f}초 안에 보지 "
                f"못했습니다. (Cloudflare 차단이거나, 해당 날짜/극장에 편성이 없을 수 있음)",
                file=sys.stderr,
            )

        # Cloudflare 차단 페이지 감지
        try:
            html = page.content()
            if "cloudflare" in html.lower() and "errorPage" in html:
                print(
                    "[에러] Cloudflare 차단 페이지가 떴습니다. 한국 IP 에서 실행 중인지 "
                    "확인하세요. (데이터센터/해외 IP 는 막힙니다)",
                    file=sys.stderr,
                )
        except Exception:
            pass

        browser.close()

    if debug and raw_bodies:
        print("=== 가로챈 원본 응답 (앞 2개, 각 2000자) ===")
        for r_url, body in raw_bodies[:2]:
            print(f"- {r_url}")
            print(json.dumps(body, ensure_ascii=False)[:2000])
            print()

    return rows, seen_json_urls


def fetch_screenings(headed: bool = False, debug: bool = False):
    target = f"{CINEMA_URL}?siteNo={SITE_NO}&siteNm={SITE_NM}&scnYmd={TARGET_PLAY_YMD}"
    rows, _ = _collect_json(target, API_MARKER, headed=headed, debug=debug)
    return rows


# ────────────────────────────────────────────────────────────────────────────
# 매칭 로직
# ────────────────────────────────────────────────────────────────────────────
def row_matches(row: dict) -> bool:
    movie = str(row.get("movNm") or row.get("MOVIE_NM") or "")
    ymd = str(row.get("scnYmd") or row.get("PLAY_YMD") or "")
    grade = str(row.get("tcscnsGradCd") or row.get("SCREEN_RATING_CD") or "")

    if TARGET_MOVIE_KEYWORD not in movie:
        return False
    if ymd and ymd != TARGET_PLAY_YMD:
        return False
    if SCREEN_GRADE_CD and grade and grade != SCREEN_GRADE_CD:
        return False
    return True


def describe_row(row: dict) -> str:
    movie = row.get("movNm") or row.get("MOVIE_NM") or "?"
    ymd = row.get("scnYmd") or row.get("PLAY_YMD") or "?"
    start = row.get("scnsrtTm") or ""
    screen = row.get("scnsEnm") or row.get("SCREEN_NM") or ""
    return f"{ymd} {start} {screen} {movie}".strip()


# ────────────────────────────────────────────────────────────────────────────
# state / discord
# ────────────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"notified": False}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


DISCORD_API = "https://discord.com/api/v10"


def send_discord_message(text: str) -> None:
    """디스코드로 알림 전송.

    - DISCORD_BOT_TOKEN + DISCORD_USER_ID 가 있으면 봇이 내 계정으로 DM 을 보낸다.
    - 아니면 DISCORD_WEBHOOK_URL 로 채널 웹훅 메시지를 보낸다.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    user_id = os.environ.get("DISCORD_USER_ID")
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    content = text[:1990]  # 디스코드 content 2000자 제한

    if token and user_id:
        _send_discord_dm(token, user_id, content)
    elif webhook:
        resp = requests.post(webhook, json={"content": content}, timeout=15)
        resp.raise_for_status()
    else:
        raise RuntimeError(
            "디스코드 알림 설정이 없습니다. "
            "DISCORD_BOT_TOKEN + DISCORD_USER_ID (봇 DM) 또는 "
            "DISCORD_WEBHOOK_URL 중 하나를 설정하세요."
        )


def _send_discord_dm(token: str, user_id: str, content: str) -> None:
    """봇 토큰으로 특정 유저에게 DM 을 보낸다."""
    headers = {"Authorization": f"Bot {token}"}

    # 1) 해당 유저와의 DM 채널 열기(이미 있으면 그대로 반환)
    r = requests.post(
        f"{DISCORD_API}/users/@me/channels",
        headers=headers,
        json={"recipient_id": str(user_id)},
        timeout=15,
    )
    r.raise_for_status()
    channel_id = r.json()["id"]

    # 2) 그 채널에 메시지 전송
    r = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=headers,
        json={"content": content},
        timeout=15,
    )
    r.raise_for_status()


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────
# searchRegnList 응답의 data[*].siteList 에 (siteNo, siteNm) 가 들어있다.
SITE_LIST_MARKER = "searchRegnList"


def run_list_theaters(headed: bool):
    print("극장 목록(searchRegnList)을 가져오는 중입니다...\n")
    rows, urls = _collect_json(CINEMA_URL, SITE_LIST_MARKER, headed=headed, debug=False)

    # 응답 구조: data = [{regnGrpNm, siteList: [{siteNo, siteNm}, ...]}, ...]
    # (일부 응답은 site 가 최상위 row 로 바로 오기도 해서 둘 다 처리)
    sites = []
    for row in rows:
        candidates = row.get("siteList") if isinstance(row.get("siteList"), list) else [row]
        for site in candidates:
            if not isinstance(site, dict):
                continue
            no, nm = site.get("siteNo"), site.get("siteNm")
            if no and nm:
                sites.append((str(no), str(nm)))
    sites = sorted(set(sites))

    if not sites:
        print("극장 목록을 못 받았습니다. Cloudflare 차단(해외/데이터센터 IP)일 수 있습니다.")
        if urls:
            print("관측된 JSON 엔드포인트:")
            for u in sorted(set(urls)):
                print(" ", u)
        return

    print(f"=== CGV 극장 {len(sites)}개 (siteNo  siteNm) ===")
    for no, nm in sites:
        mark = " ←" if "센텀" in nm else ""
        print(f"  {no}  {nm}{mark}")
    print("\n원하는 극장 코드로 실행:  CGV_SITE_NO=<코드> python watch_cgv.py --debug")


def main():
    argv = sys.argv[1:]
    debug = "--debug" in argv
    headed = "--headed" in argv

    if "--list-theaters" in argv:
        run_list_theaters(headed)
        return

    if "--test-notify" in argv:
        send_discord_message("CGV 예매 감시 봇 테스트 메시지입니다. 이게 보이면 알림 설정 정상.")
        print("[테스트 알림 전송 완료] 디스코드를 확인하세요.")
        return

    rows = fetch_screenings(headed=headed, debug=debug)

    if debug:
        print(f"\n=== 가로챈 회차 총 {len(rows)}건 ===")
        for row in rows[:80]:
            mark = "★" if row_matches(row) else "  "
            print(f" {mark} {describe_row(row)}   grade={row.get('tcscnsGradCd')}")
        keyword_hit = any(TARGET_MOVIE_KEYWORD in str(r.get('movNm', '')) for r in rows)
        print(f"\n'{TARGET_MOVIE_KEYWORD}' 포함 회차 존재: {keyword_hit}")
        print(f"대상: siteNo={SITE_NO} ({SITE_NM}), {TARGET_PLAY_YMD}, "
              f"grade={SCREEN_GRADE_CD or '(전체)'}")
        return

    matched = [r for r in rows if row_matches(r)]
    state = load_state()

    if matched and not state.get("notified"):
        sample = "\n".join(f"· {describe_row(r)}" for r in matched[:5])
        message = (
            f"CGV {SITE_NM} IMAX '{TARGET_MOVIE_KEYWORD}' {TARGET_PLAY_YMD} "
            f"예매가 열린 것으로 보입니다!\n{sample}\n\n"
            f"바로 예매 페이지를 확인하세요:\n"
            f"{CINEMA_URL}?siteNo={SITE_NO}&siteNm={SITE_NM}&scnYmd={TARGET_PLAY_YMD}"
        )
        send_discord_message(message)
        state["notified"] = True
        save_state(state)
        print("[알림 전송 완료] state.json 을 업데이트했습니다.")
    elif matched:
        print("이미 알림을 보낸 상태입니다 (state.notified = true).")
    else:
        print(
            f"아직 {TARGET_PLAY_YMD} '{TARGET_MOVIE_KEYWORD}' (IMAX) 상영 정보가 "
            f"확인되지 않습니다. (가로챈 {len(rows)}건 중 매칭 없음)"
        )


if __name__ == "__main__":
    main()
