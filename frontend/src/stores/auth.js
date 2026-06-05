import { defineStore } from 'pinia'
import { authAPI } from '../api/index.js'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    role: localStorage.getItem('role') || null,
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    isAdmin:    (s) => s.role === 'admin',
    isOperator: (s) => s.role === 'admin' || s.role === 'operator',
    isReadonly: (s) => s.role === 'readonly' || s.role === 'viewer',
    canWrite:   (s) => s.role === 'admin' || s.role === 'operator',
  },
  actions: {
    hasRole(...roles) {
      if (!this.role) return false
      const r = this.role === 'viewer' ? 'readonly' : this.role
      return roles.includes(r)
    },
    async login(username, password) {
      const { data } = await authAPI.login(username, password)
      this.token = data.access_token
      this.role = data.role
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('role', data.role)
      // Fresh session → resurrect every previously-dismissed banner.
      localStorage.removeItem('esteps:dismissed-alerts')
    },
    logout() {
      this.token = null
      this.role = null
      localStorage.removeItem('token')
      localStorage.removeItem('role')
      localStorage.removeItem('esteps:dismissed-alerts')
    },
  },
})
