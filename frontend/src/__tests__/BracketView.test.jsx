import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import BracketView from '../components/BracketView'

const PRED_WITH_KNOCKOUT = {
  matchday: 1,
  groups: [],
  knockout: [
    {
      stage: 'LAST_16',
      matches: [
        { fixtureId: 1001, stage: 'LAST_16', homeTeam: 'France', awayTeam: 'Brazil',
          predictedWinner: 'France', predictedHomeScore: 2, predictedAwayScore: 1, confidence: 'high' },
        { fixtureId: 1002, stage: 'LAST_16', homeTeam: 'Germany', awayTeam: 'Argentina',
          predictedWinner: 'Germany', predictedHomeScore: 1, predictedAwayScore: 0, confidence: 'medium' },
      ],
    },
    {
      stage: 'QUARTER_FINALS',
      matches: [
        { fixtureId: 2001, stage: 'QUARTER_FINALS', homeTeam: 'France', awayTeam: 'Germany',
          predictedWinner: 'France', predictedHomeScore: 2, predictedAwayScore: 0, confidence: 'high' },
      ],
    },
  ],
}

test('shows heading', async () => {
  server.use(http.get('/api/predictions', () => HttpResponse.json(PRED_WITH_KNOCKOUT)))
  render(<BracketView />)
  await waitFor(() => expect(screen.getByRole('heading', { name: /knockout bracket/i })).toBeInTheDocument())
})

test('shows round labels when predictions exist', async () => {
  server.use(http.get('/api/predictions', () => HttpResponse.json(PRED_WITH_KNOCKOUT)))
  render(<BracketView />)
  await waitFor(() => {
    expect(screen.getByText('Round of 16')).toBeInTheDocument()
    expect(screen.getByText('Quarter-Finals')).toBeInTheDocument()
  })
})

test('shows team names from predictions', async () => {
  server.use(http.get('/api/predictions', () => HttpResponse.json(PRED_WITH_KNOCKOUT)))
  render(<BracketView />)
  await waitFor(() => {
    expect(screen.getAllByText(/France/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Brazil/)).toBeInTheDocument()
  })
})

test('shows predicted scores', async () => {
  server.use(http.get('/api/predictions', () => HttpResponse.json(PRED_WITH_KNOCKOUT)))
  render(<BracketView />)
  await waitFor(() => {
    const twos = screen.getAllByText('2')
    expect(twos.length).toBeGreaterThan(0)
  })
})

test('shows coming-soon message when no knockout predictions', async () => {
  render(<BracketView />)
  await waitFor(() => {
    expect(screen.getByText(/group stage concludes/i)).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  server.use(http.get('/api/predictions', () => new Promise(() => {})))
  render(<BracketView />)
  expect(document.querySelector('phantom-ui')).toBeInTheDocument()
})

test('shows error when fetch fails', async () => {
  server.use(http.get('/api/predictions', () => HttpResponse.error()))
  render(<BracketView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})
