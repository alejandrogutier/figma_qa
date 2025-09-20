/// <reference types="vite/client" />

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Form,
  Image,
  Input,
  InputNumber,
  Layout,
  List,
  Popconfirm,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  LinkOutlined,
  LoginOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons'

const { Header, Sider, Content, Footer } = Layout
const { Title, Text, Paragraph } = Typography

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('figma_access_token') || ''
}

function storeToken(value: string) {
  if (value) {
    localStorage.setItem('figma_access_token', value)
  } else {
    localStorage.removeItem('figma_access_token')
  }
}

type CaseEvaluation = {
  case_id: number
  evaluated: boolean
  status: string
  score: number | null
  notes: string | null
  checked: boolean
}

type CasePayload = {
  id?: string
  frame?: string
  feature?: string
  objetivo?: string
  precondiciones?: string[]
  pasos?: string[]
  datos_prueba?: Record<string, unknown>
  resultado_esperado?: string
  negativo?: string[]
  bordes?: string[]
  accesibilidad?: string[]
  prioridad?: string
  severidad?: string
  dispositivo?: string
  dependencias?: string[]
  observaciones?: string
  image_url?: string | null
  page_name: string
  frame_name: string
  node_id: string
  bundle_label?: string | null
  evaluation: CaseEvaluation
}

type CaseRow = CasePayload & {
  rowKey: string
  caseId: number
}

type AnalysisSummary = {
  analysis_id: number
  job_id: string
  file_key: string
  figma_url?: string | null
  analysis_level: string
  model: string
  images_per_unit: number
  image_scale: number
  reasoning_effort?: string | null
  max_frames?: number | null
  status: string
  total_cases: number
  created_at: string
  updated_at: string
}

type AnalysisDetail = AnalysisSummary & {
  cases: CasePayload[]
}

type JobStatus = {
  status: string
  stage?: string
  message?: string
  error?: string
  processed?: number
  frames_processing?: number
  frames_total?: number
  cases_total?: number
  download_url?: string | null
  analysis_id?: number | null
  analysis?: AnalysisDetail
}

type HistoryFileEntry = {
  file_key: string
  figma_url?: string | null
  runs: number
  last_run_at?: string | null
  last_analysis_id?: number | null
  last_model?: string | null
  analysis_level?: string | null
}

type HistoryItem = {
  key: string
  analysis: AnalysisSummary | null
  metrics: HistoryFileEntry | null
}

type EvaluationUpdate = Partial<CaseEvaluation & { notes: string | null }>

const SIDE_TABS_STYLES = `
  .sider-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: linear-gradient(180deg, #f6f8ff 0%, #ffffff 100%);
    border-right: 1px solid #e5e7f0;
  }
  .sider-config {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 20px 22px 18px;
  }
  .sider-config .ant-space,
  .sider-config .ant-form {
    width: 100%;
  }
  .sider-container .history-card {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #e5e7f0;
    box-shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
    margin: 0 16px 16px;
    display: flex;
    flex-direction: column;
  }
  .history-card .ant-card-head {
    border-bottom: none;
    padding: 16px;
  }
  .history-card .ant-card-head-title {
    font-weight: 600;
    font-size: 15px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .history-card .ant-card-body {
    padding: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .history-card .ant-card-extra button {
    border-radius: 999px !important;
    padding-inline: 14px;
  }
  .history-card .history-list .ant-list-items {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .history-card .history-list .ant-list-item {
    flex: 0 0 auto;
  }
  .history-card .history-list .ant-list-pagination {
    margin: 10px 16px 16px;
  }
  .sider-tabs.ant-tabs {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 0 16px 20px;
  }
  .sider-tabs .ant-tabs-content-holder {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .sider-tabs .ant-tabs-content {
    flex: 1;
  }
  .sider-tabs .ant-tabs-tabpane {
    height: 100%;
    overflow-y: auto;
    padding-right: 4px;
  }
  .sider-tabs .ant-tabs-nav {
    margin: auto auto 10px !important;
    padding: 10px 14px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid #dfe6fb;
    box-shadow: 0 6px 18px rgba(30, 64, 175, 0.08);
  }
  .sider-tabs .ant-tabs-nav::before {
    border-bottom: none;
  }
  .sider-tabs .ant-tabs-nav-wrap {
    justify-content: center;
  }
  .sider-tabs .ant-tabs-tab {
    margin: 0 6px !important;
    border-radius: 12px;
    padding: 10px 20px;
    transition: all 0.18s ease;
    color: #4a5568;
  }
  .sider-tabs .ant-tabs-tab:hover {
    color: #1d39c4;
    background: rgba(29, 57, 196, 0.08);
  }
  .sider-tabs .ant-tabs-tab-active {
    background: #ffffff;
    border: 1px solid #c9d6f8;
    box-shadow: 0 5px 14px rgba(28, 55, 160, 0.12);
  }
  .sider-tabs .ant-tabs-tab-btn {
    font-weight: 500;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 12px;
    letter-spacing: 0.18px;
    padding-inline: 2px;
  }
  .sider-tabs .ant-tabs-tab-active .ant-tabs-tab-btn {
    color: #1d39c4 !important;
  }
  .sider-tabs .ant-tabs-tab-btn .tab-label-icon {
    font-size: 15px;
  }
  .sider-tabs .ant-tabs-ink-bar {
    display: none;
  }
  .history-list .ant-list-item {
    align-items: flex-start;
    padding: 16px 20px;
    border-bottom: 1px solid #eef2ff;
  }
  .history-list .ant-list-item:last-child {
    border-bottom: none;
  }
  .history-list .ant-list-item-meta {
    width: 100%;
  }
  .history-list .ant-list-item-meta-title {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }
  .history-list .ant-list-item-meta-description {
    color: #6b7280;
    font-size: 13px;
  }
  .history-list .ant-list-item-action {
    margin-inline-start: 12px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .history-list .ant-tag {
    font-size: 12px;
    border-radius: 999px;
  }
  .cases-table .ant-table-pagination {
    margin: 12px 24px 18px;
    justify-content: flex-end;
  }
  .cases-table .ant-table-thead > tr > th {
    background: #f1f5ff;
    font-weight: 600;
  }
  .cases-table .ant-table-tbody > tr.cases-row-even > td {
    background: #f9fbff;
  }
  .cases-table .ant-table-tbody > tr:hover > td {
    background: #eef2ff !important;
  }
` as const

