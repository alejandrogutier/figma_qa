from __future__ import annotations

import os
from typing import Dict, Optional
from urllib.parse import urlencode

import httpx
from httpx import HTTPStatusError


FIGMA_OAUTH_AUTHORIZE = "https://www.figma.com/oauth"
FIGMA_OAUTH_TOKEN = "https://api.figma.com/v1/oauth/token"


def get_env_cfg() -> Dict[str, Optional[str]]:
    return {
        "client_id": os.getenv("FIGMA_CLIENT_ID"),
        "client_secret": os.getenv("FIGMA_CLIENT_SECRET"),
        "redirect_uri": os.getenv("FIGMA_REDIRECT_URI"),
        "scope": os.getenv("FIGMA_OAUTH_SCOPE", "file_read profile_read"),
    }


def build_authorize_url(state: str = "state") -> str:
    cfg = get_env_cfg()
    missing = [k for k, v in cfg.items() if k in ("client_id", "redirect_uri") and not v]
    if missing:
        raise ValueError(f"Faltan variables de entorno OAuth Figma: {', '.join(missing)}")
    qs = urlencode(
        {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "scope": cfg["scope"] or "file_read",
            "state": state or "state",
            "response_type": "code",
        }
    )
    return f"{FIGMA_OAUTH_AUTHORIZE}?{qs}"


async def exchange_code_for_token(code: str) -> Dict[str, str]:
    cfg = get_env_cfg()
    if not (cfg["client_id"] and cfg["client_secret"] and cfg["redirect_uri"]):
        raise ValueError("Faltan FIGMA_CLIENT_ID/FIGMA_CLIENT_SECRET/FIGMA_REDIRECT_URI")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                FIGMA_OAUTH_TOKEN,
                data={
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "redirect_uri": cfg["redirect_uri"],
                    "code": code,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except HTTPStatusError as e:
            body = e.response.text if e.response is not None else str(e)
            raise ValueError(f"Figma token error {e.response.status_code if e.response else ''}: {body}")


async def refresh_access_token(refresh_token: str) -> Dict[str, str]:
    cfg = get_env_cfg()
    if not (cfg["client_id"] and cfg["client_secret"]):
        raise ValueError("Faltan FIGMA_CLIENT_ID/FIGMA_CLIENT_SECRET")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                FIGMA_OAUTH_TOKEN,
                data={
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except HTTPStatusError as e:
            body = e.response.text if e.response is not None else str(e)
            raise ValueError(f"Figma refresh error {e.response.status_code if e.response else ''}: {body}")
