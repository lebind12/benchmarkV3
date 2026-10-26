import { inject, type InjectionKey } from 'vue'
import { authenticatedFetch } from './session'
import { ManagementApiError } from './managementTypes'
import type { CatalogQuery,CatalogResult,CatalogSyncResult,CollectionTarget,TargetInput,CollectionRun,TranslationQuery,TranslationEntry,TranslationChange,TranslationAffiliationFilters } from './managementTypes'
export * from './managementTypes'
export interface ManagementApi {
  catalog(params?:CatalogQuery):Promise<CatalogResult>
  refreshCatalog():Promise<CatalogSyncResult>
  targets():Promise<{items:CollectionTarget[];persistence_available:boolean;scheduler_enabled?:boolean}>
  saveTarget(body:TargetInput,id?:number):Promise<CollectionTarget>
  toggleTarget(id:number,is_active:boolean):Promise<CollectionTarget>
  removeTarget(id:number):Promise<{removed:boolean}>
  run(id:string):Promise<CollectionRun>
  runs():Promise<{active:CollectionRun|null;items:CollectionRun[]}>
  start(target_ids:number[],mode:'initial'|'refresh',parent_run_id:string|null):Promise<CollectionRun>
  cancel(id:string):Promise<CollectionRun>
  translationAffiliationFilters(type:'player'|'coach',league_id?:number):Promise<TranslationAffiliationFilters>
  translations(params?:TranslationQuery):Promise<{items:TranslationEntry[];total?:number;page_size?:number;missing_count?:number}>
  saveTranslation(row:TranslationEntry,name_ko:string|null,short_name_ko:string|null):Promise<TranslationEntry>
  translationHistory(row:TranslationEntry):Promise<{items:TranslationChange[]}>
}
export const managementApiKey: InjectionKey<ManagementApi> = Symbol('managementApi')
export function useManagementApi() { const api = inject(managementApiKey); if (!api) throw new Error('관리 API가 연결되지 않았습니다.'); return api }
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await authenticatedFetch(`/api/v1/admin/management${path}`, { method, headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  const payload = await response.json().catch(() => ({ message: '서버 응답을 확인하지 못했습니다. 잠시 후 다시 시도하세요.' }))
  if (!response.ok) throw new ManagementApiError(payload.message ?? (typeof payload.detail === 'string' ? payload.detail : '입력한 설정을 확인하세요.'), response.status, payload.code ?? 'request_failed', payload.current)
  return payload as T
}
const query = (params?: Record<string, string | number | undefined>) => params ? '?' + new URLSearchParams(Object.entries(params).filter(([,v]) => v !== undefined && v !== '').map(([k,v]) => [k,String(v)])) : ''
export const managementApi: ManagementApi = {
  catalog: (params) => request(`/catalog${query(params && {...params})}`),
  refreshCatalog: () => request('/catalog/refresh','POST'),
  targets: () => request('/targets'),
  saveTarget: (body,id) => request(id ? `/targets/${id}` : '/targets', id ? 'PATCH' : 'POST', body),
  toggleTarget: (id,is_active) => request(`/targets/${id}`,'PATCH',{is_active}),
  removeTarget: (id) => request(`/targets/${id}`,'DELETE'),
  run: (id) => request(`/runs/${id}`),
  runs: () => request('/runs'),
  start: (target_ids,mode,parent_run_id) => request('/runs','POST',{target_ids,mode,parent_run_id}),
  cancel: (id) => request(`/runs/${id}/cancel`,'POST'),
  translationAffiliationFilters: (type, league_id) => request(`/translations/affiliation-filters${query({type,league_id})}`),
  translations: (params) => request(`/translations${query(params && {...params})}`),
  saveTranslation: (row,name_ko,short_name_ko) => request(`/translations/${row.type}/${row.id}`,'PATCH',{name_ko,short_name_ko,expected_version:row.version}),
  translationHistory: (row) => request(`/translations/${row.type}/${row.id}/history`),
}
