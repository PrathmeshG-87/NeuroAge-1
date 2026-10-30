import React from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { HistoryPage } from '@/pages/HistoryPage'
import { LandingPage } from '@/pages/LandingPage'
import { ModelInfoPage } from '@/pages/ModelInfoPage'
import {
  AssessmentDetailPage,
  AssessmentPage,
  MethodologyPage,
  NotFoundPage,
  ProgressPage,
  ReportsPage,
  SettingsPage,
} from '@/pages/RoutePlaceholders'
import { UploadPage } from '@/pages/UploadPage'
import { ViewerPage } from '@/pages/ViewerPage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AppShell />}>
        <Route path="/assessment" element={<AssessmentPage />} />
        <Route path="/assessments/:id" element={<AssessmentDetailPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="/methodology" element={<MethodologyPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/viewer" element={<ViewerPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/model" element={<ModelInfoPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
