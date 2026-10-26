import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import CatalogPanel from '@/components/management/CatalogPanel.vue'
import { managementApiKey, type ManagementApi, type CatalogResult } from '@/lib/api/management'
const result=(name:string):CatalogResult=>({items:[{id:7,name,name_en:'Asian Cup',country:'World',seasons:[2027,2023],standings:true}],total:1,catalog_total:1,page:1,page_size:20,countries:[{value:'World',label:'국제대회'}],updated_at:null})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()})
it('ignores stale catalog responses after a new search and disables obsolete choices during debounce',async()=>{
 vi.useFakeTimers()
 let resolveOld!:(value:CatalogResult)=>void
 const catalog=vi.fn().mockImplementationOnce(()=>new Promise< CatalogResult >(resolve=>{resolveOld=resolve})).mockResolvedValueOnce(result('새 검색 결과'))
 const wrapper=mount(CatalogPanel,{props:{targets:[]},global:{provide:{[managementApiKey as symbol]:{catalog} as unknown as ManagementApi}}})
 await wrapper.get('[aria-label="카탈로그 검색어"]').setValue('아시')
 await vi.advanceTimersByTimeAsync(250);await flushPromises()
 expect(wrapper.text()).toContain('새 검색 결과')
 resolveOld(result('이전 응답'));await flushPromises()
 expect(wrapper.text()).not.toContain('이전 응답')
 await wrapper.get('[aria-label="카탈로그 검색어"]').setValue('다른 조건')
 expect(wrapper.find('.mm-catalog-row').exists()).toBe(false)
 wrapper.unmount()
})
it('recovers from request errors while retaining the typed search and filters',async()=>{
 vi.useFakeTimers()
 const catalog=vi.fn().mockResolvedValueOnce(result('아시안컵')).mockRejectedValueOnce(new Error('조회 실패')).mockResolvedValueOnce(result('다시 찾은 대회'))
 const wrapper=mount(CatalogPanel,{props:{targets:[]},global:{provide:{[managementApiKey as symbol]:{catalog} as unknown as ManagementApi}}})
 await flushPromises()
 await wrapper.get('[aria-label="카탈로그 검색어"]').setValue('아시')
 await vi.advanceTimersByTimeAsync(250);await flushPromises()
 expect(wrapper.get('[role="alert"]').text()).toBe('조회 실패')
 expect(wrapper.findAll('.mm-catalog-row')).toHaveLength(0)
 await wrapper.findAll('button').find(button=>button.text()==='대회 검색')!.trigger('click');await flushPromises()
 expect((wrapper.get('[aria-label="카탈로그 검색어"]').element as HTMLInputElement).value).toBe('아시')
 expect(wrapper.text()).toContain('다시 찾은 대회')
 wrapper.unmount()
})
