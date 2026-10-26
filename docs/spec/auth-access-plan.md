# Auth And Access Plan

작성일: 2026-06-06

정책 갱신: 2026-10-24. [결정 기록](../decisions/2026-10-24-streamer-management-and-ax.md), [상세 기획](../../plan.md). 아래 변경은 목표 정책이며 현재 JWT/refresh/공통 서버 역할 검사는 미완성이다.

## Purpose

Phase 3 인증/권한 작업의 구현 계획이다. MVP 범위는 이메일/비밀번호 기반 회원가입, 로그인, access JWT 검증, refresh token rotation/blacklist, role 기반 접근 제어까지다.

기존 `app_user` 테이블을 사용자 원장으로 사용한다. role 값은 `USER`, `STREAMER`, `ADMIN` 세 가지이며 DB CHECK constraint가 이미 적용되어 있다.

## Scope

### In Scope

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- 비밀번호 해시/검증 helper
- access JWT 발급/검증 helper
- refresh token rotation 및 blacklist 저장
- FastAPI dependency:
  - `get_current_user`
  - `require_roles("STREAMER", "ADMIN")` (공통 관리·방송)
  - `require_admin`
- broadcast/admin endpoint의 임시/개별 auth 로직을 공통 dependency로 교체

### Out Of Scope

- 소셜 로그인
- 이메일 인증 메일 발송
- 비밀번호 재설정 플로우
- 사용자 역할 부여·변경 관리 UI (번역 검수 UI는 이번 관리 개발 범위에 포함)
- 다중 기기 세션 관리 UI
- Supabase Auth 연동

## Data Model

기존 `app_user` 컬럼을 사용한다.

| Column | Rule |
|---|---|
| `email` | lowercase normalized, unique |
| `password_hash` | MVP 현재 구현은 stdlib 기반 PBKDF2-HMAC-SHA256. argon2id 전환은 post-MVP 후보 |
| `role` | default `USER`; `STREAMER`/`ADMIN` 변경은 ADMIN 전용 |
| `is_active` | false면 로그인/refresh/API 접근 모두 거부 |
| `email_verified` | MVP에서는 false 허용, post-MVP 이메일 인증에 사용 |
| `last_login_at` | 로그인 성공 시 갱신 |

추가 DB 마이그레이션은 MVP에서 만들지 않는다. refresh token 상태는 AGENTS.md 정책에 따라 Upstash에 저장한다.

## Token Policy

| Token | Storage | TTL | Contents |
|---|---|---:|---|
| access token | client memory/local storage 정책은 FE 결정 | 15분 | `sub`, `role`, `email`, `iat`, `exp`, `jti`, `type=access` |
| refresh token | client, 서버 상태는 Upstash | 14일 | opaque random token 또는 JWT `type=refresh` |

권장 구현은 opaque refresh token이다. 서버는 원문 refresh token을 저장하지 않고 SHA-256 hash를 Upstash key에 저장한다.

Upstash key pattern:

| Key | Value | TTL |
|---|---|---:|
| `{env_prefix}auth:refresh:{token_hash}` | `{user_id, rotated_from, created_at}` | refresh 만료까지 |
| `{env_prefix}auth:blacklist:{jti}` | `1` | access token 남은 TTL |

`env_prefix`는 local 개발 `local:`, production `prod:` 등 환경별로 필수 분리한다. 빈 prefix로 새 키를 만들지 않는다.

Refresh 동작:

1. refresh token hash 조회
2. 없으면 `401 invalid_refresh_token`
3. user active/role 확인
4. 기존 refresh key 삭제 또는 rotated marker 처리
5. 새 access token과 새 refresh token 발급
6. 새 refresh hash 저장

## API Contract

### `POST /api/v1/auth/signup`

Request:

```json
{
  "email": "user@example.com",
  "password": "plain text",
  "nickname": "optional"
}
```

