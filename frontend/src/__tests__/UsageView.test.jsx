import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import UsageView from '../components/UsageView'

test('shows loading state initially', () => {
  server.use(http.get('/api/usage', () => new Promise(() => {})))
  render(<UsageView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('renders provider names after load', async () => {
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/football-data/i)).toBeInTheDocument()
    expect(screen.getByText(/anthropic/i)).toBeInTheDocument()
    expect(screen.getByText(/SerpApi/i)).toBeInTheDocument()
  })
})

test('shows call counts and limits', async () => {
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/96\s*\/\s*2500/)).toBeInTheDocument()
    expect(screen.getByText(/Rate limit: 10\/min/i)).toBeInTheDocument()
  })
})

test('shows error when fetch fails', async () => {
  server.use(http.get('/api/usage', () => HttpResponse.error()))
  render(<UsageView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})

test('shows empty state when no providers', async () => {
  server.use(
    http.get('/api/usage', () => HttpResponse.json({ providers: [] }))
  )
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/no usage data/i)).toBeInTheDocument()
  })
})
