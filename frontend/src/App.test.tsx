import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const CITATION = 'a'.repeat(24)

function jsonResponse(payload: unknown, status = 200, requestId?: string) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...(requestId ? { 'X-Request-ID': requestId } : {}),
    },
  })
}

function answerResponse(answer = `Cadre AI provides strategy support [chunk:${CITATION}]`) {
  return jsonResponse({
    answer,
    abstained: false,
    request_id: 'request-1',
    sources: [
      {
        source_id: 'services',
        title: 'Cadre AI Services',
        url: 'https://cadreai.com/services',
        locations: ['AI Strategy'],
      },
    ],
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

describe('ChatPage', () => {
  it('renders an enabled accessible session-only chat', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'How can we help?' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /cadre ai support assistant/i })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Conversation' })).toBeTruthy()
    expect((screen.getByRole('textbox', { name: 'Message Cadre AI' }) as HTMLTextAreaElement).disabled).toBe(false)
    expect((screen.getByRole('button', { name: 'Send message' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/answers are limited to approved sources/i)).toBeTruthy()
  })

  it('submits a message, announces loading, and renders trusted sources', async () => {
    let resolveRequest: ((response: Response) => void) | undefined
    const pending = new Promise<Response>((resolve) => {
      resolveRequest = resolve
    })
    const fetchMock = vi.fn().mockReturnValue(pending)
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message Cadre AI' }), {
      target: { value: 'What services are available?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(screen.getByText('Checking approved sources')).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Conversation' }).getAttribute('aria-busy')).toBe('true')
    resolveRequest?.(answerResponse())

    expect(await screen.findByText('Cadre AI provides strategy support')).toBeTruthy()
    const source = screen.getByRole('link', { name: /Cadre AI Services/i }) as HTMLAnchorElement
    expect(source.href).toBe('https://cadreai.com/services')
    expect(source.rel).toContain('noreferrer')
    expect(screen.queryByText(new RegExp(CITATION))).toBeNull()
    const request = JSON.parse(String(fetchMock.mock.calls[0][1]?.body)) as {
      message: string
      history: unknown[]
    }
    expect(request).toEqual({ message: 'What services are available?', history: [] })
  })

  it('sends bounded conversation history on a follow-up', async () => {
    const fetchMock = vi.fn().mockResolvedValue(answerResponse())
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const textbox = screen.getByRole('textbox', { name: 'Message Cadre AI' })

    fireEvent.change(textbox, { target: { value: 'What services are available?' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }))
    await screen.findByText('Cadre AI provides strategy support')
    fireEvent.change(textbox, { target: { value: 'How do I get started?' } })
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: false })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const request = JSON.parse(String(fetchMock.mock.calls[1][1]?.body)) as {
      message: string
      history: Array<{ role: string; content: string }>
    }
    expect(request.message).toBe('How do I get started?')
    expect(request.history).toEqual([
      { role: 'user', content: 'What services are available?' },
      { role: 'assistant', content: `Cadre AI provides strategy support [chunk:${CITATION}]` },
    ])
  })

  it('renders an explicit abstention without source cards', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          answer: "I don't have enough verified Cadre AI information to answer that question.",
          sources: [],
          abstained: true,
          request_id: 'request-2',
        }),
      ),
    )
    render(<App />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message Cadre AI' }), {
      target: { value: 'What is the weather?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText(/I don't have enough verified/i)).toBeTruthy()
    expect(screen.queryByRole('region', { name: /verified source/i })).toBeNull()
  })

  it('focuses a safe error, retries without duplicating the user message, and resets', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: 'provider_unavailable',
              message: 'Answer service is unavailable.',
              request_id: 'failed-request',
            },
          },
          503,
          'failed-request',
        ),
      )
      .mockResolvedValueOnce(answerResponse())
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message Cadre AI' }), {
      target: { value: 'Tell me about services' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Answer service is unavailable.')
    expect(alert.textContent).toContain('failed-request')
    expect(document.activeElement).toBe(alert)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await screen.findByText('Cadre AI provides strategy support')
    expect(screen.getAllByText('Tell me about services')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByText('Tell me about services')).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('rejects malformed success responses before rendering unsafe sources', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          answer: 'Unsafe response',
          sources: [
            {
              source_id: 'unsafe',
              title: 'Unsafe source',
              url: 'javascript:alert(1)',
              locations: [],
            },
          ],
          abstained: false,
          request_id: 'malformed-response',
        }),
      ),
    )
    render(<App />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message Cadre AI' }), {
      target: { value: 'Question' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('invalid response')
    expect(screen.queryByRole('link', { name: /Unsafe source/i })).toBeNull()
  })
})
