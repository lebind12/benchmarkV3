# 선수 섹션 저장 계약 v1

2026-11-16 NS-00. 대화의 확정 요구와 Hydrogen 독립 검토를 대조한 조정자 결정이다. 코드나 DDL이 아닌 A/B/C의 공통 구현 명세다. [배치 계획](2026-11-16-player-section-storage.md) §2의 미결정 계약은 이 문서로 고정한다. 충돌 시 사용자 결정과 이 계약이 우선한다.

## 식별과 저장

신규 테이블은 모두 `preview_dev`에 둔다. 테이블명은 `preview_watch_player_sections`, `preview_injury_player_sections`, `preview_player_name_candidates`다. 기존 public 테이블에 FK·트리거·DDL을 추가하지 않는다. public ID는 기존 자료 조회로 검증한다.

두 섹션 테이블 공통 필드:

| 필드 | 의미 |
|---|---|
| section_result_id | 기존 preview_section_results.id, UUID 기본키와 개발 영역 내부 FK. 결과마다 한 행 |
| run_id | 기존 preview_runs.id, UUID·필수·조회 인덱스. 결과의 실제 소유 실행과 일치해야 함 |
| fixture_id | API-Football 외부 경기 ID, 정수·필수. 기존 PreviewRun/FixtureCandidate와 같은 식별 공간 |
| home_team_id / away_team_id | 조회로 확인한 내부 public.team.id, nullable. 외부 팀 ID와 혼용하지 않음 |
| output_contract_version | 해당 섹션의 새 저장·조회 계약 버전, 필수 |
| created_at | 시간대 포함 생성 시각 |

각 테이블은 `home1`, `home2`, `away1`, `away2` 접두사의 고정 컬럼을 갖는다. 아래 목록을 네 자리에 각각 적용한다. 전문은 JSON 배열에만 담지 않는다.

| 자리별 필드 | 의미 |
|---|---|
| player_id | 확인된 내부 public.player.id, 미확인이면 NULL |
| original_name | 모델이 반환한 선수 이름, 채워진 자리에는 필수 |
| name_ko | DB 한글명 또는 같은 최종 응답의 AI 번역 이름, 채워진 자리에는 필수 |
| body | 선수별 설명 전문, 채워진 자리에는 비어 있지 않은 문자열 필수 |
| name_source | db_ko 또는 ai_candidate, 빈 자리는 NULL |
| unresolved_reason | player_id가 NULL인 채워진 자리의 실제 미연결 이유. 연결 성공·빈 자리는 NULL |
| translation_candidate_id | ai_candidate일 때 해당 자리의 개발 영역 후보 ID. db_ko·빈 자리는 NULL |
| evidence | 기존 유효 근거 참조 목록. JSONB 보조 컬럼이며 본문 정본을 대신하지 않음 |

부상 테이블은 자리별 `status`, `injury`, `importance`를 추가해 기존 사실 상태·설명 원문을 보존한다. body는 이 최종 응답의 injury/importance 설명으로 한 번 확정하며 API의 summary/detail도 같은 body를 투영한다. 상태만 있고 설명이 없으면 설명 누락이다. unknown을 confirmed_absence로 승격하지 않는다. 근거 검증 규칙도 보존한다.

주목 선수 테이블에만 `home_etc`, `away_etc` TEXT nullable을 둔다. 현재 두 값은 항상 NULL이다. 부상 ETC 추가는 이번 범위가 아니다.

빈 자리는 자리별 모든 값이 NULL이다. 채워진 자리에서 player_id만 NULL인 경우와 다르다. 별도 slot_status/display_name 중복 저장은 하지 않는다. 공개 display_name은 name_ko, resolution_status는 player_id/미연결 사유에서 결정한다. external_player_id와 사진 URL은 검증된 player_id로 기존 DB를 읽어 구성하며 AI가 준 숫자를 투영하지 않는다. 진단 화면에는 그 외부 ID도 제공한다.

같은 section_result_id의 동일 값 재저장은 같은 결과를 반환한다. 다른 값으로 재저장하려 하면 충돌로 중단한다. 새 생성은 새 결과 ID를 쓴다. run_id/fixture_id/section_result_id의 소유 관계를 저장 경계에서 검증한다. 기존 섹션 이력과 고정 컬럼 저장은 한 트랜잭션으로 성공하거나 실패한다.

## 번역 후보와 소유권

기존 DB에서 확인한 선수의 한글명이 최우선이다. DB 한글명이 있으면 해당 자리에 AI 후보를 만들지 않는다. DB 한글명이 없거나 선수를 확정하지 못하면 같은 최종 AI 응답의 한글명을 미검수 후보로 저장하고 즉시 표시한다. 영어 원문을 한글 번역 완료로 표시하지 않는다. AI 응답 계약에 한글명 후보를 요구하며 사용 가능한 한글명도 얻지 못한 경우 번역 결함을 진단으로 남긴다. 정상 저장 필수값이 없는데 성공 결과를 만들지 않는다.

