#!/usr/bin/env bash
#
# watch_cgv.py 를 10분마다 반복 실행한다.
# 예매가 열려서 알림이 한 번 나가면(state.json 의 notified=true) 스스로 종료한다.
#
# 사용:
#   ./run.sh                 # 포그라운드로 실행 (터미널 닫으면 멈춤)
#   caffeinate -s ./run.sh   # 맥이 잠들어도 계속 (전원 연결 시)
#   nohup ./run.sh > /dev/null 2>&1 &   # 백그라운드로
#
# 중지: Ctrl+C  (백그라운드면  pkill -f watch_cgv.py )

set -u
cd "$(dirname "$0")"

INTERVAL="${INTERVAL:-600}"   # 초 단위, 기본 10분
PYTHON=".venv/bin/python"
LOG="watch.log"

# .env 있으면 로드
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "감시 시작 (interval=${INTERVAL}s, site=${CGV_SITE_NO:-0089}, ymd=${CGV_PLAY_YMD:-20260916})"

while true; do
  "$PYTHON" -W ignore watch_cgv.py 2>&1 | tee -a "$LOG"

  # 알림이 나갔으면 종료
  if "$PYTHON" - <<'EOF'
import json, sys
try:
    sys.exit(0 if json.load(open("state.json")).get("notified") else 1)
except Exception:
    sys.exit(1)
EOF
  then
    log "알림 전송 완료 감지 → 감시 종료"
    exit 0
  fi

  sleep "$INTERVAL"
done
