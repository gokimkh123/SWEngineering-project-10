// D 여행기: D1 문체 선택, D2 여행기, D3 편집·사실 대조, D4 공유 카드 (UC-06~09, FR-09~11, UI-07, NFR-03)
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDate, fmtLongDate, pollJob } from '../api.js'
import { useApi } from '../hooks.js'
import { ErrorBox, Icon, JHero, Loading, MoreMenu, TopBar, useToast } from '../components/ui.jsx'

const STYLES = [
  { key: 'blog', label: '블로그형', sample: '토요일 아침, 해운대해수욕장에서 여행을 시작했어요.' },
  { key: 'diary', label: '일기형', sample: '토요일 아침, 해운대해수욕장에서 여행을 시작했다.' },
  { key: 'brief', label: '간결형', sample: '토요일 아침, 해운대해수욕장에서 출발.' },
]

// ------------------------------------------------------------------ D1 문체 선택
export function StyleSelect() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const [style, setStyle] = useState('blog')
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const stopRef = useRef(null)

  useEffect(() => () => stopRef.current?.(), []) // 화면을 떠날 때만 조회 중단

  async function create() {
    setError(null)
    try {
      const r = await api(`/trips/${tripId}/stories`, { method: 'POST', body: { style } })
      const stop = pollJob(r.job_id, (j, err) => {
        if (err) { setError(err); return }
        setJob(j)
        if (j.status === 'done') nav(`/stories/${r.story_id}`, { replace: true })
        if (j.status === 'failed') setError(new Error(j.error || '여행기를 만들지 못했어요'))
      }, 1000)
      stopRef.current = stop
      setJob((prev) => prev || { status: 'queued' })
    } catch (e) {
      setError(e)
    }
  }

  const busy = job && job.status !== 'failed' && !error
  return (
    <div className="screen no-tabs narrow">
      <TopBar title="여행기 문체" />
      <h2 className="title">어떤 느낌으로 쓸까요?</h2>
      <p className="lede small">확정한 방문지와 공식 관광 데이터만으로 AI가 써요. 사실 문장에는 출처 번호가 붙어요.</p>
      {STYLES.map((s) => (
        <button key={s.key} className={`style-card${style === s.key ? ' selected' : ''}`} onClick={() => setStyle(s.key)} disabled={busy}>
          <b>{s.label}</b>
          <div className="sample">“{s.sample}”</div>
        </button>
      ))}
      <ErrorBox error={error} onRetry={create} />
      <div className="bottom-cta">
        <button className="btn primary" onClick={create} disabled={busy}>{busy ? '여행기를 쓰는 중…' : '여행기 만들기'}</button>
      </div>
    </div>
  )
}

const openSources = () => { const d = document.getElementById('sources'); if (d) d.open = true }

// 본문 문장 렌더링: 장소 이름 → 장소 상세 링크, 각주 번호 → 하단 출처 (UI-07)
function Sentence({ s, places, tripId }) {
  const names = places.filter((p) => p.name && (s.place_ids.includes(p.place_id) || s.text.includes(p.name)))
    .sort((a, b) => b.name.length - a.name.length)
  const parts = []
  let rest = s.text
  let guard = 0
  while (rest && guard++ < 20) {
    let hit = null
    for (const p of names) {
      const i = rest.indexOf(p.name)
      if (i >= 0 && (!hit || i < hit.i)) hit = { i, p }
    }
    if (!hit) { parts.push(rest); break }
    if (hit.i > 0) parts.push(rest.slice(0, hit.i))
    parts.push(<Link key={parts.length} className="place-link" to={`/trips/${tripId}/places/${encodeURIComponent(hit.p.place_id)}`}>{hit.p.name}</Link>)
    rest = rest.slice(hit.i + hit.p.name.length)
  }
  return (
    <span className={s.warnings?.length ? 'warned' : ''} title={s.warnings?.map((w) => w.message).join('\n') || undefined}>
      {parts}
      {s.footnotes.length > 0 && <sup>{s.footnotes.map((n) => <a key={n} href={`#fn-${n}`} aria-label={`출처 ${n}`} onClick={openSources}>[{n}]</a>)}</sup>}
      {' '}
    </span>
  )
}

