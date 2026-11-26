// 화면 밝기: 'light' | 'dark' | 'system'(기기 설정을 따름). 이 기기에만 저장한다.
import { useEffect, useState } from 'react'

const KEY = 'chalkak.theme'
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

function read() {
  try {
    return localStorage.getItem(KEY) || 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(mode) {
  const el = document.documentElement
  if (mode === 'light' || mode === 'dark') el.dataset.theme = mode
  else delete el.dataset.theme
}

export function initTheme() {
  applyTheme(read())
}

/** [고른 값, 실제로 보이는 밝기, 바꾸기] */
export function useTheme() {
  const [mode, setMode] = useState(read)
  const [systemDark, setSystemDark] = useState(() => media().matches)
  useEffect(() => {
    const m = media()
    const on = () => setSystemDark(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  const change = (next) => {
    try {
      if (next === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, next)
    } catch {
      /* 저장 못 해도 지금 화면에는 적용 */
    }
    applyTheme(next)
    setMode(next)
  }
  const effective = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode
  return [mode, effective, change]
}
