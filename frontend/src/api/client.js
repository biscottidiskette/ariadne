/**
 * client.js — Axios API client for Ariadne frontend.
 *
 * All backend calls go through this file.
 * Base URL is empty — Vite proxy forwards /api to FastAPI on :8000.
 *
 * Usage in components:
 *   import api from '../api/client'
 *   const engagements = await api.get('/api/engagements')
 */

import axios from 'axios'

const api = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

// Response interceptor — log errors in development
api.interceptors.response.use(
  response => response,
  error => {
    console.error('[api]', error.response?.status, error.response?.data)
    return Promise.reject(error)
  }
)

export default api