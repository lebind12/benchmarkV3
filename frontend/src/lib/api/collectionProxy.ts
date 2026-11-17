/**
 * 수집 시험 전용 프록시 규칙.
 *
 * 기간 수집 시험 API(`/api/v1/admin/management/preview-test`)만 별도 수집 프로세스로 보낸다.
 * 나머지 `/api`(로그인·refresh·프리뷰 생성·조회)는 기존 서버로 그대로 간다. 브라우저는
 * 같은 오리진(5173)을 유지하므로 정식 access token이 그대로 전달되고, 수집 서버도 같은
 * 서명·ADMIN 검사를 한다.
 *
 * 설정이 없으면 광권한 서버로 조용히 대체하지 않는다. 그 접두사에만 명시적 사용 불가
 * 응답(`COLLECTION_MISSING_DETAIL`)을 돌려주고, 화면은 그 문장을 그대로 표시한다.
 *
 * 이 모듈은 vite 타입에 의존하지 않는다. `vite.config.ts`가 이 값을 서버 설정으로 옮기고,
 * 검사는 순수 함수(`buildServerProxy`)만 본다.
 */

export const COLLECTION_PREFIX = '/api/v1/admin/management/preview-test'

export const COLLECTION_MISSING_DETAIL =
  '수집 시험 서버가 설정되지 않았습니다(BENCHMARK_COLLECTION_BACKEND_URL). 이 환경에서는 후보 조회와 기간 수집을 실행할 수 없습니다.'

export type ProxyEntry = {
  target: string
  changeOrigin: boolean
  /** 한 경기 생성·수집이 오래 걸려도 프록시가 먼저 끊지 않는다. */
  timeout: number
  proxyTimeout: number
}

export type ServerProxyPlan = {
  proxy: Record<string, ProxyEntry>
  /**
   * 수집 접두사가 향할 대상. 없으면 `null`이며 서버는 그 접두사에 503을 돌려준다.
   * `null`을 기존 서버 주소로 채우지 않는다.
   */
  collectionTarget: string | null
}

function clean(value: string | undefined): string | null {
  const trimmed = (value ?? '').trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * vite 서버 프록시 표를 만든다.
 *
 * - 수집 접두사 항목을 `/api`보다 **앞에** 둔다. 앞선 항목이 먼저 매칭된다.
 * - 수집 대상이 없으면 그 항목을 만들지 않는다(`collectionTarget === null`).
 */
export function buildServerProxy(options: {
  backend?: string
  collection?: string
}): ServerProxyPlan {
  const backend = clean(options.backend) ?? 'http://127.0.0.1:8000'
  const collection = clean(options.collection)
  const proxy: Record<string, ProxyEntry> = {}
  if (collection !== null) {
    proxy[COLLECTION_PREFIX] = {
      target: collection,
      changeOrigin: false,
      timeout: 0,
      proxyTimeout: 0,
    }
  }
  proxy['/api'] = {
    target: backend,
    changeOrigin: false,
    timeout: 0,
    proxyTimeout: 0,
  }
  return { proxy, collectionTarget: collection }
}
