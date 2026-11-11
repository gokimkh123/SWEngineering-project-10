import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버는 /api 요청을 FastAPI(8000)로 넘긴다. 같은 Wi-Fi의 휴대폰에서 열 수 있게 host 공개.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
