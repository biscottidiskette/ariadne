/**
 * EngagementWorkspace.jsx — Main investigation view.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────┐
 *   │  Top bar: ← back | name | status | actions      │
 *   ├─────────────────────────────────────────────────┤
 *   │  Tab bar: Chat | Findings | Notes | IoCs        │
 *   ├───────────────────────────────┬─────────────────┤
 *   │                               │  Suggestions    │
 *   │  Active tab content           │  Sidebar        │
 *   │                               │  (persistent)   │
 *   └───────────────────────────────┴─────────────────┘
 *
 * The sidebar is always visible regardless of active tab.
 * It shows the LLM suggestion list and lets analysts update status.
 */

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'

// ---------------------------------------------------------------------------
// Status config (same as EngagementList)
// ---------------------------------------------------------------------------
const STATUS_CONFIG = {
  active:    { color: 'var(--status-active)',    label: 'ACTIVE' },
  contained: { color: 'var(--status-contained)', label: 'CONTAINED' },
  closed:    { color: 'var(--status-closed)',     label: 'CLOSED' },
  archived:  { color: 'var(--status-archived)',   label: 'ARCHIVED' },
}

const SUGGESTION_STATUS_COLORS = {
  pending:     'var(--text-muted)',
  in_progress: 'var(--accent-blue)',
  tried:       'var(--accent-orange)',
  worked:      'var(--accent-green)',
  failed:      'var(--accent-red)',
  dismissed:   'var(--text-muted)',
}

