/**
 * EngagementList.jsx — Landing page for Ariadne.
 *
 * Shows all engagements with their status, and allows creating,
 * editing, and deleting cases.
 *
 * Data flow:
 *   useQuery fetches engagements from GET /api/engagements
 *   useMutation handles create, update, delete
 *   React Query automatically refetches after mutations
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'

// ---------------------------------------------------------------------------
// Status configuration
// Drives badge colors and available transitions
// ---------------------------------------------------------------------------
const STATUS_CONFIG = {
  active:    { color: 'var(--status-active)',    label: 'ACTIVE' },
  contained: { color: 'var(--status-contained)', label: 'CONTAINED' },
  closed:    { color: 'var(--status-closed)',     label: 'CLOSED' },
  archived:  { color: 'var(--status-archived)',   label: 'ARCHIVED' },
}

// ---------------------------------------------------------------------------
// StatusBadge component
// Small colored indicator showing engagement lifecycle state
// ---------------------------------------------------------------------------
function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.active
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: '3px',
      fontSize: '11px',
      fontWeight: '600',
      letterSpacing: '0.05em',
      color: config.color,
      border: `1px solid ${config.color}`,
      backgroundColor: `${config.color}18`,
    }}>
      {config.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// NewEngagementModal component
// Form for creating a new engagement
// ---------------------------------------------------------------------------
function NewEngagementModal({ onClose, onSubmit, isLoading }) {
  const [form, setForm] = useState({
    name: '',
    description: '',
    status: 'active',
  })

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.name.trim()) return
    onSubmit(form)
  }

  const inputStyle = {
    width: '100%',
    padding: '8px 12px',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    color: 'var(--text-primary)',
    fontFamily: 'inherit',
    fontSize: '13px',
    outline: 'none',
  }

  const labelStyle = {
    display: 'block',
    fontSize: '12px',
    color: 'var(--text-secondary)',
    marginBottom: '6px',
    letterSpacing: '0.05em',
  }

  return (
    // Backdrop
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      {/* Modal — stop click from closing when clicking inside */}
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: '10px',
          padding: '28px',
          width: '480px',
          maxWidth: '90vw',
        }}
      >
        <h2 style={{
          color: 'var(--text-primary)',
          fontSize: '16px',
          marginBottom: '24px',
          borderBottom: '1px solid var(--border)',
          paddingBottom: '12px',
        }}>
          New Engagement
        </h2>

        <form onSubmit={handleSubmit}>
          {/* Name */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>ENGAGEMENT NAME *</label>
            <input
              style={inputStyle}
              placeholder="e.g. Ransomware — ACME Corp"
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              autoFocus
            />
          </div>

          {/* Description */}
          <div style={{ marginBottom: '16px' }}>
            <label style={labelStyle}>DESCRIPTION</label>
            <textarea
              style={{ ...inputStyle, height: '80px', resize: 'vertical' }}
              placeholder="Brief description of the incident..."
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
            />
          </div>

          {/* Status */}
          <div style={{ marginBottom: '24px' }}>
            <label style={labelStyle}>INITIAL STATUS</label>
            <select
              style={{ ...inputStyle, cursor: 'pointer' }}
              value={form.status}
              onChange={e => setForm({ ...form, status: e.target.value })}
            >
              <option value="active">Active</option>
              <option value="contained">Contained</option>
              <option value="closed">Closed</option>
            </select>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 18px',
                background: 'transparent',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: '13px',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !form.name.trim()}
              style={{
                padding: '8px 18px',
                background: 'var(--accent-blue)',
                border: 'none',
                borderRadius: '6px',
                color: '#000',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
                fontSize: '13px',
                fontWeight: '600',
                opacity: isLoading ? 0.7 : 1,
              }}
            >
              {isLoading ? 'Creating...' : 'Create Engagement'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EngagementCard component
// One row per engagement on the landing page
// ---------------------------------------------------------------------------
function EngagementCard({ engagement, onOpen, onDelete, onStatusChange }) {
  const [showStatusMenu, setShowStatusMenu] = useState(false)
  const statuses = ['active', 'contained', 'closed', 'archived']

  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-blue)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
      onClick={() => onOpen(engagement.id)}
    >
      {/* Left — name and meta */}
      <div>
        <div style={{
          color: 'var(--accent-blue)',
          fontSize: '15px',
          fontWeight: '500',
          marginBottom: '4px',
        }}>
          {engagement.name}
        </div>
        {engagement.description && (
          <div style={{
            color: 'var(--text-secondary)',
            fontSize: '12px',
            marginBottom: '6px',
            maxWidth: '600px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {engagement.description}
          </div>
        )}
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Created {new Date(engagement.created_at).toLocaleDateString()} ·
          Updated {new Date(engagement.updated_at).toLocaleDateString()}
          {engagement.lead_id && ` · ${engagement.lead_id}`}
        </div>
      </div>

      {/* Right — status + actions */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: '10px' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Status badge — click to change */}
        <div style={{ position: 'relative' }}>
          <div
            onClick={() => setShowStatusMenu(!showStatusMenu)}
            style={{ cursor: 'pointer' }}
          >
            <StatusBadge status={engagement.status} />
          </div>

          {showStatusMenu && (
            <div style={{
              position: 'absolute', right: 0, top: '28px',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              zIndex: 100,
              minWidth: '130px',
              overflow: 'hidden',
            }}>
              {statuses.map(s => (
                <div
                  key={s}
                  onClick={() => {
                    onStatusChange(engagement.id, s)
                    setShowStatusMenu(false)
                  }}
                  style={{
                    padding: '8px 14px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: engagement.status === s
                      ? 'var(--accent-blue)'
                      : 'var(--text-secondary)',
                    background: engagement.status === s
                      ? 'var(--bg-tertiary)'
                      : 'transparent',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                  onMouseLeave={e => e.currentTarget.style.background =
                    engagement.status === s ? 'var(--bg-tertiary)' : 'transparent'
                  }
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Delete button */}
        <button
          onClick={() => onDelete(engagement.id, engagement.name)}
          title="Delete engagement"
          style={{
            padding: '5px 8px',
            background: 'transparent',
            border: '1px solid transparent',
            borderRadius: '4px',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontSize: '14px',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.color = 'var(--accent-red)'
            e.currentTarget.style.borderColor = 'var(--accent-red)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.borderColor = 'transparent'
          }}
        >
          ✕
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EngagementList — main page component
// ---------------------------------------------------------------------------
export default function EngagementList() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)

  // Fetch all engagements
  const { data: engagements = [], isLoading, isError } = useQuery({
    queryKey: ['engagements'],
    queryFn: async () => {
      const res = await api.get('/api/engagements')
      return res.data
    },
  })

  // Create engagement
  const createMutation = useMutation({
    mutationFn: async (form) => {
      const res = await api.post('/api/engagements', form)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['engagements'])
      setShowModal(false)
    },
  })

  // Update status
  const statusMutation = useMutation({
    mutationFn: async ({ id, status }) => {
      const res = await api.patch(`/api/engagements/${id}`, { status })
      return res.data
    },
    onSuccess: () => queryClient.invalidateQueries(['engagements']),
  })

  // Delete engagement
  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/engagements/${id}`)
    },
    onSuccess: () => queryClient.invalidateQueries(['engagements']),
  })

  function handleDelete(id, name) {
    if (window.confirm(`Delete engagement "${name}"?\n\nThis will permanently remove all artifacts, messages, IoCs, and timeline events.`)) {
      deleteMutation.mutate(id)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-primary)',
      padding: '0',
    }}>

      {/* Top bar */}
      <div style={{
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        padding: '14px 32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Logo mark */}
          <span style={{ fontSize: '20px' }}>🧵</span>
          <div>
            <div style={{
              color: 'var(--accent-blue)',
              fontSize: '18px',
              fontWeight: '700',
              letterSpacing: '-0.02em',
            }}>
              Ariadne
            </div>
            <div style={{
              color: 'var(--text-muted)',
              fontSize: '11px',
              letterSpacing: '0.05em',
            }}>
              IR DECISION ENGINE
            </div>
          </div>
        </div>

        <button
          onClick={() => setShowModal(true)}
          style={{
            padding: '8px 16px',
            background: 'var(--accent-green)',
            border: 'none',
            borderRadius: '6px',
            color: '#000',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: '13px',
            fontWeight: '600',
          }}
        >
          + New Engagement
        </button>
      </div>

      {/* Main content */}
      <div style={{ padding: '32px', maxWidth: '960px', margin: '0 auto' }}>

        {/* Page header */}
        <div style={{ marginBottom: '24px' }}>
          <h2 style={{
            color: 'var(--text-primary)',
            fontSize: '16px',
            fontWeight: '500',
            marginBottom: '4px',
          }}>
            Active Engagements
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {engagements.length} engagement{engagements.length !== 1 ? 's' : ''} · Click to open workspace
          </p>
        </div>

        {/* States */}
        {isLoading && (
          <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>
            Loading engagements...
          </div>
        )}

        {isError && (
          <div style={{
            color: 'var(--accent-red)',
            padding: '16px',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--accent-red)',
            borderRadius: '6px',
          }}>
            Failed to load engagements. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && engagements.length === 0 && (
          <div style={{
            color: 'var(--text-muted)',
            padding: '60px 0',
            textAlign: 'center',
            border: '1px dashed var(--border)',
            borderRadius: '8px',
          }}>
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>🧵</div>
            <div style={{ marginBottom: '8px' }}>No engagements yet.</div>
            <div style={{ fontSize: '12px' }}>
              Click <span style={{ color: 'var(--accent-green)' }}>+ New Engagement</span> to start your first case.
            </div>
          </div>
        )}

        {/* Engagement list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {engagements.map(eng => (
            <EngagementCard
              key={eng.id}
              engagement={eng}
              onOpen={(id) => navigate(`/engagement/${id}`)}
              onDelete={handleDelete}
              onStatusChange={(id, status) => statusMutation.mutate({ id, status })}
            />
          ))}
        </div>
      </div>

      {/* New engagement modal */}
      {showModal && (
        <NewEngagementModal
          onClose={() => setShowModal(false)}
          onSubmit={(form) => createMutation.mutate(form)}
          isLoading={createMutation.isPending}
        />
      )}
    </div>
  )
}