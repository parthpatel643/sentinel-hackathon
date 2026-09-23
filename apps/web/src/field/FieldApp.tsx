import { Navigate, Route, Routes } from 'react-router-dom'
import { FieldShell } from './FieldShell'
import { FieldAlerts } from './FieldAlerts'
import { FieldLookup } from './FieldLookup'
import { FieldReport } from './FieldReport'
import { FieldNearby } from './FieldNearby'

/** The Field PWA's own route tree — deliberately not nested under the
 * Operator Console's <Shell> (docs/03-UX-DESIGN.md §3: "not a responsive
 * squeeze... a separate, drastically reduced information architecture"). */
export function FieldApp() {
  return (
    <FieldShell>
      <Routes>
        <Route path="alerts" element={<FieldAlerts />} />
        <Route path="lookup" element={<FieldLookup />} />
        <Route path="report" element={<FieldReport />} />
        <Route path="nearby" element={<FieldNearby />} />
        <Route path="*" element={<Navigate to="alerts" replace />} />
      </Routes>
    </FieldShell>
  )
}
