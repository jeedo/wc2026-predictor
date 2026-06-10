import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import TeamNewsModal from '../components/TeamNewsModal'

const NEWS_DATA = {
  teamName: 'Germany',
  date: '2026-06-09',
  snippets: ['Müller back in squad', 'Germany train in Berlin'],
}

afterEach(() => vi.restoreAllMocks())

test('shows team name in heading', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  expect(screen.getByText(/Germany/)).toBeInTheDocument()
})

test('shows loading state initially', () => {
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('renders snippets after load', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => {
    expect(screen.getByText('Müller back in squad')).toBeInTheDocument()
    expect(screen.getByText('Germany train in Berlin')).toBeInTheDocument()
  })
})

test('shows no-news message when snippets empty', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ teamName: 'Germany', snippets: [], date: null }),
  }))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByText(/no recent news/i)).toBeInTheDocument())
})

test('shows error message on fetch failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByText(/could not load/i)).toBeInTheDocument())
})

test('calls onClose when close button clicked', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: /close/i }))
  expect(onClose).toHaveBeenCalledOnce()
})

test('calls onClose when backdrop clicked', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.click(screen.getByRole('dialog'))
  expect(onClose).toHaveBeenCalledOnce()
})

test('calls onClose when Escape key pressed', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(onClose).toHaveBeenCalledOnce()
})

test('does not close when clicking inside modal box', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(NEWS_DATA),
  }))
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  await waitFor(() => screen.getByText('Müller back in squad'))
  fireEvent.click(screen.getByText('Müller back in squad'))
  expect(onClose).not.toHaveBeenCalled()
})
