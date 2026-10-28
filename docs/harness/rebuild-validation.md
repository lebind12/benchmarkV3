# 2026-10-28 하네스 재구축 검증

## 범위와 결과

운영 에이전트가 작업을 나누고, 구현과 별도 인스턴스인 `harness_verification`(GPT-6.1 Sol medium)이 임시 Git 저장소에서 동작을 검증했다. 운영 에이전트는 구현 원본·설정·변경 diff와 독립 보고를 확인했다.

- 독립 테스트: **93 passed in 53.35s**.
- 50개 새 흐름 시나리오: 역할 분리, 목표 기준 커버리지, 커밋/revision 결합, 바뀐 근거 차단, 수정/재검증, 3회 요청 후 escalation, 스키마 오류, 병합 커밋 조상 관계.
- 43개 전환/설정 시나리오: 과거 흐름 조회 및 변경 차단, 선택적 완료 어댑터, 모델/추론/속도 설정과 7역할, 6개 과거 역할 인계, 기존 상태 보존.
- 운영자 직접 확인: Ruff, 셸 구문, `git diff --check`, 기존 FE/BE `validate-all` 통과.
- 기존 상태 파일과 사용자 선행 미추적 문서는 변경하지 않았다.

```sh
.venv/bin/python -m pytest tests/unit/test_work_flow.py tests/unit/test_harness_flow_scripts.py tests/unit/test_harness_configuration.py -q --confcutdir=tests/unit
```

## 판단과 한계

로컬 하네스 변경은 검증을 통과했다. 이 재구축은 기존 운영 규칙을 전환하는 초기 작업이므로 실제 Git 머지 상태를 새 CLI에 허위 생성하지 않았다. 커밋·머지·원격 push·배포·운영 DB 변경·Notion 게시·영상 제작은 수행하지 않았다.

모델 설정 검증은 저장된 TOML의 정합성 확인이다. 현재 세션의 새 역할 자동 재로딩을 확인했다는 뜻은 아니다. 현재 작업에서는 모델을 명시한 worker를 사용했다. CLI는 실제 테스트 실행이나 신원을 증명하지 않으며 운영자가 보고와 원본 근거를 확인해야 한다. `merged`는 제출 커밋 포함 여부를 검사하며 실제 대상 브랜치 통합 확인은 운영자 책임이다.

## 검증 대상 파일 지문

아래는 테스트 완료 후 운영자가 기록한 SHA-256이다. 이후 코드 변경 시 해당 변경 범위를 재검증한다.

| 파일 | SHA-256 |
|---|---|
| `scripts/work-flow.py` | `4b93704b1ec38ed4e849d398f10306fae453a70858333e16bbbe386ff6dc58c7` |
| `scripts/work-flow.sh` | `be02c48180ca7e4bdaea50da1643d2ca9a52a0b591e4c8a4bcafa27798836fc6` |
| `scripts/harness-flow.mjs` | `8543e01fafbf557b712bb2cc5cd08dd58ef34529be6b79e06cb8a775995f2313` |
| `scripts/harness-task-completed-guard.py` | `55a903e46538f7983445b6d7e9d20b14b6e7576d0510f60b45d1ac3ad434dc77` |
| `scripts/harness-task-completed-guard.sh` | `8624a1bb0c6a25bef10bd85a37d0ffff65cea9afa1e34ed27ed28f71263c16ff` |
| `tests/unit/test_work_flow.py` | `27d6860079038b62a7aa5ec8ee7631ac740744460d16fe6c449b4e4180a61d18` |
| `tests/unit/test_harness_flow_scripts.py` | `19ca7fee2a4bf03de4c31e0fb8292ed282feb5634797385b52db3edcfb038d01` |
| `tests/unit/test_harness_configuration.py` | `33d727c8fa6e6c8915dbc20dd700193a331cb3ebe240678f881ac477944f56bb` |
| `.codex/config.toml` | `34f77a926664d79d6e8ebf542c1c290ca3f3a7a804f9a64fc6e41822dca54702` |
