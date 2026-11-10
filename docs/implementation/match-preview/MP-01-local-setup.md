# MP-01 로컬 개발 환경

MP-01 범위는 관리자 로그인과 빈 실행 목록까지입니다. 이 문서는 그 범위를
다시 시작하는 데 필요한 최소 절차만 적습니다. 운영 DB·배포·외부 API 호출은
포함하지 않습니다.

## 준비물

- Python 3.11 이상
- Node 22 이상, npm
- Docker (격리된 로컬 PostgreSQL 실행용)

호스트에 `psql`이 없어도 됩니다. 아래 컨테이너가 PostgreSQL 17을 제공합니다.

## 1. 로컬 PostgreSQL

포트 게시는 반드시 루프백으로 제한합니다. `-p 55432:5432`처럼 쓰면
`0.0.0.0`과 `[::]`에 함께 열려 같은 네트워크의 다른 호스트에서 접근할 수 있습니다.

```sh
docker run -d --name match-preview-pg-mp01 \
  -e POSTGRES_USER=preview \
  -e POSTGRES_PASSWORD=preview_local_dev \
  -e POSTGRES_DB=preview_mp01_dev \
  -p 127.0.0.1:55432:5432 postgres:17-alpine

docker exec match-preview-pg-mp01 psql -U preview -d postgres -c \
  "CREATE DATABASE preview_mp01_test OWNER preview;"
```

게시 주소는 다음으로 확인합니다. `127.0.0.1:55432->5432/tcp`만 보여야 합니다.

```sh
docker inspect match-preview-pg-mp01 --format '{{json .HostConfig.PortBindings}}'
docker ps --filter name=match-preview-pg-mp01 --format '{{.Ports}}'
```

기존 컨테이너를 루프백으로 다시 묶어야 할 때는 **볼륨을 지우지 않고** 컨테이너만
다시 만듭니다. 아래는 데이터를 보존하는 순서입니다.

```sh
VOL=$(docker inspect match-preview-pg-mp01 --format '{{range .Mounts}}{{.Name}}{{end}}')
docker exec match-preview-pg-mp01 pg_dump -U preview -d preview_mp01_dev > /tmp/mp01_dev_backup.sql
docker stop match-preview-pg-mp01 && docker rm match-preview-pg-mp01
docker run -d --name match-preview-pg-mp01 \
  -e POSTGRES_USER=preview -e POSTGRES_PASSWORD=preview_local_dev \
  -e POSTGRES_DB=preview_mp01 \
  -p 127.0.0.1:55432:5432 -v "$VOL":/var/lib/postgresql/data postgres:17-alpine
```

개발용 DB는 `preview_mp01_dev`, 테스트용 DB는 `preview_mp01_test`로 분리합니다.

## 1-1. 테스트 DB 안전장치

테스트 픽스처는 매 테스트마다 `public` 스키마를 지웁니다. 그래서 대상을 연결 전에
검사합니다(`tests/preview/_dbguard.py`).

- 호스트가 루프백이어야 합니다. `PREVIEW_ALLOW_NONLOCAL_DB`는 테스트에서 **무시**
  됩니다. 애플리케이션용 우회 플래그로 테스트 대상을 바꿀 수 없습니다.
- DB 이름이 `test_*` 또는 `*_test`여야 합니다. `preview_mp01_dev`, `postgres`,
  `template1` 같은 이름은 거부됩니다.
- PostgreSQL URL만 받습니다. SQLite 대체는 거부됩니다.

거부되면 픽스처 오류로 즉시 실패하며 어떤 연결도 열지 않습니다. 다음처럼 개발 DB를
가리키게 해 확인할 수 있습니다.

```sh
PREVIEW_TEST_DATABASE_URL="postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev" \
  .venv/bin/python -m pytest tests/preview -q
# UnsafeTestDatabase 로 실패하고 개발 DB 데이터는 그대로 남습니다.
```

가드 자체의 동작은 DB에 연결하지 않는 테스트로 검사합니다.

```sh
.venv/bin/python -m pytest tests/preview/test_db_isolation.py -q
```

## 2. 백엔드

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

export PREVIEW_DATABASE_URL="postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"
export PREVIEW_ENV=dev
.venv/bin/python -m alembic upgrade head
```

`PREVIEW_DATABASE_URL`이 루프백 주소가 아니면 앱과 마이그레이션이 기동을
거부합니다. 로컬 개발 범위를 벗어난 DB에 실수로 붙지 않게 하려는 장치입니다.

## 3. 개발자 관리자 계정

비밀번호는 저장소에 넣지 않습니다. 실행할 때 입력하거나 표준입력으로 넘깁니다.

```sh
.venv/bin/python scripts/preview_admin.py --email admin@local.test
# 비밀번호를 파이프로 넘길 때
printf '%s\n' "$ADMIN_PW" | .venv/bin/python scripts/preview_admin.py \
  --email admin@local.test --password-stdin
```

이미 있는 계정의 비밀번호를 바꾸려면 `--reset-password`를 붙입니다.
`PREVIEW_ENV=prod`에서는 이 도구가 거부됩니다.

## 4. 서버 실행

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 5. 프론트엔드

```sh
cd frontend
npm install --include=dev
npm run dev
```

`http://127.0.0.1:5173`에서 열립니다. Vite가 `/api`를 `127.0.0.1:8000`으로
프록시하므로 세션 쿠키가 같은 오리진에서 오갑니다.

## 6. 검증 명령

```sh
.venv/bin/python -m pytest tests/preview/test_admin_access.py -q
npm --prefix frontend run test:unit -- src/views/AdminLoginView.test.ts
npm --prefix frontend run type-check
npm --prefix frontend run build
```

E2E는 실제 백엔드와 실제 로컬 DB를 사용합니다. 비밀번호는 환경변수로만
전달합니다.

```sh
cd frontend
PREVIEW_E2E_ADMIN_EMAIL=admin@local.test \
PREVIEW_E2E_ADMIN_PASSWORD="$ADMIN_PW" \
npm run test:e2e -- e2e/preview-access.spec.ts
```