// ------------------------------------------------------------------ D2 여행기 (일기장 본문)
// 큰 사진 + 반투명 날짜 띠, 사진 위 아이콘: 동선 · 편집 · 더보기(공유 카드 · 근처 못 가본 곳 · 여행 삭제)
export function StoryDetail({ storyId, trip: tripIn, onBack, onDeleted }) {
  const nav = useNavigate()
  const { data: s, error, loading, reload } = useApi(`/stories/${storyId}`)
  const { data: tripLoaded } = useApi(!tripIn && s ? `/trips/${s.trip_id}` : null, [s?.trip_id])
  const trip = tripIn || tripLoaded
  if (loading && !s) return <div className="j-body"><Loading /></div>
  if (error) return <div className="j-body"><ErrorBox error={error} onRetry={reload} /></div>
  const places = s.meta?.places || []
  const days = s.route_summary || []
  const dates = Object.fromEntries(days.map((d) => [d.day, d.date]))
  const first = days[0]
  const time = first?.time_range?.split(/[–-]/)[0]
  const date = `${first?.date ? fmtLongDate(first.date) : s.date_range}${time ? ` ${time}` : ''}`
  const sub = days.flatMap((d) => d.stops.map((x) => x.name)).join(' → ')
  const removed = s.meta?.removed || []
  const multiDay = days.length > 1

  async function del() {
    if (!window.confirm('이 여행을 삭제할까요?\n사진 썸네일·방문지·여행기가 모두 지워져요.')) return
    try {
      await api(`/trips/${s.trip_id}`, { method: 'DELETE' })
      onDeleted ? onDeleted() : nav('/', { replace: true })
    } catch (e) {
      window.alert(e.message)
    }
  }

  return (
    <article>
      <JHero photoId={trip?.cover_photo_id} date={date} sub={sub} onBack={onBack}
        actions={<>
          <button className="icon-btn" aria-label="동선 보기" onClick={() => nav(`/trips/${s.trip_id}/route`)}><Icon name="map" /></button>
          <button className="icon-btn" aria-label="편집" onClick={() => nav(`/stories/${s.id}/edit`)}><Icon name="pen" /></button>
          <MoreMenu items={[
            { label: '공유 카드 만들기', icon: 'share', onClick: () => nav(`/stories/${s.id}/share`) },
            { label: '근처 못 가본 곳', icon: 'search', onClick: () => nav(`/trips/${s.trip_id}/nearby`) },
            { label: '여행 삭제', icon: 'trash', danger: true, onClick: del },
          ]} />
        </>} />
      <div className="j-body">
        <h2 className="j-title">{s.title}</h2>
        <div className="j-text">
          {s.paragraphs.map((p) => (
            <section key={p.id}>
              {multiDay && <div className="day-h">{p.day}일차{dates[p.day] ? `, ${fmtDate(dates[p.day])}` : ''}</div>}
              <p>{p.sentences.map((x) => <Sentence key={x.id} s={x} places={places} tripId={s.trip_id} />)}</p>
            </section>
          ))}
        </div>
        <p className="j-ai">{s.meta?.ai_label} {s.style_label}, 모델 {s.model}.</p>
        <details className="j-sources" id="sources">
          <summary>출처 {s.footnotes.length}개</summary>
          <ol className="footnotes">
            {s.footnotes.map((f) => (
              <li key={f.num} id={`fn-${f.num}`}>[{f.num}] {f.label}{f.updated_at ? `, 갱신 ${f.updated_at}` : ''}</li>
            ))}
          </ol>
        </details>
        {removed.length > 0 && (
          <details className="j-sources">
            <summary>근거를 확인하지 못해 뺀 문장 {removed.length}개</summary>
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{removed.map((r, i) => <li key={i}>“{r.text}”: {r.reasons.join(', ')}</li>)}</ul>
          </details>
        )}
      </div>
    </article>
  )
}

