import { http, HttpResponse } from 'msw'
import {
  MOCK_GROUPS, MOCK_PREDICTIONS,
  MOCK_FIXTURES_MD1, MOCK_FIXTURES_MD2, MOCK_FIXTURES_MD3,
  MOCK_STAGE_FIXTURES, MOCK_ACCURACY, MOCK_NEWS, MOCK_USAGE,
} from './data.js'

const FIXTURES_BY_MD = { 1: MOCK_FIXTURES_MD1, 2: MOCK_FIXTURES_MD2, 3: MOCK_FIXTURES_MD3 }

// Relative paths match any origin — works in both jsdom (tests) and the Vite dev server.
export const handlers = [
  http.get('/api/groups',      () => HttpResponse.json(MOCK_GROUPS)),
  http.get('/api/predictions', () => HttpResponse.json(MOCK_PREDICTIONS)),
  http.get('/api/accuracy',    () => HttpResponse.json(MOCK_ACCURACY)),
  http.get('/api/usage',       () => HttpResponse.json(MOCK_USAGE)),

  // Stage route must come before :matchday to avoid "stage" being captured as a matchday param
  http.get('/api/fixtures/stage/:stage', () => HttpResponse.json(MOCK_STAGE_FIXTURES)),

  http.get('/api/fixtures/:matchday', ({ params }) =>
    HttpResponse.json(FIXTURES_BY_MD[Number(params.matchday)] ?? MOCK_FIXTURES_MD1)
  ),

  http.get('/api/news/:team', () => HttpResponse.json(MOCK_NEWS)),

  http.post('/api/news/refresh', () => HttpResponse.json({
    status: 'ok', date: '2026-06-14', teams: 2, fetched: 2,
    results: { Germany: 3, Mexico: 3 },
  })),
]
