# CGV 센텀시티 IMAX '오디세이' 예매 오픈 감시

특정 극장·날짜·특별관(IMAX)의 영화 예매가 열리는 순간을 감지해 디스코드로 알려줍니다.

- 감시 대상 기본값: **CGV 센텀시티(0089) / IMAX / '오디세이' / 2026-09-16**
- 새 CGV 사이트(`cgv.co.kr`)가 내부적으로 호출하는 비공개 API(`searchMovScnInfo`)를
  Playwright(헤드리스 크롬)로 가로채서 판단합니다. (구 `ticket.cgv.co.kr` API는 폐기됨)

## ⚠️ 실행 환경 제약

`cgv.co.kr`은 Cloudflare로 **해외/데이터센터 IP를 차단(403)** 합니다.
**한국 IP(집/국내 서버)에서 실행하세요.** GitHub 호스팅 러너(미국)는 대부분 막힙니다.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 사용

```bash
python watch_cgv.py                 # 예매 오픈 확인 + 열렸으면 디스코드 알림
python watch_cgv.py --debug         # 가로챈 회차를 자세히 출력 (알림 안 보냄)
python watch_cgv.py --list-theaters # 극장명 → siteNo 목록
<<<<<<< HEAD
python watch_cgv.py --test-notify   # 디스코드 알림 설정 테스트 (메시지 1건 발송)
python watch_cgv.py --headed        # 브라우저 창 띄워서 확인 (디버깅)
```

## 디스코드 알림 설정

**방법 ① 봇 DM — 내 계정으로 봇이 개인 메시지를 보냄**

1. <https://discord.com/developers/applications> → **New Application** → 좌측 **Bot** → 토큰 **Reset Token** 후 복사 → `DISCORD_BOT_TOKEN`
2. 좌측 **OAuth2 → URL Generator** → scope `bot` 체크 → 생성된 URL로 봇을 **아무 서버에 초대** (내 개인 서버 하나 만들어서 초대하면 됨)
3. 나도 그 서버에 들어가 있고, 서버 설정에서 **"서버 멤버가 보내는 다이렉트 메시지 허용"** 이 켜져 있어야 함
4. 디스코드 **설정 → 고급 → 개발자 모드** 켜고 내 프로필 우클릭 → **사용자 ID 복사** → `DISCORD_USER_ID`
5. `python watch_cgv.py --test-notify` 로 확인

**방법 ② 웹훅 — 특정 채널로 보냄 (더 간단)**

채널 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사 → `DISCORD_WEBHOOK_URL`

=======
python watch_cgv.py --headed        # 브라우저 창 띄워서 확인 (디버깅)
```

>>>>>>> da0162a8a9b92f66865a778a7fb8da3002f49657
### 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
<<<<<<< HEAD
| `DISCORD_BOT_TOKEN` + `DISCORD_USER_ID` | — | 봇 DM 방식 (①) |
| `DISCORD_WEBHOOK_URL` | — | 웹훅 방식 (②). 위 봇 설정이 있으면 무시됨 |
=======
| `DISCORD_WEBHOOK_URL` | (필수) | 알림 받을 디스코드 웹훅 URL (채널 설정 → 연동 → 웹후크) |
>>>>>>> da0162a8a9b92f66865a778a7fb8da3002f49657
| `CGV_SITE_NO` | `0089` | 극장 코드 (`--list-theaters`로 확인) |
| `CGV_SITE_NM` | `센텀시티` | 극장명 (표시용) |
| `CGV_MOVIE_KEYWORD` | `오디세이` | 영화명 포함 키워드 |
| `CGV_PLAY_YMD` | `20260916` | 상영일 `YYYYMMDD` |
| `CGV_SCREEN_GRADE_CD` | `03` | 특별관 등급 (`03`=IMAX, `02`=4DX, `04`=SCREENX, 빈 값=전체) |

## 주기적 실행

`state.json`의 `notified`가 `true`가 되면 더 이상 알리지 않습니다. 다시 감시하려면
`{"notified": false}`로 되돌리세요.

- **국내 머신 cron (권장):** `*/10 * * * * cd /path/to/repo && .venv/bin/python watch_cgv.py`
- **GitHub Actions:** `watch.yml` 참고 — 한국 self-hosted runner 필요.

## 참고

- <https://github.com/0w0i0n0g0/cgv-open-push> (구 사이트용, AGPL-3.0)
- <https://github.com/DongminL/movie_reservation_notification> (신 사이트 API 스키마 참고)
- CGV 공식 API가 아니므로 CGV가 사이트를 개편하면 깨질 수 있습니다.
