> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `frontend/endpoint-requests/POST__api_v1_search_agentic_conversation_cancel.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# POST__api_v1_search_agentic_conversation_cancel.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "from_feature": "ax-agentic-search",
  "shared_features": [
    "ax-agentic-progress"
  ],
  "contract_status": "draft_from_FE_mock_pending_independent_impl_review",
  "fe_mockup_ref": "frontend/src/views/AgenticSearchView.vue",
  "handler_ref": "frontend/src/mocks/handlers/axSearch.ts",
  "spec_ref": "docs/features/ax-agentic-search.spec.md",
  "testplan_refs": [
    "docs/features/ax-agentic-search.testplan.md",
    "docs/features/ax-agentic-progress.testplan.md"
  ],
  "auth": {
    "roles": [
      "USER",
      "STREAMER",
      "ADMIN"
    ],
    "active_required": true,
    "shared_jwt": true
  },
  "non_functional": {
    "freshness": "6h DB-only",
    "polling": false,
    "model": "gemini-4-argon",
    "source": "existing API-Football DB",
    "max_question_chars": 500
  },
  "request_shape": {
    "request_ref": "string(16..64) current user/session-bound nonce"
  },
  "error_cases": {
    "401": "unauthenticated/expired; zero LLM/search calls",
    "403": "inactive/forbidden role",
    "409": "expired context/stale parent/nonce reused/cancelled",
    "422": "invalid input/plan/evidence",
    "429": "concurrency/budget/provider",
    "502": "model output/invalid stream",
    "503": "auth/DB/stale data/configuration",
    "504": "deadline"
  },
  "security_requirements": [
    "SEC-01 metric/name/ID semantic integrity",
    "SEC-02 grounded public explanation",
    "PI-01..12 direct/indirect injection and legitimate control pairs",
    "Never expose SQL/prompts/secrets/other user context",
    "Reject malformed/oversize/nonfinite/duplicate identities",
    "Same token/session binding owns conversation/nonce/ref; do not replay across rotation"
  ],
  "response_example": {
    "status": "cancelled"
  },
  "scenarios_used": [
    "results",
    "partial",
    "clarification_required",
    "no_matches",
    "data_unavailable",
    "unsupported",
    "provider_error",
    "missing_metadata_legacy",
    "direct_indirect_injection",
    "cancel",
    "disconnect_recovery",
    "session_rotation"
  ],
  "notes_for_be": [
    "These files are current FE-demand drafts, not retrospective MERGED/FE_DONE proof.",
    "Actual source ID/value/order/conditions need independent oracle; valid artifact ref alone is insufficient."
  ],
  "endpoint_id": "POST__api_v1_search_agentic_conversation_cancel",
  "method": "POST",
  "path": "/api/v1/search/agentic/conversation/cancel",
  "response_shape": {
    "status": "cancelled"
  },
  "cancellation": "authenticated tombstone/latest-turn rollback, no late UI append. Disconnect is not cancel; already running LLM/DB may not stop immediately. Invalid/missing acknowledgement is failure, not confirmed cancellation."
}
```
