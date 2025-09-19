# Figma QA – Generador de Casos de Prueba

MVP de backend en FastAPI que recibe un archivo de Figma (URL o file key) y un token de Figma, extrae frames, renderiza imágenes, envía texto+imagen a OpenAI (GPT) y devuelve un Excel con casos de prueba funcionales.

## Requisitos

- Python 3.10+
- Dependencias Python (ver `backend/requirements.txt`)
- Variables de entorno:
  - `OPENAI_API_KEY` (ver `backend/.env.example`)
  - `FIGMA_CLIENT_ID`, `FIGMA_CLIENT_SECRET`, `FIGMA_REDIRECT_URI` (para OAuth)

## Instalación (local)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # edita y agrega tu OPENAI_API_KEY
# agrega FIGMA_CLIENT_ID/FIGMA_CLIENT_SECRET/FIGMA_REDIRECT_URI
```

## Ejecución

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker (Dev)

1) Asegura tus variables en `backend/.env` (usa `backend/.env.example` como guía). Requiere `OPENAI_API_KEY` válido.
2) Construir y levantar:

```bash
docker compose up -d --build
```

Servicios expuestos:
- Backend: http://localhost:8000 (salud: `/health`)
- Frontend (React + AntD): http://localhost:5173

Logs:

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

Apagar:

```bash
docker compose down
```

### Frontend React (Ant Design)

```bash
cd frontend
pnpm i # o npm i / yarn
pnpm dev # http://localhost:5173
```

Configura variables en `frontend/.env.local`:

```
VITE_API_BASE_URL=http://localhost:8000
```

### Probar

POST `http://localhost:8000/analyze`

Body JSON:

```json
{
  "figma_url": "https://www.figma.com/file/FILE_KEY/YourFile",
  "figma_token": "FIGMA_PAT",
  "model": "gpt-4o-mini",
  "image_scale": 2.0
}
```

Respuesta: archivo Excel (`casos_prueba.xlsx`). En el frontend, se dispara descarga automática.

### Niveles de análisis disponibles

- `page`: consolida casos a nivel de página (varios frames juntos).
- `group`: agrupa por nombres de componentes/grupos detectados dentro de cada frame (más granular).
- `section`: agrupa por SECTIONS de Figma; si no hay SECTIONS, agrupa por prefijo del nombre del frame. Ideal para evitar hiper‑detalle y conservar contexto.
- `frame`: casos por frame individual (máxima granularidad).

Variables opcionales en `backend/.env` para ajustar seccionado/agrupado:

- `MAX_GROUPS_PER_PAGE` (default 8)
- `MAX_SECTIONS_PER_PAGE` (default 10)
- `MIN_FRAMES_PER_UNIT` (default 2) – tamaño mínimo para formar un grupo/sección; el resto cae en "(otros)".
- `MAX_GROUPS_GLOBAL` (default 12) – tope global de unidades en modo group (top por tamaño).
- `MAX_SECTIONS_GLOBAL` (default 12) – tope global de unidades en modo section (top por tamaño).

### OAuth con Figma (opcional)

1) Configura en Figma tu app con `redirect_uri` = `http://localhost:8000/oauth/figma/callback` y copia `client_id` y `client_secret` a `.env`.
2) Inicia el flujo:

```bash
curl "http://localhost:8000/oauth/figma/start?state=abc123"
```

Abre la `authorize_url` devuelta, autoriza y Figma redirigirá al callback con `code`.

3) Intercambia el `code` por token:

```bash
curl "http://localhost:8000/oauth/figma/callback?code=...&state=abc123"
```

El backend está configurado para redirigir a `http://localhost:5173/oauth/figma/callback` con los tokens como query. El frontend guarda el `access_token` en localStorage y lo usa como `Authorization: Bearer` al llamar `/analyze`.

Para refrescar tokens:

```bash
curl -X POST "http://localhost:8000/oauth/figma/refresh" -d "refresh_token=..."
```

## Notas

- Para archivos Figma muy grandes, este MVP usa `/files` para listar frames y `/nodes` por lotes, con reintentos y batching básicos.
- Las URLs de imagen de Figma son efímeras; se consumen inmediatamente para la llamada a GPT.
- El esquema de salida de GPT es flexible; el Excel contempla columnas estándares de QA.
- Mejora futura: colas/background jobs, OAuth Figma, cache, front-end, structured output con JSON Schema.
  - Ahora existe un flujo OAuth básico (start/callback/refresh) y soporte de `Authorization: Bearer`.
