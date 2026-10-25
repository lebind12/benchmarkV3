import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PreviewPlayerPhoto from '@/components/home-preview/PreviewPlayerPhoto.vue'

describe('preview player photo', () => {
  it('uses the supplied player photo, falls back on error, and resets for a new photo', async () => {
    const view = mount(PreviewPlayerPhoto, { props: { name: '선수', photoUrl: 'https://media.api-sports.io/football/players/700.png' } })
    expect(view.get('img').attributes('alt')).toBe('선수 선수 사진')
    await view.get('img').trigger('error')
    expect(view.find('img').exists()).toBe(false)
    expect(view.get('[role="img"]').attributes('aria-label')).toContain('사진 없음')
    await view.setProps({ name: '다른 선수', photoUrl: 'https://media.api-sports.io/football/players/701.png' })
    expect(view.get('img').attributes('src')).toContain('/701.png')
  })
  it('does not fabricate a URL for a missing player photo', () => {
    const view = mount(PreviewPlayerPhoto, { props: { name: '선수' } })
    expect(view.find('img').exists()).toBe(false)
    expect(view.find('[role="img"]').exists()).toBe(true)
  })
})
