// C 동선: C1 동선 지도, C2 타임라인, C3 장소 상세, C4 근처 못 가본 곳 (UC-04, UC-05, FR-07, FR-08, FR-12, UI-06)
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { fmtDate } from '../api.js'
import { useApi } from '../hooks.js'
import MapView from '../components/MapView.jsx'
import { ErrorBox, Icon, Loading, NumBadge, Photo, TopBar } from '../components/ui.jsx'

function pathsByDay(pins) {
  const days = {}
  pins.forEach((p) => { if (p.lat != null) (days[p.day] ||= []).push(p) })
  return Object.values(days)
}

// ------------------------------------------------------------------ C1·C2
export function RouteMap() {
  const { tripId } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const all = sp.get('day') === 'all'
  const day = sp.get('day') && !all ? Number(sp.get('day')) : 1
  const view = sp.get('view') || 'map'
  const { data, error, loading, reload } = useApi(`/trips/${tripId}/route${all ? '' : `?day=${day}`}`)
  const set = (k, v) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }) }

  const pins = data?.pins || []
  const cur = data?.days.find((d) => d.day === day)
  const openPlace = (p) => nav(p.place_id ? `/trips/${tripId}/places/${encodeURIComponent(p.place_id)}?visit=${p.visit_id}` : `/trips/${tripId}/visits/${p.visit_id}`)

  return (
    <div className="screen cta-tabs">
      <TopBar title="동선" right={<Link className="icon-btn" to={`/trips/${tripId}/nearby`} aria-label="근처 못 가본 곳"><Icon name="spark" /></Link>} />
      <div className="segmented" role="tablist" aria-label="날짜 선택">
        {(data?.days || [{ day: 1 }]).map((d) => (
          <button key={d.day} role="tab" aria-selected={!all && day === d.day} className={!all && day === d.day ? 'on' : ''} onClick={() => set('day', d.day)}>{d.day}일차</button>
        ))}
        <button role="tab" aria-selected={all} className={all ? 'on' : ''} onClick={() => set('day', 'all')}>전체</button>
      </div>
      <div className="segmented" style={{ marginTop: 8, boxShadow: 'none', background: 'var(--surface-2)' }}>
        <button className={view === 'map' ? 'on' : ''} onClick={() => set('view', 'map')}>지도</button>
        <button className={view === 'timeline' ? 'on' : ''} onClick={() => set('view', 'timeline')}>타임라인</button>
      </div>
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data && <div style={{ marginTop: 12 }}><Loading lines={2} /></div>}

      {data && view === 'map' && (
        <>
          <div style={{ marginTop: 12 }}>
            <MapView tall pins={pins.map((p) => ({ ...p, id: p.visit_id, title: p.name }))} paths={pathsByDay(pins)} onPinClick={openPlace} />
          </div>
          <div className="sheet">
            <div className="row between">
              <div>
                <b style={{ fontSize: 17 }}>{all ? '전체 일정' : `${day}일차 · ${fmtDate(cur?.date)}`}</b>
                <div className="small muted">방문지 {pins.length}곳 · 사진 {pins.reduce((a, p) => a + p.photo_count, 0)}장</div>
              </div>
              <span className="small muted">{all ? '' : cur?.time_range}</span>
            </div>
            <div className="strip" style={{ marginTop: 12 }}>
              {pins.map((p) => (
                <button key={p.visit_id} className="place-card" onClick={() => openPlace(p)} style={{ position: 'relative', border: 0, background: 'none', padding: 0, textAlign: 'left', cursor: 'pointer' }}>
                  <Photo id={p.rep_photo_id} className="" />
                  <span className="num"><NumBadge n={p.order} color={p.color} size={24} /></span>
                  <div className="nm">{p.name}</div>
                  <div className="tiny muted">{p.type} · {p.time_range}</div>
                </button>
              ))}
            </div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 6, margin: '10px 0 4px' }}>
              {[...new Map(pins.map((p) => [p.type, p.color])).entries()].map(([t, c]) => (
                <span key={t} className="tiny row" style={{ gap: 4 }}><i style={{ width: 10, height: 10, borderRadius: 5, background: c, display: 'inline-block' }} />{t}</span>
              ))}
            </div>
          </div>
        </>
      )}

      {data && view === 'timeline' && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="tl">
            {data.timeline.map((t) => (
              <div key={t.visit_id}>
                {t.leg_from_prev && (
                  <div className="tl-leg"><Icon name={t.leg_from_prev.mode === '도보' ? 'walk' : 'bus'} size={14} />
                    {t.leg_from_prev.mode} 약 {t.leg_from_prev.minutes}분 · {(t.leg_from_prev.distance_m / 1000).toFixed(1)}km</div>
                )}
                <button className="tl-item" onClick={() => openPlace(t)} style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 0, padding: '4px 0 12px', cursor: 'pointer' }}>
                  <NumBadge n={t.order} color={t.color} size={24} />
                  <div className="row between"><b>{t.name}</b><span className="small muted">{t.start}–{t.end}</span></div>
                  <div className="small muted">{all ? `${t.day}일차 · ` : ''}{t.type} · 머문 시간 약 {t.stay_minutes}분 · 사진 {t.photo_count}장</div>
                </button>
              </div>
            ))}
          </div>
          <p className="tiny muted" style={{ margin: '4px 0 0' }}>이동 시간은 직선 거리에 보정 계수를 곱한 추정값이에요.</p>
        </div>
      )}

      <div className="bottom-cta with-tabs">
        <button className="btn" onClick={() => nav(`/trips/${tripId}/nearby`)}>근처 못 가본 곳</button>
        <button className="btn primary" onClick={() => nav(`/trips/${tripId}/story/new`)}>여행기 만들기</button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ C3 장소 상세
