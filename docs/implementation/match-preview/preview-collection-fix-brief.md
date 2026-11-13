# PC-CONNECT 독립 검토 4건 수정

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽은 전문이 미변경이면 해시로 재사용 근거를 남긴다. 관련 원칙만 추가로 읽고 모델·추론 강도·소유권·적용 원칙을 착수 보고한다. AGENTS.md가 스킬의 검사 확대 권고보다 우선한다.

실제 DeepSeek 구현 작업이다. dsh-tui 프로필의 `deepseek-ai/deepseek-v4.1-flash-1017`/max를 유지하며 전환·하위 워커를 만들지 않는다. 이번은 이미 승인된 PC-CONNECT의 독립 지적 수정이다. 미래 두 경기 API 시험의 새 도구를 만들거나 실제 수집/모델을 호출하는 작업은 아니다.

입력은 `docs/implementation/match-preview/preview-collection-connect-review.md`의 현재 요구 위반1~4와 `preview-collection-connect-brief.md`의 기존 계약이다. 최신 검토는 collection SHA256 8005eb65…84bf, test 56ca1b0e…11a5를 대상으로 했다. 회차/잠금 보완은 보존한다. 과거 failed Dispatch 복구·worker_done 재전송·메일 probe는 하지 않는다. 새 활성 Task/Dispatch만 사용한다.

## 소유권

- `app/services/home_preview_collection.py`
- `app/services/management_runs.py`
- `app/services/worker_runs.py`
- `tests/unit/test_home_preview_collection.py`
- `docs/implementation/match-preview/preview-collection-connect-report.md`

다른 파일은 읽기 전용이다. 생성 서비스·LangGraph·본문/프롬프트·승인 행/버전 계산·모델/마이그레이션·프론트·Plans.md·새 API 시험 도구를 편집하지 않는다. 타인 변경은 원복/stash하지 않는다.

## 수정과 수용 기준

1. **세션 계약:** 실제 기본 배선에서 preview 팩토리를 호출하면 Session이 되게 한 경계를 맞춘다. 현재 wrapper가 sessionmaker를 반환하는데 with에 그대로 들어가 모든 후보가 TypeError로 실패한다. 관리 훅·기본 fallback·승인 조회가 같은 명확한 계약을 쓰도록 최소 수정한다. 리뷰 보고서의 해결 예시는 구현 코드가 아니므로 실제 callable 계약을 직접 판단한다. 세션 대역을 직접 주입해 실제 단계를 생략한 기존 검사를 보완한다.
2. **상위 예외:** management_runs와 사용 중인 worker_runs의 상위 예외 실패에서도 훅이 한 번 호출된다. 정상/부분 실패 경로와 중복 호출하지 않으며 명시 취소에는 시작하지 않는다. 원래 수집 상태·오류를 프리뷰 상태로 덮지 않는다.
3. **승인:** 생성 전에 기존 admission_state를 판정한다. missing/stale은 생성0·명확한 건너뜀 사유, 승인 조회 실패는 명확한 실패 사유다. ready일 때만 기존 동일 생성 서비스로 진입한다. 사후 기록만으로 승인 정책이 보존됐다고 표현하지 않는다. 관리자 시험·기존 승인 행은 변경하지 않는다.
4. **비예외 실패:** BundlePipelineOutcome가 FAILED를 반환하면 run_id와 사유를 failed에 남기고 generated에 넣지 않는다. 다음 경기는 처리한다. 성공 판정은 실제 enum 계약을 사용한다.

대표 검사는 위 4가지 사용자 결과를 실제 변경 경로에서 고정한다. 의미 없는 기존 대역 검사는 강화/대체하고 개수를 목표로 늘리지 않는다. 외부 연결 없는 합성 검사이며 실제 DB 저장/모델 성공이라고 보고하지 않는다.

검사 명령은 `.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q`다. 현재 리비전14 passed 근거는 기존 것이므로 변경 후 필요한 직접 명령만 실행한다. 전체 회귀·새 플랫폼·임의 재현 도구·반복 변이 실험은 추가하지 않는다. 같은 원인 수정/검증이 두 번 실패하면 최소 원인을 조정자에게 보고한다.

독립 검토의 참고 개선은 현재 범위에 추가하지 않는다. 다만 이 수정이 만든 직접 회귀는 보고한다. 실제 DB·외부 HTTP·모델·운영 수집·브라우저·서버 재시작·환경 비밀값 탐색·승인 POST·마이그레이션은 0건을 유지한다.

완료 시 4개 지적별 수정·직접 검증·미해결을 보고서에 정리하고 EDITING STOPPED/background0을 새 활성 Task/Dispatch의 worker_done 한 번으로 보고한다. 완료 후 후속 메일 탐색·추가 작업 없이 종료한다. 독립 수정 확인은 조정자가 별도 배정한다.
