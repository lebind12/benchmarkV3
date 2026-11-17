#!/bin/sh
# 수집 전용 프로세스 기동 (프리뷰 38000과 **다른 프로세스**).
#
# 왜 별도 프로세스인가: 수집은 기존 축구 자료와 public.management_run 기록을 갱신하므로
# 기존 수집 자격이 필요하다. 반면 프리뷰 서버(38000)의 제한 자격은 public SELECT와
# preview_dev 쓰기만 갖는다. 한 프로세스에 두 자격을 섞거나, 제한 서버에 광권한 DSN을
# 넣지 않는다. 그래서 프로세스마다 **단일 DATABASE_URL**을 유지한다.
#
# 이 스크립트는 앱을 하나 띄운다: `uvicorn app.main:app`. 엔진·수집기를 새로 만들지 않고
# 같은 코드를 다른 자격·다른 포트로 실행한다.
#
#   기본 포트        38003 (후보). 기동 전에 사용 중이면 실패한다(다른 포트로 몰래 바꾸지 않는다)
#   기본 자격 파일   ~/.config/match-preview/preview-dev.env (기존 수집 후보)
#
# 이 스크립트는 **자동 시작하지 않는다.** 사용자가 직접 실행한다.
# migration은 실행하지 않는다. worker scheduler·자동 홈 프리뷰 생성도 켜지 않는다.
# 비밀값은 파일에서 읽어 프로세스 환경으로만 넘기고, 어떤 값도 출력하지 않는다.
set -eu

CREDENTIALS="${PREVIEW_TEST_COLLECTION_CREDENTIALS:-$HOME/.config/match-preview/preview-dev.env}"
PORT="${PREVIEW_TEST_COLLECTION_PORT:-38003}"
HOST="${PREVIEW_TEST_COLLECTION_HOST:-127.0.0.1}"

if [ ! -f "$CREDENTIALS" ]; then
  echo "missing credentials file: $CREDENTIALS" >&2
  echo "수집 전용 자격 파일(기존 수집 자격)이 필요합니다. 값을 여기서 만들지 않습니다." >&2
  exit 1
fi

perms=$(stat -f '%Lp' "$CREDENTIALS" 2>/dev/null || stat -c '%a' "$CREDENTIALS")
if [ "$perms" != "600" ]; then
  echo "refusing credentials file with mode $perms (expected 600): $CREDENTIALS" >&2
  exit 1
fi

# 포트 소유 확인. 이미 쓰는 프로세스가 있으면 그 포트를 빼앗지 않는다.
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is already in use; refusing to start the collection process" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$CREDENTIALS"
set +a

# 수집 자격은 **원래 수집이 쓰는 연결**이다. 여기서 다른 DSN을 만들지 않는다.
DATABASE_URL="${DATABASE_URL:?DATABASE_URL must be set in the credentials file (existing collection connection)}"
# 비루프백 대상 동의는 파일에 명시된 값을 그대로 쓴다. 기본값으로 열지 않는다.
PREVIEW_ALLOW_NONLOCAL_DB="${PREVIEW_ALLOW_NONLOCAL_DB:?PREVIEW_ALLOW_NONLOCAL_DB must be set explicitly in the credentials file}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:?JWT_SECRET_KEY must be set in the credentials file (same signing key as the preview server)}"

LOCAL_DEV_AUTH_ENABLED="${LOCAL_DEV_AUTH_ENABLED:-true}"
AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME:-benchmark_refresh_local}"
AUTH_COOKIE_SECURE="${AUTH_COOKIE_SECURE:-false}"
AUTH_COOKIE_SAMESITE="${AUTH_COOKIE_SAMESITE:-lax}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"

# 수집 scheduler와 자동 홈 프리뷰 생성은 이 프로세스에서 켜지 않는다.
# 수집은 오직 관리자 시험 요청(POST /preview-test/runs)으로만 시작한다.
WORKER_SCHEDULER_ENABLED=false
HOME_PREVIEW_ENABLED=false

# 모델 설정은 이 프로세스에 넣지 않는다. 수집만 실행은 모델 전송이 0회여야 하며,
# 설정이 없으면 생성 경로가 열리지 않는다(모의 응답으로 대체하지 않는다).
unset PREVIEW_MODEL_LIVE_ENABLED PREVIEW_MODEL_CREDENTIALS_JSON 2>/dev/null || true

export DATABASE_URL PREVIEW_ALLOW_NONLOCAL_DB
export LOCAL_DEV_AUTH_ENABLED JWT_SECRET_KEY
export AUTH_COOKIE_NAME AUTH_COOKIE_SECURE AUTH_COOKIE_SAMESITE
export CORS_ALLOW_ORIGINS
export WORKER_SCHEDULER_ENABLED HOME_PREVIEW_ENABLED

BENCHMARK_PYTHON="${BENCHMARK_PYTHON:-$PWD/.venv/bin/python}"

echo "collection process: host=$HOST port=$PORT (single DATABASE_URL, scheduler off, model off)"
exec "$BENCHMARK_PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
