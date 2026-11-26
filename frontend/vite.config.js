import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버는 /api 요청을 FastAPI(8000)로 넘긴다. 같은 Wi-Fi의 휴대폰에서 열 수 있게 host 공개.
// 환경변수는 저장소 루트 .env 하나만 쓴다 (VITE_ 로 시작하는 값만 브라우저에 들어감).
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    host: true,
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
