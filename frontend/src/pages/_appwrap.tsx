import React from 'react'
import { App as AntApp, ConfigProvider, theme } from 'antd'

export default function AppWrap({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
      }}
    >
      <AntApp>{children}</AntApp>
    </ConfigProvider>
  )
}

