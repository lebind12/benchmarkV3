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
  it('counts API-Football once without miscounting it as a web publisher', () => {
    const value=preview(); expect(homePreviewSchema.safeParse(value).success).toBe(true)
    const view=mount(HomeExternalPredictions,{props:{preview:value}})
    expect(view.get('[data-testid="forecast-coverage"]').text()).toContain('1/3')
    expect(view.findAll('[data-testid="media-forecast"]')).toHaveLength(0)
    expect(view.findAll('[data-testid="algorithm-forecast"]')).toHaveLength(1)
    value.external.predictions.coverage.web_source_count=1
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
  })
  it('completes three forecasts with two web publishers and one API prediction', () => {
    const value=preview()
    for(const [i,host] of ['sportsmole.co.uk','football365.com'].entries()) {
      const id=`media-${i}`
      value.sources.push({id,fixture_id:value.fixture.external_id,kind:'web',title:host,url:`https://${host}/preview`,published_at:null,retrieved_at:value.as_of})
      value.external.predictions.source_ids.push(id)
      value.external.predictions.data.push({source_id:id,outlook:'Media view',summary:'Original verified opinion'})
    }
    value.external.predictions.coverage.web_source_count=2;value.external.predictions.status='available';value.external.predictions.reason=null
    expect(homePreviewSchema.safeParse(value).success).toBe(true)
    const view=mount(HomeExternalPredictions,{props:{preview:value}})
    expect(view.get('[data-testid="forecast-coverage"]').text()).toContain('3/3')
    expect(view.findAll('[data-testid="media-forecast"]')).toHaveLength(2)
    expect(view.findAll('[data-testid="algorithm-forecast"]')).toHaveLength(1)
  })
})
