/**
 * 수집 시험 전용 프록시 규칙 검사.
 *
 * 확인하는 것은 사용자가 관측하는 두 가지다.
 *
 * 1. 수집 시험 접두사만 별도 수집 서버로 가고, 나머지 `/api`(로그인·refresh·프리뷰)는 기존
 *    서버로 그대로 간다.
 * 2. 수집 서버 설정이 없으면 광권한 서버로 **묵시적 대체하지 않는다**(그 접두사 항목이 없다).
 */
import { describe, expect, it } from 'vitest'
import { buildServerProxy, COLLECTION_MISSING_DETAIL, COLLECTION_PREFIX } from './collectionProxy'

describe('vite 서버 프록시 — 수집 전용 경로 분리', () => {
  it('수집 접두사만 별도 서버로 보내고 나머지 /api는 기존 서버로 보낸다', () => {
    const { proxy, collectionTarget } = buildServerProxy({
      backend: 'http://127.0.0.1:38000',
      collection: 'http://127.0.0.1:38003',
    })

    expect(collectionTarget).toBe('http://127.0.0.1:38003')
    expect(proxy[COLLECTION_PREFIX]?.target).toBe('http://127.0.0.1:38003')
    expect(proxy['/api']?.target).toBe('http://127.0.0.1:38000')

    // 순서가 계약이다. 수집 접두사 항목이 먼저 매칭되어야 한다.
    expect(Object.keys(proxy)).toEqual([COLLECTION_PREFIX, '/api'])
    // 긴 작업이 프록시에서 먼저 끊기지 않는다.
    expect(proxy[COLLECTION_PREFIX]?.timeout).toBe(0)
    expect(proxy[COLLECTION_PREFIX]?.proxyTimeout).toBe(0)
  })

  it('수집 서버 설정이 없으면 그 접두사를 기존 서버로 대체하지 않는다', () => {
    const { proxy, collectionTarget } = buildServerProxy({ backend: 'http://127.0.0.1:38000' })

    expect(collectionTarget).toBeNull()
    expect(proxy[COLLECTION_PREFIX]).toBeUndefined()
    expect(proxy['/api']?.target).toBe('http://127.0.0.1:38000')
    // 빈 문자열·공백만 있는 설정도 "없음"이다.
    expect(buildServerProxy({ collection: '   ' }).collectionTarget).toBeNull()
  })

  it('서버 주소 기본값은 기존 로컬 통합 서버다', () => {
    const { proxy } = buildServerProxy({})
    expect(proxy['/api']?.target).toBe('http://127.0.0.1:8000')
  })

  it('사용 불가 사유는 설정 이름을 밝히고, 광권한 대체를 안내하지 않는다', () => {
    expect(COLLECTION_MISSING_DETAIL).toContain('BENCHMARK_COLLECTION_BACKEND_URL')
    expect(COLLECTION_MISSING_DETAIL).toContain('실행할 수 없습니다')
  })
})
