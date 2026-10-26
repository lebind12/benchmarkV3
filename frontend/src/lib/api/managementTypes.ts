export type EntityType = 'league' | 'team' | 'player' | 'coach'
export type RunStatus = 'queued' | 'running' | 'cancel_requested' | 'succeeded' | 'partial_failed' | 'failed' | 'cancelled' | 'interrupted'
export interface CatalogQuery { query?: string; id?: number; country?: string; type?: string; group?: string; page?: number; page_size?: number }
export interface CatalogResult { items: CatalogLeague[]; total: number; catalog_total: number; page: number; page_size: number; countries: {value:string;label:string}[]; updated_at: string | null }
export interface CatalogLeague { type?: string; country_label?: string; aliases?: string[]; featured?: boolean; logo_url?: string | null; id: number; name: string; name_en: string; country: string; seasons: number[]; standings: boolean }
export interface CollectionTarget { logo_url?: string | null; id: number; league_id: number; name: string; name_en: string; country: string; season: number; is_active: boolean; include_details: boolean; include_players: boolean; include_standings: boolean; fixture_limit: number | null; initial_status: string; last_sync: string | null }
export interface TargetInput { league_id: number; season: number; is_active: boolean; include_details: boolean; include_players: boolean; include_standings: boolean; fixture_limit: number | null }
export interface RunItem { stored_rows?: number; total_known?: boolean; target_id: number; name: string; season: number; status: string; total: number; saved: number; failed: number; pending: number; options?: { include_details: boolean; include_players: boolean; include_standings: boolean; fixture_limit: number | null } }
export interface LogAnalysis { code:string; title:string; action:string; category:string; category_label:string; level:'info'|'warning'|'error'; stage:string|null; target:string|null; classified:boolean }
export interface RunLog { analysis?:LogAnalysis; at: string; message: string; code?: string; level?: 'info' | 'warning' | 'error'; target_id?: number; stage?: string; attempt?: number; max_attempts?: number }
export interface CatalogSyncResult { updated_at: string; api_count: number; synced_count: number; catalog_count: number }
export interface CollectionRun { log_unclassified_count?:number; log_statistics_scope?: 'full'|'retained'; counts_kind?: string; log_statistics?: Record<string, {code: string; errors: number; warnings: number; target_ids: number[]}>; log_counts?: {total: number; retained: number; dropped: number}; id: string; mode: 'initial' | 'refresh'; status: RunStatus; created_at: string; started_at: string; finished_at: string | null; cancel_requested_at: string | null; actor: string; parent_run_id: string | null; items: RunItem[]; logs: RunLog[]; progress: number; stage: string }
export interface TranslationQuery { query?: string; type?: string; status?: string; page?: number; league_id?: number; team_id?: number }
export interface TranslationScopeOption { logo_url?: string | null; id: number; name: string; name_en: string }
export interface TranslationAffiliationFilters { leagues: TranslationScopeOption[]; teams: TranslationScopeOption[] }
export interface TranslationEntry { affiliations?: { league_id: number; team_id: number }[]; id: number; type: EntityType; original: string; context: string; name_ko: string | null; short_name_ko: string | null; protected: boolean; version: number; editor: string; updated_at: string }
export interface TranslationChange { version: number; editor: string; at: string; before: { name_ko: string | null; short_name_ko: string | null }; after: { name_ko: string | null; short_name_ko: string | null } }
export class ManagementApiError extends Error {
  constructor(message: string, public status: number, public code: string, public current?: TranslationEntry) { super(message) }
}
