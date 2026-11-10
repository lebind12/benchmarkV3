#!/bin/sh
# 로컬 개발 서버 기동 (운영 계정 읽기 + preview_dev 세션 쓰기).
#
# 자격 증명은 저장소 밖 0600 파일에서 읽는다. 이 스크립트에는 비밀값이 없다.
# 기본 경로: ~/.config/match-preview/preview-dev.env
#   PREVIEW_IDENTITY_DATABASE_URL=...  (기존 계정 public.app_user 읽기 전용)
#   PREVIEW_DEV_DATABASE_URL=...       (preview_dev 세션 쓰기)
#
# 준비: scripts/preview_dev_provision.py 를 한 번 실행한다.
set -eu

CREDENTIALS="${PREVIEW_CREDENTIALS_FILE:-$HOME/.config/match-preview/preview-dev.env}"

if [ ! -f "$CREDENTIALS" ]; then
  echo "missing credentials file: $CREDENTIALS" >&2
  echo "run scripts/preview_dev_provision.py first" >&2
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

# 앱 설정 이름으로 맞춘다. 개발 쓰기 연결과 읽기 전용 연결을 분리해 둔다.
PREVIEW_DATABASE_URL="${PREVIEW_DEV_DATABASE_URL:?PREVIEW_DEV_DATABASE_URL is required}"
PREVIEW_IDENTITY_DATABASE_URL="${PREVIEW_IDENTITY_DATABASE_URL:?PREVIEW_IDENTITY_DATABASE_URL is required}"
# 원격 대상 동의는 자격 증명 파일에 명시된 값을 그대로 쓴다. 기본값으로 열지 않는다.
PREVIEW_ALLOW_NONLOCAL_DB="${PREVIEW_ALLOW_NONLOCAL_DB:?PREVIEW_ALLOW_NONLOCAL_DB must be set explicitly in the credentials file}"
PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB="${PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB:?PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB must be set explicitly in the credentials file}"
# 저장 경기·부상·순위 자료 읽기 전용 연결(별도 좁은 역할). 없으면 조회기가 붙지 않고
# 화면에 stored_access.readable=false가 남는다. 여기서 값을 새로 만들지 않는다.
PREVIEW_FIXTURES_DATABASE_URL="${PREVIEW_FIXTURES_DATABASE_URL:-}"
PREVIEW_ENV="${PREVIEW_ENV:-dev}"
PREVIEW_COOKIE_SECURE="${PREVIEW_COOKIE_SECURE:-false}"
export PREVIEW_DATABASE_URL PREVIEW_IDENTITY_DATABASE_URL
export PREVIEW_FIXTURES_DATABASE_URL
export PREVIEW_ALLOW_NONLOCAL_DB PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB
export PREVIEW_ENV PREVIEW_COOKIE_SECURE

exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PREVIEW_PORT:-8000}"
