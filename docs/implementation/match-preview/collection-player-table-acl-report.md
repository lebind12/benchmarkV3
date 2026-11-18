# CE-ACL: 수집 실행 계정의 개발 선수 정본 접근권한 보완

작성 2026-11-18 12:2x KST. 실행 주체: DeepSeek 구현 워커(task_2125a381656f / ctx_fa037f9a5da3).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, provider `hive`, 추론 강도 `high`
(세션 캐시 projcache에서 확인, 이전 단위와 동일). 하위 워커 0, root `Plans.md` 편집 0.

범위: 계획서 `docs/superpowers/plans/2026-11-18-collection-player-table-acl.md`.
**코드·마이그레이션·검사·승인·계정 변경 0건.** 이 단위는 권한 보완이며 E2E 성공이 아니다.

## 결론

`preview_dev`의 신규 기능 3표에 대해 수집 역할 `postgres`에게 **정확히 SELECT·INSERT·
UPDATE·DELETE**를 부여했다. 부여 전에는 이 3표에 `postgres` 항목이 아예 없어 INSERT가
불가능했고, 그것이 CE-E2E2 자동 생성 실패(`ProgrammingError@section_execution`)의 원인이었다.
변경은 그 3표 ACL에만 국한되며 스키마·기본 ACL·역할 상속·public·계정·데이터는 불변이다.

## 1. 사전 확인 (비밀값 비노출)

- 연결 대상: 원격 `postgres` DB(호스트·계정 식별자는 이 보고서에 쓰지 않는다). 앱 자격의
  `session_user`/`current_user`는 모두 **`postgres`** = 수집 실행 역할.
- 소유자: 세 표 모두 **`preview_dev_app`**. 합법적 소유자 자격(`PREVIEW_DEV_DATABASE_URL`)으로
  접속해 `current_user=preview_dev_app`임을 확인한 뒤 GRANT를 실행했다(우회·권한 상승 없음).
- 사전 권한(`has_table_privilege('postgres', …)`):

| 표 | SELECT | INSERT | UPDATE | DELETE | TRUNCATE | REFERENCES | TRIGGER |
|---|---|---|---|---|---|---|---|
| preview_watch_player_sections | true | **false** | **false** | **false** | false | false | false |
| preview_injury_player_sections | true | **false** | **false** | **false** | false | false | false |
| preview_player_name_candidates | true | **false** | **false** | **false** | false | false | false |

사전 ACL 3건 모두 `{preview_dev_app=arwdDxtm/preview_dev_app, preview_dev_runtime=arwd/preview_dev_app}`
로 **`postgres=` 항목이 없었다.** 비교 대상인 다른 preview 표(`preview_runs`,
`preview_section_results`, `preview_results`, `preview_attempts`, `preview_artifacts`,
`preview_write_audit` 등)는 모두 `postgres=arwd/preview_dev_app`를 갖고 있었다.

## 2. 적용한 변경

