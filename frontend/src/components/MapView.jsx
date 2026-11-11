// 지도 표시 (FR-07, UI-02, UI-06). 카카오맵 JS 키가 있으면 카카오맵 JS SDK(설계서 CP-01),
// 없으면 Leaflet + OpenStreetMap으로 같은 핀·경로를 그린다. 브라우저 지도 표시는 CP-01이 SDK를 직접 쓴다 (의존 규칙 3 예외).
import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const KAKAO_KEY = import.meta.env.VITE_KAKAO_JS_KEY
let kakaoPromise = null

function loadKakao() {
  if (!KAKAO_KEY) return Promise.reject(new Error('no key'))
  if (window.kakao?.maps) return Promise.resolve(window.kakao)
  if (!kakaoPromise) {
    kakaoPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_KEY}&autoload=false`
      s.onload = () => window.kakao.maps.load(() => resolve(window.kakao))
      s.onerror = () => reject(new Error('카카오맵을 불러오지 못했어요'))
      document.head.appendChild(s)
    })
  }
  return kakaoPromise
}

function pinHtml(p) {
  const cls = p.kind === 'rec' ? 'pin rec' : p.ghost ? 'pin ghost' : 'pin'
  const label = p.label ?? p.order ?? ''
  return `<div class="${cls}" style="background:${p.color || '#F05C2C'}">${label}</div>`
}

/**
 * pins: [{id, lat, lng, color, order|label, kind?: 'rec', ghost?}]
 * paths: [[{lat,lng}, ...], ...] 방문 순서 경로 (날짜별로 끊어서 전달)
 */
export default function MapView({ pins = [], paths = [], onPinClick, tall = false, dashed = false }) {
  const el = useRef(null)
  const state = useRef({})
  const [provider, setProvider] = useState(KAKAO_KEY ? 'kakao' : 'leaflet')
  const [error, setError] = useState(null)
  const valid = pins.filter((p) => p.lat != null && p.lng != null)

  // 지도 만들기
  useEffect(() => {
    let cancelled = false
    if (provider === 'kakao') {
      loadKakao().then((kakao) => {
        if (cancelled || !el.current) return
        state.current.kakao = kakao
        state.current.map = new kakao.maps.Map(el.current, { center: new kakao.maps.LatLng(35.15, 129.1), level: 7 })
        state.current.overlays = []
        state.current.ready = true
        setError(null)
        draw()
      }).catch(() => !cancelled && setProvider('leaflet'))
    } else {
      const map = L.map(el.current, { zoomControl: false, attributionControl: false }).setView([35.15, 129.1], 12)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map)
      L.control.zoom({ position: 'topright' }).addTo(map)
      state.current = { map, layer: L.layerGroup().addTo(map), ready: true }
      draw()
    }
    return () => {
      cancelled = true
      if (provider === 'leaflet' && state.current.map) state.current.map.remove()
      state.current = {}
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider])

  useEffect(() => { draw() }) // 핀·경로가 바뀔 때마다 다시 그림

  function draw() {
    const s = state.current
    if (!s.ready) return
    if (provider === 'kakao') {
      const { kakao, map } = s
      s.overlays.forEach((o) => o.setMap(null))
      s.overlays = []
      const bounds = new kakao.maps.LatLngBounds()
      paths.forEach((path) => {
        if (path.length < 2) return
        const line = new kakao.maps.Polyline({
          path: path.map((q) => new kakao.maps.LatLng(q.lat, q.lng)),
          strokeWeight: 4, strokeColor: '#F05C2C', strokeOpacity: 0.85, strokeStyle: dashed ? 'shortdash' : 'solid',
        })
        line.setMap(map)
        s.overlays.push(line)
      })
      valid.forEach((p) => {
        const node = document.createElement('div')
        node.innerHTML = pinHtml(p)
        node.style.cursor = 'pointer'
        node.onclick = () => onPinClick?.(p)
        const pos = new kakao.maps.LatLng(p.lat, p.lng)
        const ov = new kakao.maps.CustomOverlay({ position: pos, content: node, yAnchor: 0.5 })
        ov.setMap(map)
        s.overlays.push(ov)
        bounds.extend(pos)
      })
      if (valid.length > 1) map.setBounds(bounds, 40, 40, 40, 40)
      else if (valid.length === 1) map.setCenter(new kakao.maps.LatLng(valid[0].lat, valid[0].lng))
      return
    }
    const { map, layer } = s
    layer.clearLayers()
    paths.forEach((path) => {
      if (path.length < 2) return
      L.polyline(path.map((q) => [q.lat, q.lng]), { color: '#F05C2C', weight: 4, opacity: 0.85, dashArray: dashed ? '6 8' : null }).addTo(layer)
    })
    valid.forEach((p) => {
      const icon = L.divIcon({ className: 'leaflet-div-icon clear', html: pinHtml(p), iconSize: [30, 30], iconAnchor: [15, 15] })
      const m = L.marker([p.lat, p.lng], { icon, keyboard: true, title: p.title || '' }).addTo(layer)
      if (onPinClick) m.on('click', () => onPinClick(p))
    })
    // 애니메이션 없이 맞춰야 화면 이동 중 지도가 제거돼도 오류가 나지 않는다
    if (valid.length > 1) map.fitBounds(L.latLngBounds(valid.map((p) => [p.lat, p.lng])), { padding: [36, 36], maxZoom: 16, animate: false })
    else if (valid.length === 1) map.setView([valid[0].lat, valid[0].lng], 15, { animate: false })
    setTimeout(() => { if (state.current.map === map) map.invalidateSize({ animate: false }) }, 50)
  }

  return (
    <div className={`map${tall ? ' tall' : ''}`}>
      <div ref={el} style={{ width: '100%', height: '100%' }} role="application" aria-label="방문 동선 지도" />
      <span className="map-attrib">{provider === 'kakao' ? '© Kakao' : '© OpenStreetMap contributors'}</span>
      {error && <div className="notice error">{error}</div>}
    </div>
  )
}
