import { render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import GroupsView from '../components/GroupsView'

const PREDICTIONS = {
  matchday: 1,
  generatedAt: '2026-06-12T10:00:00Z',
  groups: [
    { group: 'A', winner: 'Germany', runnerUp: 'Mexico', reasoning: 'Strong FIFA ranking and recent form.' },
    { group: 'B', winner: 'Brazil', runnerUp: 'Argentina', reasoning: 'Brazil leads on all metrics.' },
  ],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(PREDICTIONS),
  }))
})

afterEach(() => vi.restoreAllMocks())

test('renders a card for each group', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText('Group A')).toBeInTheDocument()
    expect(screen.getByText('Group B')).toBeInTheDocument()
  })
})

test('shows predicted winner and runner-up', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText('Germany')).toBeInTheDocument()
    expect(screen.getByText('Mexico')).toBeInTheDocument()
  })
})

test('shows Claude reasoning blurb', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/Strong FIFA ranking/)).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  render(<GroupsView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows error when fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument()
  })
})