Response `201`:

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "role": "USER",
    "nickname": "optional",
    "is_active": true
  }
}
```

현재 signup/login MVP는 토큰을 발급하지 않고 `user` payload만 반환한다. JWT/refresh 구현이 들어갈 때 로그인 응답의 token contract와 가입 직후 자동 로그인 여부를 FE 정책과 함께 확정한다.

Errors:

- `409 email_already_registered`
- `422 weak_password`

### `POST /api/v1/auth/login`

Request:

```json
{
  "email": "user@example.com",
  "password": "plain text"
}
```

Response `200`: 현재 signup response와 동일한 `user` payload를 반환한다. JWT 도입 후 access/refresh token을 추가한다.

Errors:

- `401 invalid_credentials`
- `403 inactive_user`

### `POST /api/v1/auth/refresh`

Request:

```json
{
  "refresh_token": "..."
}
```

Response `200`:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

### `POST /api/v1/auth/logout`

Request:

```json
{
  "refresh_token": "..."
}
```

Behavior:

- refresh token hash 삭제
- 현재 access token `jti`를 blacklist에 저장
- 이미 삭제된 refresh token이어도 idempotent `204`

### `GET /api/v1/auth/me`

Response `200`:

```json
{
  "id": 1,
  "email": "user@example.com",
  "role": "ADMIN",
  "nickname": "name",
  "is_active": true
}
```

## Access Rules

| Area | Required role |
|---|---|
| 일반 페이지 API | anonymous or `USER` depending endpoint |
| `/api/v1/broadcast/*` | 인증된 `STREAMER` 또는 `ADMIN` |
| `/api/v1/admin/*` 공통 수집 관리·번역 검수 | 인증된 `STREAMER` 또는 `ADMIN` |
| 수집 manual trigger | 인증된 `STREAMER` 또는 `ADMIN` |
| fixture detail의 스트리밍 버튼 | `STREAMER` 또는 `ADMIN`일 때 노출 |

Role hierarchy는 암묵적으로 두지 않는다. 공통 관리와 방송은 두 역할을 명시적으로 허용한다. 사용자 역할 부여 등 ADMIN 고유 권한을 STREAMER에게 확장하는 결정은 아니다. 브라우저 저장값이나 `X-Mock-Role`은 서버 인증의 근거로 사용하지 않는다. 필수 JWT claims·서명·만료·type과 DB의 활성 사용자·현재 role을 검증한다.

## Implementation Tasks

| Task | Files | DoD |
|---|---|---|
| Auth helpers | `app/core/security.py` | password hash/verify 단위 테스트 완료. JWT encode/decode는 후속 |
| Token store | `app/services/auth_tokens.py` | fake Upstash로 refresh rotation 테스트 |
| Auth service | `app/services/auth.py` | signup/login 완료. refresh/logout 비즈니스 로직은 후속 |
| Dependencies | `app/api/deps.py` | `get_current_user`, `require_roles`, `require_admin` |
| Auth router | `app/api/v1/auth.py` | signup/login 완료. refresh/logout/me 통합 테스트는 후속 |
| Route migration | `app/api/v1/broadcast.py`, `app/api/v1/admin.py` | 임시 auth 제거, 공통 dependency 사용 |

## Test Plan

Unit:

- password hash는 원문과 다르고 검증 가능
- 잘못된 password는 false
- access token 만료/변조/잘못된 type 거부
- role dependency가 USER/STREAMER/ADMIN 조합을 정확히 판정
- refresh token hash 저장/조회/삭제/rotation

Integration:

- signup 성공 후 `app_user` row 생성
- 중복 email signup은 409
- login 성공 시 `last_login_at` 갱신
- inactive user login/refresh 거부
- refresh는 기존 refresh token을 재사용 불가하게 만든다
- logout 후 refresh 재사용 불가
- STREAMER·ADMIN은 broadcast와 공통 수집 관리·번역 검수에 접근 가능
- USER는 서버에서 403, 미인증은 401로 거부하며 FE route guard만으로 검증을 대체하지 않음
- fixture detail의 스트리밍 버튼은 STREAMER·ADMIN에게 노출
- 비활성 사용자·만료/변조/필수 claim 누락 token과 X-Mock-Role 권한 우회를 거부

## Migration Notes

현재 broadcast overlay endpoint에는 Phase 3 이전의 로컬 JWT 검증 helper가 있다. Phase 3 완료 시 다음을 제거한다.

- `BroadcastCurrentUser`
- `_decode_verified_jwt_payload`
- `get_broadcast_current_user`

대체:

- `require_roles("STREAMER", "ADMIN")`를 사용하는 공통 current-user dependency

이 교체 후 broadcast endpoint 테스트는 auth dependency override hook을 공통 dependency 기준으로 갱신한다.

## Rollout Order

1. `app/core/security.py` password helper와 signup/login 단위 테스트 (완료: 2026-06-06 local)
2. Upstash token store와 fake store 테스트
3. auth service와 auth router
4. 공통 dependency 도입
5. broadcast/admin route를 공통 dependency로 교체
6. FE 로그인 화면/토큰 저장 정책 결정 후 연동

## 2026-10-25 관리 연결 구현 상태

`app/core/sessions.py`와 auth login/refresh/me/logout, 관리 router dependency에 JWT·Upstash 원자 rotation·DB 현재 역할 검사를 구현했다. 실제 `/admin`은 STREAMER/ADMIN으로 보호하며 cached browser role은 접근 근거로 사용하지 않는다. access는 메모리, refresh는 HttpOnly cookie. 실제 origin/CORS/prefix/서명 키 설정과 스키마 적용은 배포와 별도이며 운영 환경 값은 변경하지 않았다. 세부 계약과 로컬 검증은 `docs/features/streamer-management-api.md` 및 `.verification.md` 참조. 방송 API/MPA의 전체 인증 정합화 완료를 이번 관리 검증으로 대체하지 않는다.