export function PlaceDetail() {
  const { tripId, placeId } = useParams()
  const [sp] = useSearchParams()
  const visitId = sp.get('visit')
  const { data: p, error, loading, reload } = useApi(`/places/${encodeURIComponent(placeId)}${visitId ? `?visit_id=${visitId}` : ''}`)
  const { data: visits } = useApi(`/trips/${tripId}/visits`)
  const visit = visits?.visits.find((v) => v.id === visitId) || visits?.visits.find((v) => v.place?.place_id === placeId)

  return (
    <div className="screen">
      <TopBar title="장소 상세" />
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {p && (
        <>
          <div className="hero-photo">
            {p.image_url ? <img src={p.image_url} alt={`${p.name} 대표 사진`} /> : <Photo id={visit?.rep_photo_id} className="" />}
            <span className="overlay">{p.image_url ? `대표 사진 · ${p.source_name}` : '내 사진'}</span>
          </div>
          <div className="row" style={{ marginTop: 14, gap: 8 }}>
            <span className="chip blue">{p.type}</span>
            {p.realtime && <span className="chip warn">실시간 조회</span>}
            {p.sample && <span className="chip">샘플 데이터</span>}
          </div>
          <h2 className="title">{p.name}</h2>
          {visit && <div className="small muted">{visit.day}일차 {visit.start}–{visit.end} 방문 · 사진 {visit.photo_count}장</div>}

          <div className="card" style={{ marginTop: 14 }}>
            {p.overview ? <p style={{ margin: 0 }}>{p.overview}</p> : <p className="muted" style={{ margin: 0 }}>{p.source === 'kakao' ? '카카오 장소는 이름·주소만 실시간으로 보여 드려요.' : '공식 개요 정보가 없어요.'}</p>}
            <hr className="hr" />
            <dl className="kv">
              {p.address && (<><dt>주소</dt><dd>{p.address}</dd></>)}
              {p.usetime && (<><dt>운영시간</dt><dd>{p.usetime}</dd></>)}
              <dt>출처</dt><dd>{p.source_name}{p.updated_at ? ` · 갱신 ${p.updated_at}` : ''}</dd>
              <dt>이용조건</dt><dd className="small">{p.license}</dd>
            </dl>
            {p.source === 'kakao' && (p.place_url
              ? <a className="btn ghost block small-btn" style={{ marginTop: 12 }} href={p.place_url} target="_blank" rel="noreferrer"><Icon name="ext" size={16} />카카오맵 장소 페이지</a>
              : <div className="tiny muted" style={{ marginTop: 10 }}>샘플 장소라 카카오 장소 페이지 링크가 없어요.</div>)}
          </div>
          {visit && (
            <Link to={`/trips/${tripId}/visits/${visit.id}`} className="btn ghost block" style={{ marginTop: 12 }}>이 방문지 장소 바꾸기</Link>
          )}
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ C4 근처 못 가본 곳
export function Nearby() {
  const { tripId } = useParams()
  const nav = useNavigate()
  const { data, error, loading, reload } = useApi(`/trips/${tripId}/nearby`)
  const { data: route } = useApi(`/trips/${tripId}/route`)
  const [focus, setFocus] = useState(null)
  const groups = data?.groups || []
  const shown = focus ? groups.filter((g) => g.visit_id === focus) : groups
  const recs = shown.flatMap((g) => g.items.map((i, k) => ({ ...i, id: `${g.visit_id}-${i.place_id}`, kind: 'rec', label: '★', key: k })))
  const visited = (route?.pins || []).filter((p) => !focus || p.visit_id === focus)

  return (
    <div className="screen">
      <TopBar title="근처 못 가본 곳" />
      <p className="muted small" style={{ marginTop: 0 }}>방문지 주변 공식 관광 데이터 장소 중 이번 여행에서 가지 않은 곳이에요. 다음 부산 여행에 참고하세요.</p>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && (
        <>
          <MapView pins={[...visited.map((p) => ({ ...p, id: p.visit_id })), ...recs]} paths={focus ? [] : pathsByDay(visited)} dashed
            onPinClick={(p) => p.kind === 'rec' && nav(`/trips/${tripId}/places/${encodeURIComponent(p.place_id)}`)} />
          <div className="strip" style={{ margin: '12px 0 4px' }}>
            <button className={`chip ${!focus ? 'solid' : ''}`} style={{ minHeight: 36, border: 0, cursor: 'pointer' }} onClick={() => setFocus(null)}>전체</button>
            {groups.map((g) => (
              <button key={g.visit_id} className={`chip ${focus === g.visit_id ? 'solid' : ''}`} style={{ minHeight: 36, border: 0, cursor: 'pointer' }} onClick={() => setFocus(g.visit_id)}>
                {g.order}. {g.name}
              </button>
            ))}
          </div>
          {shown.map((g) => (
            <div key={g.visit_id}>
              <div className="section-title">{g.order}. {g.name} 근처</div>
              {g.items.length === 0 && <div className="card small muted">근처에 추천할 공식 데이터 장소가 없어요</div>}
              {g.items.map((i) => (
                <Link key={i.place_id} to={`/trips/${tripId}/places/${encodeURIComponent(i.place_id)}`} className="card row between" style={{ marginTop: 8, color: 'inherit', textDecoration: 'none' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 6 }}><b>{i.name}</b><span className="chip blue">{i.type}</span></div>
                    <div className="small muted">{i.distance_m >= 1000 ? `${(i.distance_m / 1000).toFixed(1)}km` : `${i.distance_m}m`} · {i.source_name}</div>
                  </div>
                  <span className="muted">›</span>
                </Link>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