const STATUS_OPTIONS = [
  { label: 'Pendiente', value: 'pending' },
  { label: 'Aprobado', value: 'passed' },
  { label: 'Fallido', value: 'failed' },
  { label: 'Bloqueado', value: 'blocked' },
  { label: 'Saltado', value: 'skipped' },
]

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  passed: 'green',
  failed: 'red',
  blocked: 'orange',
  skipped: 'purple',
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  try {
    const date = new Date(value)
    return date.toLocaleString()
  } catch (err) {
    return value
  }
}

function normalizeEvaluation(raw: any): CaseEvaluation {
  const scoreValue = raw?.score
  let numericScore: number | null = null
  if (typeof scoreValue === 'number') {
    numericScore = scoreValue
  } else if (typeof scoreValue === 'string' && scoreValue.trim() !== '') {
    const parsed = Number(scoreValue)
    numericScore = Number.isFinite(parsed) ? parsed : null
  }
  return {
    case_id: raw?.case_id ?? raw?.id ?? 0,
    evaluated: Boolean(raw?.evaluated),
    status: raw?.status || 'pending',
    score: numericScore,
    notes: raw?.notes ?? null,
    checked: Boolean(raw?.checked),
  }
}

function normalizeCase(raw: any): CasePayload {
  const ensureArray = (value: unknown): string[] | undefined => {
    if (!value) return undefined
    if (Array.isArray(value)) return value as string[]
    if (typeof value === 'string') {
      return value.split('\n').map((item) => item.trim()).filter(Boolean)
    }
    return undefined
  }

  return {
    id: raw?.id ?? raw?.case_id,
    frame: raw?.frame,
    feature: raw?.feature,
    objetivo: raw?.objetivo,
    precondiciones: ensureArray(raw?.precondiciones),
    pasos: ensureArray(raw?.pasos),
    datos_prueba: raw?.datos_prueba ?? undefined,
    resultado_esperado: raw?.resultado_esperado,
    negativo: ensureArray(raw?.negativo),
    bordes: ensureArray(raw?.bordes),
    accesibilidad: ensureArray(raw?.accesibilidad),
    prioridad: raw?.prioridad,
    severidad: raw?.severidad,
    dispositivo: raw?.dispositivo,
    dependencias: ensureArray(raw?.dependencias),
    observaciones: raw?.observaciones,
    image_url: raw?.image_url ?? null,
    page_name: raw?.page_name ?? '—',
    frame_name: raw?.frame_name ?? raw?.bundle_label ?? '—',
    node_id: raw?.node_id ?? '',
    bundle_label: raw?.bundle_label ?? raw?.frame_name ?? null,
    evaluation: normalizeEvaluation(raw?.evaluation ?? {}),
  }
}

function normalizeAnalysis(raw: any): AnalysisDetail {
  return {
    analysis_id: raw.analysis_id,
    job_id: raw.job_id,
    file_key: raw.file_key,
    figma_url: raw.figma_url,
    analysis_level: raw.analysis_level,
    model: raw.model,
    images_per_unit: raw.images_per_unit,
    image_scale: raw.image_scale,
    reasoning_effort: raw.reasoning_effort,
    max_frames: raw.max_frames,
    status: raw.status,
    total_cases: raw.total_cases ?? (raw.cases ? raw.cases.length : 0),
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    cases: (raw.cases || []).map(normalizeCase),
  }
}

function normalizeSummary(raw: any): AnalysisSummary {
  return {
    analysis_id: raw.analysis_id,
    job_id: raw.job_id,
    file_key: raw.file_key,
    figma_url: raw.figma_url,
    analysis_level: raw.analysis_level,
    model: raw.model,
    images_per_unit: raw.images_per_unit,
    image_scale: raw.image_scale,
    reasoning_effort: raw.reasoning_effort,
    max_frames: raw.max_frames,
    status: raw.status,
    total_cases: raw.total_cases,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  }
}

function buildRowsFromAnalysis(analysis: AnalysisDetail | null): CaseRow[] {
  if (!analysis) return []
  return analysis.cases.map((caseItem, index) => {
    const evaluation = normalizeEvaluation(caseItem.evaluation)
    return {
      ...caseItem,
      evaluation,
      rowKey: `${analysis.analysis_id}-${evaluation.case_id || index}`,
      caseId: evaluation.case_id || index,
    }
  })
}

