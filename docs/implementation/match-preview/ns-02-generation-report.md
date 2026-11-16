# NS-02 선수·부상 섹션 생성·재생성·기존 관리자 검사 UI 구현 보고

## 요약

B 워크트리(`player-section-generation`)에서 `568f2b6` 공통 계약(`dbec891` cherry-pick) 위에 NS-02 선수·부상 섹션 프롬프트, 후처리·재생성 파이프라인, 읽기 전용 관리자 검사 직렬화와 UI를 구현했다. 제한 DB 역할(`preview_dev_runtime`) 기반 B 전용 개발 서버(`38001`·`5174`)를 영속 Orca 터미널로 기동해 상태와 프록시 응답을 확인했다.

## 적용한 Poteto 원칙과 결정

- `poteto-mode`와 `playbooks/feature.md`를 작업 전 읽고 적용했다.
- `principle-modular-architecture`에 따라 후처리·팀 검증·슬롯 배치 로직을 [player_section_processing.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/player_section_processing.py)로 분리하고 [bundle_sections.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/modules/bundle_sections.py)는 호출·오케스트레이션만 담당하게 했다.
- `principle-fail-cleanly`에 따라 미확인 `bool`·원시 모델 ID 신뢰를 금지하고, 한글명 누락을 영문 원문으로 대체하지 않고 `MISSING_NAME_KO` 번역 결함으로 실패 처리했다. 최종 유효 응답 실패 시 첫 응답으로 되돌리지 않고 실패 결과를 반환한다.
- `principle-verify-the-fix` 적용 중 `test_bundle_pipeline.py`에서 `_LazyTeamResolver._names_for(None)` `TypeError`를 발견해 `_SectionScopedResolverProxy`의 기본 팀 범위 보완으로 즉시 수정했다.
- `principle-honest-testing`과 `principle-report-truthfully`에 따라 기존 테스트의 구 계약 불일치와 무인증 환경의 미실행 항목(실제 ADMIN 로그인 후 AI 생성 화면 검사)을 완료로 감추지 않고 그대로 보고한다.
- `typescript-best-practices`에 따라 프론트엔드 진단 타입을 [types.ts](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/types.ts)에 명시하고 `vue-tsc --noEmit`로 확인했다.

## 변경 파일과 버전

공통 파일(`app/preview/player_section_contracts.py`)과 C 소유 저장·레지스트리·마이그레이션 파일은 수정하지 않았다.

- [bundle_players.md](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/prompts/bundle_players.md)와 [bundle_availability.md](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/prompts/bundle_availability.md)는 선수·부상 섹션 모두 `team`과 `korean_labels`를 요구하고 중복·빈 설명 금지를 명시했다.
- [localized_names.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/localized_names.py)에 읽기 전용 색인을 공유하고 가변 상태만 복제하는 `DisplayNames.fork()`를 추가했다.
- [modules/players.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/modules/players.py)는 `bool`의 `int` 오인을 차단하고 `rewrite_reason` 옵션을 추가했다.
- [provider.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/provider.py)는 논리 호출 재생성 시 0부터 이어지는 `attempt_ordinal` 연속성을 위해 `starting_ordinal` 매개변수를 추가했다(`MAX_MODULE_ATTEMPTS=3`과 `send_ledger` 정책 유지).
- [player_section_processing.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/player_section_processing.py)는 원시 JSON 필드 분리, 조기 필터링·절단 전 누락·중복 검사, 팀·경기 문맥 기반 내부 `player_id` 검증, 검증된 내부 ID 기반 `external_player_id` 조회, DB 한글명 우선과 AI `korean_labels` 후보 적용, `MISSING_NAME_KO` 번역 결함 분리, 고정 4슬롯(`home1`..`away2`, `home_etc=None`, `away_etc=None`) 배치, 부상 `status`와 본문(`body == summary == detail`) 유지를 구현했다.
- [bundle_sections.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/modules/bundle_sections.py)는 구현 버전 `mp11-bundle-sections-8`, 프롬프트 버전 `mp11-bundle-players-prompt-4`, `mp11-bundle-availability-prompt-4`로 올리고 섹션 전체 단위 최대 1회 내용 재생성을 연결했다.
- [bundle_pipeline.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/preview/bundle_pipeline.py)는 병렬 섹션 분기마다 `_section_resolver`로 이름 해석기를 격리하고 섹션 요약에 `processing` 진단을 전달한다(`_save_draft` 신규 테이블 저장 미수정).
- [preview_admin.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/app/api/v1/preview_admin.py)는 조회 시 `player_section_processing`을 모델 재호출과 본문 재작성 없이 직렬화한다.
- [PlayerSectionProcessingView.vue](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/PlayerSectionProcessingView.vue), [RunInspector.vue](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/RunInspector.vue), [SectionRunView.vue](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/SectionRunView.vue), [ModuleResultPanel.vue](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/ModuleResultPanel.vue), [types.ts](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/types.ts)는 `"저장 예정 값"`(`persisted=false`), `mock`와 `live` 구분, 채택 시도·재생성 사유·횟수, 고정 4슬롯·`ETC=NULL`, ID와 한글명 출처, 미연결·미배치 사유, 시도별 원문 JSON을 표시한다.
- [test_player_section_processing.py](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/tests/preview/test_player_section_processing.py)와 [PlayerSectionProcessingView.test.ts](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/PlayerSectionProcessingView.test.ts)에 처리·재생성·직렬화·검사 UI 단위 검사를 추가했다.

