import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import { MOCK_GROUPS, MOCK_PREDICTIONS } from '../mocks/data'
import GroupsView from '../components/GroupsView'

const PREDICTIONS_WITH_MATCHES = {
  ...MOCK_PREDICTIONS,
  groups: [{
    group: 'A', winner: 'Germany', runnerUp: 'Mexico', confidence: 'high',
    reasoning: 'Strong FIFA ranking.',
    matches: [
      { homeTeam: 'Germany', awayTeam: 'Mexico',  matchday: 1, predictedHomeScore: 2, predictedAwayScore: 1, confidence: 'high' },
      { homeTeam: 'Germany', awayTeam: 'Poland',  matchday: 2, predictedHomeScore: 1, predictedAwayScore: 0, confidence: 'medium' },
    ],
  }],
}

test('shows group teams when no predictions available', async () => {
  server.use(
    http.get('/api/predictions', () => new HttpResponse(null, { status: 404 }))
  )
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText('Group A')).toBeInTheDocument()
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
  })
})

test('shows predicted winner and runner-up when predictions exist', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
    expect(screen.getByText(/Mexico/)).toBeInTheDocument()
    expect(screen.getByText(/Strong FIFA ranking/)).toBeInTheDocument()
  })
})

test('shows confidence badge next to winner', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    const badges = screen.getAllByText(/high|medium|low/i)
    expect(badges.length).toBeGreaterThan(0)
  })
})

test('shows loading state initially', () => {
  server.use(http.get('/api/groups', () => new Promise(() => {})))
  render(<GroupsView />)
  expect(document.querySelectorAll('.group-card--skeleton').length).toBe(12)
})

test('shows error when groups fetch fails', async () => {
  server.use(http.get('/api/groups', () => HttpResponse.error()))
  render(<GroupsView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})

test('shows individual match predictions when matches are present', async () => {
  server.use(
    http.get('/api/predictions', () => HttpResponse.json(PREDICTIONS_WITH_MATCHES))
  )
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/2\s*[–-]\s*1/)).toBeInTheDocument()
    expect(screen.getByText(/match predictions/i)).toBeInTheDocument()
  })
})

test('shows no match predictions section when matches array is absent', async () => {
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
    expect(screen.queryByText(/\d\s*[–-]\s*\d/)).not.toBeInTheDocument()
  })
})
