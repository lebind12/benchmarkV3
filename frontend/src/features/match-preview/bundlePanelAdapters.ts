/**
 * bundle_pipeline 섹션 실행 결과와 기존 R2/R4 진단 패널, 그리고 관리자 카드
 * 미리보기(`MatchPreviewBody`) 사이를 잇는 순수 표시 어댑터.
 *
 * 값을 지어내거나 실패를 성공으로 바꾸지 않는다. 기존 R2/R4 모듈 모양이 이미
 * 있으면 그대로 통과시킨다.
 */
import { toMatchPreviewView, type MatchPreviewView } from '@/lib/api/previewView'
import type { FixtureCandidate } from './fixtures'
import type { AvailabilityR2ResultView } from './panels/AvailabilityPanel.vue'
import type {
  PlayersR4ResultView,
  PlayersUnmappedView,
  SelectedPlayerView,
} from './panels/players'
import type {
  ModuleInspection,
  PlayerSectionProcessingViewData,
  PlayerSectionSlotDraftView,
  RunDetail,
  SectionResultView,
} from './types'

const SLOT_KEYS = ['home1', 'home2', 'away1', 'away2'] as const

function slotDraftsFromProcessing(
  processing: PlayerSectionProcessingViewData | null | undefined,
): PlayerSectionSlotDraftView[] {
  if (!processing) return []
  const items: PlayerSectionSlotDraftView[] = []
  for (const key of SLOT_KEYS) {
    const slot = processing[key]
    if (slot) items.push(slot)
  }
  return items
}

function resolveRawModelText(
  body: Record<string, unknown> | null,
  module: ModuleInspection | null,
  processing: PlayerSectionProcessingViewData | null | undefined,
): string | null {
  if (typeof body?.raw_model_text === 'string' && body.raw_model_text) {
    return body.raw_model_text
  }
  if (typeof body?.model_text === 'string' && body.model_text) {
    return body.model_text
  }
  const attempts = processing?.attempts ?? []
  if (attempts.length > 0) {
    const adoptedOrd = processing?.adopted_attempt_ordinal
    const chosen =
      (adoptedOrd !== null && adoptedOrd !== undefined
        ? attempts.find((a) => a.attempt_ordinal === adoptedOrd)
        : undefined) ?? attempts[attempts.length - 1]
    if (chosen?.raw_text) return chosen.raw_text
    if (chosen?.parsed_json) return JSON.stringify(chosen.parsed_json, null, 2)
  }
  const moduleAttempts = module?.tabs?.response?.attempts ?? []
  if (moduleAttempts.length > 0) {
    const content = moduleAttempts[moduleAttempts.length - 1]?.content
    if (typeof content === 'string') return content
    if (content && typeof content === 'object') return JSON.stringify(content, null, 2)
  }
  return null
}

