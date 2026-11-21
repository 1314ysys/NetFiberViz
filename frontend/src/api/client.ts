import axios from 'axios'

export const api = axios.create({ baseURL: '/fiber/api/v1' })

api.interceptors.request.use(cfg => {
  const t = localStorage.getItem('token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) location.hash = '#/login'
    return Promise.reject(err)
  }
)
