// A 업로드·분석: A1 홈, A2 사진 선택, A3 분석 중 (UC-01, FR-01, FR-02, UI-01~03, NFR-04)
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, fmtDate, pollJob } from '../api.js'
import { useApi, useMeta } from '../hooks.js'
import MapView from '../components/MapView.jsx'
import { shrinkPhoto } from '../imagePrep.js'
import { useTheme } from '../theme.js'
import { ErrorBox, Icon, Loading, NumBadge, Photo, TopBar, TripStatusChip } from '../components/ui.jsx'

const MAX_PHOTOS = 30
const MAX_MB = 20
const OK_TYPES = ['image/jpeg', 'image/png', 'image/heic', 'image/heif']
// 한 요청에 보내는 양 (공개 서버 앞단 Cloudflare 무료 한도 100MB · 웹 서버 한도 45MB 안쪽으로 나눠 보냄)
const BATCH_BYTES = 40 * 1024 * 1024
const BATCH_FILES = 6

function batches(list) {
  const out = []
  let cur = []
  let size = 0
  for (const it of list) {
    if (cur.length && (cur.length >= BATCH_FILES || size + it.file.size > BATCH_BYTES)) {
      out.push(cur)
      cur = []
      size = 0
    }
    cur.push(it)
    size += it.file.size
  }
  if (cur.length) out.push(cur)
  return out
}

export function tripLink(t) {
  if (t.status === 'analyzing' || t.status === 'draft') return `/trips/${t.id}/analyzing`
  if (t.status === 'review') return `/trips/${t.id}/visits`
  const story = t.stories?.find((s) => s.status === 'ready')
  return story ? `/stories/${story.id}` : `/trips/${t.id}/done`
}

export function ModeBanner() {
  const { data } = useMeta()
  if (!data) return null
  const sample = Object.values(data.place_data).some((m) => m === 'sample')
  const fakeAi = data.ai.vlm_provider === 'fake' || data.ai.llm_provider === 'fake'
  if (!sample && !fakeAi) return null
  return (
    <div className="mode-banner">
      {sample ? '장소 후보는 샘플 관광 데이터에서 찾아요. ' : ''}
      {fakeAi ? 'AI는 모의 응답이에요. ' : `사진 판별과 글쓰기는 이 서버의 ${data.ai.vlm_model}가 해요. `}
      <Link to="/my" style={{ fontWeight: 700, color: 'var(--sea)' }}>자세히</Link>
    </div>
  )
}

