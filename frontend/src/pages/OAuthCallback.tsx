import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App as AntApp, Spin, Typography } from 'antd'

const { Text } = Typography

export default function OAuthCallback() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { message } = AntApp.useApp?.() || { message: { success: console.log, error: console.error } as any }

  useEffect(() => {
    const err = sp.get('error')
    const accessToken = sp.get('access_token')
    const refreshToken = sp.get('refresh_token')
    if (err) {
      const msg = decodeURIComponent(err)
      console.error('OAuth callback error:', msg)
      try { (message as any).error(msg) } catch {}
      setTimeout(() => nav('/', { replace: true }), 3000)
      return
    }
    if (accessToken) {
      localStorage.setItem('figma_access_token', accessToken)
      if (refreshToken) localStorage.setItem('figma_refresh_token', refreshToken)
      try { message.success('Conectado con Figma') } catch {}
      nav('/', { replace: true })
    } else {
      console.error('OAuth callback: missing access_token in query')
      try { message.error('No se encontró access_token en el callback') } catch {}
      nav('/', { replace: true })
    }
  }, [sp, nav])

  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
      <div style={{ textAlign: 'center' }}>
        <Spin size="large" />
        <div style={{ marginTop: 12 }}>
          <Text type="secondary">Procesando autenticación con Figma…</Text>
        </div>
      </div>
    </div>
  )
}