function stringListFromRecord(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function sourceListFromBody(body: Record<string, unknown> | null) {
  const raw = Array.isArray(body?.sources) ? body.sources : []
  return raw
    .filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object'))
    .map((row) => ({
      label: typeof row.label === 'string' ? row.label : null,
      url: typeof row.url === 'string' ? row.url : null,
      kind: typeof row.kind === 'string' ? row.kind : undefined,
      note: typeof row.note === 'string' ? row.note : null,
    }))
}

export function adaptPlayersPanelResult(
  body: Record<string, unknown> | null,
  module: ModuleInspection | null,
  processing: PlayerSectionProcessingViewData | null | undefined,
): PlayersR4ResultView | null {
  if (!body && !processing) return null
  if (body && Array.isArray(body.players)) {
    return body as unknown as PlayersR4ResultView
  }

  const slots = slotDraftsFromProcessing(processing)
  const structuredObj =
    body?.structured && typeof body.structured === 'object'
      ? (body.structured as Record<string, unknown>)
      : null
  const structuredPlayers = Array.isArray(structuredObj?.players)
    ? (structuredObj.players as Record<string, unknown>[])
    : []

  if (slots.length === 0 && structuredPlayers.length === 0) {
    return body as unknown as PlayersR4ResultView
  }

  const players: SelectedPlayerView[] = []
  const unmapped: PlayersUnmappedView[] = []
  let resolvedCount = 0
  let unresolvedCount = 0

  if (slots.length > 0) {
    for (const slot of slots) {
      if (slot.resolution_status === 'empty' && !slot.name_ko && !slot.original_name) continue
      const isResolved = slot.resolution_status === 'resolved'
      if (isResolved) resolvedCount += 1
      else unresolvedCount += 1
      const displayName = slot.name_ko || slot.original_name || ''
      const mappedNameSource =
        slot.name_source === 'db_ko' ? 'db_korean' : (slot.name_source ?? 'original')
      players.push({
        selected_player: displayName,
        selection_reason: slot.body || '',
        team: slot.team_name ?? null,
        model_selected_player: slot.original_name || null,
        player_id: slot.player_id ?? null,
        external_id: slot.external_player_id ?? null,
        id_space: slot.external_player_id ? 'external' : 'internal',
        name_source: mappedNameSource,
        mapping_status: isResolved ? 'resolved' : 'unresolved',
        mapping_reason: isResolved ? null : (slot.unresolved_reason ?? 'db_korean_missing'),
        team_display_name: slot.team_name ?? null,
        evidence: slot.evidence ?? [],
        claim_id: slot.slot_key,
      })
      if (!isResolved) {
        unmapped.push({
          kind: 'player',
          original: slot.original_name || displayName,
          display_name: slot.name_ko || null,
          reason: slot.unresolved_reason ?? 'db_korean_missing',
          detail: slot.slot_key,
        })
      }
    }
  } else {
    for (const row of structuredPlayers) {
      const playerName = typeof row.player === 'string' ? row.player : ''
      const reason = typeof row.reason === 'string' ? row.reason : ''
      const isUnresolved = Boolean(row.unresolved)
      if (isUnresolved) unresolvedCount += 1
      else resolvedCount += 1
      players.push({
        selected_player: playerName,
        selection_reason: reason,
        team: typeof row.team === 'string' ? row.team : null,
        model_selected_player: typeof row.original_name === 'string' ? row.original_name : null,
        player_id: typeof row.player_id === 'number' ? row.player_id : null,
        external_id: typeof row.external_player_id === 'number' ? row.external_player_id : null,
        name_source: typeof row.name_source === 'string' ? row.name_source : 'original',
        mapping_status: isUnresolved ? 'unresolved' : 'resolved',
        mapping_reason:
          typeof row.unresolved_reason === 'string' ? row.unresolved_reason : null,
      })
    }
  }

  const attemptCount =
    processing && processing.module_attempt_count > 0
      ? processing.module_attempt_count
      : (module?.attempt_count ?? 0)
  const latest = module?.tabs?.transform
  return {
    module_id: 'R4',
    output_contract_version:
      processing?.output_contract_version ?? latest?.contract_version ?? undefined,
    implementation_version:
      (typeof body?.implementation_version === 'string'
        ? body.implementation_version
        : latest?.implementation_version) ?? undefined,
    prompt_version:
      (typeof body?.prompt_version === 'string'
        ? body.prompt_version
        : latest?.prompt_version) ?? undefined,
    mode:
      (typeof body?.mode === 'string' ? body.mode : processing?.mode) ??
      module?.run_mode?.mode ??
      undefined,
    players,
    unmapped,
    mapping: {
      resolved: resolvedCount,
      unresolved: unresolvedCount,
      resolver_injected: true,
    },
    diagnostics: [
      ...(processing?.diagnostics ?? []),
      ...stringListFromRecord(latest?.diagnostics),
    ],
    raw_model_text: resolveRawModelText(body, module, processing),
    reader_sources: sourceListFromBody(body),
    attempt_count: attemptCount,
    external_calls: typeof body?.external_calls === 'number' ? body.external_calls : undefined,
  }
}

export function adaptAvailabilityPanelResult(
  body: Record<string, unknown> | null,
  module: ModuleInspection | null,
  processing: PlayerSectionProcessingViewData | null | undefined,
): AvailabilityR2ResultView | null {
  if (!body && !processing) return null
  if (body && body.research && typeof body.research === 'object') {
    return body as unknown as AvailabilityR2ResultView
  }

  const slots = slotDraftsFromProcessing(processing)
  const structuredObj =
    body?.structured && typeof body.structured === 'object'
      ? (body.structured as Record<string, unknown>)
      : null
  const structuredInjuries = Array.isArray(structuredObj?.injuries)
    ? (structuredObj.injuries as Record<string, unknown>[])
    : []

  if (slots.length === 0 && structuredInjuries.length === 0 && !body) {
    return null
  }

  const sources = sourceListFromBody(body)
  const groundingSources = sources
    .filter((s): s is typeof s & { url: string } => typeof s.url === 'string' && s.url.length > 0)
    .map((s) => ({ uri: s.url, title: s.label ?? null }))

  const teamNames: Record<string, string> = {}
  const facts: AvailabilityR2ResultView['research']['facts'] = []
  const updates: AvailabilityR2ResultView['research']['player_updates'] = []

  if (slots.length > 0) {
    for (const slot of slots) {
      if (slot.team_id !== null && slot.team_name) {
        teamNames[String(slot.team_id)] = slot.team_name
      }
      const displayName = slot.name_ko || slot.original_name || null
      const rawStatus = slot.status || 'unknown'
      const normalizedStatus =
        rawStatus === 'out' || rawStatus === 'confirmed_absence'
          ? 'confirmed_absence'
          : rawStatus === 'doubt' || rawStatus === 'doubtful'
            ? 'doubtful'
            : rawStatus
      facts.push({
        evidence_id: slot.slot_key,
        player_id: slot.player_id ?? 0,
        player_name: displayName,
        team_id: slot.team_id ?? null,
        type_marker: slot.status ?? null,
        reason: slot.injury ?? null,
        uncertainty: slot.body || '',
        expected_status: normalizedStatus,
        collected_at: null,
        snapshot_id: null,
        adopted: true,
      })
      updates.push({
        player_id: slot.player_id ?? null,
        player_name: displayName,
        team_id: slot.team_id ?? null,
        status: normalizedStatus,
        summary: slot.body || '',
        evidence: slot.evidence ?? [],
        conflict: false,
        api_status: slot.status ?? null,
      })
    }
  } else {
    structuredInjuries.forEach((row, index) => {
      const teamId = typeof row.team_id === 'number' ? row.team_id : null
      if (teamId !== null && typeof row.team === 'string') {
        teamNames[String(teamId)] = row.team
      }
      const rawStatus = typeof row.status === 'string' ? row.status : 'unknown'
      const playerName = typeof row.player === 'string' ? row.player : null
      const summary = typeof row.summary === 'string' ? row.summary : ''
      facts.push({
        evidence_id: `injury-${index}`,
        player_id: typeof row.player_id === 'number' ? row.player_id : 0,
        player_name: playerName,
        team_id: teamId,
        type_marker: rawStatus,
        reason: typeof row.reason === 'string' ? row.reason : null,
        uncertainty: summary,
        expected_status: rawStatus,
        collected_at: null,
        snapshot_id: null,
        adopted: true,
      })
      updates.push({
        player_id: typeof row.player_id === 'number' ? row.player_id : null,
        player_name: playerName,
        team_id: teamId,
        status: rawStatus,
        summary,
        evidence: [],
        conflict: false,
        api_status: rawStatus,
      })
    })
  }

  const attemptCount =
    processing && processing.module_attempt_count > 0
      ? processing.module_attempt_count
      : (module?.attempt_count ?? 0)
  const latest = module?.tabs?.transform
  const grounding: AvailabilityR2ResultView['research']['grounding'] = {
    available: groundingSources.length > 0,
    sources: groundingSources,
    queries: [],
    supports: [],
    search_entry_point: null,
  }

  return {
    module_id: 'R2',
    implementation_version:
      (typeof body?.implementation_version === 'string'
        ? body.implementation_version
        : latest?.implementation_version) ?? '-',
    prompt_version:
      (typeof body?.prompt_version === 'string'
        ? body.prompt_version
        : latest?.prompt_version) ?? '-',
    mode:
      (typeof body?.mode === 'string' ? body.mode : processing?.mode) ??
      module?.run_mode?.mode ??
      '',
    claims: (latest?.claims ?? []).map((c) => ({
      claim_id: String(c.claim_id ?? ''),
      kind: String(c.kind ?? ''),
      text: String(c.text ?? ''),
      decision: String(c.decision ?? ''),
      decision_reason: c.decision_reason ? String(c.decision_reason) : null,
      source_url: c.source_url ? String(c.source_url) : null,
    })),
    coverage: (latest?.coverage ?? []).map((c) => ({
      topic: String(c.topic ?? ''),
      state: String(c.state ?? ''),
      detail: c.detail ? String(c.detail) : null,
    })),
    research: {
      material_state: facts.length > 0 ? 'available' : 'empty_response',
      material_detail:
        facts.length > 0
          ? '섹션 워크플로우(R2) 저장 결과에서 투영했습니다.'
          : '저장된 부상·결장 슬롯 항목이 없습니다.',
      facts,
      player_updates: updates,
      reported_absences: [],
      impacts: [],
      uncertainties: [],
      search_note: null,
      rejected: [],
      grounding,
      search_snapshot_id: null,
      team_names: teamNames,
      fixture_label: null,
    },
    raw_grounding: grounding,
    model_text: resolveRawModelText(body, module, processing),
    attempt_count: attemptCount,
    status: module?.status,
    quality:
      typeof body?.quality === 'string' ? body.quality : (module?.quality ?? undefined),
  }
}

export function buildAdminCardPreviewFromDetail(
  detail: RunDetail,
  rows: readonly SectionResultView[],
): MatchPreviewView | null {
  if (rows.length === 0) return null
  const candidate: FixtureCandidate | null =
    detail.fixture || detail.summary.fixture_label
      ? {
          fixture_id: detail.fixture?.fixture_id ?? 0,
          league_id: detail.fixture?.league_id ?? 0,
          season: detail.fixture?.season ?? 0,
          home_team_id: detail.fixture?.home_team_id ?? null,
          away_team_id: detail.fixture?.away_team_id ?? null,
          kickoff_at: detail.fixture?.kickoff_at ?? '',
          league_name: '',
          home_team_name: null,
          away_team_name: null,
          label: detail.summary.fixture_label ?? '',
        }
      : null
  return toMatchPreviewView({
    run_id: detail.summary.run_id,
    preview: null,
    sections: {
      run_id: detail.summary.run_id,
      section_results: [...rows],
    },
    fixture: candidate,
  })
}

export function buildAdminCardPreviewFromSectionRun(
  runId: string,
  rows: readonly SectionResultView[],
  fixture: FixtureCandidate | null,
): MatchPreviewView | null {
  if (rows.length === 0) return null
  return toMatchPreviewView({
    run_id: runId,
    preview: null,
    sections: {
      run_id: runId,
      section_results: [...rows],
    },
    fixture,
  })
}