소유자 세션에서 **한 트랜잭션**으로 아래 3문만 실행하고 커밋했다(지원 SQL 도구, 새 스크립트
저장 없음 — 임시 실행 파일은 `/tmp`에만 두었고 저장소에 추가하지 않았다).

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_watch_player_sections" TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_injury_player_sections" TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_player_name_candidates" TO postgres;
```

부여 전에 세 표의 `tableowner = preview_dev_app = current_user`를 코드로 검증했고, 불일치하면
중단하도록 했다(실제로 전부 일치).

4개 권한을 고른 이유: SELECT는 정본 재조회·멱등 비교, INSERT는 신규 저장, UPDATE/DELETE는
기존 저장 갱신과 소유 undo 경로의 DML 계약과 맞춘다. 기존 preview 표가 `postgres`에게 준
권한 집합(`arwd`)과 **정확히 같은 모양**이 된다.

## 3. 사후 확인

- `has_table_privilege('postgres', …)` 3표 모두 **SELECT/INSERT/UPDATE/DELETE = true**,
  TRUNCATE/REFERENCES/TRIGGER = **false**(새로 늘지 않음).
- 사후 ACL 3건 모두 `{preview_dev_app=arwdDxtm/preview_dev_app, preview_dev_runtime=arwd/preview_dev_app, postgres=arwd/preview_dev_app}`
  로, 기존 다른 preview 표와 같은 형태다. 소유권(`preview_dev_app`)은 그대로다.

### 불변 경계(전후 지문 대조)

전후 스냅숏의 SHA256: before `6a665c63…c0ce`, after `13050b5e…ac3a`.

| 항목 | 결과 |
|---|---|
| `preview_dev` 테이블 ACL 변경 | **정확히 3표만** 변경(watch / injury / candidates) |
| 스키마 ACL(`preview_dev`, `public`) | 변경 없음 |
| 역할 멤버십·`inherit_option` | 변경 없음 |
| 기본 ACL(`pg_default_acl`) | 변경 없음 |
| 역할 속성(super/inherit/bypassrls/login) | 변경 없음 |
| RLS 설정 | 변경 없음 |
| `public.management_run` 행 수 | 51 → 51 |
| 승인 행 | 7건, 최대 approved_at 2026-11-17T21:52:31Z 그대로 |
| 선수 3표 행 수 | watch 21 / injury 22 / candidates 11 그대로 |
| 실패 run 증거 | `639cb2a0`(원문 34)·`176271d7`(원문 35) 모두 `failed`, `cancelled_at IS NULL`, `failure_detail` 보존 |

- 38000이 쓰는 `preview_dev_runtime`은 `public.fixture` UPDATE=**false** 유지,
  `preview_dev.preview_runs` INSERT=**true** 유지, 선수 표 INSERT도 **true** 유지(변화 없음).
- `public` 테이블(`fixture`, `app_user`, `management_run`)은 소유자가 `postgres` 자신이며
  이번 GRANT로 권한이 바뀌지 않았다(지문 대조에서 `public` 관련 변경 0건).
- 새 계정·비밀번호 변경 0건.

## 4. 하지 않은 일 / 재기동

- 실수집 POST **0회**, 실모델 호출 **0회**, 원문 재생 0회, 데이터 삽입 0회.
- 제품 코드·마이그레이션·검사·새 검증 스크립트 작성 **0건**, 승인 변경 0건.
- **서버 재기동 0회.** 권한은 DB 측 객체이므로 이미 실행 중인 38003(PID 58185)과
  38000(PID 57643)에 재기동 없이 즉시 적용된다(코드·env 불변).
- 즉시 REVOKE는 하지 않았다. 권한은 개발 기능 실행을 위해 유지하며, 되돌림 범위는 아래에 적는다.

## 5. 되돌림 범위 (필요 시)

되돌릴 때는 같은 소유자 자격으로 아래 3문만 실행하면 부여 전 상태로 정확히 복원된다
(당시 `postgres=` 항목이 없었으므로 REVOKE ALL로 원상복구된다).

```sql
REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_watch_player_sections" FROM postgres;
REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_injury_player_sections" FROM postgres;
REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev."preview_player_name_candidates" FROM postgres;
```

되돌리면 CE-E2E2의 실패(선수 섹션 저장 불가)가 재현되므로, E2E3 확인 전에는 되돌리지 않는다.

## 6. 미검증 / 남은 일

- **미검증**: 이 권한으로 수집 경로가 실제로 선수 섹션을 커밋하는지. 이번 단위는 실수집·모델
  0회이므로 **행이 실제로 저장되는 것은 아직 확인하지 않았다.** 다음 E2E3에서 확인해야 한다.
- `ProgrammingError`는 SQLAlchemy가 감싼 **일반 오류 클래스**이고, 보존된 실행 기록에는
  원문 메시지가 없다. 따라서 SQLSTATE `42501`을 직접 관측했다고 주장하지 않는다. **확정된
  것은 "수집 역할의 INSERT 실행 권한 불가"** 이고, 실패 원인이 그 권한 부재라는 연결은
  권한 실측 + 예외 클래스 + 롤백 서명에 근거한 **정황 판정**이다.
- 프로비저닝 자동화(새 환경에서 같은 GRANT를 재현하는 절차)는 만들어 넣지 않았다.
  후속 후보로만 기록한다.

## EDITING STOPPED

제품 코드·검사·마이그레이션·설정 파일 수정 **0건**. 저장소 변경은 이 보고서 1개뿐이다.
DB 변경은 위 3개의 GRANT뿐이며 전후 지문으로 범위를 확인했다. 승인·계정·public 데이터 무변경.
실수집·실모델·서버 재기동 0회. E2E3은 별도 배정 대상이며 이 작업을 E2E 성공으로 표현하지 않는다.
