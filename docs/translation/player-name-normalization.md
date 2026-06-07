# Player Name Korean Normalization

This document is the SSOT for the player translation full pass. The target is
not the most academically accurate native pronunciation. The target is the
representative Korean display name that Korean football users recognize most
naturally.

Backend translation workers are not used for this flow. The flow is:

1. Export DB rows to a queue CSV.
2. Process queue shards in ChatGPT Desktop.
3. Merge and validate returned CSVs.
4. Import only rows that pass the validator.
5. Keep review/audit rows outside the import CSV.

## Source Priority

1. `manual_override_name_ko` / `manual_override_short_name_ko`
2. `locked_common_name_ko`
3. Korean football usage evidence from `evidence_ko_candidates` and
   `evidence_source_summary`
4. Clear API registered name / mononym
5. Language-family fallback rules
6. Review-only candidate

Korean football usage can override native-pronunciation style, wiki labels, or
official labels. Wiki/official/native-pronunciation alternatives should be kept
in `aliases_ko` when useful, but `aliases_ko` is audit-only for now because the
current DB table stores only `name_ko` and `short_name_ko`.

## Required Input Columns

```csv
api_player_id,api_name_raw,firstname,lastname,nationality_raw,birth_country_raw,current_team_names,current_league_names,previous_name_ko,previous_short_name_ko,manual_override_name_ko,manual_override_short_name_ko,locked_common_name_ko,known_aliases_ko,evidence_ko_candidates,evidence_source_summary,popularity_tier,nationality_ko_mapped,birth_country_ko_mapped,country_mapping_status
```

`api_player_id` is API-Football `player.id` and maps to
`player.external_id` in the database.

Country names are not newly translated by ChatGPT. `nationality_ko_mapped` and
`birth_country_ko_mapped` must be copied from input. Missing mapped country
values are review conditions.

## Required Output Columns

```csv
api_player_id,api_name_raw,firstname,lastname,nationality_raw,birth_country_raw,name_ko,short_name_ko,aliases_ko,name_base_used,name_origin_language,name_structure_type,source_type,source_ref,rule_id,method,confidence,usage_score,usage_conflict,needs_review,review_codes,reason
```

Every input `api_player_id` must appear exactly once. Additional, missing, or
modified IDs are invalid.

## Method Values

- `accepted_manual_override`
- `accepted_service_locked_common`
- `accepted_korean_football_usage`
- `accepted_usage_over_phonetic`
- `accepted_usage_over_official`
- `accepted_registered_name`
- `generated_by_language_rule`
- `generated_from_api_first_last`
- `generated_from_api_last_first`
- `review_usage_conflict`
- `review_only_candidate`

## Source Type Values

- `manual_override`
- `service_locked_common`
- `korean_football_usage`
- `korean_media_common`
- `korean_community_common`
- `official_ko`
- `wiki_label`
- `api_registered_name`
- `language_rule`
- `llm_candidate`

## Review Codes

- `COMMON_USAGE_OVERRIDES_PHONETIC`
- `WIKI_LABEL_DIFFERS_FROM_USAGE`
- `OFFICIAL_LABEL_DIFFERS_FROM_USAGE`
- `COMMUNITY_USAGE_DOMINANT`
- `MEDIA_USAGE_DOMINANT`
- `USAGE_CONFLICT_REVIEW`
- `FAMOUS_PLAYER_NO_USAGE_EVIDENCE`
- `API_NAME_ABBREVIATED`
- `FIRST_LAST_MISSING`
- `SHORT_NAME_COLLISION`
- `LATIN_REMAINS`
- `INITIAL_OR_DOT_REMAINS`
- `TOO_LONG_LEGAL_NAME`
- `NATIONALITY_LANGUAGE_MISMATCH`
- `API_COUNTRY_MAPPING_MISSING`
- `API_COUNTRY_IS_FOOTBALL_ASSOCIATION`
- `KOREAN_SHORT_SURNAME_ONLY`
- `LOW_CONFIDENCE_IMPORT_BLOCKED`

Review codes are joined with `;`.

## Confidence

- `100`: manual override
- `95-99`: service locked common name
- `90-95`: very clear Korean football usage
- `85-90`: consistent media/community/evidence candidate
- `75-85`: weak usage evidence but clear name structure and language rule
- `60-75`: language-rule candidate
- `40-60`: possible candidate, not suitable for automatic import
- `0-40`: review only

Automatic import requires `confidence >= 80`, `needs_review=false`, no Latin
letters, no dots/initials, mapped countries present, no manual override conflict,
and no ambiguous short name.

## Name Rules

### Common Usage

Use Korean football usage when evidence clearly favors one form. If wiki,
official, or native-pronunciation style differs from usage, choose usage for
`name_ko` and put alternatives in `aliases_ko`.

For high-popularity players, do not generate a new display name from language
rules alone. If usage evidence or a locked name is missing, set
`needs_review=true`.

### Abbreviated API Names

Do not transliterate initial forms like `P. Sandler`, `J. Kim`, or `A. Silva`.
Use `firstname`/`lastname` when reliable and add `API_NAME_ABBREVIATED` to
`review_codes`. If full name is missing or uncertain, mark review.

### Korean Players

For Korean players, use `lastname + firstname` and write without spaces.

- `firstname=Heung-Min`, `lastname=Son` -> `손흥민`
- `firstname=Kang-In`, `lastname=Lee` -> `이강인`

`short_name_ko` is normally the full Korean name. Do not use a single Korean
surname such as `김`, `이`, `박`, `손` as `short_name_ko`.

### Japanese Players

Use family-given order.

- `Wataru Endo` -> `엔도 와타루`
- `Kaoru Mitoma` -> `미토마 가오루`

`short_name_ko` is normally the family name. If there is collision risk in the
same team/league context, use full name or mark review.

### Chinese and East Asian Names

Prefer family-given order, but do not rely on nationality alone. Use the actual
name shape and context. If uncertain, mark review.

### Spanish-Language Names

Avoid long legal names. Prefer given name plus primary surname, or registered
nickname when usage is strong.

### Portuguese and Brazilian Names

Prefer registered names, mononyms, and common football usage.

- `Neymar` -> `네이마르`
- `Richarlison` -> common Korean football usage

### Particle Names

Do not blindly remove particles such as `van`, `de`, `da`, `dos`, `del`,
`de la`, `bin`, `ben`, `al`, or `el`. They may be part of the UI short name.

## Post-Validator Responsibilities

The validator has final authority for import eligibility. It must re-check:

- Missing/additional/duplicate `api_player_id`
- Required header order
- Latin letters, dots, initials, and suspicious symbols
- Missing country mappings
- Korean surname-only short names
- Short-name collision within same team/league context
- High-popularity rows generated only by language rules
- Large changes from previous values
- Too-long legal names
- Low confidence

Rows failing import conditions are written to review CSV, not imported.
