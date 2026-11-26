// 일기장: 여행 목록 | 여행기 본문 (참고 디자인: 사진 일기장 앱). 휴대폰은 목록 → 본문 화면으로 넘어간다.
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, fmtLongDate } from '../api.js'
import { useApi, useWide } from '../hooks.js'
import { useTheme } from '../theme.js'
import { AppBar, ErrorBox, Fab, JHero, Loading, MoreMenu, Photo, TripStatusChip } from '../components/ui.jsx'
import { ModeBanner, tripLink } from './A_upload.jsx'
import { StoryDetail } from './D_story.jsx'

const readyStory = (t) => [...(t.stories || [])].reverse().find((s) => s.status === 'ready')

function statusText(t) {
  if ((t.stories || []).some((s) => s.status === 'generating')) return '여행기를 쓰고 있어요.'
  if (t.status === 'analyzing') return '사진에서 다녀온 곳을 찾고 있어요.'
  if (t.status === 'draft') return `사진 ${t.photo_count}장을 올렸어요. 분석을 시작해 주세요.`
  if (t.status === 'review') return `확인이 필요한 곳이 ${t.needs_user + t.pending_photos}곳 있어요. 장소를 확인하면 여행기를 만들 수 있어요.`
  return `방문지 ${t.visit_count}곳을 모두 확정했어요. 여행기를 만들어 보세요.`
}

function nextAction(t) {
  if (t.status === 'ready') return { label: '여행기 만들기', to: `/trips/${t.id}/story/new` }
  if (t.status === 'review') return { label: '장소 확인하기', to: `/trips/${t.id}/visits` }
  if (t.status === 'analyzing') return { label: '분석 진행 보기', to: `/trips/${t.id}/analyzing` }
  return { label: '사진 다시 올리기', to: '/upload' }
}

