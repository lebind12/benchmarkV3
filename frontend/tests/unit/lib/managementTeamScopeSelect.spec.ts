import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TeamScopeSelect from '@/components/management/TeamScopeSelect.vue'
import ResourceLogo from '@/components/management/ResourceLogo.vue'
const options = [
  {id:42,name:'아스널',name_en:'Arsenal',logo_url:'https://media.api-sports.io/football/teams/42.png'},
  {id:40,name:'리버풀',name_en:'Liverpool',logo_url:null},
]
afterEach(() => { document.body.innerHTML=''; vi.restoreAllMocks() })
describe('team logo scope dropdown', () => {
  it('supports country strings, Korean and English search without team logos',async()=>{
    const wrapper=mount(TeamScopeSelect,{attachTo:document.body,props:{modelValue:'',options:[{id:'South-Korea',name:'대한민국',name_en:'South-Korea',aliases:['한국']}],label:'카탈로그 국가',allLabel:'전체 국가·국제대회',showLogos:false}})
    expect(wrapper.get('button').text()).toContain('전체 국가·국제대회')
    await wrapper.get('button').trigger('click');await flushPromises()
    const input=new DOMWrapper(document.querySelector('.mm-team-menu input') as HTMLInputElement)
    await input.setValue('south korea')
    expect(document.querySelectorAll('[role=option]')).toHaveLength(1)
    expect(document.querySelector('[role=option]')?.textContent).toContain('대한민국')
    expect(document.querySelector('.mm-team-menu img')).toBeNull()
    await input.setValue('대한');expect(document.querySelectorAll('[role=option]')).toHaveLength(1)
    await input.setValue('한국');await input.trigger('keydown',{key:'Enter'});await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([['South-Korea']])
    wrapper.unmount()
  })
  it('searches English names, selects with Enter and restores focus to the trigger', async () => {
    const wrapper=mount(TeamScopeSelect,{attachTo:document.body,props:{modelValue:'',options,label:'선수 팀 조건'}})
    await wrapper.get('button').trigger('click'); await flushPromises()
    const input=new DOMWrapper(document.querySelector('.mm-team-menu input') as HTMLInputElement)
    expect(document.activeElement).toBe(input.element)
    await input.setValue('ars')
    expect(document.querySelectorAll('[role=option]')).toHaveLength(1)
    expect(document.querySelector('[role=option]')?.textContent).toContain('아스널')
    expect(document.querySelector('[role=option] img')?.getAttribute('src')).toContain('/42.png')
    await input.trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([['42']])
    expect(document.querySelector('.mm-team-menu')).toBeNull()
    expect(document.activeElement).toBe(wrapper.get('button').element)
    wrapper.unmount()
  })
  it('supports Escape and outside pointer closing without changing the selection',async()=>{
    const wrapper=mount(TeamScopeSelect,{attachTo:document.body,props:{modelValue:'40',options,label:'감독 팀 조건'}})
    await wrapper.get('button').trigger('click'); await flushPromises()
    await new DOMWrapper(document.querySelector('.mm-team-menu input')!).trigger('keydown',{key:'Escape'})
    await flushPromises(); expect(document.querySelector('.mm-team-menu')).toBeNull()
    await wrapper.get('button').trigger('click'); await flushPromises()
    document.body.dispatchEvent(new Event('pointerdown',{bubbles:true})); await flushPromises()
    expect(document.querySelector('.mm-team-menu')).toBeNull()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })
  it('shows a named fallback on broken images and retries when the URL changes',async()=>{
    const wrapper=mount(ResourceLogo,{props:{src:options[0].logo_url,alt:'아스널 팀 로고'}})
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('[role=img]').attributes('aria-label')).toBe('아스널 팀 로고 없음')
    await wrapper.setProps({src:'https://media.api-sports.io/football/teams/40.png'})
    expect(wrapper.get('img').attributes('src')).toContain('/40.png')
    wrapper.unmount()
  })
  it('ignores unrelated scrolling and stays anchored during result layout changes',async()=>{
    const wrapper=mount(TeamScopeSelect,{attachTo:document.body,props:{modelValue:'',options,label:'감독 팀 조건'}})
    await wrapper.get('button').trigger('click'); await flushPromises()
    const unrelated=document.createElement('select'); document.body.append(unrelated)
    unrelated.dispatchEvent(new Event('scroll')); await flushPromises()
    expect(document.querySelector('.mm-team-menu')).not.toBeNull()
    document.dispatchEvent(new Event('scroll')); await flushPromises()
    expect(document.querySelector('.mm-team-menu')).not.toBeNull()
    vi.spyOn(wrapper.get('button').element,'getBoundingClientRect').mockReturnValue({top:-100,bottom:-60} as DOMRect)
    document.dispatchEvent(new Event('scroll')); await flushPromises()
    expect(document.querySelector('.mm-team-menu')).toBeNull()
    wrapper.unmount()
  })
})