// ------------------------------------------------------------------ A2 사진 선택
export function Upload() {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const input = useRef(null)
  const [items, setItems] = useState([]) // {file, url, problem}
  const [notes, setNotes] = useState([])
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const { data: meta } = useMeta()

  const itemsRef = useRef(items)
  itemsRef.current = items
  // 미리보기 URL은 화면을 떠날 때 해제 (사진을 더 고를 때는 기존 미리보기를 유지)
  useEffect(() => () => itemsRef.current.forEach((i) => i.url && URL.revokeObjectURL(i.url)), [])
  const clearItems = () => { items.forEach((i) => i.url && URL.revokeObjectURL(i.url)); setItems([]) }

  function addFiles(list) {
    const files = Array.from(list)
    const msgs = []
    if (items.length + files.length > MAX_PHOTOS) {
      setNotes([`사진은 최대 ${MAX_PHOTOS}장까지 올릴 수 있어요. 지금 ${items.length}장 + ${files.length}장을 골랐어요.`])
      return
    }
    const next = []
    for (const f of files) {
      const heic = /\.(heic|heif)$/i.test(f.name)
      if (!OK_TYPES.includes(f.type) && !heic) { msgs.push(`${f.name}: 지원하지 않는 형식이라 뺐어요`); continue }
      if (f.size > MAX_MB * 1024 * 1024) { msgs.push(`${f.name}: ${MAX_MB}MB를 넘어 뺐어요`); continue }
      next.push({ file: f, url: heic ? null : URL.createObjectURL(f) })
    }
    setItems((prev) => [...prev, ...next])
    setNotes(msgs)
  }

  async function loadDemo() {
    setBusy('샘플 사진을 불러오는 중…')
    setError(null)
    try {
      const { photos } = await api('/demo/photos')
      if (!photos.length) throw new Error('샘플 사진이 없어요. 서버에서 scripts/make_demo_photos.py를 실행해 주세요.')
      const files = await Promise.all(photos.map(async (name) => {
        const blob = await (await fetch(`/api/v1/demo/photos/${name}`)).blob()
        return new File([blob], name, { type: 'image/jpeg' })
      }))
      clearItems()
      addFiles(files)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  // 처음 화면의 '샘플 사진으로 체험하기' → /upload?sample=1 로 오면 샘플 사진을 바로 담는다
  useEffect(() => { if (sp.get('sample') === '1') loadDemo() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setError(null)
    try {
      setBusy('여행을 만드는 중…')
      const trip = await api('/trips', { method: 'POST', body: { title: '부산 여행' } })
      // 큰 사진은 브라우저에서 줄여 보낸다(촬영 시각·위치는 그대로) → 올리는 양과 시간을 크게 줄임
      const ready = []
      for (const [n, it] of items.entries()) {
        setBusy(`사진 준비하는 중… ${n + 1} / ${items.length}`)
        ready.push({ ...it, file: await shrinkPhoto(it.file) })
      }
      const up = { accepted: [], rejected: [] }
      let sent = 0
      for (const group of batches(ready)) {
        setBusy(`사진 올리는 중… ${sent} / ${items.length}`)
        const form = new FormData()
        group.forEach((i) => form.append('files', i.file, i.file.name))
        const r = await api(`/trips/${trip.id}/photos`, { method: 'POST', form })
        up.accepted.push(...r.accepted)
        up.rejected.push(...r.rejected)
        sent += group.length
      }
      if (!up.accepted.length) throw new Error('올릴 수 있는 사진이 없어요')
      if (up.rejected.length) sessionStorage.setItem(`rejected:${trip.id}`, JSON.stringify(up.rejected))
      setBusy('분석을 시작하는 중…')
      await api(`/trips/${trip.id}/analysis`, { method: 'POST', body: { consent } })
      nav(`/trips/${trip.id}/analyzing`, { replace: true })
    } catch (e) {
      setError(e)
      setBusy(null)
    }
  }

  return (
    <div className="screen no-tabs">
      <TopBar title="새 여행기" close />
      <div className="split">
        <div>
          <h2 className="title">부산에서 찍은 사진을 골라 주세요</h2>
          <p className="lede small">한 번에 {MAX_PHOTOS}장까지, JPEG·HEIC·PNG, 장당 {MAX_MB}MB 이하. 메신저로 받은 사진은 위치가 지워져 있을 수 있으니 휴대폰 앨범의 원본을 올려 주세요.</p>

          <input ref={input} type="file" multiple accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif" hidden
            onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          <div className="row" style={{ gap: 8, marginTop: 14 }}>
            <button className="btn primary" style={{ flex: 1 }} onClick={() => input.current.click()} disabled={!!busy}>
              <Icon name="plus" /> 갤러리에서 선택
            </button>
            <button className="btn" onClick={loadDemo} disabled={!!busy}>샘플 사진으로 체험</button>
          </div>

          {notes.map((n) => <div key={n} className="notice warn" style={{ marginTop: 8 }}>{n}</div>)}

          <div className="section-title">
            고른 사진 <span className="small muted">{items.length} / {MAX_PHOTOS}</span>
          </div>
          {items.length === 0 ? (
            <div className="empty small" style={{ border: '1px dashed var(--line)', borderRadius: 'var(--r-lg)' }}>아직 고른 사진이 없어요</div>
          ) : (
            <div className="photo-grid">
              {items.map((it, i) => (
                <div className="cell" key={i}>
                  {it.url ? <img className="thumb" src={it.url} alt="" /> : <div className="thumb" style={{ display: 'grid', placeItems: 'center', fontSize: 11 }}>HEIC</div>}
                </div>
              ))}
            </div>
          )}
          {items.length > 0 && (
            <button className="link-btn" onClick={() => { clearItems(); setNotes([]) }}>선택 비우기</button>
          )}
        </div>

        <div className="aside">
          <div className="card" style={{ marginTop: 16 }}>
            <label className="check">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span><b>사진 AI 분석에 동의해요</b> (필수)</span>
            </label>
            <ul className="small muted" style={{ margin: '6px 0 0', paddingLeft: 32 }}>
              <li>사진은 찰칵부산 서버 안의 AI(VLM)로만 분석하고 외부 AI 서비스로 보내지 않아요.</li>
              <li>원본 사진과 사진별 위치는 분석이 끝나면 지워요. 위치 정보를 없앤 작은 썸네일만 남아요.</li>
              <li>사진 속 사람은 분석하지 않아요. 여행을 삭제하면 관련 데이터가 모두 지워져요.</li>
              {meta?.retention_days > 0 && <li>공개 시연 서버라서 만든 지 {meta.retention_days}일이 지난 여행은 자동으로 지워요.</li>}
            </ul>
            {meta && <div className="tiny muted" style={{ marginTop: 8, paddingLeft: 32 }}>지금 AI: {meta.ai.vlm_model}</div>}
            <button className="btn primary block desktop-only" style={{ marginTop: 16 }} disabled={!items.length || !consent || !!busy} onClick={start}>
              {busy || (consent ? `사진 ${items.length}장 분석 시작` : '동의 후 분석할 수 있어요')}
            </button>
          </div>
          <ErrorBox error={error} />
        </div>
      </div>

      <div className="bottom-cta mobile-only">
        <button className="btn primary" disabled={!items.length || !consent || !!busy} onClick={start}>
          {busy || (consent ? `사진 ${items.length}장 분석 시작` : '동의 후 분석할 수 있어요')}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ A3 분석 중
export function Analyzing() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const [notify, setNotify] = useState(false)
  const rejected = useMemo(() => {
    try { return JSON.parse(sessionStorage.getItem(`rejected:${tripId}`) || '[]') } catch { return [] }
  }, [tripId])

  useEffect(() => {
    let stop = () => {}
    api(`/trips/${tripId}`).then((trip) => {
      const j = trip.jobs?.analysis
      if (!j) { setError(new Error('분석 작업이 없어요. 사진을 다시 올려 주세요.')); return }
      if (j.status === 'done' && trip.status !== 'analyzing') { nav(`/trips/${tripId}/visits`, { replace: true }); return }
      stop = pollJob(j.id, (next, err) => {
        if (err) { setError(err); return }
        setJob(next)
        if (next.status === 'done') {
          if (document.hidden && notify && 'Notification' in window && Notification.permission === 'granted') {
            new Notification('찰칵부산', { body: '사진 분석이 끝났어요. 방문지를 확인해 보세요.' })
          }
          setTimeout(() => nav(`/trips/${tripId}/visits`, { replace: true }), 900)
        }
      })
    }).catch(setError)
    return () => stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId])

  async function askNotify() {
    if (!('Notification' in window)) { setNotify(true); return }
    const p = await Notification.requestPermission()
    setNotify(p === 'granted')
  }

  const d = job?.detail || {}
  const pct = Math.round((job?.progress || 0) * 100)
  const stageText = {
    exif: d.exif ? `${d.exif.total}장 · 위치 있음 ${d.exif.with_gps}장 · 없음 ${d.exif.without_gps}장` : '촬영 시각·위치를 읽어요',
    cluster: d.cluster ? `시간·거리 기준 ${d.cluster.visits}곳${d.cluster.time_only ? ' (위치 없음 → 시각으로 묶음)' : ''}` : '사진을 방문지로 묶어요',
    match: d.match ? `공식 데이터 후보와 비교 ${d.match.done}/${d.match.total}` : '공식 관광 데이터에서 후보를 찾아요',
    finalize: d.result ? '완료' : '위치 없는 사진 추천 · 정리',
  }
  const preview = (d.preview || []).filter((p) => p.lat != null)
  const dayColors = ['#2196F3', '#E5534B', '#2E7D32', '#B26A00']

  return (
    <div className="screen no-tabs">
      <TopBar title="사진 분석" close onBack={() => nav('/')} />
      <div className="split">
        <div>
          <h2 className="title">
            {job?.status === 'done' ? '방문지를 찾았어요' : job?.status === 'failed' ? '분석하지 못했어요' : '다녀온 곳을 찾고 있어요'}
          </h2>
          <div className="progress" style={{ margin: '14px 0 6px' }}><i style={{ width: `${pct}%` }} /></div>
          <div className="small muted">{pct}%{job?.eta_seconds ? `, 약 ${job.eta_seconds}초 남음` : ''}</div>

          <div className="card" style={{ marginTop: 16 }}>
            {(job?.stages || [{ key: 'exif', label: '촬영 정보 읽기', state: 'running' }, { key: 'cluster', label: '방문지 묶기', state: 'pending' },
              { key: 'match', label: '장소 찾기', state: 'pending' }, { key: 'finalize', label: '동선·여행기 준비', state: 'pending' }]).map((s) => (
              <div key={s.key} className={`stage ${s.state}`}>
                <span className="dot">{s.state === 'done' && <Icon name="check" size={14} stroke={3} />}</span>
                <div>
                  <div style={{ fontWeight: 700 }}>{s.label}</div>
                  <div className="small muted">{stageText[s.key]}</div>
                </div>
              </div>
            ))}
          </div>

          {rejected.length > 0 && (
            <div className="notice warn" style={{ marginTop: 12 }}>
              제외한 사진 {rejected.length}장: {rejected.map((r) => `${r.filename} (${r.reason})`).join(', ')}
            </div>
          )}
          <ErrorBox error={error || (job?.status === 'failed' && new Error(job.error))} onRetry={() => window.location.reload()} />
          <p className="tiny muted" style={{ marginTop: 14 }}>화면을 떠나도 분석은 서버에서 계속돼요. ‘내 여행’에서 다시 열 수 있어요.</p>
        </div>

        <div className="aside">
          {preview.length > 0 ? (
            <>
              <div className="section-title" style={{ marginTop: 16 }}>묶인 방문지
                <span className="small muted">{(d.cluster?.per_day || []).map((n, i) => `${i + 1}일차 ${n}곳`).join(', ')}</span>
              </div>
              <MapView pins={preview.map((p) => ({ id: p.order, lat: p.lat, lng: p.lng, order: p.order, color: dayColors[(p.day - 1) % 4], ghost: true }))} />
            </>
          ) : <div className="skeleton desktop-only" style={{ height: 460, marginTop: 16 }} />}
        </div>
      </div>

      <div className="bottom-cta">
        <button className="btn" onClick={askNotify} disabled={notify}>
          <Icon name="bell" size={18} /> {notify ? '끝나면 알려 드릴게요' : '끝나면 알림 받기'}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ MY
export function MyPage() {
  const nav = useNavigate()
  const [mode, , setMode] = useTheme()
  const { data: meta } = useMeta()
  const [msg, setMsg] = useState(null)
  async function wipe() {
    if (!window.confirm('이 기기의 여행을 모두 삭제할까요? 되돌릴 수 없어요.')) return
    const trips = await api('/trips')
    for (const t of trips) await api(`/trips/${t.id}`, { method: 'DELETE' }).catch(() => {})
    setMsg(`여행 ${trips.length}개와 관련 데이터를 삭제했어요`)
  }
  return (
    <div className="screen narrow">
      <TopBar title="MY" onBack={() => nav('/')} />
      {msg && <div className="notice info">{msg}</div>}
      <div className="section-title">화면 밝기</div>
      <div className="segmented" role="radiogroup" aria-label="화면 밝기">
        {[['system', '기기 설정'], ['light', '밝게'], ['dark', '어둡게']].map(([k, label]) => (
          <button key={k} role="radio" aria-checked={mode === k} className={mode === k ? 'on' : ''} onClick={() => setMode(k)}>{label}</button>
        ))}
      </div>
      <div className="section-title">데이터 출처·이용조건</div>
      <div className="card small">
        {meta?.sources.map((s) => (
          <div key={s.key} style={{ padding: '6px 0' }}>
            <b>{s.name}</b> <span className={`chip ${meta.place_data[s.key] === 'real' ? 'green' : 'warn'}`} style={{ marginLeft: 6 }}>{meta.place_data[s.key] === 'real' ? '실제 API' : '샘플 데이터'}</span>
            <div className="muted tiny">{s.license}</div>
          </div>
        ))}
        <div className="muted tiny" style={{ marginTop: 6 }}>지도: {import.meta.env.VITE_KAKAO_JS_KEY ? '카카오맵' : 'OpenStreetMap (카카오맵 키가 없을 때 대체)'}</div>
        <p className="tiny muted">샘플 데이터는 키 없이 시연하기 위한 팀 작성 소개문·대략 좌표이며, 운영시간 등은 실제와 다를 수 있어요.</p>
      </div>
      <div className="section-title">AI 사용 범위</div>
      <div className="card small">
        <div>장소 판별(VLM): <b>{meta?.ai.vlm_model}</b></div>
        <div>여행기 작성(LLM): <b>{meta?.ai.llm_model}</b></div>
        <div className="muted tiny" style={{ marginTop: 6 }}>
          AI는 후보 중 장소 고르기와 확정된 사실로 문장 쓰기에만 써요. EXIF·방문지 묶기·후보 검색·확신도 판단·각주·사실 대조는 코드로 처리해요.
          확신도 {meta?.thresholds.auto} 이상 자동 확정, {meta?.thresholds.check} 이상 확인 요청.
        </div>
      </div>
      <div className="section-title">개인정보</div>
      <div className="card small">
        <div>원본 사진·사진 위치는 분석 후 삭제, 위치 정보 없는 썸네일만 보관해요. 사진은 외부 AI로 보내지 않아요.</div>
        <button className="btn ghost block small-btn" style={{ marginTop: 12, color: 'var(--flare)' }} onClick={wipe}>
          <Icon name="trash" size={18} /> 이 기기의 여행 모두 삭제
        </button>
      </div>
      <p className="tiny muted" style={{ margin: '16px 4px' }}>
        찰칵부산 프로토타입 · 2026-2 소프트웨어공학 Team 10 · AI 활용: 코드 작성에 Claude Code(Anthropic) 활용
      </p>
    </div>
  )
}
