// B 장소 확인: B1 방문지 목록, B2 장소 확인, B3 위치 없는 사진, B4 확정 완료 (UC-02, UC-03, FR-03~06, UI-04, UI-05)
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, fmtDate } from '../api.js'
import { useApi } from '../hooks.js'
import { ErrorBox, Icon, Loading, NumBadge, Photo, StatusChip, TopBar, useToast } from '../components/ui.jsx'

const typeColor = (v) => v.place?.color || v.ai?.place?.color || '#8A8F98'

function groupByDay(visits) {
  const days = {}
  visits.forEach((v) => { (days[v.day] ||= []).push(v) })
  return Object.entries(days).map(([day, list]) => ({ day: Number(day), date: list[0].date, list }))
}

// ------------------------------------------------------------------ B1 방문지 목록
export function VisitList() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const { data, error, loading, reload } = useApi(`/trips/${tripId}/visits`)
  if (loading && !data) return <div className="screen"><TopBar title="방문지" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="방문지" /><ErrorBox error={error} onRetry={reload} /></div>
  const { visits, untagged, trip } = data
  const asks = visits.filter((v) => v.needs_user)
  const pendingPhotos = untagged.filter((u) => u.assign_state === 'pending')
  const auto = visits.filter((v) => v.status === '자동확정').length

  return (
    <div className="screen no-tabs">
      <TopBar title="방문지 확인" onBack={() => nav('/')} />
      <h2 className="title">방문지 {visits.length}곳을 찾았어요</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        AI가 {auto}곳을 확정했어요. {asks.length ? `${asks.length}곳만 확인해 주세요.` : '확인할 곳이 없어요.'}
      </p>

      {pendingPhotos.length > 0 && (
        <Link to={`/trips/${tripId}/untagged`} className="notice accent row between" style={{ textDecoration: 'none', marginBottom: 6 }}>
          <span>위치 없는 사진 <b>{pendingPhotos.length}장</b>의 방문지를 추천했어요</span><b>확인 ›</b>
        </Link>
      )}

      {groupByDay(visits).map((g) => (
        <div key={g.day}>
          <div className="section-title">{g.day}일차 · {fmtDate(g.date)}</div>
          {g.list.map((v) => (
            <Link key={v.id} to={`/trips/${tripId}/visits/${v.id}`} className={`card visit-card${v.needs_user ? ' attention' : ''}`} style={{ color: 'inherit' }}>
              <div style={{ position: 'relative' }}>
                <Photo id={v.rep_photo_id} />
                <span style={{ position: 'absolute', top: -6, left: -6 }}><NumBadge n={v.order} color={typeColor(v)} size={24} /></span>
              </div>
              <div style={{ minWidth: 0 }}>
                <div className="name" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {v.place?.name || (v.status === '기타장소' ? '기타 장소' : v.ai?.place ? `${v.ai.place.name}?` : '어디였을까요?')}
                </div>
                <div className="small muted">{v.start}–{v.end} · 사진 {v.photo_count}장</div>
                <div className="row" style={{ gap: 6, marginTop: 4 }}>
                  <StatusChip status={v.status} />
                  {v.ai?.confidence != null && <span className="tiny muted">AI 확신도 {Math.round(v.ai.confidence * 100)}%</span>}
                </div>
              </div>
              <span className="muted">›</span>
            </Link>
          ))}
        </div>
      ))}

      <div className="bottom-cta">
        {asks.length > 0 ? (
          <button className="btn primary" onClick={() => nav(`/trips/${tripId}/visits/${asks[0].id}?queue=1`)}>
            장소 확인하기 ({asks.length}곳)
          </button>
        ) : pendingPhotos.length > 0 ? (
          <button className="btn primary" onClick={() => nav(`/trips/${tripId}/untagged`)}>위치 없는 사진 배정하기</button>
        ) : (
          <button className="btn primary" onClick={() => nav(`/trips/${tripId}/done`)}>확정 완료 ({trip.visit_count}곳)</button>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ B2 장소 확인
export function PlaceCheck() {
  const { tripId, visitId } = useParams()
  const [sp] = useSearchParams()
  const queue = sp.get('queue') === '1'
  const nav = useNavigate()
  const [toast, showToast] = useToast()
  const { data, error, loading, reload } = useApi(`/visits/${visitId}/candidates`)
  const { data: all } = useApi(`/trips/${tripId}/visits`, [visitId]) // 방문지를 옮길 때마다 남은 확인 목록 새로 조회
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [showSearch, setShowSearch] = useState(false)

  useEffect(() => {
    if (!data) return
    const v = data.visit
    // 확인필요는 AI 추천을 미리 골라 두고, 선택필요(확신도 0.5 미만)는 사용자가 직접 고르게 한다
    setSelected(v.place?.place_id || (v.status === '확인필요' ? v.ai?.place?.place_id : null) || null)
    setShowSearch(data.candidates.length === 0)
    setResults(null)
    setQuery('')
  }, [data])

  if (loading && !data) return <div className="screen"><TopBar title="장소 확인" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="장소 확인" /><ErrorBox error={error} onRetry={reload} /></div>

  const v = data.visit
  const asks = all?.visits.filter((x) => x.needs_user) || []
  const idx = asks.findIndex((x) => x.id === v.id)
  const title = v.needs_user && asks.length ? `장소 확인 ${idx + 1}/${asks.length}` : '장소 확인'

  async function search(e) {
    e?.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api(`/places/search?q=${encodeURIComponent(query.trim())}&visit_id=${v.id}`)
      setResults(r.results)
    } catch (err) {
      showToast(err.message)
    } finally {
      setSearching(false)
    }
  }

  async function save(other = false) {
    setSaving(true)
    setSaveError(null)
    try {
      const r = await api(`/visits/${v.id}/place`, { method: 'PUT', body: other ? { other: true } : { place_id: selected } })
      const remaining = (all?.visits || []).filter((x) => x.needs_user && x.id !== v.id)
      showToast(other ? '기타 장소로 저장했어요' : '장소를 확정했어요')
      if (queue && remaining.length) nav(`/trips/${tripId}/visits/${remaining[0].id}?queue=1`, { replace: true })
      else if (r.trip.status === 'ready') nav(`/trips/${tripId}/done`, { replace: true })
      else nav(`/trips/${tripId}/visits`, { replace: true })
    } catch (err) {
      setSaveError(err)
    } finally {
      setSaving(false)
    }
  }

  const aiPick = data.candidates.find((c) => c.ai_pick)
  const reasonLines = (v.ai?.reason || '').split(/(?<=[.요])\s+/).filter(Boolean)
  const list = results ?? data.candidates

  return (
    <div className="screen no-tabs">
      {toast}
      <TopBar title={title} />
      <div className="hero-photo">
        <Photo id={v.rep_photo_id} className="" />
        <span className="overlay"><Icon name="clock" size={13} /> {v.start} · 사진 {v.photo_count}장</span>
      </div>
      {v.photo_ids.length > 1 && (
        <div className="strip" style={{ marginTop: 8 }}>
          {v.photo_ids.map((pid) => <Photo key={pid} id={pid} className="thumb" style={{ width: 56, height: 56 }} />)}
        </div>
      )}

      <h2 className="title" style={{ marginTop: 16 }}>이 사진, 어디서 찍었나요?</h2>
      <div className="row between small muted">
        <span>{results ? `‘${query}’ 검색 결과 ${results.length}곳` : data.candidates.length
          ? `반경 ${data.radius_m}m 안 공식 데이터 후보 ${data.candidates.length}곳` : (v.note || '근처에서 공식 데이터 후보를 찾지 못했어요')}</span>
        <StatusChip status={v.status} />
      </div>

      <div style={{ marginTop: 12 }}>
        {list.map((c) => (
          <button key={c.place_id} className={`cand${selected === c.place_id ? ' selected' : ''}`} onClick={() => setSelected(c.place_id)}>
            <span className="radio" />
            <span className="body">
              <span className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                <b>{c.name}</b><span className="chip blue">{c.type}</span>
              </span>
              <span className="small muted" style={{ display: 'block' }}>
                {c.distance_m != null ? `촬영 위치에서 ${c.distance_m}m · ` : ''}{c.source_name}
              </span>
            </span>
            {c.ai_pick && <span className="chip solid"><Icon name="spark" size={12} /> AI 추천</span>}
          </button>
        ))}
        {results && results.length === 0 && <div className="notice">검색 결과가 없어요. ‘기타 장소’로 저장할 수 있어요.</div>}
      </div>

      {!showSearch ? (
        <button className="link-btn" onClick={() => setShowSearch(true)}><Icon name="search" size={16} /> 목록에 없어요 · 직접 검색</button>
      ) : (
        <form onSubmit={search} className="row" style={{ marginTop: 12, gap: 8 }}>
          <input className="input" placeholder="장소 이름 (예: 돼지국밥, 해운대)" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="장소 검색" />
          <button className="btn small-btn" disabled={searching}>{searching ? '…' : '검색'}</button>
        </form>
      )}
      {results && <button className="link-btn" onClick={() => setResults(null)}>추천 후보 다시 보기</button>}

      {v.ai?.reason && (
        <div className="reason" style={{ marginTop: 14 }}>
          <div className="row between"><b>AI 판단 근거</b>
            {v.ai.confidence != null && <span className="small muted">확신도 {Math.round(v.ai.confidence * 100)}%</span>}</div>
          <ul>{reasonLines.map((l) => <li key={l}>{l}</li>)}</ul>
          <div className="tiny muted" style={{ marginTop: 8 }}>
            근거: {aiPick ? `${aiPick.source_name} 장소 정보` : '후보 목록'} · 대표 사진 1장 · 사진 속 인물은 분석하지 않아요
          </div>
        </div>
      )}
      {v.note && !v.ai?.reason && <div className="notice warn" style={{ marginTop: 12 }}>{v.note}</div>}

      <ErrorBox error={saveError} />
      <div className="bottom-cta">
        <button className="btn ghost" style={{ flex: '0 0 auto' }} onClick={() => save(true)} disabled={saving}>기타 장소</button>
        <button className="btn primary" disabled={!selected || saving} onClick={() => save(false)}>
          {saving ? '저장 중…' : '이 장소로 확정'}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ B3 위치 없는 사진
export function Untagged() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const { data, error, loading, reload } = useApi(`/trips/${tripId}/visits`)
  const [choice, setChoice] = useState({})
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  if (loading && !data) return <div className="screen"><TopBar title="위치 없는 사진" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="위치 없는 사진" /><ErrorBox error={error} onRetry={reload} /></div>
  const photos = data.untagged.filter((u) => u.assign_state === 'pending')
  const name = (v) => v.place?.name || v.ai?.place?.name || `방문지 ${v.order}`

  async function assign(p, skip = false) {
    setBusy(p.id)
    setErr(null)
    try {
      const body = skip ? { skip: true } : { visit_id: choice[p.id] || p.suggested_visit_id }
      const r = await api(`/photos/${p.id}/visit`, { method: 'PUT', body })
      if (photos.length === 1) nav(r.trip.status === 'ready' ? `/trips/${tripId}/done` : `/trips/${tripId}/visits`, { replace: true })
      else reload()
    } catch (e) {
      setErr(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="screen no-tabs">
      <TopBar title="위치 없는 사진" />
      <h2 className="title">이 사진들은 어디에 넣을까요?</h2>
      <p className="muted small" style={{ marginTop: 0 }}>촬영 시각으로 앞뒤 방문지를 찾아 추천했어요. 애매하면 AI가 사진을 비교했어요.</p>
      <ErrorBox error={err} />
      {photos.length === 0 && <div className="card empty">배정할 사진이 없어요</div>}
      {photos.map((p) => {
        const sel = choice[p.id] || p.suggested_visit_id || ''
        return (
          <div key={p.id} className="card" style={{ marginTop: 12 }}>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <Photo id={p.id} className="thumb" style={{ width: 84, height: 84, flex: 'none' }} />
              <div style={{ minWidth: 0 }}>
                <div className="small muted">{p.taken_at ? p.taken_at.slice(5, 16).replace('T', ' ') : '촬영 정보 없음'}</div>
                <div className="small" style={{ marginTop: 4 }}>{p.suggest_reason}</div>
              </div>
            </div>
            <select className="input" style={{ marginTop: 10 }} value={sel} onChange={(e) => setChoice({ ...choice, [p.id]: e.target.value })} aria-label="방문지 선택">
              <option value="" disabled>방문지 선택</option>
              {data.visits.map((v) => (
                <option key={v.id} value={v.id}>{v.day}일차 {v.order}. {name(v)} ({v.start}){v.id === p.suggested_visit_id ? ' · 추천' : ''}</option>
              ))}
            </select>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn ghost small-btn" onClick={() => assign(p, true)} disabled={busy === p.id}>배정 안 함</button>
              <button className="btn primary small-btn" style={{ flex: 1 }} onClick={() => assign(p)} disabled={!sel || busy === p.id}>이 방문지에 넣기</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ------------------------------------------------------------------ B4 확정 완료
export function ConfirmDone() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const { data, error, loading, reload } = useApi(`/trips/${tripId}/visits`)
  if (loading && !data) return <div className="screen"><TopBar title="확정 완료" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="확정 완료" /><ErrorBox error={error} onRetry={reload} /></div>
  const { visits, trip } = data
  const counts = visits.reduce((a, v) => ({ ...a, [v.status]: (a[v.status] || 0) + 1 }), {})
  const notReady = trip.status !== 'ready'

  return (
    <div className="screen no-tabs">
      <TopBar title="확정 완료" onBack={() => nav(`/trips/${tripId}/visits`)} />
      <div style={{ textAlign: 'center', padding: '12px 0 6px' }}>
        <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--green)', color: '#fff', display: 'grid', placeItems: 'center', margin: '0 auto' }}>
          <Icon name="check" size={30} stroke={3} />
        </div>
        <h2 className="title">{notReady ? '아직 확인할 곳이 있어요' : `방문지 ${visits.length}곳 확정!`}</h2>
        <div className="small muted">
          {Object.entries(counts).map(([k, n]) => `${k} ${n}`).join(' · ')}
        </div>
      </div>
      {groupByDay(visits).map((g) => (
        <div key={g.day} className="card" style={{ marginTop: 12 }}>
          <b>{g.day}일차 · {fmtDate(g.date)}</b>
          {g.list.map((v) => (
            <Link key={v.id} to={`/trips/${tripId}/visits/${v.id}`} className="row between" style={{ padding: '8px 0', color: 'inherit', textDecoration: 'none', minHeight: 44 }}>
              <span className="row"><NumBadge n={v.order} color={typeColor(v)} size={24} />
                <span>{v.place?.name || (v.status === '기타장소' ? '기타 장소' : '미확정')}<span className="tiny muted"> · {v.start}</span></span></span>
              <StatusChip status={v.status} />
            </Link>
          ))}
        </div>
      ))}
      <p className="tiny muted" style={{ margin: '12px 4px' }}>자동 확정된 곳도 눌러서 바꿀 수 있어요.</p>
      <div className="bottom-cta">
        <button className="btn" onClick={() => nav(`/trips/${tripId}/route`)} disabled={notReady}>동선 보기</button>
        <button className="btn primary" onClick={() => nav(`/trips/${tripId}/story/new`)} disabled={notReady}>여행기 만들기</button>
      </div>
    </div>
  )
}
