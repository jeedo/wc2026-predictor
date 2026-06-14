import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import { MOCK_FIXTURES_MD1, MOCK_FIXTURES_MD2 } from '../mocks/data'
import FixturesView from '../components/FixturesView'

const PREDICTIONS_EMPTY_KNOCKOUT = { matchday: 1, groups: [], knockout: [] }

const PREDICTIONS_WITH_KNOCKOUT = {
  matchday: 1, groups: [],
  knockout: [{ stage: 'LAST_16', matches: [
    { fixtureId: 5001, stage: 'LAST_16', homeTeam: 'France', awayTeam: 'Brazil',
      predictedWinner: 'France', predictedHomeScore: 2, predictedAwayScore: 1, confidence: 'high' },
  ]}],
}

const STAGE_FIXTURES = {
  stage: 'LAST_16',
  fixtures: [
    { id: 'f-ko-1', fixtureId: 5001, stage: 'LAST_16', matchday: 'LAST_16',
      homeTeam: 'France', awayTeam: 'Brazil', homeScore: null, awayScore: null,
      status: 'NS', kickoff: '2026-06-28T18:00:00Z' },
  ],
}

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
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
    expect(screen.getByText(/Mexico/)).toBeInTheDocument()
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
    expect(screen.queryByText('null – null')).not.toBeInTheDocument()
  })
})

test('switching tab loads different matchday', async () => {
  server.use(
    http.get('/api/fixtures/:matchday', ({ params }) =>
      HttpResponse.json(params.matchday === '2' ? MOCK_FIXTURES_MD2 : MOCK_FIXTURES_MD1)
    )
  )
  const user = userEvent.setup()
  render(<FixturesView />)
  await waitFor(() => screen.getByText(/Germany/))
  await user.click(screen.getByRole('tab', { name: /matchday 2/i }))
  await waitFor(() => {
    expect(screen.getByText(/France/)).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  server.use(http.get('/api/fixtures/:matchday', () => new Promise(() => {})))
  render(<FixturesView />)
  expect(document.querySelector('phantom-ui')).toBeInTheDocument()
})

test('shows error when fetch fails', async () => {
  server.use(http.get('/api/fixtures/:matchday', () => HttpResponse.error()))
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument()
  })
})

test('shows predicted score for upcoming matches with predictions', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText('2 – 1')).toBeInTheDocument()
    expect(screen.getByText('pred · medium')).toBeInTheDocument()
  })
})

test('shows confidence level in predicted score', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText('pred · medium')).toBeInTheDocument()
  })
})

test('shows kickoff time alongside predicted score', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText(/Brazil/)).toBeInTheDocument()
    expect(screen.getByText(/Argentina/)).toBeInTheDocument()
    expect(screen.getByText('pred · medium')).toBeInTheDocument()
  })
})

test('shows only kickoff time for upcoming matches without predictions', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByText(/France/)).toBeInTheDocument()
    expect(screen.getByText(/Spain/)).toBeInTheDocument()
  })
})

test('renders Knockout tab button', async () => {
  render(<FixturesView />)
  await waitFor(() => {
    expect(screen.getByRole('tab', { name: /knockout/i })).toBeInTheDocument()
  })
})

test('switching to Knockout tab shows coming-soon when no knockout predictions', async () => {
  server.use(
    http.get('/api/predictions', () => HttpResponse.json(PREDICTIONS_EMPTY_KNOCKOUT))
  )
  const user = userEvent.setup()
  render(<FixturesView />)
  await user.click(screen.getByRole('tab', { name: /knockout/i }))
  await waitFor(() => {
    expect(screen.getByText(/group stage concludes/i)).toBeInTheDocument()
  })
})

test('Knockout tab shows loading then stage sections when predictions exist', async () => {
  server.use(
    http.get('/api/predictions', () => HttpResponse.json(PREDICTIONS_WITH_KNOCKOUT)),
    http.get('/api/fixtures/stage/:stage', () => HttpResponse.json(STAGE_FIXTURES)),
  )
  const user = userEvent.setup()
  render(<FixturesView />)
  await user.click(screen.getByRole('tab', { name: /knockout/i }))
  await waitFor(() => {
    expect(screen.queryByText(/group stage concludes/i)).not.toBeInTheDocument()
  })
})