후보는 이번 단계에서 실행·섹션 결과·자리 소유의 스냅샷이다. 실행 간 이름 문자열 또는 미확인 인물을 자동 병합하지 않는다. 같은 선수라도 서로 다른 섹션 결과는 각자의 후보를 소유한다. 실행 내 동일 자리 재저장만 멱등 처리한다. 후보 공유·검수 후 카드 이름 변경은 NS-06에서 설계한다.

후보 필드는 id(UUID), run_id, section_result_id, workflow_id, slot_key, fixture_id(외부), team_id(확인된 내부 ID 또는 NULL), player_id(확인된 내부 ID 또는 NULL), original_name, candidate_name_ko, source(ai_translation), review_status(pending), created_at이다. section_result_id+slot_key는 유일하다. 부모는 preview_dev 내부 참조만 사용한다. 후보와 자리는 같은 실행·결과·자리 관계여야 하며 FK 순환을 피하는 저장 순서는 구현자가 정한다. 후보 조회에는 원래 섹션 슬롯의 미연결 사유를 연결한다.

설명 body는 생성 당시 전문을 보존한다. 카드 한글명 보정으로 본문을 다시 치환하지 않고 이름 변수 템플릿도 만들지 않는다. 섹션별 이름 해석기는 공유 가변 상태를 변경하지 않도록 분리한다. 표시 이름 우선순위 확정은 본문 사후 재작성과 분리한다.

Undo는 해당 실행이 소유한 새 3개 테이블 데이터와 기존 해당 실행 기록만 대상으로 한다. 기존 승인 또는 다른 실행의 저장 구성본이 참조하는 결과를 삭제하려면 충돌로 중단한다. 삭제 건수·대상 관계와 취소 결과를 남긴다. 기존 public 데이터는 대상이 아니다. 새 후보는 실행 간 공유하지 않으므로 범용 공유 후보 관리 엔진은 만들지 않는다.

## AI 처리와 재생성

모델 ID는 검색 힌트일 뿐이다. 팀·경기 범위의 DB 조회로 선수 ID를 확인하고 bool/원시 정수를 그대로 연결하지 않는다. 홈/원정 배치는 확인된 경기·팀 문맥으로 정한다. 어느 팀인지도 배치할 수 없는 항목은 미배치 진단으로 남기고 임의 홈/원정에 넣지 않는다. 팀은 알지만 선수만 미확인이면 본문·한글명을 정상 보존하고 player_id=NULL로 둔다.

원시 JSON 파싱 후 설명 누락과 동일 선수 중복을 먼저 검사한다. 누락 항목을 버리거나 팀당 두 명으로 자르기 전에 수행한다. 확인된 내부 player_id가 같으면 중복이다. 미확인 항목은 동일 팀의 정규화된 동일 원문/확인된 별칭 근거가 있을 때만 중복으로 처리하며, 이름이 비슷하다는 이유만으로 인물을 합치지 않는다.

첫 유효 응답에 누락/중복이 있으면 해당 섹션 전체의 내용 재생성을 최대 한 번 한다. 선수 한 명만 재질의하거나 다른 섹션을 재생성하지 않는다. 통신/JSON 오류 재시도와 내용 재생성이 같은 logical_call_id·전송 장부를 공유하고 실제 전송은 모듈당 최대 3회다. 시도 번호는 계속 이어져야 하며 동일 run_id/logical_call_id/attempt_ordinal 충돌이 없어야 한다. 구체 함수 인자 형태는 구현자가 정하되 새 논리 ID로 예산을 초기화하지 않는다.

재생성의 마지막 유효 응답만 사용한다. 설명 없는 항목 제거 → 동일 선수 중 설명 있는 첫 항목 보존 → 원래 순서를 유지해 팀당 앞 두 명 배치 순서다. 한 명이면 한 명만 저장하며 자리는 1번부터 채운다. 남은 자리는 NULL, ETC도 NULL이다. 마지막 응답을 파싱하지 못하거나 전송 실패/예산 소진으로 얻지 못하면 기존 실패 계약으로 남긴다. 첫 응답으로 fallback하거나 두 응답을 합쳐 성공 처리하지 않는다.

검사 화면은 각 시도의 원문, 생성 JSON, 내용 재생성 이유·횟수, 최종 채택 시도, 제외/미연결 사유와 네 자리 처리 결과를 연결한다. 새 테이블 연동 전에는 '저장 예정 값'이다. 최종 저장 조회와 모델 재호출을 구분한다.

## 조회·버전·파일 소유권

