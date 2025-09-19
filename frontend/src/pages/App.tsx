import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
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

type FigmaFileEntry = {
  key?: string
  name?: string
  thumbnail_url?: string
  last_modified?: string
  project?: { id?: string; name?: string }
  analysis?: {
    runs: number
    last_run_at: string | null
    last_analysis_id: number | null
  } | null
}

type FigmaProjectEntry = {
  id?: string
  name?: string
  files: FigmaFileEntry[]
}

type FigmaTeamEntry = {
  id?: string
  name?: string
  role?: string
  projects: FigmaProjectEntry[]
}

type EvaluationUpdate = Partial<CaseEvaluation & { notes: string | null }>

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
  const [figmaTeams, setFigmaTeams] = useState<FigmaTeamEntry[]>([])
  const [figmaTeamsLoading, setFigmaTeamsLoading] = useState(false)
  const [figmaScopeLimited, setFigmaScopeLimited] = useState(false)
  const [figmaFiles, setFigmaFiles] = useState<FigmaFileEntry[]>([])
  const [figmaLoading, setFigmaLoading] = useState(false)
  const [figmaTeamId, setFigmaTeamId] = useState('')
  const [figmaProjectId, setFigmaProjectId] = useState('')
  const pollRef = useRef<number | null>(null)
  const [form] = Form.useForm()
  const analysisLevel = Form.useWatch('analysis_level', form)

  const rows = useMemo(() => buildRowsFromAnalysis(selectedAnalysis), [selectedAnalysis])
  const evaluationStats = useMemo(() => calculateEvaluationStats(selectedAnalysis), [selectedAnalysis])

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
    [loadAnalysis, refreshAnalyses],
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

  const fetchFigmaTeams = useCallback(async () => {
    if (!token) {
      setFigmaTeams([])
      return
    }
    setFigmaTeamsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/figma/teams`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || res.statusText)
      }
      const data = await res.json()
      let scopeIssue = false
      if (Array.isArray(data.errors) && data.errors.length) {
        scopeIssue = data.errors.some((msg: string) => msg.includes('403') || msg.includes('404'))
        if (scopeIssue) {
          message.warning('Conecta con Figma mediante OAuth con permisos file_read, projects:read y organization:read para ver todos tus equipos.')
        } else {
          message.warning(`Algunos recursos de Figma no se pudieron obtener: ${data.errors.join('; ')}`)
        }
      }
      setFigmaScopeLimited(scopeIssue)
      setFigmaTeams(Array.isArray(data.teams) ? data.teams : [])
      if (!scopeIssue) {
        setFigmaFiles([])
      }
    } catch (err: any) {
      console.error('Figma teams error', err)
      message.error('No se pudieron obtener los equipos y archivos de Figma. Reautentica con OAuth si es necesario.')
      if (err?.message?.includes('403') || err?.message?.includes('404')) {
        setFigmaScopeLimited(true)
      }
    } finally {
      setFigmaTeamsLoading(false)
    }
  }, [token])

  const fetchFigmaFiles = useCallback(async () => {
    if (!token) {
      message.warning('Conecta o pega un Access Token para consultar Figma')
      return
    }
    if (!figmaTeamId && !figmaProjectId) {
      message.warning('Ingresa un Team ID o Project ID de Figma')
      return
    }
    setFigmaLoading(true)
    try {
      const params = new URLSearchParams()
      if (figmaTeamId) params.append('team_id', figmaTeamId)
      if (figmaProjectId) params.append('project_id', figmaProjectId)
      const res = await fetch(`${API_BASE}/figma/files?${params.toString()}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setFigmaFiles(Array.isArray(data.files) ? data.files : [])
    } catch (err: any) {
      console.error('Figma files error', err)
      message.error('No se pudieron obtener los archivos de Figma con los identificadores provistos')
    } finally {
      setFigmaLoading(false)
    }
  }, [token, figmaTeamId, figmaProjectId])

  useEffect(() => {
    if (token) {
      fetchFigmaTeams()
    } else {
      setFigmaTeams([])
      setFigmaScopeLimited(false)
      setFigmaFiles([])
    }
  }, [token, fetchFigmaTeams])

  const handleUseFigmaFile = (file: FigmaFileEntry) => {
    if (!file.key) return
    form.setFieldsValue({
      file_key: file.key,
      figma_url: `https://www.figma.com/file/${file.key}`,
    })
    setActiveTab('config')
    message.success('Archivo cargado en el formulario')
  }

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
        width: 240,
        render: (_: unknown, record) => (
          <Input.TextArea
            autoSize={{ minRows: 1, maxRows: 4 }}
            value={record.evaluation.notes ?? ''}
            placeholder="Observaciones"
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
    ],
    [applyEvaluationLocal, getCaseById, handleEvaluationSave],
  )

  const tokenStatus = useMemo(() => (token ? 'Conectado con Figma' : 'No conectado'), [token])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={380} theme="light" style={{ padding: 0, borderRight: '1px solid #f0f0f0', overflow: 'auto' }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'config',
              label: 'Configurar',
              children: (
                <div style={{ padding: 24 }}>
                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Title level={4} style={{ margin: 0 }}>
                        <CloudUploadOutlined style={{ marginRight: 8 }} /> Figma QA
                      </Title>
                      <Button icon={<LoginOutlined />} type="primary" onClick={onConnect}>
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
                  </Space>
                </div>
              ),
            },
            {
              key: 'history',
              label: 'Historial',
              children: (
                <div style={{ padding: 24 }}>
                  <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    <Card
                      title={
                        <Space>
                          <HistoryOutlined /> Historial de análisis
                        </Space>
                      }
                      extra={
                        <Button size="small" icon={<ReloadOutlined />} onClick={refreshAnalyses} loading={historyLoading}>
                          Actualizar
                        </Button>
                      }
                      size="small"
                      styles={{ body: { padding: 0 } }}
                    >
                      <List
                        loading={historyLoading}
                        dataSource={analyses}
                        locale={{ emptyText: 'Aún no hay análisis guardados' }}
                        renderItem={(item) => {
                          const selected = selectedAnalysisId === item.analysis_id
                          return (
                            <List.Item
                              actions={[
                                <Button
                                  key="view"
                                  size="small"
                                  icon={<FileSearchOutlined />}
                                  type={selected ? 'primary' : 'default'}
                                  onClick={() => loadAnalysis(item.analysis_id, { focusTab: false })}
                                >
                                  Ver
                                </Button>,
                                <Button
                                  key="rerun"
                                  size="small"
                                  icon={<ReloadOutlined />}
                                  onClick={() => handleRerunAnalysis(item.analysis_id)}
                                >
                                  Re-ejecutar
                                </Button>,
                                <Popconfirm
                                  key="delete"
                                  title="Eliminar análisis"
                                  description="Esta acción borrará los resultados guardados"
                                  onConfirm={() => handleDeleteAnalysis(item.analysis_id)}
                                >
                                  <Button danger size="small" icon={<DeleteOutlined />}>Borrar</Button>
                                </Popconfirm>,
                              ]}
                            >
                              <List.Item.Meta
                                title={
                                  <Space>
                                    <Text strong>{item.file_key}</Text>
                                    <Tag color="blue">{item.analysis_level}</Tag>
                                    {selected && <Tag color="geekblue">Seleccionado</Tag>}
                                  </Space>
                                }
                                description={
                                  <Space direction="vertical" size={4}>
                                    <Text type="secondary">{formatDate(item.created_at)}</Text>
                                    <Space size={8}>
                                      <Tag color="gold">{item.total_cases} casos</Tag>
                                      <Tag>{item.model}</Tag>
                                      {item.reasoning_effort && <Tag color="purple">{item.reasoning_effort}</Tag>}
                                    </Space>
                                  </Space>
                                }
                              />
                            </List.Item>
                          )
                        }}
                      />
                    </Card>

                    <Card
                      title={
                        <Space>
                          <FileSearchOutlined /> Recursos de Figma
                        </Space>
                      }
                      size="small"
                      extra={
                        <Button size="small" icon={<ReloadOutlined />} loading={figmaTeamsLoading} onClick={fetchFigmaTeams}>
                          Actualizar
                        </Button>
                      }
                    >
                      {figmaTeamsLoading ? (
                        <Spin />
                      ) : figmaTeams.length === 0 ? (
                        <Text type="secondary">Conecta con Figma para listar tus equipos y archivos.</Text>
                      ) : (
                        <Collapse accordion>
                          {figmaTeams.map((team) => (
                            <Collapse.Panel
                              header={
                                <Space>
                                  <Text strong>{team.name || team.id}</Text>
                                  {team.role && <Tag>{team.role}</Tag>}
                                  <Tag color="blue">{team.projects.length} proyectos</Tag>
                                </Space>
                              }
                              key={team.id || team.name}
                            >
                              {team.projects.length === 0 ? (
                                <Text type="secondary">Este equipo no tiene proyectos visibles.</Text>
                              ) : (
                                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                                  {team.projects.map((project) => (
                                    <Card
                                      key={project.id || project.name}
                                      size="small"
                                      title={
                                        <Space>
                                          <Text strong>{project.name || project.id}</Text>
                                          <Tag color="gold">{project.files.length} archivos</Tag>
                                        </Space>
                                      }
                                    >
                                      <List
                                        dataSource={project.files}
                                        locale={{ emptyText: 'Sin archivos en este proyecto' }}
                                        renderItem={(file) => (
                                          <List.Item
                                            actions={[
                                              file.analysis?.last_analysis_id ? (
                                                <Tooltip
                                                  key="open"
                                                  title={`Ver último análisis (${formatDate(file.analysis.last_run_at)})`}
                                                >
                                                  <Button
                                                    size="small"
                                                    onClick={() => loadAnalysis(file.analysis!.last_analysis_id!, { focusTab: true })}
                                                  >
                                                    Abrir resultados
                                                  </Button>
                                                </Tooltip>
                                              ) : null,
                                              file.key ? (
                                                <Button
                                                  key="fill"
                                                  size="small"
                                                  type="dashed"
                                                  onClick={() => handleUseFigmaFile({ ...file, project: { id: project.id, name: project.name } })}
                                                >
                                                  Usar archivo
                                                </Button>
                                              ) : null,
                                            ].filter(Boolean)}
                                          >
                                            <List.Item.Meta
                                              title={
                                                <Space>
                                                  <Text strong>{file.name || file.key || 'Archivo sin nombre'}</Text>
                                                  {file.analysis && file.analysis.runs > 0 && (
                                                    <Badge
                                                      count={file.analysis.runs}
                                                      style={{ backgroundColor: '#1890ff' }}
                                                      offset={[6, -2]}
                                                    />
                                                  )}
                                                </Space>
                                              }
                                              description={
                                                <Space direction="vertical" size={2}>
                                                  <Text type="secondary">Key: {file.key || '—'}</Text>
                                                  <Text type="secondary">Proyecto: {project.name || project.id || '—'}</Text>
                                                  <Text type="secondary">Última modificación: {formatDate(file.last_modified)}</Text>
                                                </Space>
                                              }
                                            />
                                          </List.Item>
                                        )}
                                      />
                                    </Card>
                                  ))}
                                </Space>
                              )}
                            </Collapse.Panel>
                          ))}
                        </Collapse>
                      )}
                      {figmaScopeLimited && (
                        <Space direction="vertical" size="small" style={{ width: '100%', marginTop: 16 }}>
                          <Alert
                            type="info"
                            showIcon
                            message="Tu token no tiene permisos organization:read o tu cuenta no pertenece a una organización de Figma. Ingresa manualmente un Team ID o Project ID para cargar los archivos."
                          />
                          <Space.Compact style={{ width: '100%' }}>
                            <Input
                              placeholder="Team ID"
                              value={figmaTeamId}
                              onChange={(event) => setFigmaTeamId(event.target.value)}
                            />
                            <Input
                              placeholder="Project ID"
                              value={figmaProjectId}
                              onChange={(event) => setFigmaProjectId(event.target.value)}
                            />
                            <Button icon={<HistoryOutlined />} loading={figmaLoading} onClick={fetchFigmaFiles}>
                              Consultar
                            </Button>
                          </Space.Compact>
                          <List
                            loading={figmaLoading}
                            dataSource={figmaFiles}
                            locale={{ emptyText: 'Ingresa identificadores y presiona Consultar' }}
                            renderItem={(file) => (
                              <List.Item
                                actions={[
                                  file.analysis?.last_analysis_id ? (
                                    <Tooltip
                                      key="open"
                                      title={`Ver último análisis (${formatDate(file.analysis.last_run_at)})`}
                                    >
                                      <Button
                                        size="small"
                                        onClick={() => loadAnalysis(file.analysis!.last_analysis_id!, { focusTab: true })}
                                      >
                                        Abrir resultados
                                      </Button>
                                    </Tooltip>
                                  ) : null,
                                  file.key ? (
                                    <Button
                                      key="fill"
                                      size="small"
                                      type="dashed"
                                      onClick={() => handleUseFigmaFile({ ...file })}
                                    >
                                      Usar archivo
                                    </Button>
                                  ) : null,
                                ].filter(Boolean)}
                              >
                                <List.Item.Meta
                                  title={<Text strong>{file.name || file.key || 'Archivo sin nombre'}</Text>}
                                  description={
                                    <Space direction="vertical" size={2}>
                                      <Text type="secondary">Key: {file.key || '—'}</Text>
                                      <Text type="secondary">Última modificación: {formatDate(file.last_modified)}</Text>
                                    </Space>
                                  }
                                />
                              </List.Item>
                            )}
                          />
                        </Space>
                      )}
                    </Card>
                  </Space>
                </div>
              ),
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', borderBottom: '1px solid #f0f0f0', padding: '0 24px' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Title level={3} style={{ margin: 0 }}>
                Resultados del análisis
              </Title>
              {selectedAnalysis && (
                <Space size={12} style={{ marginTop: 4 }}>
                  <Tag color="blue">Archivo: {selectedAnalysis.file_key}</Tag>
                  <Tag icon={<CheckCircleOutlined />} color={evaluationStats.checked === evaluationStats.total ? 'green' : 'gold'}>
                    {evaluationStats.checked}/{evaluationStats.total} completados
                  </Tag>
                  <Tag color="purple">
                    Promedio: {evaluationStats.avgScore !== null ? evaluationStats.avgScore.toFixed(1) : '—'}
                  </Tag>
                </Space>
              )}
            </div>
            <Space>
              {job?.download_url && (
                <Button icon={<DownloadOutlined />} onClick={handleDownload}>
                  Descargar Excel
                </Button>
              )}
            </Space>
          </Space>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
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
              <Card size="small" title={`Casos de prueba (${rows.length})`} styles={{ body: { padding: 0 } }}>
                <Table
                  rowKey="rowKey"
                  columns={columns}
                  dataSource={rows}
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                  scroll={{ x: 'max-content', y: 'calc(100vh - 360px)' }}
                  locale={{ emptyText: 'Sin casos disponibles' }}
                />
              </Card>
            )}
          </Space>
        </Content>
        <Footer style={{ textAlign: 'center' }}>Figma QA © {new Date().getFullYear()}</Footer>
      </Layout>
    </Layout>
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
