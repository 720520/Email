import axios from 'axios'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  withCredentials: true,
})

type UnauthorizedHandler = () => void | Promise<void>
let unauthorizedHandler: UnauthorizedHandler | undefined
let handlingUnauthorized = false

export function setUnauthorizedHandler(handler: UnauthorizedHandler) {
  unauthorizedHandler = handler
}

http.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const requestUrl = axios.isAxiosError(error) ? error.config?.url : undefined
    const isAuthenticationProbe = requestUrl === '/auth/login' || requestUrl === '/auth/me'
    if (
      axios.isAxiosError(error)
      && error.response?.status === 401
      && !isAuthenticationProbe
      && unauthorizedHandler
      && !handlingUnauthorized
    ) {
      handlingUnauthorized = true
      try {
        await unauthorizedHandler()
      } finally {
        handlingUnauthorized = false
      }
    }
    return Promise.reject(error)
  },
)

export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.error?.message ?? error.message ?? '请求失败'
  }
  return error instanceof Error ? error.message : '请求失败'
}