## 검증 명령과 관측 결과

1. `.venv/bin/python -m pytest tests/preview/test_player_section_processing.py tests/preview/test_provider.py -q`
   - 최종 편집 후 실행 결과 25건 통과(`25 passed, 1 warning`).
2. `.venv/bin/python -m pytest tests/preview/test_bundle_sections.py -k "test_players_split_name_and_reason_per_team or test_players_never_exceed_two_per_team or test_availability_keeps_uncertain_status_and_caps_two_per_team or test_truncated_then_parse_failure_then_ok_sends_exactly_three" -q`
   - 최종 편집 후 실행 결과 4건 통과(`4 passed, 11 deselected, 1 warning`).
3. `cd frontend && npm run test:unit -- src/features/match-preview/PlayerSectionProcessingView.test.ts && npm run type-check`
   - 최종 편집 후 실행 결과 Vitest 3건 통과(`3 passed`)와 `vue-tsc --noEmit` 종료 코드 0.
4. `tests/preview/test_bundle_pipeline.py` 실행 결과(`15 passed, 1 skipped, 1 failed`)
   - `_SectionScopedResolverProxy` 수정 뒤 기존 5건 실패 중 4건이 해소됐다. 남은 1건(`test_bundle_pipeline_saves_section_results_with_bodies`)은 `reader=None`과 DB 스냅샷 부재로 팀명이 `'team 13'`·`'team 4'`만 있을 때, NS-02 팀 검증이 미확인 문자열 `'맨체스터 시티'`를 추측 배치하지 않고 `team_unresolved`로 차단해 발생한다.
5. 참고 관측(기존 파일 변경 전후 비교)
   - `tests/preview/test_bundle_sections.py` 전체는 이전 회차에서 15건 모두 통과했다.
   - `tests/preview/test_bundle_review_fixes.py`의 구 F4 단언 2건(`test_injury_name_not_in_db_keeps_name_without_id`, `test_injury_conflicting_model_player_id_is_dropped_not_guessed`)은 NS-02 이전 계약(한글명 후보 없는 영문 원문 통과, 원시 모델 ID 충돌 시 DB 검증 선수 폐기)을 전제해 실패한다. B 범위 외 파일이므로 수정하지 않았다.
   - 기존 `frontend/src/features/match-preview/RunInspector.test.ts`는 기준 리비전부터 `session.ts`의 인증 토큰 없이 `authenticatedFetch`가 `/api/v1/auth/refresh` 404를 받아 실패(10건)한다. 신규 [PlayerSectionProcessingView.test.ts](file:///Users/woolee/orca/workspaces/benchmark/player-section-generation/frontend/src/features/match-preview/PlayerSectionProcessingView.test.ts)는 `setAccessToken('test-token')`으로 정상 GET 전용 경로를 검증했다.

## B 제한 연결 서버 기동과 확인 상태

`~/.config/match-preview/preview-dev-restricted.env` (`preview_dev_runtime` 제한 DB 역할)를 사용해 B 전용 서버를 영속 Orca 터미널에서 실행 중이다.

- 백엔드 URL `http://127.0.0.1:38001`
  - Orca 터미널 ID `term_06359f9b-5c6c-4f6a-beb2-b61e2359e802` (`B-backend-38001`)
  - 환경 `LOCAL_DEV_AUTH_ENABLED=true`, `BENCHMARK_PORT=38001`, `AUTH_COOKIE_NAME=benchmark_refresh_b`, `CORS_ALLOW_ORIGINS="http://localhost:5174,http://127.0.0.1:5174"`
  - `GET http://127.0.0.1:38001/health` 응답 `200 OK` (`{"status":"ok"}`)
- 프론트엔드 URL `http://127.0.0.1:5174`
  - Orca 터미널 ID `term_6e336f14-b178-4a7d-80b6-d0cf7d766fc0` (`B-frontend-5174`)
  - `GET http://127.0.0.1:5174/` 응답 `200`
  - `GET http://127.0.0.1:5174/api/v1/auth/me` 프록시 응답 `401 Unauthorized` (`{"detail":"로그인이 필요합니다."}`)
  - `GET http://127.0.0.1:5174/api/v1/home/fixtures` 프록시 응답 `200`

## 남은 작업과 제한 사항

- 실제 ADMIN 계정 로그인 후 섹션 실행·실제 AI 응답 검사 화면 확인은 사용자 로그인 자격이 필요해 실행하지 않았다(임의 토큰 우회·무인증 호출 미실행).
- 신규 3표 마이그레이션과 `_save_draft` 영속 저장 연동은 C(`NS-03`) 소유이며, 현재 B UI는 `"저장 예정 값"`(`persisted=false`) 상태로 진단 결과를 표시한다.