새 계약 버전은 section_players와 section_availability에만 둔다. 전역 SECTION_RESULT_CONTRACT_VERSION을 올려 다른 섹션 승인을 무효화하지 않는다. 기존 저장 결과는 기존 경로를 유지한다. 신버전 결과는 해당 section_result_id의 새 테이블을 읽고, 행이 없으면 저장 불일치로 노출한다. 기존 payload를 조용히 대신 읽지 않는다. 해당 두 섹션의 실제 bundle 작성/조립 구현 변경도 워크플로우 버전에 반영한다.

새 버전은 관리자 시험/명시 미리보기 대상이다. 기본 공개 문서는 기존 승인 버전·기존 구성본을 보존한다. 사용자 승인은 섹션 워크플로우 단위이며 자동 검사가 대신하지 않는다.

- C 준비: 공통 player_section_contracts.py와 A/B 공유 입력·출력 타입. 두 브랜치가 분기할 기준 커밋을 제공한다.
- A: 새 저장 모델/저장소/후보/마이그레이션, 기존 store.py의 실행 소유 undo와 감사. 새 schema의 정본 저장 구현을 맡는다.
- B: 두 프롬프트/응답 처리/선수 확인/번역/재생성/provider 시도 연속성, 섹션 로컬 resolver 사용. 필요시 bundle_pipeline.py의 resolver 주입 부분만 B가 맡는다. _save_draft 저장 연결은 C 소유이며 B가 선행 구현하지 않는다. 기존 검사 UI/API 변경은 배치 계획 범위대로 맡고 저장 예정 값으로 확인 가능하게 한다.
- C 통합: A/B 편집 종료 후 병합, _save_draft와 새 테이블 조회 투영, registry.py/version_manifest.py, section_structured.py, section_preview.py, home_preview_document.py. B 소유 API/UI 파일은 인계 후 수정한다.
- C 프론트: 기존 목록 외에 실제 렌더링 경로인 frontend/src/components/home-preview/MatchPreviewBody.vue, frontend/src/lib/api/previewView.ts, homePreviewDocument.ts 및 SectionStructuredView.vue의 필요한 연결을 포함한다. 이미지 오류 처리 전면 개편은 하지 않는다.

## DB 및 환경 수용 경계

코드상 public 쓰기 없음과 DB 계정의 public 쓰기 권한 없음은 별도 검사다. 현재 단일 DATABASE_URL 런처는 후자를 보장하지 않는다. 하나의 제한 역할이 public SELECT와 preview_dev 쓰기를 지원해도 요구를 충족하며 반드시 여러 DSN이 필요한 것은 아니다. 기존 권한을 가진 운영 계정의 권한을 자동 변경하지 않는다. 개발 전용 제한 역할/연결이 준비되지 않았으면 실제 연동만 차단으로 남기고 공통 계약·격리 단위 구현은 진행할 수 있다.

최초 연결 전에 비밀값을 노출하지 않고 실제 대상과 필요한 권한을 확인한다. 기존 역할/권한 변경이나 운영 마이그레이션은 이번 준비 배정에 포함하지 않는다. 같은 DB의 preview_dev를 쓰는 원칙은 유지하고 별도 임시 DB에 운영 자료 복제를 요구하지 않는다. 로컬 합성 단위 검사는 파괴적 fixture가 안전하게 허용된 테스트 DB에 한정한다.

A 5173/38000, B 5174/38001, C 준비 5175/38002, C 최종은 A 인계 후 5173/38000이다. 동일 호스트의 쿠키는 포트로 격리되지 않으므로 개발 쿠키 이름은 작업 환경별로 구분한다. 서버와 프론트 프록시는 각 워크트리의 코드만 사용한다.

## 독립 검토 처리 기록

Hydrogen 검토 task_c962009d4799 / ctx_00e79f308bce 완료 보고를 수용한 뒤 조정자가 현재 소스의 ID 통과 경로, provider ordinal과 유일 제약, DB 런처, 버전 manifest 및 실제 카드 파일을 대조했다. 코드 결함의 수정 완료를 의미하지 않는다.

채택: 미검증 ID 제거, 부상 번역 후보 수집, 조기 필터링 전 검사, 연속 시도 번호, 섹션별 resolver 격리, 실제 카드 경로와 버전 추적, 부상 body/summary 일치, 개발 권한 분리 확인, 실행별 후보 소유와 undo 참조 보호.

미채택: 초과 선수를 ETC에 저장, 재생성 실패 시 첫 응답 fallback, 부상 ETC 추가, 영어 원문을 정상 한글명으로 대체. 이는 확정 사용자 요구 또는 현재 범위와 맞지 않는다. 모든 저장·투영 파일을 B로 옮기는 권고도 채택하지 않고 기존 A/B/C 인계를 유지한다. slot_status/display_name/external ID의 중복 저장은 최소 계약에서 제외했다. 사진은 확인된 DB 외부 ID를 조회해 제공한다.
