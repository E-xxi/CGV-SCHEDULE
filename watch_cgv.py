"""
CGV 센텀시티 IMAX '오디세이' 예매 오픈 감시 스크립트

- 참고: https://github.com/0w0i0n0g0/cgv-open-push (CGV 예매 오픈 알리미, AGPL-3.0)
  위 오픈소스 프로젝트의 API 엔드포인트/헤더/극장 코드 구조를 그대로 활용했습니다.
- CGV 공식 API가 아니라 웹 예매 페이지가 내부적으로 호출하는 비공개 API를 사용합니다.
  CGV가 앱/웹을 개편하면 이 스크립트도 함께 깨질 수 있습니다.

동작 방식
1) 센텀시티 IMAX관의 "전체 상영 스케줄"을 가져온다 (특정 영화로 좁히지 않음).
2) 응답 안에서 영화명에 '오디세이'가 포함되고, 상영일이 TARGET_PLAY_YMD와
   일치하는 항목이 있는지 찾는다.
3) 처음 발견되는 순간(state.json에 아직 notified가 안 찍혀 있을 때) 텔레그램으로 알림을 보낸다.
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET

STATE_FILE = "state.json"

CGV_URL = "http://ticket.cgv.co.kr/CGV2011/RIA/CJ000.aspx/CJ_TICKET_SCHEDULE_TOTAL_PLAY_YMD"

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Origin": "http://ticket.cgv.co.kr",
    "Referer": "http://ticket.cgv.co.kr/Reservation/Reservation.aspx",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

# 센텀시티 IMAX관 필터. 특정 영화 코드를 지정하지 않고(=nG6tVgEQPGU2GvOIdnwTjg== 는
# "전체/미지정"을 뜻하는 값) IMAX관에서 상영되는 모든 스케줄을 가져온 뒤,
# 그 안에서 영화 제목으로 직접 걸러낸다.
CENTUM_IMAX_PAYLOAD = {
    "REQSITE": "x02PG4EcdFrHKluSEQQh4A==",
    "TheaterCd": "2jX4VAQPhAUY/gxvZBhDdQ==",       # CGV 센텀시티
    "ISNormal": "ECFppiyFz/nvSGsg7VwPQw==",
    "MovieGroupCd": "nG6tVgEQPGU2GvOIdnwTjg==",      # 영화 미지정 = 전체
    "ScreenRatingCd": "kXwoR3tnLM/+Tu0BILP3Qg==",    # IMAX
    "MovieTypeCd": "nG6tVgEQPGU2GvOIdnwTjg==",
    "Subtitle_CD": "nG6tVgEQPGU2GvOIdnwTjg==",
    "SOUNDX_YN": "nG6tVgEQPGU2GvOIdnwTjg==",
    "Third_Attr_CD": "nG6tVgEQPGU2GvOIdnwTjg==",
    "Language": "zqWM417GS6dxQ7CIf65+iA==",
}

TARGET_MOVIE_KEYWORD = "오디세이"
TARGET_PLAY_YMD = "20260916"  # YYYYMMDD, 확인하고 싶은 상영일


def fetch_schedule_xml() -> str:
    resp = requests.post(
        CGV_URL, headers=HEADERS, json=CENTUM_IMAX_PAYLOAD, verify=False, timeout=15
    )
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    data = json.loads(text)
    return data["d"]["DATA"]  # 실제 내용은 XML 문자열로 들어있음


def parse_rows(xml_string: str):
    """
    태그 구조를 정확히 몰라도 되도록, MOVIE_NM과 PLAY_YMD를
    동시에 자식으로 가진 요소를 전부 찾아서 (영화명, 상영일) 쌍의 리스트로 반환.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        # 최상위가 여러 형제 요소로만 구성돼 파싱 에러가 나는 경우 감싸서 재시도
        root = ET.fromstring(f"<root>{xml_string}</root>")

    rows = []
    for elem in root.iter():
        movie_nm_elem = elem.find("MOVIE_NM")
        play_ymd_elem = elem.find("PLAY_YMD")
        if movie_nm_elem is not None and play_ymd_elem is not None:
            rows.append(((movie_nm_elem.text or "").strip(), (play_ymd_elem.text or "").strip()))
    return rows


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"notified": False}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_telegram_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()


def main():
    xml_string = fetch_schedule_xml()
    rows = parse_rows(xml_string)

    debug = "--debug" in sys.argv

    if debug:
        print("=== 원본 응답 앞부분 3000자 ===")
        print(xml_string[:3000])
        print()
        print(f"=== 파싱된 (영화명, 상영일) 총 {len(rows)}건 ===")
        for movie_nm, play_ymd in rows[:50]:
            print(f"  {play_ymd}  {movie_nm}")
        print()
        print(f"'{TARGET_MOVIE_KEYWORD}' 포함 여부:", TARGET_MOVIE_KEYWORD in xml_string)
        return

    state = load_state()

    matched = [
        (movie_nm, play_ymd)
        for movie_nm, play_ymd in rows
        if TARGET_MOVIE_KEYWORD in movie_nm and play_ymd == TARGET_PLAY_YMD
    ]

    if matched and not state.get("notified"):
        message = (
            f"CGV 센텀시티 IMAX '{TARGET_MOVIE_KEYWORD}' {TARGET_PLAY_YMD} "
            f"예매가 열린 것으로 보입니다!\n"
            f"바로 예매 페이지를 확인하세요:\n"
            f"http://ticket.cgv.co.kr/Reservation/Reservation.aspx"
        )
        send_telegram_message(message)
        state["notified"] = True
        save_state(state)
        print("[알림 전송 완료] state.json을 업데이트했습니다.")
    elif matched:
        print("이미 알림을 보낸 상태입니다 (state.notified = true).")
    else:
        print(f"아직 {TARGET_PLAY_YMD} '{TARGET_MOVIE_KEYWORD}' 상영 정보가 확인되지 않습니다. "
              f"(총 {len(rows)}건의 스케줄 중 매칭 없음)")


if __name__ == "__main__":
    main()