function calculateEvaluationStats(analysis: AnalysisDetail | null) {
  if (!analysis) {
    return { total: 0, checked: 0, avgScore: null as number | null }
  }
  const total = analysis.cases.length
  const checked = analysis.cases.filter((c) => c.evaluation.checked).length
  const scored = analysis.cases
    .map((c) => c.evaluation.score)
    .filter((value): value is number => typeof value === 'number')
  const avgScore = scored.length ? scored.reduce((sum, v) => sum + v, 0) / scored.length : null
  return { total, checked, avgScore }
}

export default function App() {
  const [loading, setLoading] = useState(false)
  const [token, setToken] = useState(getToken())
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisDetail | null>(null)
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState('config')
  const [historyFiles, setHistoryFiles] = useState<HistoryFileEntry[]>([])
  const [historyFilesLoading, setHistoryFilesLoading] = useState(false)
  const [historyFilesError, setHistoryFilesError] = useState<string | null>(null)
  const [casesPageSize, setCasesPageSize] = useState(15)
  const pollRef = useRef<number | null>(null)
  const [form] = Form.useForm()
  const analysisLevel = Form.useWatch('analysis_level', form)

  const rows = useMemo(() => buildRowsFromAnalysis(selectedAnalysis), [selectedAnalysis])
  const evaluationStats = useMemo(() => calculateEvaluationStats(selectedAnalysis), [selectedAnalysis])
  const historyFilesMap = useMemo(() => {
    const map = new Map<string, HistoryFileEntry>()
    historyFiles.forEach((file) => {
      if (file.file_key) {
        map.set(file.file_key, file)
      }
    })
    return map
  }, [historyFiles])

  const historyItems = useMemo<HistoryItem[]>(() => {
    const items: HistoryItem[] = analyses.map((analysis) => ({
      key: `analysis-${analysis.analysis_id}`,
      analysis,
      metrics: historyFilesMap.get(analysis.file_key) || null,
    }))
    historyFiles.forEach((file) => {
      const alreadyIncluded = items.some((item) => item.analysis?.file_key === file.file_key)
      if (!alreadyIncluded) {
        items.push({ key: `file-${file.file_key}`, analysis: null, metrics: file })
      }
    })
    items.sort((a, b) => {
      const dateA = new Date(a.analysis?.updated_at || a.metrics?.last_run_at || 0).getTime()
      const dateB = new Date(b.analysis?.updated_at || b.metrics?.last_run_at || 0).getTime()
      return dateB - dateA
    })
    return items
  }, [analyses, historyFiles, historyFilesMap])

  const refreshAnalyses = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const res = await fetch(`${API_BASE}/analyses?limit=200`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const items = Array.isArray(data.items) ? data.items.map(normalizeSummary) : []
      setAnalyses(items)
    } catch (err: any) {
      console.error('Analyses list error', err)
      message.error('No se pudieron cargar los análisis previos')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const fetchHistoryFiles = useCallback(async () => {
    setHistoryFilesLoading(true)
    setHistoryFilesError(null)
    try {
      const res = await fetch(`${API_BASE}/history/files`)
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || res.statusText)
      }
      const data = await res.json()
      setHistoryFiles(Array.isArray(data.files) ? data.files : [])
    } catch (err: any) {
      console.error('History files error', err)
      const msg = err?.message ? String(err.message) : 'No se pudo obtener el historial de archivos'
      setHistoryFilesError(msg)
      message.error('No se pudo cargar el historial de archivos analizados')
    } finally {
      setHistoryFilesLoading(false)
    }
  }, [])

  const loadAnalysis = useCallback(
    async (analysisId: number, opts: { focusTab?: boolean } = {}) => {
      setAnalysisLoading(true)
      try {
        const res = await fetch(`${API_BASE}/analyses/${analysisId}`)
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        const normalized = normalizeAnalysis(data)
        setSelectedAnalysis(normalized)
        setSelectedAnalysisId(normalized.analysis_id)
        if (opts.focusTab) {
          setActiveTab('history')
        }
      } catch (err: any) {
        console.error('Load analysis error', err)
        message.error('No se pudo cargar el análisis seleccionado')
      } finally {
        setAnalysisLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    refreshAnalyses()
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [refreshAnalyses])

  const getCaseById = useCallback(
    (caseId: number): CasePayload | undefined =>
      selectedAnalysis?.cases.find((item) => item.evaluation.case_id === caseId),
    [selectedAnalysis],
  )

  const mutateCase = useCallback(
    (caseId: number, updater: (current: CasePayload) => CasePayload) => {
      setSelectedAnalysis((prev) => {
        if (!prev) return prev
        const updatedCases = prev.cases.map((item) =>
          item.evaluation.case_id === caseId ? updater(item) : item,
        )
        return {
          ...prev,
          cases: updatedCases,
          updated_at: new Date().toISOString(),
        }
      })
    },
    [],
  )

  const applyEvaluationLocal = useCallback(
    (caseId: number, changes: EvaluationUpdate) => {
      mutateCase(caseId, (current) => {
        const nextEvaluation: CaseEvaluation = { ...current.evaluation }
        if (changes.checked !== undefined) nextEvaluation.checked = changes.checked
        if (changes.evaluated !== undefined) nextEvaluation.evaluated = changes.evaluated
        if (changes.status !== undefined) nextEvaluation.status = changes.status || 'pending'
        if (changes.score !== undefined) nextEvaluation.score = changes.score ?? null
        if (changes.notes !== undefined) nextEvaluation.notes = changes.notes ?? null
        return {
          ...current,
          evaluation: nextEvaluation,
        }
      })
    },
    [mutateCase],
  )

  const handleEvaluationSave = useCallback(
    async (caseId: number, payload: EvaluationUpdate) => {
      if (!selectedAnalysisId) return
      const body: Record<string, unknown> = {}
      if (payload.checked !== undefined) body.checked = payload.checked
      if (payload.evaluated !== undefined) body.evaluated = payload.evaluated
      if (payload.status !== undefined) body.status = payload.status
      if (payload.score !== undefined) body.score = payload.score
      if (payload.notes !== undefined) body.notes = payload.notes

      try {
        const res = await fetch(`${API_BASE}/analyses/${selectedAnalysisId}/cases/${caseId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        const normalized = normalizeCase(data)
        mutateCase(caseId, () => normalized)
      } catch (err: any) {
        console.error('Evaluation update error', err)
        message.error('No se pudo guardar la evaluación, se restaurarán los datos')
        loadAnalysis(selectedAnalysisId)
      }
    },
    [loadAnalysis, mutateCase, selectedAnalysisId],
  )

  const startPolling = useCallback(
    (jobIdentifier: string) => {
      const poll = window.setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/jobs/${jobIdentifier}`)
          if (!res.ok) {
            if (res.status === 404) return
            const errText = await res.text()
            throw new Error(errText)
          }
          const js: JobStatus = await res.json()
          setJob(js)
          if (js.status === 'completed') {
            window.clearInterval(poll)
            pollRef.current = null
            message.success('Análisis completado')
            refreshAnalyses()
            fetchHistoryFiles()
            if (js.analysis) {
              const normalized = normalizeAnalysis(js.analysis)
              setSelectedAnalysis(normalized)
              setSelectedAnalysisId(normalized.analysis_id)
            } else if (js.analysis_id) {
              loadAnalysis(js.analysis_id)
            }
          } else if (js.status === 'failed') {
            window.clearInterval(poll)
            pollRef.current = null
            message.error(js.error || 'El análisis falló')
          }
        } catch (err) {
          console.error('Polling error', err)
        }
      }, 2000) as unknown as number
      pollRef.current = poll
    },
    [loadAnalysis, refreshAnalyses, fetchHistoryFiles],
  )

  const onConnect = async () => {
    try {
      const res = await fetch(`${API_BASE}/oauth/figma/start?state=spa`, { method: 'GET' })
      if (!res.ok) throw new Error('No se pudo iniciar OAuth')
      const data = await res.json()
      const url = data.authorize_url
      if (!url) throw new Error('authorize_url vacío')
      window.location.href = url
    } catch (e: any) {
      message.error(e.message || 'Error en OAuth')
    }
  }

  const onFinish = async (values: any) => {
    const { figma_url, file_key, image_scale, model, max_frames, analysis_level, images_per_unit, reasoning_effort } = values
    if (!figma_url && !file_key) {
      message.error('Ingresa la URL de Figma o el File Key')
      return
    }
    if (!token) {
      message.warning('Conecta con Figma primero o pega un Access Token')
      return
    }
    setLoading(true)
    setSelectedAnalysis(null)
    setSelectedAnalysisId(null)
    setJob(null)
    let hide: (() => void) | undefined
    try {
      hide = message.loading('Creando trabajo de análisis…', 0)
      const res = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          figma_url,
          file_key,
          image_scale: Number(image_scale),
          model,
          max_frames: max_frames ? Number(max_frames) : undefined,
          analysis_level,
          images_per_unit: Number(images_per_unit || 12),
          reasoning_effort,
        }),
      })
      const j = await res.json()
      if (!res.ok) throw new Error(j.detail || j.message || 'No se pudo iniciar el análisis')
      setJobId(j.job_id)
      setJob({ status: 'queued', processed: 0, frames_processing: 0, cases_total: 0 })
      message.success('Análisis iniciado')
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      setTimeout(() => startPolling(j.job_id), 300)
    } catch (e: any) {
      message.error(e.message || 'Fallo al iniciar el análisis')
    } finally {
      hide?.()
      setLoading(false)
    }
  }

  const handleDownload = async () => {
    if (!jobId) return
    const currentJob = job
    if (!currentJob?.download_url) {
      message.info('Ejecuta un análisis y espera a que finalice para descargar el Excel')
      return
    }
    try {
      const res = await fetch(`${API_BASE}${currentJob.download_url}`)
      if (!res.ok) throw new Error('No se pudo descargar el Excel')
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'casos_prueba.xlsx'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      message.success('Excel descargado')
    } catch (e: any) {
      message.error(e.message || 'Fallo al descargar el Excel')
    }
  }

  const handleDeleteAnalysis = async (analysisId: number) => {
    try {
      const res = await fetch(`${API_BASE}/analyses/${analysisId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      message.success('Análisis eliminado')
      refreshAnalyses()
      if (selectedAnalysisId === analysisId) {
        setSelectedAnalysis(null)
        setSelectedAnalysisId(null)
      }
    } catch (err: any) {
      console.error('Delete analysis error', err)
      message.error('No se pudo eliminar el análisis seleccionado')
    }
  }

  const handleRerunAnalysis = async (analysisId: number) => {
    if (!token) {
      message.warning('Necesitas un Access Token para re-ejecutar el análisis')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/analyses/${analysisId}/rerun`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ figma_token: token }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      message.success('Re-ejecución iniciada')
      setSelectedAnalysis(null)
      setSelectedAnalysisId(null)
      setJobId(data.job_id)
      setJob({ status: 'queued', processed: 0, frames_processing: 0, cases_total: 0 })
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      setTimeout(() => startPolling(data.job_id), 300)
    } catch (err: any) {
      console.error('Re-run error', err)
      message.error('No se pudo re-ejecutar el análisis')
    }
  }

  useEffect(() => {
    fetchHistoryFiles()
  }, [fetchHistoryFiles])

  const handleUseHistoryFile = (file: HistoryFileEntry) => {
    if (!file.file_key) return
    form.setFieldsValue({
      file_key: file.file_key,
      figma_url: file.figma_url || `https://www.figma.com/file/${file.file_key}`,
    })
    setActiveTab('config')
    message.success('Archivo cargado en el formulario')
  }

  const handleDeleteCase = useCallback(
    async (caseId: number) => {
      if (!selectedAnalysisId) return
      try {
        const res = await fetch(`${API_BASE}/analyses/${selectedAnalysisId}/cases/${caseId}`, {
          method: 'DELETE',
        })
        if (!res.ok) throw new Error(await res.text())
        message.success('Caso eliminado')
        setSelectedAnalysis((prev) => {
          if (!prev) return prev
          const filtered = prev.cases.filter((item) => item.evaluation.case_id !== caseId)
          return {
            ...prev,
            cases: filtered,
            total_cases: Math.max((prev.total_cases || 0) - 1, 0),
          }
        })
        refreshAnalyses()
      } catch (err: any) {
        console.error('Delete case error', err)
        message.error('No se pudo eliminar el caso seleccionado')
      }
    },
    [selectedAnalysisId, refreshAnalyses],
  )

  const handleExportAnalysis = useCallback(async () => {
    if (!selectedAnalysisId) return
    try {
      const res = await fetch(`${API_BASE}/analyses/${selectedAnalysisId}/export`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `analisis_${selectedAnalysisId}.xlsx`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
      message.success('Descarga lista')
    } catch (err: any) {
      console.error('Export analysis error', err)
      message.error('No se pudo descargar el Excel del análisis')
    }
  }, [selectedAnalysisId])

  const columns: ColumnsType<CaseRow> = useMemo(
    () => [
      {
        title: 'Vista',
        dataIndex: 'image_url',
        key: 'image_url',
        width: 220,
        render: (value: string | null | undefined, record) =>
          value ? (
            <Image src={value} width={200} alt={record.frame_name} />
          ) : (
            <Text type="secondary">Sin imagen</Text>
          ),
      },
      {
        title: 'Página',
        dataIndex: 'page_name',
        key: 'page_name',
        width: 160,
        render: (value: string) => <Text strong>{value}</Text>,
      },
      {
        title: 'Frame',
        dataIndex: 'frame_name',
        key: 'frame_name',
        width: 200,
      },
      {
        title: 'Feature',
        dataIndex: 'feature',
        key: 'feature',
        width: 200,
        render: (value?: string) => value || <Text type="secondary">—</Text>,
      },
      {
        title: 'Objetivo',
        dataIndex: 'objetivo',
        key: 'objetivo',
        width: 260,
        render: (value?: string) => (value ? <Paragraph>{value}</Paragraph> : <Text type="secondary">—</Text>),
      },
      {
        title: 'Precondiciones',
        dataIndex: 'precondiciones',
        key: 'precondiciones',
        width: 220,
        render: (value?: string[]) => renderList(value),
      },
      {
        title: 'Pasos',
        dataIndex: 'pasos',
        key: 'pasos',
        width: 320,
        render: (value?: string[]) => renderList(value),
      },
      {
        title: 'Resultado esperado',
        dataIndex: 'resultado_esperado',
        key: 'resultado_esperado',
        width: 260,
        render: (value?: string) => (value ? <Paragraph>{value}</Paragraph> : <Text type="secondary">—</Text>),
      },
      {
        title: 'Negativos',
        dataIndex: 'negativo',
        key: 'negativo',
        width: 220,
        render: (value?: string[]) => renderList(value),
      },
      {
        title: 'Accesibilidad',
        dataIndex: 'accesibilidad',
        key: 'accesibilidad',
        width: 220,
        render: (value?: string[]) => renderList(value),
      },
      {
        title: 'Estado',
        dataIndex: 'evaluation',
        key: 'evaluation.status',
        width: 160,
        render: (_: unknown, record) => (
          <Select
            size="small"
            value={record.evaluation.status}
            options={STATUS_OPTIONS}
            onChange={async (value) => {
              applyEvaluationLocal(record.caseId, { status: value, evaluated: value !== 'pending' })
              await handleEvaluationSave(record.caseId, { status: value, evaluated: value !== 'pending' })
            }}
          />
        ),
      },
      {
        title: 'Listo',
        dataIndex: 'evaluation.checked',
        key: 'evaluation.checked',
        width: 90,
        render: (_: unknown, record) => (
          <Checkbox
            checked={record.evaluation.checked}
            onChange={async (event) => {
              const checked = event.target.checked
              applyEvaluationLocal(record.caseId, { checked, evaluated: checked })
              await handleEvaluationSave(record.caseId, { checked, evaluated: checked })
            }}
          />
        ),
      },
      {
        title: 'Puntaje',
        dataIndex: 'evaluation.score',
        key: 'evaluation.score',
        width: 140,
        render: (_: unknown, record) => (
          <InputNumber
            min={0}
            max={100}
            precision={0}
            value={record.evaluation.score ?? undefined}
            onChange={(value) => {
              applyEvaluationLocal(record.caseId, { score: value === null ? null : Number(value) })
            }}
            onBlur={async () => {
              const latest = getCaseById(record.caseId)
              await handleEvaluationSave(record.caseId, { score: latest?.evaluation.score ?? null })
            }}
            style={{ width: '100%' }}
            size="small"
          />
        ),
      },
      {
        title: 'Notas del evaluador',
        dataIndex: 'evaluation.notes',
        key: 'evaluation.notes',
        width: 320,
        render: (_: unknown, record) => (
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={record.evaluation.notes ?? ''}
            placeholder="Observaciones"
            style={{ minWidth: 280 }}
            onChange={(event) => {
              applyEvaluationLocal(record.caseId, { notes: event.target.value || null })
            }}
            onBlur={async (event) => {
              const value = event.target.value.trim()
              await handleEvaluationSave(record.caseId, { notes: value ? value : null })
            }}
          />
        ),
      },
      {
        title: 'Acciones',
        key: 'actions',
        fixed: 'right',
        width: 120,
        render: (_: unknown, record) => (
          <Space size={8}>
            <Popconfirm
              title="Eliminar caso"
              description="Esta acción quitará el caso del análisis"
              okText="Eliminar"
              cancelText="Cancelar"
              onConfirm={() => handleDeleteCase(record.caseId)}
            >
              <Button danger size="small" icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [applyEvaluationLocal, getCaseById, handleEvaluationSave, handleDeleteCase],
  )

  const tokenStatus = useMemo(() => (token ? 'Conectado con Figma' : 'No conectado'), [token])

  return (
    <>
      <style>{SIDE_TABS_STYLES}</style>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          width={390}
          theme="light"
          style={{ padding: 0, background: 'transparent', display: 'flex', flexDirection: 'column' }}
        >
          <div className="sider-container">
            <Tabs
              className="sider-tabs"
              activeKey={activeTab}
              onChange={setActiveTab}
              centered
              size="middle"
              tabBarGutter={32}
              animated={{ inkBar: false, tabPane: true }}
              tabPosition="bottom"
              style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
              items={[
              {
                key: 'config',
                label: (
                  <Space size={10} align="center">
                    <SettingOutlined className="tab-label-icon" />
                    <span>Configurar</span>
                  </Space>
                ),
                children: (
                  <div className="sider-config">
                    <Space align="center" style={{ justifyContent: 'space-between' }}>
                      <Title level={4} style={{ margin: 0 }}>
                        <CloudUploadOutlined style={{ marginRight: 8 }} /> Figma QA
                      </Title>
                      <Button icon={<LoginOutlined />} type="primary" onClick={onConnect} shape="round">
                        Conectar
                      </Button>
                    </Space>
                    <Text type={token ? 'success' : 'secondary'}>{tokenStatus}</Text>
                    <Form
                      form={form}
                      layout="vertical"
                      onFinish={onFinish}
                      initialValues={{
                        image_scale: 2.0,
                        model: 'gpt-5',
                        analysis_level: 'group',
                        images_per_unit: 12,
                        reasoning_effort: 'medium',
                      }}
                    >
                      <Form.Item label="URL de Figma" name="figma_url">
                        <Input prefix={<LinkOutlined />} placeholder="https://www.figma.com/file/FILE_KEY/TuArchivo" allowClear />
                      </Form.Item>
                      <Form.Item label="File Key" name="file_key">
                        <Input placeholder="FILE_KEY" allowClear />
                      </Form.Item>
                      <Form.Item label="Access Token">
                        <Input.Password
                          placeholder="Pega un Access Token de Figma si no usas OAuth"
                          value={token}
                          onChange={(e) => {
                            setToken(e.target.value)
                            storeToken(e.target.value)
                          }}
                        />
                        <Text type="secondary">Se usará como Bearer en el backend.</Text>
                      </Form.Item>
                      <Divider plain>Modelo</Divider>
                      <Form.Item label="Modelo" name="model">
                        <Select
                          options={[
                            { label: 'gpt-5 (por defecto)', value: 'gpt-5' },
                            { label: 'gpt-4o', value: 'gpt-4o' },
                            { label: 'gpt-4o-mini', value: 'gpt-4o-mini' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item label="Esfuerzo de razonamiento" name="reasoning_effort">
                        <Select
                          options={[
                            { label: 'Bajo', value: 'low' },
                            { label: 'Medio', value: 'medium' },
                            { label: 'Alto', value: 'high' },
                          ]}
                        />
                      </Form.Item>
                      <Divider plain>Parámetros</Divider>
                      <Form.Item label="Image Scale" name="image_scale">
                        <Input type="number" step={0.5} min={1} max={4} />
                      </Form.Item>
                      <Form.Item label="Nivel de análisis" name="analysis_level">
                        <Select
                          options={[
                            { label: 'Por grupo de elementos', value: 'group' },
                            { label: 'Por sección (sections/prefijo)', value: 'section' },
                            { label: 'Por página (consolidado)', value: 'page' },
                            { label: 'Por frame (detallado)', value: 'frame' },
                          ]}
                        />
                      </Form.Item>
                      {analysisLevel === 'frame' && (
                        <Form.Item label="Max Frames" name="max_frames">
                          <Input type="number" min={1} placeholder="Ej: 3 para prueba rápida" />
                        </Form.Item>
                      )}
                      <Form.Item label="Imágenes por unidad" name="images_per_unit">
                        <Input type="number" min={1} max={12} />
                      </Form.Item>
                      <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} icon={<PlayCircleOutlined />} block>
                          Analizar mockup
                        </Button>
                      </Form.Item>
                    </Form>
                  </div>
                ),
              },
              {
                key: 'history',
                label: (
                  <Space size={10} align="center">
                    <HistoryOutlined className="tab-label-icon" />
                    <span>Historial</span>
                  </Space>
                ),
                children: (
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '18px 16px 12px' }}>
                    <Card
                      className="history-card"
                      size="small"
                      styles={{ body: { padding: 0 } }}
                      title={
                        <Space>
                          <HistoryOutlined /> Historial
                        </Space>
                      }
                      extra={
                        <Space size={8}>
                          <Button
                            size="small"
                            icon={<ReloadOutlined />}
                            loading={historyLoading || historyFilesLoading}
                            onClick={() => {
                              refreshAnalyses()
                              fetchHistoryFiles()
                            }}
                            shape="round"
                          >
                            Actualizar
                          </Button>
                        </Space>
                      }
                    >
                      {historyFilesError && (
                        <Alert
                          type="warning"
                          showIcon
                          style={{ margin: '16px 16px 0' }}
                          message="No se pudo obtener el historial"
                          description={<Text type="secondary">{historyFilesError}</Text>}
                        />
                      )}
                      <List
                        className="history-list"
                        loading={historyLoading || historyFilesLoading}
                        dataSource={historyItems}
                        locale={{ emptyText: 'Aún no hay ejecuciones registradas en este entorno.' }}
                        pagination={{ pageSize: 6, size: 'small' }}
                        style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}
                        renderItem={(item) => {
                          const analysis = item.analysis
                          const metrics = item.metrics
                          const selected = analysis ? selectedAnalysisId === analysis.analysis_id : false
                          const fileKey = analysis?.file_key || metrics?.file_key || 'Desconocido'

                          const actions: ReactNode[] = []
                          if (analysis) {
                            actions.push(
                              <Button
                                key="view"
                                size="small"
                                icon={<FileSearchOutlined />}
                                type={selected ? 'primary' : 'default'}
                                onClick={() => loadAnalysis(analysis.analysis_id, { focusTab: false })}
                                shape="round"
                              >
                                Ver
                              </Button>,
                            )
                            actions.push(
                              <Button
                                key="rerun"
                                size="small"
                                icon={<ReloadOutlined />}
                                onClick={() => handleRerunAnalysis(analysis.analysis_id)}
                                shape="round"
                              >
                                Re-ejecutar
                              </Button>,
                            )
                            actions.push(
                              <Popconfirm
                                key="delete"
                                title="Eliminar análisis"
                                description="Esta acción borrará los resultados guardados"
                                onConfirm={() => handleDeleteAnalysis(analysis.analysis_id)}
                              >
                                <Button danger size="small" icon={<DeleteOutlined />} shape="round">Borrar</Button>
                              </Popconfirm>,
                            )
                          }
                          if (metrics) {
                            actions.push(
                              <Button
                                key="use"
                                size="small"
                                type="dashed"
                                onClick={() => handleUseHistoryFile(metrics)}
                                shape="round"
                              >
                                Usar archivo
                              </Button>,
                            )
                            if (metrics.figma_url) {
                              actions.push(
                                <Button
                                  key="figma"
                                  size="small"
                                  type="link"
                                  href={metrics.figma_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  shape="round"
                                >
                                  Abrir en Figma
                                </Button>,
                              )
                            }
                          }

                          const tagRow = (
                            <Space size={8} wrap>
                              {analysis && <Tag color="blue">{analysis.analysis_level}</Tag>}
                              {analysis && <Tag color="gold">{analysis.total_cases} casos</Tag>}
                              {(analysis?.model || metrics?.last_model) && (
                                <Tag color="purple">{analysis?.model || metrics?.last_model}</Tag>
                              )}
                              {metrics?.runs && <Tag color="geekblue">{metrics.runs} ejecuciones</Tag>}
                              {selected && <Tag color="geekblue">Seleccionado</Tag>}
                            </Space>
                          )

                          const actionItems = actions.filter(Boolean) as ReactNode[]
                          const lastRunLabel = analysis?.updated_at || metrics?.last_run_at

                          return (
                            <List.Item key={item.key} actions={actionItems}>
                              <List.Item.Meta
                                title={
                                  <Space size={8} wrap>
                                    <Text strong style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {fileKey}
                                    </Text>
                                    {tagRow}
                                  </Space>
                                }
                                description={
                                  <Space direction="vertical" size={4}>
                                    {lastRunLabel && (
                                      <Text type="secondary">Último análisis: {formatDate(lastRunLabel)}</Text>
                                    )}
                                    {metrics?.figma_url && (
                                      <Text type="secondary" ellipsis={{ tooltip: metrics.figma_url }}>
                                        URL: {metrics.figma_url}
                                      </Text>
                                    )}
                                  </Space>
                                }
                              />
                            </List.Item>
                          )
                        }}
                      />
                    </Card>
                  </div>
                ),
              },
            ]}
            />
          </div>
        </Sider>
      <Layout>
        <Header style={{ background: '#fff', borderBottom: '1px solid #f0f0f0', padding: '0 24px' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between', alignItems: 'center', gap: 16 }} wrap>
            <Title level={3} style={{ margin: 0 }}>
              Resultados del análisis
            </Title>
            <Space size={10} align="center" wrap style={{ flexGrow: 1, justifyContent: 'flex-end' }}>
              {selectedAnalysis && (
                <>
                  <Tag color="blue" bordered={false} icon={<FileSearchOutlined />}
                    style={{ fontSize: 13 }}>
                    {selectedAnalysis.file_key}
                  </Tag>
                  <Tag
                    icon={<CheckCircleOutlined />}
                    color={evaluationStats.checked === evaluationStats.total ? 'success' : 'warning'}
                    bordered={false}
                    style={{ fontSize: 13 }}
                  >
                    {evaluationStats.checked}/{evaluationStats.total} completados
                  </Tag>
                  <Tag color="purple" bordered={false} style={{ fontSize: 13 }}>
                    Promedio: {evaluationStats.avgScore !== null ? evaluationStats.avgScore.toFixed(1) : '—'}
                  </Tag>
                  <Tag color="geekblue" bordered={false} style={{ fontSize: 13 }}>
                    Casos visibles: {rows.length}
                  </Tag>
                </>
              )}
              {job?.download_url && (
                <Button icon={<DownloadOutlined />} onClick={handleDownload} shape="round" type="default">
                  Último Excel
                </Button>
              )}
              {selectedAnalysis && (
                <Button icon={<DownloadOutlined />} onClick={handleExportAnalysis} shape="round" type="primary">
                  Exportar todo
                </Button>
              )}
            </Space>
          </Space>
        </Header>
        <Content style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 24, overflow: 'hidden' }}>
          {job && (
            <Card size="small" title="Progreso del análisis">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <Text strong>Estado:</Text> <Text>{job.status}</Text>
                </div>
                {job.stage && (
                  <div>
                    <Text strong>Etapa:</Text> <Text>{job.stage}</Text>
                  </div>
                )}
                {job.message && <Alert type="info" message={job.message} showIcon />} 
                {job.status === 'failed' && (job.error || job.message) && (
                  <Alert type="error" message={job.error || job.message} showIcon />
                )}
                <div>
                  <Text>
                    Frames procesados: {job.processed || 0}/{job.frames_processing || job.frames_total || 0}
                  </Text>
                </div>
                <div>
                  <Text>Casos generados: {job.cases_total || selectedAnalysis?.cases.length || 0}</Text>
                </div>
                <Progress
                  percent={Math.min(
                    100,
                    Math.round(((job.processed || 0) / Math.max(1, job.frames_processing || job.frames_total || 1)) * 100),
                  )}
                  status={job.status === 'failed' ? 'exception' : undefined}
                />
              </Space>
            </Card>
          )}

          {analysisLoading && (
            <Card size="small">
              <Spin /> Cargando análisis seleccionado…
            </Card>
          )}

          {!selectedAnalysis && !analysisLoading && (
            <Alert
              type="info"
              message="Selecciona un análisis desde el historial o ejecuta uno nuevo para visualizar los casos"
              showIcon
            />
          )}

          {selectedAnalysis && (
            <Card
              size="small"
              title={`Casos de prueba (${rows.length})`}
              extra={
                <Space>
                  <Button icon={<DownloadOutlined />} onClick={handleExportAnalysis} size="small" shape="round">
                    Descargar Excel
                  </Button>
                </Space>
              }
              style={{ flex: 1, minHeight: 0 }}
              styles={{ body: { padding: 0, height: '100%', display: 'flex', flexDirection: 'column' } }}
            >
              <Table
                className="cases-table"
                rowKey="rowKey"
                columns={columns}
                dataSource={rows}
                pagination={{
                  pageSize: casesPageSize,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '15', '20', '50'],
                  onChange: (_, pageSize) => setCasesPageSize(pageSize),
                  position: ['bottomRight'],
                }}
                scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
                locale={{ emptyText: 'Sin casos disponibles' }}
                style={{ flex: 1 }}
                rowClassName={(_, index) => (index % 2 === 0 ? 'cases-row-even' : '')}
              />
              </Card>
            )}
        </Content>
        <Footer style={{ textAlign: 'center' }}>Figma QA © {new Date().getFullYear()}</Footer>
      </Layout>
      </Layout>
    </>
  )
}

function renderList(items?: string[]) {
  if (!items || !items.length) return <Text type="secondary">—</Text>
  return (
    <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-line' }}>
      {items.map((item, idx) => `${idx + 1}. ${item}`).join('\n')}
    </Paragraph>
  )
}
