# 생성 변경 릴리스 — 커밋·푸시·운영 배포 (GEN-RELEASE)

작성 2026-11-19. DeepSeek 실행 워커(task_0a0cfd6dea8d / ctx_5cd84c0411db).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 하위 워커 0.
명세 `docs/superpowers/plans/2026-11-19-preview-generation-release.md`.

**사용자 승인 구분.** 2026-11-19 사용자의 생성 범위 릴리스 승인(“생성관련해서는 커밋 푸시
배포 진행”)에 따른 실행이다. 과거 두 경기 홈 표시 조건으로 커밋을 막던 게이트는 **생성
범위에 대해 해제**됐고, Chelsea 홈 링크 선택 불일치는 **별도 후속**이다. 새 생성·수집
호출 승인이 아니다.

## 1. 커밋·푸시

| 항목 | 값 |
|---|---|
| commit | **`017bca2ae67bb4957e81964ae1c9ca3b3edd422d`** |
| 부모 | `f6c7876` |
| branch | `lebind12/preview-api-migration` (upstream 신규 설정) |
| push | 성공, `git ls-remote` = `017bca2ae67b…` **(원격 SHA 동일)** |
| 변경 | 19파일 2296+/62− — 제품6·검사6·보고서7 |

staged만 커밋하지 않고 **검토된 최종 작업트리 버전을 명시 경로로 stage**했다.
root 소유 `collection-home-e2e-report.md`는 stage 제외(미커밋 유지), `refs/backup/rb-review-79a5418`
보존. main 병합·force push·reset·stash·backup 삭제 **0**.
비밀값 스캔: 스테이징 diff와 제품 파일에서 자격 패턴 0건, `.env.example`은 변경 없음.

## 2. 배포 — Koyeb backend

| 항목 | 값 |
|---|---|
| service | `benchmark-v3/api` (`5178062c-1ff2-49a3-a683-e96df3d672cb`) |
| 최종 deployment | **`c431d9a3`** (HEALTHY) |
| archive | CLI 생성(디렉터리), buildpack, `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| APP_REVISION | **`017bca2ae67bb4957e81964ae1c9ca3b3edd422d`** |
| 유지 설정 | tyo/small/1인스턴스/8000/`/health`, 기존 env 24개(secret 참조 포함) 그대로 |
| rollback 대상 | 이전 정상 **`13237d92-1e6f-453f-b4a8-841a2d413255`**, 그 이전 `6b6fbe4f` |

### 배포 중 실제로 발생한 두 실패 (성공으로 덮지 않고 기록)

1. **`60c0443f` ERROR** — 내가 만든 tar에 `./` 루트 엔트리가 있어 Koyeb이
   `Unable to create file: open /builder/workspace: is a directory`로 archive-clone 단계에서
   실패. `./`를 제거한 tar로 재시도했으나 **`b197947b`도 동일 오류**.
2. **전환**: tar 업로드 대신 **CLI가 디렉터리에서 직접 archive를 만들게** 하자
   `96605080` HEALTHY. 다만 이 배포는 `docs/`를 제외한 archive여서 아래 3번 문제를 낳았다.
3. **`recommendations` 500** — 앱이 `docs/spec/schemas/*.json`을 **런타임에 읽는다**
   (`app/schemas/home_preview.py: SCHEMAS = parents[2]/"docs/spec/schemas"`).
   `docs/`를 뺀 archive에서는 `FileNotFoundError`였다. 런타임에 필요한 `docs/spec/schemas`만
   포함해 재배포 → **`c431d9a3` HEALTHY, recommendations 200**.

`APP_REVISION`은 처음 두 번 옛 값 `b2ac969…`가 남아 있었으므로 명시 env로 교정했다.

## 3. 배포 — Vercel frontend

| 항목 | 값 |
|---|---|
| production deployment | `https://benchmark-v3-mrf8m21nj-woolees-projects.vercel.app` |
| 운영 alias | **`https://benchmark-v3-steel.vercel.app`** (Ready, 신규 배포로 승격) |
| build | 원격 Vite build 성공(`✓ built in 10.46s`, Build Completed 30s) |
| rollback 대상 | 직전 production 배포(alias 이전 대상) |

`vercel link`가 `.gitignore`에 `.vercel` 한 줄을 추가했으나 **범위 밖 변경이라 즉시 되돌렸다**
(`git checkout -- .gitignore`). 현재 작업트리는 root 문서 1건 외 깨끗하다.

## 4. 운영 확인 (공개 GET)

| 경로 | 결과 |
|---|---|
| `/health` (backend 직접·프록시) | **200** |
| `/api/v1/home/recommendations` | **200** (수정 후) |
| `/api/v1/home/fixtures/1557474/document` | **200**, run `cf5572b9`, **5섹션 ready** |
| `/api/v1/home/fixtures/1557470/document` | **200**, run `d29d8899`, **5섹션 ready** |

운영 응답의 `section_result_id`가 로컬 검증값과 **정확히 일치**한다:

| workflow | City 1557474 | Chelsea 1557470 |
|---|---|---|
| players | `68db8daf` 392자 | `a4b9ed8e` 367자 |
| availability | `2373310a` 308자 | `189be142` 363자 |
| outlook | `5526dea5` 392자 | `2f7f527b` 353자 |
| odds | `4d10727d` 294자 | `0596cc61` 294자 |
| ai_forecast | `1cc0d93d` 460자 | `5f9387d0` 462자 |

## 5. 사전 호환성 확인 (값 비노출)

- DB: `preview_dev` 스키마에 대해 `postgres`·`preview_dev_app`·`preview_dev_runtime` 모두
  선수 3표(watch/injury/candidates) **INSERT 권한 보유**를 메타데이터로 확인했다.
- 운영 env: `PREVIEW_ENV=prod`·`PREVIEW_COOKIE_SECURE=true`·`PREVIEW_ALLOW_NONLOCAL_DB=true`·
  모델 `vertex`/`gemini-3.5-flash`/`global`·`HOME_PREVIEW_ENABLED=true` 유지.
  **로컬 인증 플래그는 켜지 않았다.**
- migration·GRANT·계정/승인행 수정·기존 테이블 변경·수집/생성/모델 POST **0**.

## 6. 한계·미확인

- **실제 운영 브라우저 화면은 이번에 확인하지 않았다.** 공개 GET으로 5섹션과 ID 일치를
  확인했을 뿐이며, 조정자가 앞서 확인한 §9 기록(관리자 두 문서·City 실홈)을 근거로 인용한다.
  Chelsea 홈 링크가 City를 표시하는 문제는 **별도 후속**으로 남아 있다(이번 수정 범위 아님).
- HTTP 소유자별 수치(`http_owners`) 미영속과 번들 `network_usage` 옛 limit 24는 그대로다.
- 과거 City collection 첫 예외는 **여전히 미확정**이며, 이 릴리스로 해결됐다고 주장하지 않는다.

## 7. 상태

- 새 제품 수정 0(배포는 검증된 커밋 그대로), 새 수집·생성·모델 POST 0.
- 로컬 5173/38000/38003 및 다른 포트 유지. 기존 run 증거 보존.
- 이 보고서는 untracked. 명세 §21에 따라 보고서 후속 커밋은 승인 범위다.
