// CP-01 Web Client — 화면 A1~D4 (요구사항분석서 6.1) + 하단 탭 (홈 · 내 여행 · 업로드 · 여행기 · MY)
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import './styles.css'
import { Tabs } from './components/ui.jsx'
import { Analyzing, Home, MyPage, MyTrips, StoriesTab, Upload } from './screens/A_upload.jsx'
import { ConfirmDone, PlaceCheck, Untagged, VisitList } from './screens/B_confirm.jsx'
import { Nearby, PlaceDetail, RouteMap } from './screens/C_route.jsx'
import { ShareCard, StoryEdit, StoryView, StyleSelect } from './screens/D_story.jsx'

// 전체 화면 흐름(업로드·확인·편집)에서는 하단 탭을 숨긴다
const NO_TABS = [/^\/upload/, /\/analyzing$/, /\/visits/, /\/untagged$/, /\/done$/, /\/story\/new$/, /\/edit$/, /\/share$/]

function Shell() {
  const { pathname } = useLocation()
  const showTabs = !NO_TABS.some((r) => r.test(pathname))
  return (
    <div className="app">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/trips" element={<MyTrips />} />
        <Route path="/stories" element={<StoriesTab />} />
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
      {showTabs && <Tabs />}
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
