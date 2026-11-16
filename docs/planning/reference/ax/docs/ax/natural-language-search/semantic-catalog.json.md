> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/semantic-catalog.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# semantic-catalog.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "schema_version": "0.1-draft",
  "catalog_version": "draft-20261025-db-audit-1",
  "normalization_version": "nfkc-casefold-space-v1",
  "publication_status": "draft",
  "source_audit": "data-audit.evidence.json",
  "runtime_note": "Definitions are grounded in stored DB fields but are not enabled for production or backed by executable registry implementations.",
  "metrics": [
    {
      "key": "player_goals",
      "kind": "metric",
      "label": "득점",
      "terms": [
        "득점",
        "골",
        "goals"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.goals",
      "expression_ref": "player_goals_sum_v1",
      "unit": "골",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "key": "player_assists",
      "kind": "metric",
      "label": "도움",
      "terms": [
        "도움",
        "어시스트",
        "assists"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.assists",
      "expression_ref": "player_assists_sum_v1",
      "unit": "회",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "key": "player_minutes",
      "kind": "metric",
      "label": "출전 시간",
      "terms": [
        "출전 시간",
        "출전 분",
        "minutes"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.minutes",
      "expression_ref": "player_minutes_sum_v1",
      "unit": "분",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "key": "player_appearances",
      "kind": "metric",
      "label": "출전 횟수",
      "terms": [
        "출전 횟수",
        "경기 출전",
        "appearances"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.appearances",
      "expression_ref": "player_appearances_sum_v1",
      "unit": "회",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "key": "player_yellow_cards",
      "kind": "metric",
      "label": "경고",
      "terms": [
        "경고",
        "옐로카드",
        "yellow cards"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.yellow_cards",
      "expression_ref": "player_yellow_cards_sum_v1",
      "unit": "장",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "key": "player_red_cards",
      "kind": "metric",
      "label": "퇴장",
      "terms": [
        "퇴장",
        "레드카드",
        "red cards"
      ],
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ],
        [
          "player",
          "team",
          "league",
          "season"
        ]
      ],
      "source_ref": "player_season_stat.red_cards",
      "expression_ref": "player_red_cards_sum_v1",
      "unit": "장",
      "value_type": "integer",
      "operators": [
        "eq",
        "gte",
        "lte",
        "sort",
        "sum"
      ],
      "aggregation": "sum_across_confirmed_team_rows",
      "null_policy": "preserve_and_report_coverage",
      "required_context": [
        "league",
        "season"
      ],
      "dependencies": [],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "league_season_policy_not_integrated",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage",
        "data-audit.evidence.json#stat_source_presence"
      ],
      "enabled": false,
      "version": 1
    },
    {
      "kind": "metric",
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ]
      ],
      "value_type": "decimal",
      "operators": [
        "sort",
        "gte",
        "lte"
      ],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage"
      ],
      "enabled": false,
      "version": 1,
      "key": "player_goals_per90",
      "label": "90분당 득점",
      "terms": [
        "90분당 득점",
        "90분당 골",
        "goals per 90"
      ],
      "dependencies": [
        "player_goals",
        "player_minutes"
      ],
      "unit": "골/90분",
      "expression_ref": "player_goals_per90_v1",
      "aggregation": "ratio_of_sums",
      "null_policy": "reject_unknown_or_nonpositive_denominator",
      "required_context": [
        "league",
        "season",
        "minimum_minutes_or_confirmation"
      ]
    },
    {
      "kind": "metric",
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ]
      ],
      "value_type": "integer",
      "operators": [
        "sort",
        "gte",
        "lte"
      ],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "coverage_contract_not_implemented"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage"
      ],
      "enabled": false,
      "version": 1,
      "key": "player_goal_contributions",
      "label": "득점+도움",
      "terms": [
        "득점+도움",
        "골+도움",
        "goals and assists"
      ],
      "dependencies": [
        "player_goals",
        "player_assists"
      ],
      "unit": "회",
      "expression_ref": "player_goal_contributions_v1",
      "aggregation": "sum_of_known_components",
      "null_policy": "unknown_if_any_required_component_missing",
      "required_context": [
        "league",
        "season"
      ]
    },
    {
      "kind": "metric",
      "entity_type": "player",
      "domain": "player_season",
      "source_grain": [
        "player",
        "team",
        "league",
        "season"
      ],
      "result_grains": [
        [
          "player",
          "league",
          "season"
        ]
      ],
      "value_type": "decimal",
      "operators": [
        "sort",
        "gte",
        "lte"
      ],
      "coverage_requirements": [
        "player_season_stats"
      ],
      "activation_blockers": [
        "expression_registry_not_implemented",
        "coverage_contract_not_implemented",
        "rating_aggregation_semantics_unverified"
      ],
      "evidence": [
        "data-audit.evidence.json#player_stat_coverage"
      ],
      "enabled": false,
      "version": 1,
      "key": "player_rating",
      "label": "평점",
      "terms": [
        "평점",
        "rating"
      ],
      "dependencies": [],
      "unit": "점",
      "source_ref": "player_season_stat.rating",
      "expression_ref": "player_rating_observation_v1",
      "aggregation": "none_until_provider_definition_verified",
      "null_policy": "preserve",
      "required_context": [
        "league",
        "season",
        "team_if_multiple"
      ]
    }
  ],
  "scopes": [
    {
      "key": "current_season",
      "kind": "scope",
      "label": "이번 시즌",
      "terms": [
        "이번 시즌",
        "올 시즌"
      ],
      "resolver_ref": "resolve_catalog_current",
      "required_context": [
        "league"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "previous_season",
      "kind": "scope",
      "label": "지난 시즌",
      "terms": [
        "지난 시즌",
        "직전 시즌"
      ],
      "resolver_ref": "resolve_actual_previous_catalog_season",
      "required_context": [
        "league"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "explicit_season",
      "kind": "scope",
      "label": "명시 시즌",
      "terms": [
        "시즌"
      ],
      "resolver_ref": "resolve_explicit_season_with_retention",
      "required_context": [
        "league"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "calendar_period",
      "kind": "scope",
      "label": "달력 기간",
      "terms": [
        "올해",
        "작년",
        "어제",
        "오늘"
      ],
      "resolver_ref": "resolve_calendar_interval_kst",
      "required_context": [
        "reference_time",
        "timezone"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "recent_completed_fixtures",
      "kind": "scope",
      "label": "최근 완료 경기",
      "terms": [
        "최근 경기",
        "최근 5경기"
      ],
      "resolver_ref": "resolve_completed_fixture_order",
      "required_context": [
        "competition_scope",
        "reference_time"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "home_fixtures",
      "kind": "scope",
      "label": "홈 경기",
      "terms": [
        "홈 경기",
        "홈에서"
      ],
      "resolver_ref": "filter_fixture_home",
      "required_context": [
        "team"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "away_fixtures",
      "kind": "scope",
      "label": "원정 경기",
      "terms": [
        "원정 경기",
        "원정에서"
      ],
      "resolver_ref": "filter_fixture_away",
      "required_context": [
        "team"
      ],
      "dependencies": [],
      "enabled": false,
      "version": 1
    }
  ],
  "relations": [
    {
      "key": "player_team_season",
      "kind": "relation",
      "label": "선수의 시즌별 팀 기록",
      "terms": [
        "소속 선수",
        "에서 뛴 선수"
      ],
      "entity_types": [
        "player",
        "team"
      ],
      "relation_ref": "player_season_stat.player_id_team_id_league_id_season_year",
      "required_context": [
        "league",
        "season"
      ],
      "unknown_policy": "preserve_candidate",
      "dependencies": [],
      "enabled": false,
      "version": 1
    },
    {
      "key": "fixture_team_side",
      "kind": "relation",
      "label": "경기의 홈/원정 팀",
      "terms": [
        "홈팀",
        "원정팀"
      ],
      "entity_types": [
        "fixture",
        "team"
      ],
      "relation_ref": "fixture.home_team_id_away_team_id",
      "required_context": [
        "fixture_or_range"
      ],
      "unknown_policy": "clarify",
      "dependencies": [],
      "enabled": false,
      "version": 1
    }
  ]
}
```
