import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { thumbUrl } from '../api.js'

const I = {
  back: <path d="M15 5l-7 7 7 7" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  home: <path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" />,
  map: <path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" />,
  plus: <path d="M12 5v14M5 12h14" />,
  pen: <path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4" />,
  user: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0" />,
  share: <path d="M18 8a3 3 0 1 0-3-3M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.6 13.5l6.8 4M15.4 6.5l-6.8 4" />,
  search: <path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4" />,
  bell: <path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2zM10 20a2 2 0 0 0 4 0" />,
  check: <path d="M5 12l5 5 9-10" />,
  spark: <path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  clock: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2" />,
  walk: <path d="M13 4a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM10 22l2-7 3 3v6M8 12l2-5 4 2 3 3M7 9l3-2" />,
  bus: <path d="M5 16V6a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v10M5 16h14v3H5zM7 19v2M17 19v2M5 11h14" />,
  info: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5v.5" />,
  refresh: <path d="M20 11a8 8 0 0 0-14-5l-2 2M4 13a8 8 0 0 0 14 5l2-2M4 4v4h4M20 20v-4h-4" />,
  download: <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />,
  ext: <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />,
}

export function Icon({ name, size = 22, stroke = 2 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {I[name]}
    </svg>
  )
}

export function TopBar({ title, back = true, close = false, right = null, onBack }) {
  const nav = useNavigate()
  const goBack = onBack || (() => (window.history.length > 1 ? nav(-1) : nav('/')))
  return (
    <header className="topbar">
      {back || close ? (
        <button className="icon-btn" onClick={goBack} aria-label={close ? '닫기' : '뒤로'}>
          <Icon name={close ? 'close' : 'back'} />
        </button>
      ) : <span />}
      <h1>{title}</h1>
      <div>{right}</div>
    </header>
  )
}

export function Tabs() {
  const cls = ({ isActive }) => `tab${isActive ? ' active' : ''}`
  return (
    <nav className="tabs" aria-label="하단 탭">
      <NavLink to="/" end className={cls}><Icon name="home" />홈</NavLink>
      <NavLink to="/trips" className={cls}><Icon name="map" />내 여행</NavLink>
      <NavLink to="/upload" className="tab" aria-label="새 여행기 업로드">
        <span className="tab-fab"><Icon name="plus" stroke={2.4} /></span>
      </NavLink>
      <NavLink to="/stories" className={cls}><Icon name="pen" />여행기</NavLink>
      <NavLink to="/my" className={cls}><Icon name="user" />MY</NavLink>
    </nav>
  )
}

const STATUS_CHIP = {
  분석중: 'chip',
  자동확정: 'chip green',
  확정: 'chip green',
  확인필요: 'chip orange',
  선택필요: 'chip red',
  기타장소: 'chip',
}
export function StatusChip({ status }) {
  return <span className={STATUS_CHIP[status] || 'chip'}>{status}</span>
}

export function TripStatusChip({ trip }) {
  if (trip.status === 'analyzing') return <span className="chip orange">분석 중</span>
  if (trip.status === 'review') return <span className="chip orange">확인 {trip.needs_user + trip.pending_photos}건</span>
  if (trip.status === 'ready') return trip.stories?.some((s) => s.status === 'ready')
    ? <span className="chip green">여행기 완성</span> : <span className="chip blue">장소 확정</span>
  return <span className="chip">사진 준비</span>
}

export function NumBadge({ n, color = '#F05C2C', size = 26 }) {
  return <span className="badge-num" style={{ background: color, width: size, height: size }}>{n}</span>
}

export function Photo({ id, alt = '', className = 'thumb', style }) {
  const [failed, setFailed] = useState(false)
  if (!id || failed) return <div className={`${className} ph`} style={style} aria-hidden="true" />
  return <img className={className} style={style} src={thumbUrl(id)} alt={alt} loading="lazy" onError={() => setFailed(true)} />
}

export function useToast() {
  const [msg, setMsg] = useState(null)
  useEffect(() => {
    if (!msg) return undefined
    const t = setTimeout(() => setMsg(null), 2600)
    return () => clearTimeout(t)
  }, [msg])
  const node = msg ? <div className="toast" role="status">{msg}</div> : null
  return [node, setMsg]
}

export function Loading({ lines = 3 }) {
  return (
    <div className="stack" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton" style={{ height: 72 }} />)}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="notice error" role="alert">
      {error.message || String(error)}
      {onRetry && <div><button className="link-btn" onClick={onRetry}><Icon name="refresh" size={16} />다시 시도</button></div>}
    </div>
  )
}
