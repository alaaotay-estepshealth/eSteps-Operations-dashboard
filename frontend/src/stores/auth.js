import { defineStore } from 'pinia'
import { authAPI } from '../api/index.js'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    role: localStorage.getItem('role') || null,
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    isAdmin: (s) => s.role === 'admin',
  },
  actions: {
    async login(username, password) {
      const { data } = await authAPI.login(username, password)
      this.token = data.access_token
      this.role = data.role
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('role', data.role)
    },
    logout() {
      this.token = null
      this.role = null
      localStorage.removeItem('token')
      localStorage.removeItem('role')
    },
  },
})