// ------------------------------------------------------------------ D3 편집 · 사실 대조
export function StoryEdit() {
  const { storyId } = useParams()
  const nav = useNavigate()
  const [toast, showToast] = useToast()
  const { data: loaded, error, loading, reload } = useApi(`/stories/${storyId}`)
  const [s, setS] = useState(null)
  const [draft, setDraft] = useState({})
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(null)
  const [saveErr, setSaveErr] = useState(null)

  useEffect(() => { if (loaded) { setS(loaded); setTitle(loaded.title); setDraft({}) } }, [loaded])
  if (loading && !s) return <div className="screen"><TopBar title="편집" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="편집" /><ErrorBox error={error} onRetry={reload} /></div>
  if (!s) return null

  const changed = Object.entries(draft).filter(([id, text]) => {
    const orig = s.paragraphs.flatMap((p) => p.sentences).find((x) => x.id === id)
    return orig && orig.text !== text
  })

  async function save() {
    setBusy('save')
    setSaveErr(null)
    try {
      const r = await api(`/stories/${s.id}`, { method: 'PATCH', body: { title, edits: changed.map(([sentence_id, text]) => ({ sentence_id, text })) } })
      setS(r)
      setDraft({})
      const warns = r.paragraphs.flatMap((p) => p.sentences).filter((x) => x.warnings?.length).length
      showToast(warns ? `저장했어요 · 공식 데이터와 다른 문장 ${warns}개` : '저장했어요')
    } catch (e) {
      setSaveErr(e)
    } finally {
      setBusy(null)
    }
  }

  async function rewrite(pid) {
    setBusy(pid)
    setSaveErr(null)
    try {
      const r = await api(`/stories/${s.id}/paragraphs/${pid}/rewrite`, { method: 'POST' })
      setS(r)
      setDraft({})
      showToast('문단을 다시 썼어요')
    } catch (e) {
      setSaveErr(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="screen no-tabs narrow">
      {toast}
      <TopBar title="편집과 사실 대조" />
      <label className="small muted" htmlFor="title">제목</label>
      <input id="title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
      <p className="tiny muted">고친 문장은 장소명·시간·요금·거리를 공식 데이터와 대조해 다르면 경고해요.</p>
      <ErrorBox error={saveErr} />
      {s.paragraphs.map((p) => (
        <div key={p.id} className="card" style={{ marginTop: 12 }}>
          <div className="row between">
            <b>{p.day}일차</b>
            <button className="btn ghost small-btn" onClick={() => rewrite(p.id)} disabled={!!busy}>
              <Icon name="refresh" size={16} /> {busy === p.id ? '쓰는 중…' : '문단 다시 쓰기'}
            </button>
          </div>
          {p.sentences.map((x) => {
            const val = draft[x.id] ?? x.text
            return (
              <div key={x.id} style={{ marginTop: 10 }}>
                <textarea className={`edit-sent${x.warnings?.length ? ' warned' : ''}`} value={val} rows={2}
                  onChange={(e) => setDraft({ ...draft, [x.id]: e.target.value })} aria-label="문장 편집" />
                <div className="row tiny muted" style={{ gap: 6, flexWrap: 'wrap' }}>
                  {x.is_fact && <span className="chip blue">사실 문장 {x.footnotes.map((n) => `[${n}]`).join('')}</span>}
                  {x.edited && <span className="chip">직접 고침</span>}
                </div>
                {x.warnings?.map((w) => <div key={w.code} className="notice warn small" style={{ marginTop: 6 }}>⚠ {w.message}</div>)}
              </div>
            )
          })}
        </div>
      ))}
      <div className="bottom-cta">
        <button className="btn" onClick={() => nav(`/stories/${s.id}`)}>완료</button>
        <button className="btn primary" onClick={save} disabled={busy === 'save' || (!changed.length && title === s.title)}>
          {busy === 'save' ? '대조 중…' : `저장${changed.length ? ` (${changed.length})` : ''}`}
        </button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ D4 공유 카드
export function ShareCard() {
  const { storyId } = useParams()
  const [url, setUrl] = useState(null)
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)

  async function make() {
    setError(null)
    setUrl(null)
    try {
      const res = await api(`/stories/${storyId}/share-card`, { method: 'POST', raw: true })
      const blob = await res.blob()
      setFile(new File([blob], `chalkak-busan-${storyId}.png`, { type: 'image/png' }))
      setUrl(URL.createObjectURL(blob))
    } catch (e) {
      setError(e)
    }
  }
  useEffect(() => { make() }, [storyId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => url && URL.revokeObjectURL(url), [url])

  const canShare = file && navigator.canShare?.({ files: [file] })
  return (
    <div className="screen no-tabs narrow">
      <TopBar title="공유 카드" />
      {!url && !error && <div className="skeleton" style={{ aspectRatio: '4 / 5' }} />}
      {url && <img src={url} alt="공유 카드 미리보기" style={{ borderRadius: 'var(--r-lg)', border: '1px solid var(--line)', maxWidth: 480, margin: '0 auto', width: '100%' }} />}
      <ErrorBox error={error} onRetry={make} />
      <div className="notice small" style={{ marginTop: 12 }}>
        좌표·정확한 위치 정보는 넣지 않았어요. 사진은 위치 정보를 지운 썸네일이에요.
      </div>
      <div className="bottom-cta">
        {url && <a className="btn" href={url} download={file?.name}><Icon name="download" size={18} /> 이미지 저장</a>}
        <button className="btn primary" disabled={!canShare}
          onClick={() => navigator.share({ files: [file], title: '찰칵부산 여행기' }).catch(() => {})}>
          <Icon name="share" size={18} /> {canShare ? '공유하기' : '공유는 휴대폰에서'}
        </button>
      </div>
    </div>
  )
}
