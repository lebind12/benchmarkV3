import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import RunLogs from '@/components/management/RunLogs.vue'
import { createSeed } from '../../fixtures/management/data'
const sample=()=>createSeed().runs.find(run=>run.id==='sample-1006')!
it('renders only populated categories and keeps the initial log bodies collapsed',()=>{
 const wrapper=mount(RunLogs,{props:{run:sample()}})
 expect(wrapper.findAll('.mm-log-group')).toHaveLength(3)
 expect(wrapper.find('[data-testid="log-group-teams"]').exists()).toBe(false)
 expect(wrapper.findAll('.mm-event-list')).toHaveLength(0)
 expect(wrapper.findAll('.mm-log-group-toggle').every(button=>button.attributes('aria-expanded')==='false')).toBe(true)
 wrapper.unmount()
})
it('appends to the open category while new categories start collapsed and empty ones disappear',async()=>{
 const run=sample(),wrapper=mount(RunLogs,{props:{run}})
 await wrapper.get('[data-testid="log-group-events"] button').trigger('click')
 const earlier={...run.logs[0],at:'2000-01-01T00:00:00Z',analysis:{...run.logs[0].analysis!,title:'먼저 발생한 이벤트'}}
 const team={...earlier,analysis:{...earlier.analysis,category:'teams',category_label:'팀',title:'팀 데이터 처리'}}
 await wrapper.setProps({run:{...run,logs:[...run.logs,earlier,team]}})
 const group=wrapper.get('[data-testid="log-group-events"]')
 expect(group.get('button').attributes('aria-expanded')).toBe('true')
 expect(group.get('.mm-log-group-count').text()).toBe('2건')
 expect(group.findAll('li')).toHaveLength(2)
 expect(group.findAll('li strong')[0]!.text()).toBe('먼저 발생한 이벤트')
 expect(wrapper.get('[data-testid="log-group-teams"] button').attributes('aria-expanded')).toBe('false')
 await wrapper.setProps({run:{...run,logs:[team]}})
 expect(wrapper.find('[data-testid="log-group-events"]').exists()).toBe(false)
 expect(wrapper.findAll('.mm-log-group')).toHaveLength(1)
 wrapper.unmount()
})
it('shows a single empty notice without zero-count sections',()=>{
 const wrapper=mount(RunLogs,{props:{run:{...sample(),logs:[]}}})
 expect(wrapper.findAll('.mm-log-group')).toHaveLength(0)
 expect(wrapper.text()).toContain('아직 수집 로그가 없습니다')
 wrapper.unmount()
})
it('expands matching errors and warnings, hides empty filtered groups and keeps raw messages',async()=>{
 const run=createSeed().runs.find(run=>run.id==='sample-1001')!
 const wrapper=mount(RunLogs,{props:{run}})
 expect(wrapper.findAll('.mm-event-list')).toHaveLength(0)
 await wrapper.get('[aria-label="로그 수준"]').setValue('error')
 expect(wrapper.findAll('.mm-log-group')).toHaveLength(1)
 expect(wrapper.findAll('li')).toHaveLength(2)
 expect(wrapper.get('[data-testid="log-group-error"] button').text()).toContain('오류 2')
 expect(wrapper.find('pre').text()).toContain('IntegrityError')
 await wrapper.get('[aria-label="로그 수준"]').setValue('warning')
 expect(wrapper.findAll('li')).toHaveLength(2)
 expect(wrapper.get('[data-testid="log-group-error"] button').text()).toContain('경고 2')
 await wrapper.findAll('button').find(button=>button.text()==='전체 접기')!.trigger('click')
 expect(wrapper.findAll('li')).toHaveLength(0)
 wrapper.unmount()
})
it('opens the groups matching a cause and resets disclosure state for another run',async()=>{
 const run=createSeed().runs.find(run=>run.id==='sample-1001')!
 const wrapper=mount(RunLogs,{props:{run}})
 await wrapper.findAll('.mm-cause-list button').find(button=>button.text().includes('외부 API 응답 지연'))!.trigger('click')
 expect(wrapper.findAll('li')).toHaveLength(2)
 expect(wrapper.findAll('.mm-log-group')).toHaveLength(1)
 await wrapper.setProps({run:{...run,id:'another-run'}})
 expect(wrapper.findAll('.mm-event-list')).toHaveLength(0)
 expect((wrapper.get('[aria-label="로그 수준"]').element as HTMLSelectElement).value).toBe('all')
 wrapper.unmount()
})
