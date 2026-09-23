import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/layout/Shell'
import { Home } from './routes/Home'
import { Cameras } from './routes/Cameras'
import { LiveWall } from './routes/LiveWall'
import { FindVehicle } from './routes/FindVehicle'
import { Alerts } from './routes/Alerts'
import { Health } from './routes/Health'
import { AdminPortal } from './routes/AdminPortal'
import { Login } from './routes/Login'
import { AuthProvider, useAuth } from './lib/AuthContext'
import { CommandPalette } from './components/CommandPalette'
import { FieldApp } from './field/FieldApp'
import type { ReactNode } from 'react'

function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="flex h-screen w-screen items-center justify-center bg-bg-base" />
  }
  if (!user) {
    return <Login />
  }
  return (
    <>
      <CommandPalette />
      {children}
    </>
  )
}

function OperatorConsole() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/live-wall" element={<LiveWall />} />
        <Route path="/cameras" element={<Cameras />} />
        <Route path="/find-a-vehicle" element={<FindVehicle />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/health" element={<Health />} />
        <Route path="/admin" element={<AdminPortal />} />
      </Routes>
    </Shell>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AuthGate>
          <Routes>
            {/* The Field PWA is a completely separate information
             * architecture (docs/03-UX-DESIGN.md §3) — it gets its own
             * route branch with its own layout, not the console's Shell. */}
            <Route path="/field/*" element={<FieldApp />} />
            <Route path="/*" element={<OperatorConsole />} />
          </Routes>
        </AuthGate>
      </BrowserRouter>
    </AuthProvider>
  )
}
