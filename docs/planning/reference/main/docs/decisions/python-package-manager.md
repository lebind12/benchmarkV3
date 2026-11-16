> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `docs/decisions/python-package-manager.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# Decision: Python package manager

- **선택**: `pyproject.toml` (PEP 621) + `pip` 기본. `uv` 사용 권장하되 강제 아님.
- **사유**: pyproject.toml 은 모든 모던 도구 (pip, uv, poetry, hatch) 의 공통 입력이므로 lock-in 회피. `requirements.txt` 는 pip-only 환경 호환용 fallback 으로 병행 유지. lockfile (uv.lock / poetry.lock) 은 Phase 0 완료 후 의존성 안정화되면 도입.
- **결정일**: 2026-05-13 / be-dev
