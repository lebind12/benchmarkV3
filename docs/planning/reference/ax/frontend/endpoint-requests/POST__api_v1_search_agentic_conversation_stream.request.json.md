> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `frontend/endpoint-requests/POST__api_v1_search_agentic_conversation_stream.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# POST__api_v1_search_agentic_conversation_stream.request.json

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
    "request_ref": "string(16..64), user-bound idempotency nonce",
    "message": "string(1..500)",
    "conversation_ref": "optional string, paired with parent_turn_ref",
    "parent_turn_ref": "optional string"
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
  "release_metadata": {
    "required_statuses": [
      "results",
      "partial",
      "no_matches"
    ],
    "applied": "array(max16), each artifact_ref connected to table or source; scopes(max4): league_id,league,season,team|null; metrics(max8): key,label,unit,definition; filters(max8): metric,op,value; minimum_minutes|null; sort(max8): key,direction,nulls; selection: basis,limit(1..100),truncated",
    "coverage": "array(max16), artifact_ref; state(partial|unavailable|unknown); observed_rows nonnegative int; known_metric_players/excluded_unknown_players nonnegative int|null; truncated bool; exported_at ISO8601 offset; source_as_of ISO8601 offset|null; dataset_version; limitations(max16)",
    "legacy_compatibility": "FE temporarily accepts absent metadata from unaccepted local backend but displays absence explicitly. Release contract must require metadata for result statuses; no fake default conditions/timestamps.",
    "derivations": "Applied.derivations?: array(max24) of {output_key, operation:difference|ratio, left:{artifact_ref,column:8metricKey}, right:{artifact_ref,column:8metricKey}, join_keys:[player_id], unit, null_policy:propagate, zero_denominator:unavailable|null}. Optional only for source/legacy; release derived artifacts require it.",
    "derivation_constraints": [
      "Each left/right ref must resolve to the same response sources and Applied metric definition; metadata linked by artifact_ref, never array order.",
      "Initial supported derivations compare the same metric key/unit across two source artifacts; compound derived-on-derived is not in this first typed contract.",
      "difference unit equals both source metric units; zero_denominator=null. ratio is raw left/right (no x100), unit=배, zero_denominator=unavailable; NULL or denominator0 yields null/자료 없음.",
      "current and previous output columns are source values with source units. change maps to derivation.output_key and uses derivation.unit, never inferred from source metric."
    ]
  },
  "response_example": {
    "events": [
      {
        "event": "progress",
        "data": {
          "sequence": 1,
          "step": {
            "id": "mock-plan",
            "stage": "planning",
            "label": "질문 기준 확인",
            "status": "running",
            "started_ms": 0,
            "duration_ms": null
          }
        }
      },
      {
        "event": "progress",
        "data": {
          "sequence": 2,
          "step": {
            "id": "mock-plan",
            "stage": "planning",
            "label": "질문 기준 확인",
            "status": "completed",
            "started_ms": 0,
            "duration_ms": 10
          }
        }
      },
      {
        "event": "result",
        "data": {
          "conversation_ref": "mock-search-conversation",
          "expires_in": 1800,
          "turn": {
            "turn_ref": "mock-search-turn",
            "question": "이번 시즌 EPL 득점 상위 3명",
            "answer": "같은 선수의 두 시즌 득점 비율입니다. 비교 기록이 없거나 분모가 영이면 자료 없음으로 표시했습니다.",
            "status": "partial",
            "tables": [
              {
                "artifact_ref": "mock-ratio",
                "title": "두 시즌 득점 비율",
                "columns": [
                  {
                    "key": "name",
                    "label": "선수"
                  },
                  {
                    "key": "current",
                    "label": "이번 득점",
                    "unit": "골"
                  },
                  {
                    "key": "previous",
                    "label": "직전 득점",
                    "unit": "골"
                  },
                  {
                    "key": "change",
                    "label": "비율",
                    "unit": "배"
                  }
                ],
                "rows": [
                  {
                    "name": "선수 A",
                    "current": 12,
                    "previous": 8,
                    "change": 1.5
                  },
                  {
                    "name": "선수 B",
                    "current": 0,
                    "previous": 0,
                    "change": null
                  },
                  {
                    "name": "선수 C",
                    "current": null,
                    "previous": 2,
                    "change": null
                  }
                ]
              }
            ],
            "steps": [
              {
                "label": "저장 기록 조회",
                "status": "완료"
              }
            ],
            "missing": [
              "일부 선수의 득점 자료가 없습니다."
            ],
            "sources": [
              {
                "artifact_ref": "mock-previous",
                "description": "직전 시즌 원천 기록",
                "exported_at": "2026-10-29T02:00:00Z"
              },
              {
                "artifact_ref": "mock-current",
                "description": "현재 시즌 원천 기록",
                "exported_at": "2026-10-29T01:00:00Z"
              },
              {
                "artifact_ref": "mock-ratio",
                "description": "같은 선수의 두 시즌 득점 나눗셈",
                "exported_at": "2026-10-29T02:00:00Z"
              }
            ],
            "applied": [
              {
                "artifact_ref": "mock-ratio",
                "scopes": [
                  {
                    "league_id": 1,
                    "league": "프리미어리그",
                    "season": 2026,
                    "team": null
                  },
                  {
                    "league_id": 1,
                    "league": "프리미어리그",
                    "season": 2025,
                    "team": null
                  }
                ],
                "metrics": [
                  {
                    "key": "player_goals",
                    "label": "득점",
                    "unit": "골",
                    "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
                  }
                ],
                "filters": [],
                "minimum_minutes": null,
                "sort": [
                  {
                    "key": "player_goals",
                    "direction": "desc",
                    "nulls": "last"
                  },
                  {
                    "key": "player_id",
                    "direction": "asc",
                    "nulls": "last"
                  }
                ],
                "selection": {
                  "basis": "관측된 선수 기록 내 득점 순위",
                  "limit": 3,
                  "truncated": false
                },
                "derivations": [
                  {
                    "output_key": "change",
                    "operation": "ratio",
                    "left": {
                      "artifact_ref": "mock-current",
                      "column": "player_goals"
                    },
                    "right": {
                      "artifact_ref": "mock-previous",
                      "column": "player_goals"
                    },
                    "join_keys": [
                      "player_id"
                    ],
                    "unit": "배",
                    "null_policy": "propagate",
                    "zero_denominator": "unavailable"
                  }
                ]
              },
              {
                "artifact_ref": "mock-previous",
                "scopes": [
                  {
                    "league_id": 1,
                    "league": "프리미어리그",
                    "season": 2025,
                    "team": null
                  }
                ],
                "metrics": [
                  {
                    "key": "player_goals",
                    "label": "득점",
                    "unit": "골",
                    "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
                  }
                ],
                "filters": [],
                "minimum_minutes": null,
                "sort": [
                  {
                    "key": "player_goals",
                    "direction": "desc",
                    "nulls": "last"
                  },
                  {
                    "key": "player_id",
                    "direction": "asc",
                    "nulls": "last"
                  }
                ],
                "selection": {
                  "basis": "관측된 선수 기록 내 득점 순위",
                  "limit": 3,
                  "truncated": false
                }
              },
              {
                "artifact_ref": "mock-current",
                "scopes": [
                  {
                    "league_id": 1,
                    "league": "프리미어리그",
                    "season": 2026,
                    "team": null
                  }
                ],
                "metrics": [
                  {
                    "key": "player_goals",
                    "label": "득점",
                    "unit": "골",
                    "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
                  }
                ],
                "filters": [],
                "minimum_minutes": null,
                "sort": [
                  {
                    "key": "player_goals",
                    "direction": "desc",
                    "nulls": "last"
                  },
                  {
                    "key": "player_id",
                    "direction": "asc",
                    "nulls": "last"
                  }
                ],
                "selection": {
                  "basis": "관측된 선수 기록 내 득점 순위",
                  "limit": 3,
                  "truncated": true
                }
              }
            ],
            "coverage": [
              {
                "artifact_ref": "mock-current",
                "state": "partial",
                "observed_rows": 5,
                "known_metric_players": 4,
                "excluded_unknown_players": 1,
                "truncated": true,
                "exported_at": "2026-10-29T01:00:00Z",
                "source_as_of": "2026-10-29T00:00:00Z",
                "dataset_version": "mock-fixture-20261029",
                "limitations": [
                  "전체 수집 완료를 보증하지 않습니다."
                ]
              },
              {
                "artifact_ref": "mock-previous",
                "state": "partial",
                "observed_rows": 1,
                "known_metric_players": 1,
                "excluded_unknown_players": 0,
                "truncated": false,
                "exported_at": "2026-10-29T02:00:00Z",
                "source_as_of": "2025-09-01T00:00:00Z",
                "dataset_version": "mock-fixture-20261029",
                "limitations": [
                  "전체 수집 완료를 보증하지 않습니다."
                ]
              },
              {
                "artifact_ref": "mock-ratio",
                "state": "partial",
                "observed_rows": 3,
                "known_metric_players": 1,
                "excluded_unknown_players": 2,
                "truncated": false,
                "exported_at": "2026-10-29T01:00:00Z",
                "source_as_of": "2026-10-29T00:00:00Z",
                "dataset_version": "mock-fixture-20261029",
                "limitations": [
                  "전체 수집 완료를 보증하지 않습니다."
                ]
              }
            ],
            "progress_steps": [
              {
                "id": "mock-plan",
                "stage": "planning",
                "label": "질문 기준 확인",
                "status": "completed",
                "started_ms": 0,
                "duration_ms": 10
              }
            ]
          }
        }
      }
    ]
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
  "endpoint_id": "POST__api_v1_search_agentic_conversation_stream",
  "method": "POST",
  "path": "/api/v1/search/agentic/conversation/stream",
  "response_transport": "text/event-stream; no-store/no-buffering",
  "response_shape": {
    "progress": "sequence + step(id,stage,label,status,started_ms,duration_ms)",
    "result": "same final JSON schema as conversation",
    "error": "status(400..599), detail(safe_code)",
    "keepalive": "comment only"
  },
  "stream_limits": {
    "total_bytes": 2097152,
    "buffer_frame_bytes": 300000,
    "progress_steps_max": 128,
    "terminal": "exactly one; reject post-terminal data/identity regression/conflicting final history",
    "utf8": "chunk-safe, CRLF, multiline data"
  },
  "derived_response_example": {
    "conversation_ref": "mock-search-conversation",
    "expires_in": 1800,
    "turn": {
      "turn_ref": "mock-search-turn",
      "question": "이번 시즌 EPL 득점 상위 3명",
      "answer": "같은 선수의 두 시즌 득점 비율입니다. 비교 기록이 없거나 분모가 영이면 자료 없음으로 표시했습니다.",
      "status": "partial",
      "tables": [
        {
          "artifact_ref": "mock-ratio",
          "title": "두 시즌 득점 비율",
          "columns": [
            {
              "key": "name",
              "label": "선수"
            },
            {
              "key": "current",
              "label": "이번 득점",
              "unit": "골"
            },
            {
              "key": "previous",
              "label": "직전 득점",
              "unit": "골"
            },
            {
              "key": "change",
              "label": "비율",
              "unit": "배"
            }
          ],
          "rows": [
            {
              "name": "선수 A",
              "current": 12,
              "previous": 8,
              "change": 1.5
            },
            {
              "name": "선수 B",
              "current": 0,
              "previous": 0,
              "change": null
            },
            {
              "name": "선수 C",
              "current": null,
              "previous": 2,
              "change": null
            }
          ]
        }
      ],
      "steps": [
        {
          "label": "저장 기록 조회",
          "status": "완료"
        }
      ],
      "missing": [
        "일부 선수의 득점 자료가 없습니다."
      ],
      "sources": [
        {
          "artifact_ref": "mock-previous",
          "description": "직전 시즌 원천 기록",
          "exported_at": "2026-10-29T02:00:00Z"
        },
        {
          "artifact_ref": "mock-current",
          "description": "현재 시즌 원천 기록",
          "exported_at": "2026-10-29T01:00:00Z"
        },
        {
          "artifact_ref": "mock-ratio",
          "description": "같은 선수의 두 시즌 득점 나눗셈",
          "exported_at": "2026-10-29T02:00:00Z"
        }
      ],
      "applied": [
        {
          "artifact_ref": "mock-ratio",
          "scopes": [
            {
              "league_id": 1,
              "league": "프리미어리그",
              "season": 2026,
              "team": null
            },
            {
              "league_id": 1,
              "league": "프리미어리그",
              "season": 2025,
              "team": null
            }
          ],
          "metrics": [
            {
              "key": "player_goals",
              "label": "득점",
              "unit": "골",
              "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
            }
          ],
          "filters": [],
          "minimum_minutes": null,
          "sort": [
            {
              "key": "player_goals",
              "direction": "desc",
              "nulls": "last"
            },
            {
              "key": "player_id",
              "direction": "asc",
              "nulls": "last"
            }
          ],
          "selection": {
            "basis": "관측된 선수 기록 내 득점 순위",
            "limit": 3,
            "truncated": false
          },
          "derivations": [
            {
              "output_key": "change",
              "operation": "ratio",
              "left": {
                "artifact_ref": "mock-current",
                "column": "player_goals"
              },
              "right": {
                "artifact_ref": "mock-previous",
                "column": "player_goals"
              },
              "join_keys": [
                "player_id"
              ],
              "unit": "배",
              "null_policy": "propagate",
              "zero_denominator": "unavailable"
            }
          ]
        },
        {
          "artifact_ref": "mock-previous",
          "scopes": [
            {
              "league_id": 1,
              "league": "프리미어리그",
              "season": 2025,
              "team": null
            }
          ],
          "metrics": [
            {
              "key": "player_goals",
              "label": "득점",
              "unit": "골",
              "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
            }
          ],
          "filters": [],
          "minimum_minutes": null,
          "sort": [
            {
              "key": "player_goals",
              "direction": "desc",
              "nulls": "last"
            },
            {
              "key": "player_id",
              "direction": "asc",
              "nulls": "last"
            }
          ],
          "selection": {
            "basis": "관측된 선수 기록 내 득점 순위",
            "limit": 3,
            "truncated": false
          }
        },
        {
          "artifact_ref": "mock-current",
          "scopes": [
            {
              "league_id": 1,
              "league": "프리미어리그",
              "season": 2026,
              "team": null
            }
          ],
          "metrics": [
            {
              "key": "player_goals",
              "label": "득점",
              "unit": "골",
              "definition": "같은 선수의 팀별 득점을 NULL 보존 후 합산"
            }
          ],
          "filters": [],
          "minimum_minutes": null,
          "sort": [
            {
              "key": "player_goals",
              "direction": "desc",
              "nulls": "last"
            },
            {
              "key": "player_id",
              "direction": "asc",
              "nulls": "last"
            }
          ],
          "selection": {
            "basis": "관측된 선수 기록 내 득점 순위",
            "limit": 3,
            "truncated": true
          }
        }
      ],
      "coverage": [
        {
          "artifact_ref": "mock-current",
          "state": "partial",
          "observed_rows": 5,
          "known_metric_players": 4,
          "excluded_unknown_players": 1,
          "truncated": true,
          "exported_at": "2026-10-29T01:00:00Z",
          "source_as_of": "2026-10-29T00:00:00Z",
          "dataset_version": "mock-fixture-20261029",
          "limitations": [
            "전체 수집 완료를 보증하지 않습니다."
          ]
        },
        {
          "artifact_ref": "mock-previous",
          "state": "partial",
          "observed_rows": 1,
          "known_metric_players": 1,
          "excluded_unknown_players": 0,
          "truncated": false,
          "exported_at": "2026-10-29T02:00:00Z",
          "source_as_of": "2025-09-01T00:00:00Z",
          "dataset_version": "mock-fixture-20261029",
          "limitations": [
            "전체 수집 완료를 보증하지 않습니다."
          ]
        },
        {
          "artifact_ref": "mock-ratio",
          "state": "partial",
          "observed_rows": 3,
          "known_metric_players": 1,
          "excluded_unknown_players": 2,
          "truncated": false,
          "exported_at": "2026-10-29T01:00:00Z",
          "source_as_of": "2026-10-29T00:00:00Z",
          "dataset_version": "mock-fixture-20261029",
          "limitations": [
            "전체 수집 완료를 보증하지 않습니다."
          ]
        }
      ],
      "progress_steps": [
        {
          "id": "mock-plan",
          "stage": "planning",
          "label": "질문 기준 확인",
          "status": "completed",
          "started_ms": 0,
          "duration_ms": 10
        }
      ]
    }
  }
}
```
