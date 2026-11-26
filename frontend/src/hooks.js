import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

export function useApi(path, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    if (!path) return
    setLoading(true)
    setError(null)
    try {
      setData(await api(path))
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps])
  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load, setData }
}

export function useMeta() {
  return useApi('/meta')
}

// 데스크톱 너비(960px 이상)인지. 휴대폰에서 보이지 않는 지도는 아예 만들지 않으려고 쓴다
export function useWide(query = '(min-width: 960px)') {
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setWide(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [query])
  return wide
}
