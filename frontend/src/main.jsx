// CP-01 Web Client — 화면 A1~D4 (요구사항분석서 6.1). 첫 화면은 일기장(여행 목록 | 여행기), 새 여행기는 + 버튼
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './styles.css'
import { initTheme } from './theme.js'
import { Analyzing, MyPage, Upload } from './screens/A_upload.jsx'
import { ConfirmDone, PlaceCheck, Untagged, VisitList } from './screens/B_confirm.jsx'
import { Nearby, PlaceDetail, RouteMap } from './screens/C_route.jsx'
import { ShareCard, StoryEdit, StyleSelect } from './screens/D_story.jsx'
import { Journal, StoryView } from './screens/Journal.jsx'

initTheme() // 밝게·어둡게·기기 설정 (그리기 전에 적용)

function Shell() {
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Journal />} />
        <Route path="/trips" element={<Journal />} />
        <Route path="/stories" element={<Journal />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/my" element={<MyPage />} />
        <Route path="/trips/:tripId/analyzing" element={<Analyzing />} />
        <Route path="/trips/:tripId/visits" element={<VisitList />} />
        <Route path="/trips/:tripId/visits/:visitId" element={<PlaceCheck />} />
        <Route path="/trips/:tripId/untagged" element={<Untagged />} />
        <Route path="/trips/:tripId/done" element={<ConfirmDone />} />
        <Route path="/trips/:tripId/route" element={<RouteMap />} />
        <Route path="/trips/:tripId/places/:placeId" element={<PlaceDetail />} />
        <Route path="/trips/:tripId/nearby" element={<Nearby />} />
        <Route path="/trips/:tripId/story/new" element={<StyleSelect />} />
        <Route path="/stories/:storyId" element={<StoryView />} />
        <Route path="/stories/:storyId/edit" element={<StoryEdit />} />
        <Route path="/stories/:storyId/share" element={<ShareCard />} />
        <Route path="*" element={<div className="screen empty">페이지를 찾을 수 없어요</div>} />
      </Routes>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </React.StrictMode>,
)
