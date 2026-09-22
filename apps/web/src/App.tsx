import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/layout/Shell'
import { Home } from './routes/Home'
import { Cameras } from './routes/Cameras'
import { FindVehicle } from './routes/FindVehicle'
import { Alerts } from './routes/Alerts'

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/cameras" element={<Cameras />} />
          <Route path="/find-a-vehicle" element={<FindVehicle />} />
          <Route path="/alerts" element={<Alerts />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
