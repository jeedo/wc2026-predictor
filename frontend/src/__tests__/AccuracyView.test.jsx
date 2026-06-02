import { render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import AccuracyView from '../components/AccuracyView'

const ACCURACY_DATA = {
  matchday: 2,
  evaluatedAt: '2026-06-22T10:00:00Z',
  score: 8,
  totalGroups: 12,
  groups: [
    { group: 'A', correct: true, predictedWinner: 'Germany', actualWinner: 'Germany',
      predictedRunnerUp: 'Mexico', actualRunnerUp: 'Mexico' },
    { group: 'B', correct: false, predictedWinner: 'Brazil', actualWinner: 'France',
      predictedRunnerUp: 'Argentina', actualRunnerUp: 'England' },
  ],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(ACCURACY_DATA),
  }))
})

afterEach(() => vi.restoreAllMocks())

test('shows overall score', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText('8 / 12')).toBeInTheDocument()
  })
})

test('shows per-group rows', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText('Group A')).toBeInTheDocument()
    expect(screen.getByText('Group B')).toBeInTheDocument()
  })
})

test('correct groups show a correct indicator', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    const rows = screen.getAllByRole('row')
    const groupARow = rows.find(r => r.textContent.includes('Group A'))
    expect(groupARow).toHaveClass('correct')
  })
})

test('incorrect groups show an incorrect indicator', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    const rows = screen.getAllByRole('row')
    const groupBRow = rows.find(r => r.textContent.includes('Group B'))
    expect(groupBRow).toHaveClass('incorrect')
  })
})

test('shows predicted and actual values', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getAllByText('Germany').length).toBeGreaterThan(0)
    expect(screen.getByText('France')).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  render(<AccuracyView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows 404 message when no data', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: () => Promise.resolve({ error: 'No accuracy data available' }),
  }))
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText(/no accuracy/i)).toBeInTheDocument()
  })
})
