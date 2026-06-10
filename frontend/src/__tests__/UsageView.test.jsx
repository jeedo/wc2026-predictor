import { render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import UsageView from '../components/UsageView'

const USAGE_DATA = {
  asOf: '2026-06-03T10:00:00Z',
  providers: [
    { name: 'football-data', callCount: 8, limit: 10, window: 'minute', percentUsed: 80.0 },
    { name: 'anthropic', callCount: 2, inputTokens: 20000, outputTokens: 1500, limit: null, window: 'day' },
    { name: 'serper', callCount: 96, limit: 2500, window: 'month', percentUsed: 3.84 },
  ],
}

afterEach(() => vi.restoreAllMocks())

test('shows loading state initially', () => {
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
  render(<UsageView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('renders provider names after load', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(USAGE_DATA),
  }))
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/football-data/i)).toBeInTheDocument()
    expect(screen.getByText(/anthropic/i)).toBeInTheDocument()
    expect(screen.getByText(/serper/i)).toBeInTheDocument()
  })
})

test('shows call counts and limits', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(USAGE_DATA),
  }))
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/8\s*\/\s*10/)).toBeInTheDocument()
  })
})

test('shows error when fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<UsageView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})

test('shows empty state when no providers', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ providers: [] }),
  }))
  render(<UsageView />)
  await waitFor(() => {
    expect(screen.getByText(/no usage data/i)).toBeInTheDocument()
  })
})
