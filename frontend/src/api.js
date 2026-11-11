// CP-01 → IF-02~04 REST 호출. 익명 기기 토큰을 헤더로 보낸다 (AD-07).
const TOKEN_KEY = 'chalkak.deviceToken'
let memoryToken = null

function randomToken() {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes) // http(사설 IP)에서도 동작 — randomUUID는 보안 컨텍스트에서만 됨
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function deviceToken() {
  if (memoryToken) return memoryToken
  try {
    let t = localStorage.getItem(TOKEN_KEY)
    if (!t) {
      t = randomToken()
      localStorage.setItem(TOKEN_KEY, t)
    }
    memoryToken = t
  } catch {
    memoryToken = randomToken() // 저장소를 못 쓰는 환경(사생활 보호 모드 등)
  }
  return memoryToken
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body, form, raw } = {}) {
  const headers = { 'X-Device-Token': deviceToken() }
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, '서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.')
  }
  if (!res.ok) {
    let msg = `요청을 처리하지 못했어요 (${res.status})`
    try {
      const j = await res.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : msg
    } catch {
      /* 본문 없음 */
    }
    throw new ApiError(res.status, msg)
  }
  if (raw) return res
  if (res.status === 204) return null
  return res.json()
}

export const thumbUrl = (photoId) => (photoId ? `/api/v1/photos/${photoId}/thumb?t=${deviceToken()}` : null)

export function pollJob(jobId, onUpdate, intervalMs = 2000) {
  // 진행 상태 주기 조회 (AD-06, 2초). 반환값을 호출하면 중단.
  let stopped = false
  let timer
  const tick = async () => {
    if (stopped) return
    try {
      const job = await api(`/jobs/${jobId}`)
      onUpdate(job)
      if (job.status === 'done' || job.status === 'failed') return
    } catch (e) {
      onUpdate(null, e)
    }
    timer = setTimeout(tick, intervalMs)
  }
  tick()
  return () => {
    stopped = true
    clearTimeout(timer)
  }
}

export const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']
export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return `${d.getMonth() + 1}.${d.getDate()} (${WEEKDAYS[d.getDay()]})`
}
