export const MOCK_GROUPS = {
  groups: [
    { group: 'A', teams: [
      { teamId: 1, name: 'Germany' }, { teamId: 2, name: 'Mexico' },
      { teamId: 3, name: 'South Africa' }, { teamId: 4, name: 'Ecuador' },
    ]},
    { group: 'B', teams: [
      { teamId: 5, name: 'Brazil' }, { teamId: 6, name: 'Argentina' },
      { teamId: 7, name: 'France' }, { teamId: 8, name: 'Spain' },
    ]},
  ],
}

export const MOCK_PREDICTIONS = {
  matchday: 1,
  generatedAt: '2026-06-12T10:00:00Z',
  groups: [
    { group: 'A', winner: 'Germany', runnerUp: 'Mexico', confidence: 'high', reasoning: 'Strong FIFA ranking.' },
    { group: 'B', winner: 'Brazil', runnerUp: 'Argentina', confidence: 'medium', reasoning: 'Brazil leads.' },
  ],
  knockout: [],
}

export const MOCK_FIXTURES_MD1 = {
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

export const MOCK_FIXTURES_MD2 = {
  matchday: 2,
  fixtures: [
    { id: 'fixture-201', matchday: 2, homeTeam: 'France', awayTeam: 'England',
      homeScore: 1, awayScore: 1, status: 'FT', kickoff: '2026-06-17T15:00:00Z' },
  ],
}

export const MOCK_FIXTURES_MD3 = { matchday: 3, fixtures: [] }

export const MOCK_STAGE_FIXTURES = { stage: 'LAST_16', fixtures: [] }

export const MOCK_ACCURACY = {
  matchday: 2,
  evaluatedAt: '2026-06-22T10:00:00Z',
  score: 8,
  totalGroups: 12,
  groups: [
    { group: 'A', correct: true,  predictedWinner: 'Germany', actualWinner: 'Germany',
      predictedRunnerUp: 'Mexico',    actualRunnerUp: 'Mexico' },
    { group: 'B', correct: false, predictedWinner: 'Brazil',  actualWinner: 'France',
      predictedRunnerUp: 'Argentina', actualRunnerUp: 'England' },
  ],
}

export const MOCK_NEWS = {
  date: '2026-06-14',
  snippets: ['Müller back in full training', 'Germany prep warm-up win', 'Squad morale high ahead of opener'],
}

export const MOCK_USAGE = {
  asOf: '2026-06-03T10:00:00Z',
  providers: [
    { name: 'football-data', callCount: 8,  limit: 10,   window: 'minute' },
    { name: 'anthropic',     callCount: 2,  inputTokens: 20000, outputTokens: 1500, limit: null, window: 'day' },
    { name: 'SerpApi',       callCount: 96, limit: 2500, window: 'month', percentUsed: 3.84 },
  ],
}