function matches(t, q) {
  if (!q.trim()) return true
  const s = readyStory(t)
  const hay = [t.title, s?.title, s?.excerpt, ...(s?.places || []), t.start_date].join(' ').toLowerCase()
  return q.trim().toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

export function Journal({ selectedTripId }) {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const wide = useWide()
  const [, theme, setTheme] = useTheme()
  const [q, setQ] = useState('')
  const { data: trips, error, loading, reload } = useApi('/trips')
  const list = (trips || []).filter((t) => matches(t, q))
  const pick = selectedTripId || sp.get('trip')
  const selected = (trips || []).find((t) => t.id === pick) || list[0]
  const bar = <AppBar query={q} onQuery={setQ} theme={theme} onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')} />

  function open(t) {
    if (wide) { nav(`/?trip=${t.id}`, { replace: true }); return }
    const s = readyStory(t)
    nav(s ? `/stories/${s.id}` : tripLink(t))
  }

  if (trips && trips.length === 0) return <>{bar}<Welcome /></>

  return (
    <div className="journal">
      {bar}
      <div className="journal-body">
        <div className="j-pane-list">
          {loading && !trips && <Loading />}
          <ErrorBox error={error} onRetry={reload} />
          <ul className="j-list">
            {list.map((t) => (
              <li key={t.id}><JournalItem t={t} selected={wide && selected?.id === t.id} onOpen={() => open(t)} /></li>
            ))}
          </ul>
          {q && trips && list.length === 0 && <div className="empty small">‘{q}’ 검색 결과가 없어요</div>}
        </div>
        {wide && (
          <div className="j-pane-detail">
            {selected && <TripDetail key={selected.id} trip={selected} onChanged={() => { nav('/', { replace: true }); reload() }} />}
          </div>
        )}
      </div>
      <Fab />
    </div>
  )
}

function JournalItem({ t, selected, onOpen }) {
  const s = readyStory(t)
  return (
    <button className={`j-item${selected ? ' selected' : ''}`} onClick={onOpen} aria-current={selected || undefined}>
      <div className="j-date">{t.start_date ? fmtLongDate(t.start_date) : '촬영 날짜 없음'}</div>
      <div className="j-row">
        <p className={`j-excerpt${s?.excerpt ? '' : ' status'}`}>{s?.excerpt || statusText(t)}</p>
        <Photo id={t.cover_photo_id} className="j-thumb" />
      </div>
      <div className="j-time">
        {t.first_time && <span>{t.first_time}</span>}
        <span>방문지 {t.visit_count}곳, 사진 {t.photo_count}장</span>
        {!s && <TripStatusChip trip={t} />}
      </div>
    </button>
  )
}

/** 오른쪽 본문: 여행기가 있으면 여행기, 없으면 다음에 할 일 */
function TripDetail({ trip, onChanged }) {
  const nav = useNavigate()
  const s = readyStory(trip)
  if (s) return <StoryDetail storyId={s.id} trip={trip} onDeleted={onChanged} />
  const next = nextAction(trip)
  async function del() {
    if (!window.confirm(`'${trip.title}' 여행을 삭제할까요?\n사진 썸네일·방문지·여행기가 모두 지워져요.`)) return
    await api(`/trips/${trip.id}`, { method: 'DELETE' }).catch((e) => window.alert(e.message))
    onChanged()
  }
  return (
    <article>
      <JHero photoId={trip.cover_photo_id}
        date={`${trip.start_date ? fmtLongDate(trip.start_date) : trip.title}${trip.first_time ? ` ${trip.first_time}` : ''}`}
        sub={`사진 ${trip.photo_count}장${trip.visit_count ? `, 방문지 ${trip.visit_count}곳` : ''}`}
        actions={<MoreMenu items={[{ label: '여행 삭제', icon: 'trash', danger: true, onClick: del }]} />} />
      <div className="j-body">
        <h2 className="j-title">{trip.title}</h2>
        <p className="lede">{statusText(trip)}</p>
        <div className="row" style={{ marginTop: 16, flexWrap: 'wrap' }}>
          <button className="btn primary" onClick={() => nav(next.to)}>{next.label}</button>
          {trip.status === 'ready' && <Link className="btn" to={`/trips/${trip.id}/route`}>동선 보기</Link>}
        </div>
      </div>
    </article>
  )
}

/** 여행이 없을 때: 큰 문장 · 그림 · 파란 버튼 두 개 */
function Welcome() {
  const nav = useNavigate()
  return (
    <div className="screen">
      <section className="welcome">
        <h2>부산 여행 사진으로<br />여행기를 남겨 보세요.</h2>
        <p className="lede" style={{ marginTop: 10 }}>촬영 시각과 위치로 다녀온 곳을 찾고, 공식 관광 정보에 출처를 달아 글로 정리해 드려요.</p>
        <div className="art"><TravelArt /></div>
        <div className="actions">
          <button className="btn primary block lg" onClick={() => nav('/upload')}>사진으로 새 여행기 만들기</button>
          <button className="btn primary block lg" onClick={() => nav('/upload?sample=1')}>샘플 사진으로 체험하기</button>
        </div>
        <ModeBanner />
      </section>
    </div>
  )
}

function TravelArt() {
  return (
    <svg viewBox="0 0 320 260" role="img" aria-label="사진 두 장과 지도 핀">
      <path d="M62 64C96 18 196 8 246 48c56 44 50 140-18 172-66 31-160 22-190-34C20 150 32 104 62 64z" fill="var(--blob, #a9c4ee)" />
      <g transform="rotate(-9 128 128)">
        <rect x="64" y="66" width="124" height="112" rx="6" fill="#fff" stroke="#1f2937" strokeWidth="2" />
        <rect x="74" y="76" width="104" height="70" fill="#d6e5f9" />
        <path d="M74 132l30-26 20 15 26-26 28 30v21H74z" fill="#4a7bd0" />
        <circle cx="160" cy="92" r="7" fill="#fff" />
        <path d="M78 158h60M78 166h40" stroke="#9aa4b2" strokeWidth="2" strokeLinecap="round" />
      </g>
      <g transform="rotate(8 206 138)">
        <rect x="150" y="88" width="112" height="102" rx="6" fill="#fff" stroke="#1f2937" strokeWidth="2" />
        <rect x="159" y="97" width="94" height="62" fill="#a9c4ee" />
        <path d="M159 141c10-7 20-7 30 0s20 7 32 0 22-7 32 0v18h-94z" fill="#2f5fb3" />
        <path d="M163 172h52M163 180h34" stroke="#9aa4b2" strokeWidth="2" strokeLinecap="round" />
      </g>
      <path d="M58 218c48-26 100 18 160-12" fill="none" stroke="#1f2937" strokeWidth="2" strokeDasharray="5 7" strokeLinecap="round" />
      <path d="M236 168c-11 0-20 9-20 19 0 14 20 32 20 32s20-18 20-32c0-10-9-19-20-19z" fill="#f26b5e" stroke="#1f2937" strokeWidth="2" />
      <circle cx="236" cy="187" r="6" fill="#fff" stroke="#1f2937" strokeWidth="2" />
      <circle cx="58" cy="218" r="5" fill="#fff" stroke="#1f2937" strokeWidth="2" />
    </svg>
  )
}

/** /stories/:id — 휴대폰은 본문만, 넓은 화면은 일기장에서 그 여행을 고른 상태 */
export function StoryView() {
  const { storyId } = useParams()
  const nav = useNavigate()
  const wide = useWide()
  const { data: s, error, reload } = useApi(`/stories/${storyId}`)
  if (wide) {
    if (error) return <div className="screen"><ErrorBox error={error} onRetry={reload} /></div>
    return s ? <Journal selectedTripId={s.trip_id} /> : <div className="screen"><Loading /></div>
  }
  return <StoryDetail storyId={storyId} onBack={() => (window.history.length > 1 ? nav(-1) : nav('/'))} onDeleted={() => nav('/', { replace: true })} />
}

