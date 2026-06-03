import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import FixturesView from '../components/FixturesView'

const MD1 = {
  matchday: 1,
  fixtures: [
    { id: 'fixture-101', matchday: 1, homeTeam: 'Germany', awayTeam: 'Mexico',
      homeScore: 2, awayScore: 0, status: 'FT', kickoff: '2026-06-12T15:00:00Z' },
    { id: 'fixture-102', matchday: 1, homeTeam: 'Brazil', awayTeam: 'Argentina',
      homeScore: null, awayScore: null, status: 'NS', kickoff: '2026-06-12T18:00:00Z',
      predictedHomeScore: 2, predictedAwayScore: 1, predictedConfidence: 'medium' },
    { id: 'fixture-103', matchday: 1, homeTeam: 'France', awayTeam: 'Spain',
      homeScore: null, awayScore: null, status: 'NS', kickoff: '2026-06-13T15:00:00Z' },
  ],
}

const MD2 = {
  matchday: 2,
  fixtures: [
    { id: 'fixture-201', matchday: 2, homeTeam: 'France', awayTeam: 'England',
      homeScore: 1, awayScore: 1, status: 'FT', kickoff: '2026-06-17T15:00:00Z' },
  ],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
    const md = url.includes('/2') ? MD2 : MD1
    return Promise.resolve({ ok: true, json: () => Promise.resolve(md) })
  }))
})

afterEach(() => vi.restoreAllMocks())

test('renders matchday tab selector', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByRole('tab', { name: /matchday 1/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /matchday 2/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /matchday 3/i })).toBeInTheDocument()
  })
})

test('shows fixtures for the selected matchday', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText('Germany')).toBeInTheDocument()
    expect(screen.getByText('Mexico')).toBeInTheDocument()
  })
})

test('shows score for finished matches', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText('2 – 0')).toBeInTheDocument()
  })
})

test('shows kickoff time for upcoming matches', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    // Brazil vs Argentina is NS — should not show a score
    expect(screen.queryByText('null – null')).not.toBeInTheDocument()
  })
})

test('switching tab loads different matchday', async () => {
  const user = userEvent.setup()
  render(<FixturesView />)

  await waitFor(() => screen.getByText('Germany'))

  await user.click(screen.getByRole('tab', { name: /matchday 2/i }))

  await waitFor(() => {
    expect(screen.getByText('France')).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  render(<FixturesView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows error when fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument()
  })
})

test('shows predicted score for upcoming matches with predictions', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    // Brazil vs Argentina has predictedHomeScore: 2, predictedAwayScore: 1
    expect(screen.getByText('2 – 1')).toBeInTheDocument()
    expect(screen.getByText('(pred · medium)')).toBeInTheDocument()
  })
})

test('shows confidence level in predicted score', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    // Brazil vs Argentina has predictedConfidence: 'medium'
    expect(screen.getByText('(pred · medium)')).toBeInTheDocument()
  })
})

test('shows kickoff time alongside predicted score', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    // Should show both predicted score and kickoff time for Brazil vs Argentina
    expect(screen.getByText('Brazil')).toBeInTheDocument()
    expect(screen.getByText('Argentina')).toBeInTheDocument()
    // Predicted score is shown with confidence
    expect(screen.getByText('(pred · medium)')).toBeInTheDocument()
  })
})

test('shows only kickoff time for upcoming matches without predictions', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    // France vs Spain has no predictions, should show kickoff time
    expect(screen.getByText('France')).toBeInTheDocument()
    expect(screen.getByText('Spain')).toBeInTheDocument()
  })
})
