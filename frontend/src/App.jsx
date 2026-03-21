import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import EngagementList from './pages/EngagementList'
import EngagementWorkspace from './pages/EngagementWorkspace'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30000,
    }
  }
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<EngagementList />} />
          <Route path="/engagement/:id" element={<EngagementWorkspace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}