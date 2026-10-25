import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HomeExternalPredictions from '@/components/home-preview/HomeExternalPredictions.vue'
import { homePreviewSchema } from '@/lib/api/homePreviewSchema'
import records from '@/mocks/home-preview/previews.json'

function preview() {
  const value: any = structuredClone(records['90001'])
  value.sources.push({id:'api-algorithm',fixture_id:value.fixture.external_id,kind:'api',title:'API',url:'https://v3.football.api-sports.io/predictions',published_at:null,retrieved_at:value.as_of})
  value.external.predictions={status:'partial',reason:'insufficient_sample',as_of:value.as_of,source_ids:['api-algorithm'],data:[{source_id:'api-algorithm',outlook:'API prediction',summary:'API algorithm'}],coverage:{target_count:3,web_source_count:0,candidate_count:0,checked_at:null,reason_codes:['no_verified_source']}}
  return value
}
describe('independent media forecast target', () => {
  it('does not count API-Football as a media source or invent missing sources', () => {
    const value=preview(); expect(homePreviewSchema.safeParse(value).success).toBe(true)
    const view=mount(HomeExternalPredictions,{props:{preview:value}})
    expect(view.get('[data-testid="forecast-coverage"]').text()).toContain('0/3')
    expect(view.findAll('[data-testid="media-forecast"]')).toHaveLength(0)
    expect(view.findAll('[data-testid="algorithm-forecast"]')).toHaveLength(1)
    value.external.predictions.coverage.web_source_count=1
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
  })
  it('counts three different verified publishers and keeps the API separate', () => {
    const value=preview()
    for(const [i,host] of ['sportsmole.co.uk','racingpost.com','football365.com'].entries()) {
      const id=`media-${i}`
      value.sources.push({id,fixture_id:value.fixture.external_id,kind:'web',title:host,url:`https://${host}/preview`,published_at:null,retrieved_at:value.as_of})
      value.external.predictions.source_ids.push(id)
      value.external.predictions.data.push({source_id:id,outlook:'Media view',summary:'Original verified opinion'})
    }
    value.external.predictions.coverage.web_source_count=3;value.external.predictions.status='available';value.external.predictions.reason=null
    expect(homePreviewSchema.safeParse(value).success).toBe(true)
    const view=mount(HomeExternalPredictions,{props:{preview:value}})
    expect(view.get('[data-testid="forecast-coverage"]').text()).toContain('3/3')
    expect(view.findAll('[data-testid="media-forecast"]')).toHaveLength(3)
    expect(view.findAll('[data-testid="algorithm-forecast"]')).toHaveLength(1)
  })
})