// ---------------------------------------------------------------------------
// ChatTab — streaming chat interface
// ---------------------------------------------------------------------------
function ChatTab({ engagementId }) {
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const messagesEndRef = useRef(null)
  const queryClient = useQueryClient()

  const { data: messages = [] } = useQuery({
    queryKey: ['messages', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}/messages`)).data,
  })

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  async function handleSend() {
    if (!input.trim() || streaming) return
    const message = input.trim()
    setInput('')
    setStreaming(true)
    setStreamingContent('')

    try {
      const response = await fetch(`/api/engagements/${engagementId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engagement_id: engagementId, content: message }),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assembled = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const chunk = line.slice(6).replace(/\\n/g, '\n')
            assembled += chunk
            setStreamingContent(assembled)
          }
          if (line.startsWith('event: done')) {
            // Stream complete — refetch messages and suggestions
            queryClient.invalidateQueries(['messages', engagementId])
            queryClient.invalidateQueries(['suggestions', engagementId])
          }
        }
      }
    } catch (err) {
      console.error('[chat] Stream error:', err)
    } finally {
      setStreaming(false)
      setStreamingContent('')
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const clearMutation = useMutation({
    mutationFn: async () => { await api.delete(`/api/engagements/${engagementId}/messages`) },
    onSuccess: () => queryClient.invalidateQueries(['messages', engagementId]),
  })

  // Filter out system messages for display
  const displayMessages = messages.filter(m => m.role !== 'system')

  function renderContent(content) {
    // Simple rendering — highlight [SUGGEST] markers
    return content.split('\n').map((line, i) => {
      if (line.startsWith('[SUGGEST]')) {
        return (
          <div key={i} style={{
            color: 'var(--accent-cyan)',
            background: 'rgba(57, 211, 83, 0.06)',
            borderLeft: '2px solid var(--accent-cyan)',
            padding: '4px 8px',
            margin: '4px 0',
            fontSize: '12px',
          }}>
            {line}
          </div>
        )
      }
      return <div key={i}>{line || <br />}</div>
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Message thread */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {displayMessages.length === 0 && !streaming && (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0', fontSize: '13px' }}>
            <div style={{ fontSize: '28px', marginBottom: '12px' }}>🧵</div>
            Start by describing what you know about the incident, or upload an artifact using the buttons below.
          </div>
        )}

        {displayMessages.map(msg => (
          <div key={msg.id} style={{
            display: 'flex',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            gap: '10px',
          }}>
            <div style={{
              maxWidth: '75%',
              padding: '10px 14px',
              borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
              background: msg.role === 'user' ? 'var(--accent-blue)' : 'var(--bg-elevated)',
              color: msg.role === 'user' ? '#000' : 'var(--text-primary)',
              fontSize: '13px',
              lineHeight: '1.6',
            }}>
              {msg.role === 'assistant' ? renderContent(msg.content) : msg.content}
              <div style={{
                fontSize: '10px',
                color: msg.role === 'user' ? 'rgba(0,0,0,0.5)' : 'var(--text-muted)',
                marginTop: '6px',
              }}>
                {new Date(msg.created_at).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}

        {/* Streaming message in progress */}
        {streaming && (
          <div style={{ display: 'flex', gap: '10px' }}>
            <div style={{
              maxWidth: '75%', padding: '10px 14px',
              borderRadius: '12px 12px 12px 2px',
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              fontSize: '13px', lineHeight: '1.6',
            }}>
              {streamingContent
                ? renderContent(streamingContent)
                : <span style={{ color: 'var(--text-muted)' }}>Thinking...</span>
              }
              <span style={{ color: 'var(--accent-blue)', animation: 'pulse 1s infinite' }}>▊</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={{
        borderTop: '1px solid var(--border)',
        padding: '12px 16px',
        background: 'var(--bg-secondary)',
      }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask something... (Enter to send, Shift+Enter for newline)"
            disabled={streaming}
            style={{
              flex: 1, padding: '10px 12px', minHeight: '44px', maxHeight: '120px',
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              borderRadius: '6px', color: 'var(--text-primary)',
              fontFamily: 'inherit', fontSize: '13px', resize: 'none', outline: 'none',
              opacity: streaming ? 0.6 : 1,
            }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <button onClick={handleSend} disabled={streaming || !input.trim()} style={{
              padding: '10px 16px', background: 'var(--accent-blue)', border: 'none',
              borderRadius: '6px', color: '#000', cursor: streaming ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', fontSize: '12px', fontWeight: '600',
              opacity: streaming || !input.trim() ? 0.6 : 1,
            }}>
              {streaming ? '...' : 'Send'}
            </button>
            <button onClick={() => {
              if (window.confirm('Clear all chat messages? Artifacts and IoCs are preserved.')) {
                clearMutation.mutate()
              }
            }} style={{
              padding: '6px 10px', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: '6px',
              color: 'var(--text-muted)', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: '10px',
            }}>
              Clear
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FindingsTab — displays ingested artifacts
// ---------------------------------------------------------------------------
function FindingsTab({ engagementId }) {
  const [pasteContent, setPasteContent] = useState('')
  const [pasteType, setPasteType] = useState('paste')
  const [showPaste, setShowPaste] = useState(false)
  const queryClient = useQueryClient()

  const { data: artifacts = [] } = useQuery({
    queryKey: ['artifacts', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}/artifacts`)).data,
  })

  const pasteMutation = useMutation({
    mutationFn: async ({ content, artifactType }) => {
      const form = new FormData()
      form.append('content', content)
      form.append('artifact_type', artifactType)
      return (await api.post(`/api/engagements/${engagementId}/artifacts/paste`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['artifacts', engagementId])
      setPasteContent('')
      setShowPaste(false)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: async (file) => {
      const form = new FormData()
      form.append('file', file)
      form.append('artifact_type', 'other')
      return (await api.post(`/api/engagements/${engagementId}/artifacts/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })).data
    },
    onSuccess: () => queryClient.invalidateQueries(['artifacts', engagementId]),
  })

  const ARTIFACT_TYPE_COLORS = {
    evtx: 'var(--accent-blue)',
    chainsaw: 'var(--accent-purple)',
    edr: 'var(--accent-orange)',
    siem: 'var(--accent-cyan)',
    ioc: 'var(--accent-red)',
    paste: 'var(--text-secondary)',
    other: 'var(--text-muted)',
  }

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      {/* Action bar */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button onClick={() => setShowPaste(!showPaste)} style={{
          padding: '7px 14px', background: 'var(--bg-elevated)',
          border: '1px solid var(--border)', borderRadius: '6px',
          color: 'var(--text-primary)', cursor: 'pointer',
          fontFamily: 'inherit', fontSize: '12px',
        }}>
          📋 Paste Artifact
        </button>
        <label style={{
          padding: '7px 14px', background: 'var(--bg-elevated)',
          border: '1px solid var(--border)', borderRadius: '6px',
          color: 'var(--text-primary)', cursor: 'pointer', fontSize: '12px',
        }}>
          📁 Upload File
          <input type="file" style={{ display: 'none' }}
            onChange={e => e.target.files[0] && uploadMutation.mutate(e.target.files[0])} />
        </label>
      </div>

      {/* Paste form */}
      {showPaste && (
        <div style={{
          marginBottom: '20px', padding: '16px',
          background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderRadius: '8px',
        }}>
          <div style={{ marginBottom: '10px', display: 'flex', gap: '10px', alignItems: 'center' }}>
            <select value={pasteType} onChange={e => setPasteType(e.target.value)} style={{
              padding: '6px 10px', background: 'var(--bg-primary)',
              border: '1px solid var(--border)', borderRadius: '4px',
              color: 'var(--text-primary)', fontFamily: 'inherit', fontSize: '12px',
            }}>
              <option value="paste">Generic Paste</option>
              <option value="edr">EDR Alert</option>
              <option value="siem">SIEM Query Result</option>
              <option value="chainsaw">Chainsaw Output</option>
              <option value="ioc">IoC List</option>
              <option value="memory">Memory Strings</option>
            </select>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Select artifact type before pasting
            </span>
          </div>
          <textarea
            value={pasteContent}
            onChange={e => setPasteContent(e.target.value)}
            placeholder="Paste artifact content here..."
            style={{
              width: '100%', height: '140px', padding: '10px',
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              borderRadius: '4px', color: 'var(--text-primary)',
              fontFamily: 'inherit', fontSize: '12px', resize: 'vertical', outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px', justifyContent: 'flex-end' }}>
            <button onClick={() => { setShowPaste(false); setPasteContent('') }} style={{
              padding: '6px 14px', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: '4px',
              color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: '12px',
            }}>Cancel</button>
            <button
              onClick={() => pasteMutation.mutate({ content: pasteContent, artifactType: pasteType })}
              disabled={!pasteContent.trim() || pasteMutation.isPending}
              style={{
                padding: '6px 14px', background: 'var(--accent-blue)', border: 'none',
                borderRadius: '4px', color: '#000', cursor: 'pointer',
                fontFamily: 'inherit', fontSize: '12px', fontWeight: '600',
              }}>
              {pasteMutation.isPending ? 'Submitting...' : 'Submit Artifact'}
            </button>
          </div>
        </div>
      )}

      {/* Artifacts list */}
      {artifacts.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0' }}>
          No artifacts ingested yet. Paste content or upload a file.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {artifacts.map(a => (
            <div key={a.id} style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border)',
              borderRadius: '8px', padding: '14px 16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                <span style={{
                  fontSize: '10px', fontWeight: '600', letterSpacing: '0.08em',
                  color: ARTIFACT_TYPE_COLORS[a.artifact_type] || 'var(--text-muted)',
                  border: `1px solid ${ARTIFACT_TYPE_COLORS[a.artifact_type] || 'var(--text-muted)'}`,
                  padding: '2px 6px', borderRadius: '3px',
                }}>
                  {a.artifact_type.toUpperCase()}
                </span>
                <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
                  {a.filename || 'Pasted content'}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', marginLeft: 'auto' }}>
                  {new Date(a.created_at).toLocaleString()}
                </span>
              </div>
              {a.summary && (
                <div style={{ color: 'var(--text-secondary)', fontSize: '12px', marginBottom: '8px' }}>
                  {a.summary}
                </div>
              )}
              {a.raw_content && (
                <pre style={{
                  background: 'var(--bg-primary)', padding: '10px', borderRadius: '4px',
                  fontSize: '11px', color: 'var(--text-muted)', overflow: 'auto',
                  maxHeight: '120px', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                }}>
                  {a.raw_content.slice(0, 500)}{a.raw_content.length > 500 ? '...' : ''}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// NotesTab — append-only analyst notes
// ---------------------------------------------------------------------------
function NotesTab({ engagementId }) {
  const [noteContent, setNoteContent] = useState('')
  const queryClient = useQueryClient()

  const { data: notes = [] } = useQuery({
    queryKey: ['notes', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}/notes`)).data,
  })

  const createNote = useMutation({
    mutationFn: async (content) => (await api.post(`/api/engagements/${engagementId}/notes`, {
      engagement_id: engagementId, content, hits_context: true,
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries(['notes', engagementId])
      setNoteContent('')
    },
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {notes.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0' }}>
            No notes yet. Notes feed directly into the LLM context.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {notes.map(note => (
              <div key={note.id} style={{
                background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                borderRadius: '6px', padding: '12px 14px',
              }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                  {new Date(note.created_at).toLocaleString()}
                  {note.hits_context === 1 && (
                    <span style={{ color: 'var(--accent-cyan)', marginLeft: '8px' }}>● LLM CONTEXT</span>
                  )}
                </div>
                <div style={{ color: 'var(--text-primary)', fontSize: '13px', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                  {note.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Note input */}
      <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px', background: 'var(--bg-secondary)' }}>
        <textarea
          value={noteContent}
          onChange={e => setNoteContent(e.target.value)}
          placeholder="Add a timestamped note... (analyst observations, phone call summaries, out-of-band intel)"
          style={{
            width: '100%', height: '80px', padding: '10px',
            background: 'var(--bg-primary)', border: '1px solid var(--border)',
            borderRadius: '6px', color: 'var(--text-primary)',
            fontFamily: 'inherit', fontSize: '13px', resize: 'none', outline: 'none',
            marginBottom: '8px',
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={() => createNote.mutate(noteContent)}
            disabled={!noteContent.trim() || createNote.isPending}
            style={{
              padding: '7px 16px', background: 'var(--accent-blue)', border: 'none',
              borderRadius: '6px', color: '#000', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: '12px', fontWeight: '600',
            }}>
            Append Note
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// IoCsTab — IoC list and manual add
// ---------------------------------------------------------------------------
function IoCsTab({ engagementId }) {
  const [form, setForm] = useState({ ioc_type: 'ip', value: '', context: '' })
  const queryClient = useQueryClient()

  const { data: iocs = [] } = useQuery({
    queryKey: ['iocs', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}/iocs`)).data,
  })

  const createIoc = useMutation({
    mutationFn: async (data) => (await api.post(`/api/engagements/${engagementId}/iocs`, {
      engagement_id: engagementId, ...data,
    })).data,
    onSuccess: () => {
      queryClient.invalidateQueries(['iocs', engagementId])
      setForm({ ioc_type: 'ip', value: '', context: '' })
    },
  })

  const IOC_TYPE_COLORS = {
    ip: 'var(--accent-red)',
    domain: 'var(--accent-orange)',
    hash_md5: 'var(--accent-purple)',
    hash_sha1: 'var(--accent-purple)',
    hash_sha256: 'var(--accent-purple)',
    file_path: 'var(--accent-blue)',
    registry_key: 'var(--accent-cyan)',
    email: 'var(--accent-green)',
    url: 'var(--accent-orange)',
    mutex: 'var(--text-secondary)',
    other: 'var(--text-muted)',
  }

  const inputStyle = {
    padding: '7px 10px', background: 'var(--bg-primary)',
    border: '1px solid var(--border)', borderRadius: '4px',
    color: 'var(--text-primary)', fontFamily: 'inherit', fontSize: '12px', outline: 'none',
  }

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      {/* Manual add form */}
      <div style={{
        marginBottom: '20px', padding: '14px 16px',
        background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: '8px',
      }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '10px', letterSpacing: '0.05em' }}>
          MANUALLY ADD IoC
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <select value={form.ioc_type} onChange={e => setForm({ ...form, ioc_type: e.target.value })}
            style={{ ...inputStyle, cursor: 'pointer' }}>
            <option value="ip">IP Address</option>
            <option value="domain">Domain</option>
            <option value="hash_md5">MD5 Hash</option>
            <option value="hash_sha1">SHA1 Hash</option>
            <option value="hash_sha256">SHA256 Hash</option>
            <option value="file_path">File Path</option>
            <option value="registry_key">Registry Key</option>
            <option value="url">URL</option>
            <option value="email">Email</option>
            <option value="mutex">Mutex</option>
            <option value="other">Other</option>
          </select>
          <input value={form.value} onChange={e => setForm({ ...form, value: e.target.value })}
            placeholder="IoC value..." style={{ ...inputStyle, flex: 1, minWidth: '200px' }} />
          <input value={form.context} onChange={e => setForm({ ...form, context: e.target.value })}
            placeholder="Context (optional)..." style={{ ...inputStyle, flex: 1, minWidth: '200px' }} />
          <button
            onClick={() => createIoc.mutate(form)}
            disabled={!form.value.trim() || createIoc.isPending}
            style={{
              padding: '7px 14px', background: 'var(--accent-blue)', border: 'none',
              borderRadius: '4px', color: '#000', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: '12px', fontWeight: '600',
            }}>Add</button>
        </div>
      </div>

      {/* IoC list */}
      {iocs.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0' }}>
          No IoCs yet. Add manually above or ingest artifacts to auto-extract.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {iocs.map(ioc => (
            <div key={ioc.id} style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border)',
              borderRadius: '6px', padding: '10px 14px',
              display: 'flex', alignItems: 'center', gap: '12px',
            }}>
              <span style={{
                fontSize: '10px', fontWeight: '600',
                color: IOC_TYPE_COLORS[ioc.ioc_type] || 'var(--text-muted)',
                border: `1px solid ${IOC_TYPE_COLORS[ioc.ioc_type] || 'var(--text-muted)'}`,
                padding: '2px 6px', borderRadius: '3px', whiteSpace: 'nowrap',
              }}>
                {ioc.ioc_type.toUpperCase()}
              </span>
              <code style={{ color: 'var(--text-primary)', fontSize: '12px', flex: 1 }}>
                {ioc.value}
              </code>
              {ioc.context && (
                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                  {ioc.context}
                </span>
              )}
              <span style={{ color: 'var(--text-muted)', fontSize: '10px', whiteSpace: 'nowrap' }}>
                {new Date(ioc.created_at).toLocaleDateString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SuggestionsSidebar — persistent right panel
// ---------------------------------------------------------------------------
function SuggestionsSidebar({ engagementId }) {
  const queryClient = useQueryClient()

  const { data: suggestions = [] } = useQuery({
    queryKey: ['suggestions', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}/suggestions`)).data,
    refetchInterval: 5000, // Poll every 5s to pick up new suggestions from chat
  })

  const updateStatus = useMutation({
    mutationFn: async ({ id, status }) => (await api.patch(
      `/api/engagements/${engagementId}/suggestions/${id}`,
      { status }
    )).data,
    onSuccess: () => queryClient.invalidateQueries(['suggestions', engagementId]),
  })

  const statusOptions = ['pending', 'in_progress', 'tried', 'worked', 'failed', 'dismissed']

  const activeSuggestions = suggestions.filter(s => s.status !== 'dismissed')

  return (
    <div style={{
      width: '280px', minWidth: '280px',
      borderLeft: '1px solid var(--border)',
      background: 'var(--bg-secondary)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflow: 'hidden',
    }}>
      {/* Sidebar header */}
      <div style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: '11px', fontWeight: '600', letterSpacing: '0.08em', color: 'var(--text-secondary)' }}>
            NEXT QUERIES
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
            {activeSuggestions.length} outstanding
          </div>
        </div>
        <div style={{
          width: '8px', height: '8px', borderRadius: '50%',
          background: activeSuggestions.length > 0 ? 'var(--accent-orange)' : 'var(--text-muted)',
        }} />
      </div>

      {/* Suggestion list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
        {activeSuggestions.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '11px', textAlign: 'center', padding: '30px 10px' }}>
            Suggestions from the LLM will appear here as you chat.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {activeSuggestions.map(s => (
              <div key={s.id} style={{
                background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)',
                borderRadius: '6px', padding: '10px',
                borderLeft: `3px solid ${SUGGESTION_STATUS_COLORS[s.status] || 'var(--text-muted)'}`,
              }}>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: '1.5', marginBottom: '8px' }}>
                  {s.canonical_text}
                </div>
                <select
                  value={s.status}
                  onChange={e => updateStatus.mutate({ id: s.id, status: e.target.value })}
                  style={{
                    width: '100%', padding: '4px 6px',
                    background: 'var(--bg-primary)', border: '1px solid var(--border)',
                    borderRadius: '3px', color: SUGGESTION_STATUS_COLORS[s.status] || 'var(--text-muted)',
                    fontFamily: 'inherit', fontSize: '10px', cursor: 'pointer',
                  }}
                >
                  {statusOptions.map(opt => (
                    <option key={opt} value={opt}>
                      {opt.replace('_', ' ').toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EngagementWorkspace — main layout
// ---------------------------------------------------------------------------
export default function EngagementWorkspace() {
  const { id } = useParams()
  const navigate = useNavigate()
  const engagementId = parseInt(id)
  const [activeTab, setActiveTab] = useState('chat')

  const { data: engagement, isLoading } = useQuery({
    queryKey: ['engagement', engagementId],
    queryFn: async () => (await api.get(`/api/engagements/${engagementId}`)).data,
  })

  const tabs = [
    { id: 'chat',     label: '💬 Chat' },
    { id: 'findings', label: '🔍 Findings' },
    { id: 'notes',    label: '📝 Notes' },
    { id: 'iocs',     label: '🎯 IoCs' },
  ]

  if (isLoading) return (
    <div style={{ color: 'var(--text-muted)', padding: '40px', textAlign: 'center' }}>
      Loading engagement...
    </div>
  )

  if (!engagement) return (
    <div style={{ color: 'var(--accent-red)', padding: '40px', textAlign: 'center' }}>
      Engagement not found. <span style={{ color: 'var(--accent-blue)', cursor: 'pointer' }}
        onClick={() => navigate('/')}>Go back</span>
    </div>
  )

  const statusConfig = STATUS_CONFIG[engagement.status] || STATUS_CONFIG.active

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>

      {/* Top bar */}
      <div style={{
        background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)',
        padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '16px',
        flexShrink: 0,
      }}>
        <button onClick={() => navigate('/')} style={{
          background: 'transparent', border: 'none',
          color: 'var(--text-muted)', cursor: 'pointer', fontSize: '18px', padding: '0 4px',
        }}>←</button>

        <span style={{ fontSize: '16px' }}>🧵</span>

        <div style={{ flex: 1 }}>
          <div style={{ color: 'var(--text-primary)', fontSize: '15px', fontWeight: '500' }}>
            {engagement.name}
          </div>
          {engagement.description && (
            <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
              {engagement.description}
            </div>
          )}
        </div>

        <span style={{
          fontSize: '11px', fontWeight: '600', letterSpacing: '0.05em',
          color: statusConfig.color, border: `1px solid ${statusConfig.color}`,
          padding: '3px 10px', borderRadius: '3px',
          background: `${statusConfig.color}18`,
        }}>
          {statusConfig.label}
        </span>
      </div>

      {/* Tab bar */}
      <div style={{
        background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)',
        padding: '0 20px', display: 'flex', gap: '0', flexShrink: 0,
      }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
            padding: '10px 18px', background: 'transparent', border: 'none',
            borderBottom: activeTab === tab.id ? '2px solid var(--accent-blue)' : '2px solid transparent',
            color: activeTab === tab.id ? 'var(--accent-blue)' : 'var(--text-muted)',
            cursor: 'pointer', fontFamily: 'inherit', fontSize: '13px',
            transition: 'color 0.15s',
          }}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main content + sidebar */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Tab content */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'chat'     && <ChatTab engagementId={engagementId} />}
          {activeTab === 'findings' && <FindingsTab engagementId={engagementId} />}
          {activeTab === 'notes'    && <NotesTab engagementId={engagementId} />}
          {activeTab === 'iocs'     && <IoCsTab engagementId={engagementId} />}
        </div>

        {/* Persistent suggestions sidebar */}
        <SuggestionsSidebar engagementId={engagementId} />
      </div>
    </div>
  )
}
