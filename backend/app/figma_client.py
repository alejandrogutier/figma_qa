from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple
import logging

import httpx
from tenacity import RetryError, retry, wait_exponential_jitter, stop_after_attempt, retry_if_exception_type


FIGMA_API = "https://api.figma.com/v1"


class FigmaError(Exception):
    pass


def extract_file_key(url_or_key: str) -> str:
    """Obtiene el file key a partir de una URL de Figma o retorna la cadena si ya parece un key.

    Soporta URLs tipo /file/, /design/ o /proto/.
    """
    if not url_or_key:
        raise ValueError("Se requiere figma_url o file_key")

    # Si ya parece un key (alfanumérico y largo razonable)
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,64}", url_or_key):
        return url_or_key

    m = re.search(r"/(?:file|design|proto)/([a-zA-Z0-9_-]{10,64})", url_or_key)
    if m:
        return m.group(1)

    # Fallback: intenta leer query param key=...
    m2 = re.search(r"[?&]key=([a-zA-Z0-9_-]{10,64})", url_or_key)
    if m2:
        return m2.group(1)

    raise ValueError("No se pudo extraer el file_key de la URL proporcionada")


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _chunked(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential_jitter(initial=0.5, max=8.0),
    stop=stop_after_attempt(5),
)
async def _get_json(client: httpx.AsyncClient, url: str, headers: Dict[str, str], params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    log = logging.getLogger("app.figma")
    r = await client.get(url, headers=headers, params=params, timeout=30)
    if r.status_code >= 400:
        log.error("Figma API error %s for %s params=%s body=%s", r.status_code, url, params, r.text[:500])
        raise httpx.HTTPStatusError(
            f"Figma API error {r.status_code}: {r.text}", request=r.request, response=r
        )
    # Log de cabeceras de rate limit si existen
    rl = {k: r.headers.get(k) for k in ("X-RateLimit-Remaining", "X-RateLimit-Limit") if r.headers.get(k) is not None}
    if rl:
        log.info("Figma rate %s for %s", rl, url)
    return r.json()


async def get_file(client: httpx.AsyncClient, token: str, file_key: str) -> Dict[str, Any]:
    url = f"{FIGMA_API}/files/{file_key}"
    return await _get_json(client, url, _auth_headers(token))


async def get_me(client: httpx.AsyncClient, token: str) -> Dict[str, Any]:
    """Obtiene información del usuario autenticado y equipos asociados."""
    url = f"{FIGMA_API}/me"
    return await _get_json(client, url, _auth_headers(token))


def _extract_pages(file_json: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Devuelve lista de (page_name, page_id)."""
    document = file_json.get("document") or {}
    pages = document.get("children") or []
    out: List[Tuple[str, str]] = []
    for page in pages:
        out.append((page.get("name", "Untitled Page"), page.get("id")))
    return out


def _collect_frames_from_doc(doc: Dict[str, Any], page_id: str, page_name: str) -> List[Tuple[str, str, str, str]]:
    """Recorre un árbol de página (CANVAS) y devuelve (page_name, page_id, frame_name, node_id) para cada FRAME encontrado.

    Nota: incluye frames anidados dentro de SECTION/GRUPO/COMPONENT_SET.
    """
    acc: List[Tuple[str, str, str, str]] = []

    def _walk(n: Dict[str, Any]):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "FRAME":
            acc.append((page_name, page_id, n.get("name", "Untitled Frame"), n.get("id")))
        for ch in n.get("children", []) or []:
            _walk(ch)

    _walk(doc)
    return acc


async def list_frames(client: httpx.AsyncClient, token: str, file_key: str) -> List[Tuple[str, str, str, str]]:
    """Lista frames de manera robusta recorriendo cada página mediante /nodes.

    Devuelve (page_name, frame_name, node_id) para todos los frames encontrados.
    """
    file_json = await get_file(client, token, file_key)
    pages = _extract_pages(file_json)
    page_ids = [pid for _, pid in pages]
    # Llama /nodes por lotes de páginas para obtener árboles completos por página
    nodes_payload = await get_nodes_details(client, token, file_key, page_ids)
    nodes_map = nodes_payload.get("nodes") or {}
    frames: List[Tuple[str, str, str, str]] = []
    for page_name, page_id in pages:
        node = nodes_map.get(page_id)
        if not node:
            # fallback: si no vino en nodes (raro), intenta desde file_json
            continue
        doc = node.get("document") or {}
        frames.extend(_collect_frames_from_doc(doc, page_id, page_name))
    return frames


async def list_pages(client: httpx.AsyncClient, token: str, file_key: str) -> List[Tuple[str, str]]:
    """Lista las páginas (nombre, id) del archivo."""
    file_json = await get_file(client, token, file_key)
    return _extract_pages(file_json)


async def list_user_teams(client: httpx.AsyncClient, token: str) -> List[Dict[str, Any]]:
    teams: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add_team(team_info: Dict[str, Any]) -> None:
        team_id = team_info.get("id") or team_info.get("team_id") or team_info.get("teamId")
        if not team_id:
            return
        sid = str(team_id)
        if sid in seen:
            return
        seen.add(sid)
        teams.append({
            "id": sid,
            "name": team_info.get("name"),
            "role": team_info.get("role"),
        })

    async def _load_legacy() -> None:
        url = f"{FIGMA_API}/me/teams"
        data = await _get_json(client, url, _auth_headers(token))
        legacy_teams = data.get("teams") or []
        if isinstance(legacy_teams, list):
            for item in legacy_teams:
                if isinstance(item, dict):
                    _add_team(item)
                elif isinstance(item, str):
                    _add_team({"id": item})

    try:
        me = await get_me(client, token)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (403, 404):
            try:
                await _load_legacy()
            except httpx.HTTPStatusError:
                raise exc
            return teams
        raise

    raw_teams = me.get("teams")
    if isinstance(raw_teams, list):
        for item in raw_teams:
            if isinstance(item, dict):
                _add_team(item)
            elif isinstance(item, str):
                _add_team({"id": item})

    # Algunos tenants devuelven teams incrustados dentro de organizaciones
    orgs = me.get("organizations")
    if isinstance(orgs, list):
        for org in orgs:
            if not isinstance(org, dict):
                continue
            org_teams = org.get("teams")
            if isinstance(org_teams, list):
                for org_team in org_teams:
                    if isinstance(org_team, dict):
                        _add_team(org_team)

    # Compatibilidad con payloads que solo exponen ids
    fallback_ids = me.get("teamIds") or me.get("team_ids")
    if isinstance(fallback_ids, list):
        for tid in fallback_ids:
            if isinstance(tid, (str, int)):
                _add_team({"id": str(tid)})

    if not teams:
        await _load_legacy()

    return teams


async def list_team_projects(client: httpx.AsyncClient, token: str, team_id: str) -> List[Dict[str, Any]]:
    url = f"{FIGMA_API}/teams/{team_id}/projects"
    data = await _get_json(client, url, _auth_headers(token))
    return data.get("projects") or []


async def list_project_files(client: httpx.AsyncClient, token: str, project_id: str) -> List[Dict[str, Any]]:
    url = f"{FIGMA_API}/projects/{project_id}/files"
    data = await _get_json(client, url, _auth_headers(token))
    return data.get("files") or []


async def list_figma_files(
    client: httpx.AsyncClient,
    token: str,
    *,
    project_id: str | None = None,
    team_id: str | None = None,
) -> List[Dict[str, Any]]:
    if project_id:
        files = await list_project_files(client, token, project_id)
        return [
            {
                "key": f.get("key"),
                "name": f.get("name"),
                "thumbnail_url": f.get("thumbnail_url"),
                "last_modified": f.get("last_modified"),
                "project": {"id": project_id},
            }
            for f in files
        ]
    if not team_id:
        raise ValueError("Debes proporcionar project_id o team_id para listar archivos")

    projects = await list_team_projects(client, token, team_id)
    output: List[Dict[str, Any]] = []
    for proj in projects:
        pid = proj.get("id")
        if not pid:
            continue
        files = await list_project_files(client, token, pid)
        for f in files:
            output.append(
                {
                    "key": f.get("key"),
                    "name": f.get("name"),
                    "thumbnail_url": f.get("thumbnail_url"),
                    "last_modified": f.get("last_modified"),
                    "project": {"id": pid, "name": proj.get("name")},
                }
            )
    return output


async def list_all_accessible_files(
    client: httpx.AsyncClient,
    token: str,
) -> Dict[str, Any]:
    """Enumera todos los archivos accesibles agrupando proyectos por equipo.

    Devuelve un diccionario con listas de equipos, archivos y errores recopilados.
    Cada entrada de archivo incluye metadatos del proyecto y equipo correspondientes.
    """

    teams = await list_user_teams(client, token)
    errors: List[str] = []
    files: List[Dict[str, Any]] = []

    def _friendly_error(kind: str, identifier: str, exc: Exception) -> str:
        status: int | None = None
        if isinstance(exc, RetryError):
            last_exc = exc.last_attempt.exception()
            if isinstance(last_exc, httpx.HTTPStatusError) and last_exc.response is not None:
                status = last_exc.response.status_code
        elif isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            status = exc.response.status_code

        if status == 403:
            return f"{kind} {identifier}: token sin permisos (HTTP 403)"
        if status == 404:
            return f"{kind} {identifier}: recurso no encontrado o sin acceso (HTTP 404)"
        return f"{kind} {identifier}: {exc}"

    for team in teams:
        team_id = team.get("id")
        if not team_id:
            continue
        try:
            projects = await list_team_projects(client, token, team_id)
        except (httpx.HTTPStatusError, RetryError) as exc:
            errors.append(_friendly_error("Equipo", str(team_id), exc))
            continue
        except Exception as exc:  # pragma: no cover - defensivo
            errors.append(f"Equipo {team_id}: error al listar proyectos: {exc}")
            continue

        for project in projects:
            project_id = project.get("id") or project.get("project_id")
            if not project_id:
                continue
            try:
                project_files = await list_project_files(client, token, project_id)
            except (httpx.HTTPStatusError, RetryError) as exc:
                errors.append(_friendly_error("Proyecto", str(project_id), exc))
                continue
            except Exception as exc:  # pragma: no cover - defensivo
                errors.append(f"Proyecto {project_id}: error al listar archivos: {exc}")
                continue

            for file_item in project_files:
                files.append(
                    {
                        "team": {
                            "id": team_id,
                            "name": team.get("name"),
                            "role": team.get("role"),
                        },
                        "project": {
                            "id": project_id,
                            "name": project.get("name"),
                        },
                        "file": {
                            "key": file_item.get("key"),
                            "name": file_item.get("name"),
                            "thumbnail_url": file_item.get("thumbnail_url"),
                            "last_modified": file_item.get("last_modified"),
                        },
                    }
                )

    return {"teams": teams, "files": files, "errors": errors}


def _collect_sections_and_frames(doc: Dict[str, Any]) -> Dict[str, List[Tuple[str, str]]]:
    """Devuelve mapping section_name -> [(frame_name, node_id), ...].

    - Una SECTION agrupa todos los FRAME que están dentro de su subárbol.
    - Los frames que no pertenezcan a ninguna SECTION no aparecen aquí.
    """
    sections: Dict[str, List[Tuple[str, str]]] = {}

    def _walk(n: Dict[str, Any], current_section: str | None = None):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        name = n.get("name") or ""
        # Si entramos a una SECTION, cambiamos el current_section
        if t == "SECTION":
            current_section = name or "Sección"
        if t == "FRAME" and current_section:
            sections.setdefault(current_section, []).append((name or "Untitled Frame", n.get("id")))
        for ch in n.get("children", []) or []:
            _walk(ch, current_section)

    _walk(doc, None)
    return sections


def _prefix_of(name: str) -> str:
    """Obtiene un prefijo estable para agrupar frames por convención de nombres.

    Corta por separadores comunes y devuelve la primera parte normalizada.
    """
    if not name:
        return ""
    s = name.strip().lower()
    parts = re.split(r"\s*[\/:|>›»–\-]+\s*", s)
    base = (parts[0] if parts else s).strip()
    base = re.sub(r"\s+", " ", base)
    return base


def group_frames_by_section_or_prefix(
    page_doc: Dict[str, Any],
    frames_in_page: List[Tuple[str, str]],
    *,
    min_group_size: int = 2,
) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Genera grupos de frames a nivel superior para dar contexto.

    Estrategia:
    1) Si hay SECTIONS, agrupa por SECTION.
    2) Para los que queden fuera, agrupa por prefijo de nombre de frame.
    3) Solo devuelve grupos con al menos `min_group_size` frames. El resto cae en "(otros)" si hay >0.
    """
    # 1) Agrupar por SECTION
    sec_map = _collect_sections_and_frames(page_doc)
    grouped_ids = set()
    groups: List[Tuple[str, List[Tuple[str, str]]]] = []
    for sec_name, items in sec_map.items():
        if len(items) >= min_group_size:
            groups.append((f"{sec_name}", items))
            grouped_ids.update([nid for _, nid in items])

    # 2) Prefijo para los restantes
    rest: List[Tuple[str, str]] = [(fn, nid) for (fn, nid) in frames_in_page if nid not in grouped_ids]
    if rest:
        by_prefix: Dict[str, List[Tuple[str, str]]] = {}
        for fn, nid in rest:
            pref = _prefix_of(fn)
            by_prefix.setdefault(pref or "", []).append((fn, nid))
        for pref, items in list(by_prefix.items()):
            if len(items) >= min_group_size and pref:
                groups.append((pref, items))
                grouped_ids.update([nid for _, nid in items])

    # 3) Otros
    leftovers = [(fn, nid) for (fn, nid) in frames_in_page if nid not in grouped_ids]
    if leftovers and len(leftovers) >= min_group_size:
        groups.append(("(otros)", leftovers))

    return groups


async def get_images_for_nodes(
    client: httpx.AsyncClient,
    token: str,
    file_key: str,
    node_ids: List[str],
    *,
    format: str = "jpg",
    scale: float = 2.0,
) -> Dict[str, str]:
    """Devuelve mapping node_id -> image_url efímera."""
    headers = _auth_headers(token)
    base_url = f"{FIGMA_API}/images/{file_key}"
    result: Dict[str, str] = {}
    # Lotes para evitar URLs muy largas
    log = logging.getLogger("app.figma")
    for chunk in _chunked(node_ids, 40):
        params = {"ids": ",".join(chunk), "format": format, "scale": scale}
        log.info("/images chunk size=%s", len(chunk))
        data = await _get_json(client, base_url, headers, params=params)
        images = data.get("images") or {}
        result.update({k: v for k, v in images.items() if v})
    log.info("/images resolved=%s/%s", len(result), len(node_ids))
    return result


async def get_nodes_details(
    client: httpx.AsyncClient, token: str, file_key: str, node_ids: List[str]
) -> Dict[str, Any]:
    """Devuelve el payload de /nodes para múltiples IDs. Puede requerir paginar por lotes."""
    headers = _auth_headers(token)
    base_url = f"{FIGMA_API}/files/{file_key}/nodes"
    out: Dict[str, Any] = {"nodes": {}}
    log = logging.getLogger("app.figma")
    for chunk in _chunked(node_ids, 35):  # deja margen a límites de tamaño
        params = {"ids": ",".join(chunk)}
        log.info("/nodes chunk size=%s", len(chunk))
        data = await _get_json(client, base_url, headers, params=params)
        out["nodes"].update(data.get("nodes") or {})
    log.info("/nodes fetched=%s", len(out["nodes"]))
    return out


def _flatten_texts(node: Dict[str, Any], acc: List[str]) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "TEXT":
        chars = node.get("characters")
        if isinstance(chars, str) and chars.strip():
            acc.append(chars.strip())
    for child in node.get("children", []) or []:
        _flatten_texts(child, acc)


CONTROL_KEYWORDS = [
    "button",
    "input",
    "textfield",
    "select",
    "dropdown",
    "checkbox",
    "radio",
    "switch",
    "tab",
    "accordion",
    "modal",
    "dialog",
    "toast",
    "tooltip",
    "link",
]


def _detect_elements(node: Dict[str, Any], acc: List[Dict[str, Any]]) -> None:
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    name = (node.get("name") or "").lower()
    if node_type in {"INSTANCE", "COMPONENT", "COMPONENT_SET"}:
        # Marca por keyword (control) si coincide
        for kw in CONTROL_KEYWORDS:
            if kw in name:
                acc.append({"type": kw, "name": node.get("name")})
                break
        # Registra siempre el nombre del componente/instancia
        if node.get("name"):
            acc.append({"type": "component", "name": node.get("name")})
    if node_type in {"GROUP", "SECTION"} and node.get("name"):
        acc.append({"type": "group", "name": node.get("name")})
    for child in node.get("children", []) or []:
        _detect_elements(child, acc)


def summarize_frame_document(doc: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    texts: List[str] = []
    _flatten_texts(doc, texts)
    elements: List[Dict[str, Any]] = []
    _detect_elements(doc, elements)
    # Dedup textos conservando orden
    seen = set()
    dedup = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup, elements
