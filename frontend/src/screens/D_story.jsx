// D 여행기: D1 문체 선택, D2 여행기, D3 편집·사실 대조, D4 공유 카드 (UC-06~09, FR-09~11, UI-07, NFR-03)
import { Fragment, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDate, pollJob } from '../api.js'
import { useApi } from '../hooks.js'
import { ErrorBox, Icon, Loading, NumBadge, Photo, TopBar, useToast } from '../components/ui.jsx'

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
    <div className="screen no-tabs">
      <TopBar title="여행기 문체" />
      <h2 className="title">어떤 느낌으로 쓸까요?</h2>
      <p className="muted small" style={{ marginTop: 0 }}>확정한 방문지와 공식 관광 데이터만으로 AI가 써요. 사실 문장에는 출처 각주가 붙어요.</p>
      {STYLES.map((s) => (
        <button key={s.key} className={`style-card${style === s.key ? ' selected' : ''}`} onClick={() => setStyle(s.key)} disabled={busy}>
          <b>{s.label}</b>
          <div className="small muted" style={{ marginTop: 4 }}>“{s.sample}”</div>
        </button>
      ))}
      <ErrorBox error={error} onRetry={create} />
      <div className="bottom-cta">
        <button className="btn primary" onClick={create} disabled={busy}>{busy ? '여행기를 쓰는 중…' : '여행기 만들기'}</button>
      </div>
    </div>
  )
}

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
      {s.footnotes.length > 0 && <sup>{s.footnotes.map((n) => <a key={n} href={`#fn-${n}`} aria-label={`출처 ${n}`}>[{n}]</a>)}</sup>}
      {' '}
    </span>
  )
}

function RouteSummary({ days }) {
  return days.map((d) => (
    <div key={d.day} className="route-sum" style={{ marginTop: 10 }}>
      <div className="small" style={{ fontWeight: 700, marginBottom: 6 }}>{d.day}일차 동선 <span className="muted" style={{ fontWeight: 400 }}>· {d.time_range}</span></div>
      <div className="row">
        {d.stops.map((st, i) => (
          <Fragment key={st.order}>
            <span className="row" style={{ gap: 4 }}><NumBadge n={st.order} color={st.color} size={22} /><span className="small">{st.name}</span></span>
            {i < d.stops.length - 1 && <span className="muted">›</span>}
          </Fragment>
        ))}
      </div>
    </div>
  ))
}

// ------------------------------------------------------------------ D2 여행기
export function StoryView() {
  const { storyId } = useParams()
  const nav = useNavigate()
  const { data: s, error, loading, reload } = useApi(`/stories/${storyId}`)
  const { data: trip } = useApi(s ? `/trips/${s.trip_id}` : null, [s?.trip_id])
  if (loading && !s) return <div className="screen"><TopBar title="여행기" /><Loading /></div>
  if (error) return <div className="screen"><TopBar title="여행기" /><ErrorBox error={error} onRetry={reload} /></div>
  const places = s.meta?.places || []
  const dates = Object.fromEntries((s.route_summary || []).map((d) => [d.day, d.date]))
  const removed = s.meta?.removed || []

  return (
    <div className="screen cta-tabs">
      <TopBar title="여행기" onBack={() => nav('/stories')}
        right={<Link className="icon-btn" to={`/stories/${s.id}/share`} aria-label="공유 카드"><Icon name="share" /></Link>} />
      <h2 className="title">{s.title}</h2>
      <div className="small muted">{s.date_range} · 방문지 {s.visit_count}곳 · {s.style_label}</div>
      <div className="hero-photo" style={{ margin: '14px 0 0' }}>
        <Photo id={trip?.cover_photo_id} className="" style={{ borderRadius: 16 }} />
      </div>
      <div className="notice info small" style={{ marginTop: 12 }}><Icon name="spark" size={14} /> {s.meta?.ai_label}</div>

      <article className="story" style={{ marginTop: 6 }}>
        {s.paragraphs.map((p) => (
          <section key={p.id}>
            <div className="day-h">{p.day}일차{dates[p.day] ? ` · ${fmtDate(dates[p.day])}` : ''}</div>
            <p>{p.sentences.map((x) => <Sentence key={x.id} s={x} places={places} tripId={s.trip_id} />)}</p>
          </section>
        ))}
      </article>

      <RouteSummary days={s.route_summary || []} />

      <div className="section-title">출처</div>
      <ol className="footnotes">
        {s.footnotes.map((f) => (
          <li key={f.num} id={`fn-${f.num}`}>[{f.num}] {f.label}{f.updated_at ? ` · 갱신 ${f.updated_at}` : ''}</li>
        ))}
      </ol>
      {removed.length > 0 && (
        <details className="notice warn small" style={{ marginTop: 12 }}>
          <summary>근거를 확인하지 못한 문장 {removed.length}개를 뺐어요</summary>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{removed.map((r, i) => <li key={i}>“{r.text}” — {r.reasons.join(', ')}</li>)}</ul>
        </details>
      )}
      <p className="tiny muted">모델: {s.model} · 프롬프트 {s.prompt_version}</p>

      <div className="bottom-cta with-tabs">
        <button className="btn" onClick={() => nav(`/stories/${s.id}/edit`)}>편집</button>
        <button className="btn primary" onClick={() => nav(`/stories/${s.id}/share`)}>공유 카드 만들기</button>
      </div>
    </div>
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
    <div className="screen no-tabs">
      {toast}
      <TopBar title="편집 · 사실 대조" />
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
    <div className="screen no-tabs">
      <TopBar title="공유 카드" />
      {!url && !error && <div className="skeleton" style={{ aspectRatio: '4 / 5' }} />}
      {url && <img src={url} alt="공유 카드 미리보기" style={{ borderRadius: 16, boxShadow: 'var(--shadow)' }} />}
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
