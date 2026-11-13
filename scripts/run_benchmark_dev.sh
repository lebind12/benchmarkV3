#!/bin/sh
# 통합 로컬 benchmark 앱 기동 (원래 관리·홈·인증 + 프리뷰).
#
# 띄우는 것은 하나의 FastAPI 앱이다: `uvicorn app.main:app`. 원래 benchmark 라우터와
# 프리뷰 라우터가 같은 프로세스에 있다. 별도 프리뷰 서버나 운영 API 프록시가 아니다.
#
# 이 스크립트는 **자동 시작하지 않는다.** 사용자가 직접 실행한다. 기존 프로세스
# 소유를 확인한 뒤 root가 전환한다. 8000/5173/5174 포트 선택을 바꾸지 않는다.
#
# 접속 자격 증명은 **원래 benchmark DATABASE_URL 하나**다. 그 계정의 기존 전체
# 읽기·쓰기 권한을 그대로 쓴다. 이 스크립트는 다른 DSN으로 DATABASE_URL을
# 덮어쓰지 않고, 프리뷰용 DSN 다섯 개를 요구하지도 않는다. 새 역할/GRANT도 없다.
#
# 비밀값은 저장소 밖 0600 파일에서 읽어 프로세스 환경으로만 넘긴다. 값을 출력하지
# 않는다. 파일이 없거나 권한이 넓으면 기동하지 않는다.
#
#   PREVIEW_CREDENTIALS_FILE              기본 ~/.config/match-preview/preview-dev.env
#   PREVIEW_MODEL_CREDENTIALS_FILE        기본 ~/.config/match-preview/model-live.env
#
# 기대 키(값은 여기 없다):
#   원격 DB(같은 운영 DB) 기준
#     DATABASE_URL                       원래 benchmark 연결. 앱·인증·프리뷰 공통.
#     PREVIEW_ALLOW_NONLOCAL_DB          비루프백 대상 명시 동의(값 그대로 사용)
#   로컬 프로필
#     LOCAL_DEV_AUTH_ENABLED=true        로컬 인증 adapter 사용(원격 세션 쓰기 없음)
#     JWT_SECRET_KEY                     로컬 전용 서명키(운영 키와 분리)
#     AUTH_COOKIE_NAME / AUTH_COOKIE_SECURE / AUTH_COOKIE_SAMESITE
#     CORS_ALLOW_ORIGINS                 로컬 출처만. Origin 검사는 끄지 않는다.
#     WORKER_SCHEDULER_ENABLED=false     수집 scheduler 자동 시작 없음
#
# 자동 migration 없음: 이 스크립트는 alembic을 실행하지 않는다.
set -eu

CREDENTIALS="${PREVIEW_CREDENTIALS_FILE:-$HOME/.config/match-preview/preview-dev.env}"
MODEL_CREDENTIALS="${PREVIEW_MODEL_CREDENTIALS_FILE:-$HOME/.config/match-preview/model-live.env}"

if [ ! -f "$CREDENTIALS" ]; then
  echo "missing credentials file: $CREDENTIALS" >&2
  exit 1
fi

perms=$(stat -f '%Lp' "$CREDENTIALS" 2>/dev/null || stat -c '%a' "$CREDENTIALS")
if [ "$perms" != "600" ]; then
  echo "refusing credentials file with mode $perms (expected 600): $CREDENTIALS" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$CREDENTIALS"
set +a

# 선택: 모델(Vertex) 설정. 파일이 없으면 설정 없이 기동하고 생성 경로는 열리지 않는다
# (모의 응답으로 본문을 채우지 않는다). 다른 파일의 DSN을 덮어쓰지 않는다.
if [ -f "$MODEL_CREDENTIALS" ]; then
  model_perms=$(stat -f '%Lp' "$MODEL_CREDENTIALS" 2>/dev/null || stat -c '%a' "$MODEL_CREDENTIALS")
  if [ "$model_perms" != "600" ]; then
    echo "refusing model credentials file with mode $model_perms (expected 600): $MODEL_CREDENTIALS" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  . "$MODEL_CREDENTIALS"
  set +a
fi

# 원래 benchmark 연결. **덮어쓰지 않는다.**
# 기본값을 만들거나 fixture 전용 계정으로 바꾸지 않는다. 없으면 명확히 실패한다.
DATABASE_URL="${DATABASE_URL:?DATABASE_URL must be set in the credentials file: the original benchmark connection}"

# 원격 대상 동의는 자격 증명 파일에 명시된 값을 그대로 쓴다. 기본값으로 열지 않는다.
PREVIEW_ALLOW_NONLOCAL_DB="${PREVIEW_ALLOW_NONLOCAL_DB:?PREVIEW_ALLOW_NONLOCAL_DB must be set explicitly in the credentials file}"

# 로컬 프로필: 원격 세션 저장소·기존 계정 갱신 없이 같은 계정으로 로그인한다.
LOCAL_DEV_AUTH_ENABLED="${LOCAL_DEV_AUTH_ENABLED:-true}"
JWT_SECRET_KEY="${JWT_SECRET_KEY:?JWT_SECRET_KEY must be set in the credentials file (local signing key, not the production key)}"
AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME:-benchmark_refresh_local}"
AUTH_COOKIE_SECURE="${AUTH_COOKIE_SECURE:-false}"
AUTH_COOKIE_SAMESITE="${AUTH_COOKIE_SAMESITE:-lax}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"

# 수집 자동 시작 없음. 이 프로세스는 worker 소유자가 아니다.
WORKER_SCHEDULER_ENABLED="${WORKER_SCHEDULER_ENABLED:-false}"
# 공개 홈 프리뷰 생성도 이 프로세스에서 자동 실행하지 않는다.
HOME_PREVIEW_ENABLED="${HOME_PREVIEW_ENABLED:-false}"

# 옛 프리뷰 전용 DSN은 더 이상 쓰지 않는다. 자격 증명 파일에 남아 있어도 앱이
# 읽지 않게 명시적으로 지운다(다른 계정으로 분기하는 경로를 남기지 않는다).
unset PREVIEW_DATABASE_URL PREVIEW_DEV_DATABASE_URL 2>/dev/null || true
unset PREVIEW_IDENTITY_DATABASE_URL PREVIEW_FIXTURES_DATABASE_URL 2>/dev/null || true
unset PREVIEW_NAMES_DATABASE_URL PREVIEW_STATS_DATABASE_URL 2>/dev/null || true
unset BENCHMARK_READ_DATABASE_URL 2>/dev/null || true

export DATABASE_URL
export PREVIEW_ALLOW_NONLOCAL_DB
export LOCAL_DEV_AUTH_ENABLED JWT_SECRET_KEY
export AUTH_COOKIE_NAME AUTH_COOKIE_SECURE AUTH_COOKIE_SAMESITE
export CORS_ALLOW_ORIGINS
export WORKER_SCHEDULER_ENABLED HOME_PREVIEW_ENABLED

exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${BENCHMARK_PORT:-8000}"
