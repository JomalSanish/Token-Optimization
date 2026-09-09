import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'

// Layouts
import UserLayout from './layouts/UserLayout'
import AdminLayout from './layouts/AdminLayout'

// User Pages
import KeysPage from './pages/user/KeysPage'
import ProjectPage from './pages/user/ProjectPage'
import EstimatePage from './pages/user/EstimatePage'
import OptimizePage from './pages/user/OptimizePage'
import DiscoverPage from './pages/user/DiscoverPage'

// Admin Pages
import ProvidersPage from './pages/admin/ProvidersPage'
import ModelsPage from './pages/admin/ModelsPage'
import PricingPage from './pages/admin/PricingPage'
import RulesPage from './pages/admin/RulesPage'
import PhasesPage from './pages/admin/PhasesPage'

// Stub pages for other routes to prevent render errors
const Stub = ({ title }) => <div style={{ padding: '40px' }}><h2>{title}</h2><p>Placeholder page</p></div>;

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Redirect root to /keys */}
        <Route path="/" element={<Navigate to="/keys" replace />} />

        {/* User Routes */}
        <Route element={<UserLayout />}>
          <Route path="/keys" element={<KeysPage />} />
          <Route path="/models" element={<Navigate to="/keys#model-details" replace />} />
          <Route path="/project" element={<ProjectPage />} />
          <Route path="/estimate" element={<EstimatePage />} />
          <Route path="/optimize" element={<OptimizePage />} />
          <Route path="/discover" element={<DiscoverPage />} />
        </Route>

        {/* Admin Routes */}
        <Route path="/admin" element={<Navigate to="/admin/providers" replace />} />
        <Route element={<AdminLayout />}>
          <Route path="/admin/providers" element={<ProvidersPage />} />
          <Route path="/admin/models" element={<ModelsPage />} />
          <Route path="/admin/pricing" element={<PricingPage />} />
          <Route path="/admin/rules" element={<RulesPage />} />
          <Route path="/admin/phases" element={<PhasesPage />} />
        </Route>

        {/* 404 Catch-All */}
        <Route path="*" element={
          <div style={{ padding: '40px', textAlign: 'center' }}>
            <h2>404 - Not Found</h2>
            <p>The page you are looking for does not exist.</p>
          </div>
        } />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
