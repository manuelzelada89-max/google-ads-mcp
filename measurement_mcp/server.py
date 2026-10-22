"""Independent Google Tag Manager + GA4 MCP for the existing Cloud Run project.

The Google Ads MCP is not imported or changed. This service uses the user's
Google OAuth token obtained from FastMCP and never accepts arbitrary URLs.
Writes require a short-lived signed preview and a separate approval call.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Literal

import requests
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

from measurement_mcp.storage import create_client_storage


GTM_BASE = "https://tagmanager.googleapis.com/tagmanager/v2/"
ADMIN_BASE = "https://analyticsadmin.googleapis.com/v1beta/"
DATA_BASE = "https://analyticsdata.googleapis.com/v1beta/"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
    "https://www.googleapis.com/auth/tagmanager.publish",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
]

_client_id = os.getenv("MEASUREMENT_MCP_OAUTH_CLIENT_ID")
_client_secret = os.getenv("MEASUREMENT_MCP_OAUTH_CLIENT_SECRET")
_base_url = os.getenv("MEASUREMENT_MCP_BASE_URL", "http://localhost:8080")

if bool(_client_id) != bool(_client_secret):
    raise RuntimeError("Both MEASUREMENT_MCP_OAUTH_CLIENT_ID and SECRET are required")

if _client_id:
    settings: dict[str, Any] = {
        "client_id": _client_id,
        "client_secret": _client_secret,
        "base_url": _base_url,
        "required_scopes": SCOPES,
    }
    signing_key = os.getenv("MEASUREMENT_MCP_JWT_SIGNING_KEY")
    if signing_key:
        settings["jwt_signing_key"] = signing_key
    store = create_client_storage()
    if store is not None:
        settings["client_storage"] = store
    mcp = FastMCP("Google Measurement (GTM + GA4)", auth=GoogleProvider(**settings))
else:
    mcp = FastMCP("Google Measurement (GTM + GA4)")


def _id(value: str | int) -> str:
    value = str(value)
    if not re.fullmatch(r"[0-9]+", value):
        raise ToolError("IDs must be numeric (use API IDs, not GTM-XXXXXX)")
    return value


def _gtm_workspace(account_id: str, container_id: str, workspace_id: str) -> str:
    return (
        f"accounts/{_id(account_id)}/containers/{_id(container_id)}"
        f"/workspaces/{_id(workspace_id)}"
    )


def _api(method: str, base: str, path: str, *, body: dict | None = None,
         params: dict | None = None) -> dict:
    token = get_access_token()
    if token is None or not token.token:
        raise ToolError("Conecta este MCP con Google OAuth en ChatGPT antes de consultar datos.")
    if not path or path.startswith("/") or ".." in path or "://" in path:
        raise ToolError("Ruta de API no permitida")
    try:
        res = requests.request(
            method, base + path,
            headers={"Authorization": f"Bearer {token.token}", "Accept": "application/json"},
            json=body, params=params, timeout=35,
        )
    except requests.RequestException as exc:
        raise ToolError(f"Error de conexión con Google: {type(exc).__name__}") from exc
    try:
        payload = res.json() if res.content else {}
    except ValueError:
        payload = {}
    if not res.ok:
        message = payload.get("error", {}).get("message", res.reason)
        raise ToolError(f"Google API HTTP {res.status_code}: {message}")
    return payload


def _gtm(method: str, path: str, **kwargs: Any) -> dict:
    return _api(method, GTM_BASE, path, **kwargs)


def _admin(method: str, path: str, **kwargs: Any) -> dict:
    return _api(method, ADMIN_BASE, path, **kwargs)


def _signature_key() -> bytes:
    key = os.getenv("MEASUREMENT_MCP_APPROVAL_KEY") or os.getenv("MEASUREMENT_MCP_JWT_SIGNING_KEY")
    if not key or len(key) < 32:
        raise ToolError("Configura una MEASUREMENT_MCP_APPROVAL_KEY de 32+ caracteres")
    return key.encode()


def _make_ticket(details: dict) -> str:
    payload = {**details, "expires": int(time.time()) + 600}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    sig = hmac.new(_signature_key(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + sig).decode().rstrip("=")


def _decode_ticket(ticket: str, category: str) -> dict:
    try:
        data = base64.urlsafe_b64decode(ticket + "=" * (-len(ticket) % 4))
        raw, signature = data[:-32], data[-32:]
        good = hmac.new(_signature_key(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, good):
            raise ValueError("bad signature")
        payload = json.loads(raw)
        if payload["category"] != category or not int(time.time()) <= payload["expires"]:
            raise ValueError("wrong action or expired")
        return payload
    except (KeyError, ValueError, TypeError) as exc:
        raise ToolError("Vista previa vencida o modificada. Prepara el cambio de nuevo.") from exc


def _check_approval(confirmation: str) -> None:
    if confirmation.strip().upper() != "APRUEBO":
        raise ToolError(
            "No se aplicó nada. Muestra el cambio al usuario y solicita su "
            "aprobación explícita; tras recibirla, escribe APRUEBO."
        )


@mcp.tool
def gtm_list_accounts() -> dict:
    """Lista las cuentas GTM accesibles por la persona que autorizó OAuth."""
    return _gtm("GET", "accounts")


@mcp.tool
def gtm_list_containers(account_id: str) -> dict:
    """Lista contenedores GTM de una cuenta."""
    return _gtm("GET", f"accounts/{_id(account_id)}/containers")


@mcp.tool
def gtm_list_workspaces(account_id: str, container_id: str) -> dict:
    """Lista espacios de trabajo GTM; usa el workspace ID numérico para editar."""
    return _gtm("GET", f"accounts/{_id(account_id)}/containers/{_id(container_id)}/workspaces")


@mcp.tool
def gtm_list_entities(account_id: str, container_id: str, workspace_id: str,
                      entity_type: Literal["tags", "triggers", "variables"]) -> dict:
    """Lee etiquetas, activadores o variables en un workspace GTM."""
    root = _gtm_workspace(account_id, container_id, workspace_id)
    return _gtm("GET", f"{root}/{entity_type}")


@mcp.tool
def gtm_get_entity(account_id: str, container_id: str, workspace_id: str,
                   entity_type: Literal["tags", "triggers", "variables"],
                   entity_id: str) -> dict:
    """Lee recurso GTM completo, incluyendo fingerprint para cambios seguros."""
    root = _gtm_workspace(account_id, container_id, workspace_id)
    return _gtm("GET", f"{root}/{entity_type}/{_id(entity_id)}")


@mcp.tool
def gtm_get_workspace_status(account_id: str, container_id: str,
                             workspace_id: str) -> dict:
    """Detecta conflictos y cambios pendientes antes de crear una versión."""
    return _gtm("GET", _gtm_workspace(account_id, container_id, workspace_id) + "/status")


@mcp.tool
def gtm_get_live_version(account_id: str, container_id: str) -> dict:
    """Lee la versión actualmente publicada, sin modificar nada."""
    root = f"accounts/{_id(account_id)}/containers/{_id(container_id)}"
    return _gtm("GET", root + "/versions:live")


@mcp.tool
def gtm_list_versions(account_id: str, container_id: str) -> dict:
    """Lista historial de versiones para auditoría y rollback."""
    root = f"accounts/{_id(account_id)}/containers/{_id(container_id)}"
    return _gtm("GET", root + "/version_headers")


@mcp.tool
def gtm_prepare_change(account_id: str, container_id: str, workspace_id: str,
                       entity_type: Literal["tags", "triggers", "variables"],
                       operation: Literal["create", "update", "delete"],
                       entity: dict | None = None, entity_id: str | None = None) -> dict:
    """PREVISUALIZA un cambio GTM; no modifica Google. Presentar diff y esperar sí."""
    root = _gtm_workspace(account_id, container_id, workspace_id)
    path = f"{root}/{entity_type}"
    current = None
    if operation in ("update", "delete"):
        if not entity_id:
            raise ToolError("entity_id obligatorio en update/delete")
        path += f"/{_id(entity_id)}"
        current = _gtm("GET", path)
    if operation in ("create", "update"):
        if not isinstance(entity, dict) or not entity:
            raise ToolError("entity debe ser un objeto no vacío")
        if operation == "create" and (not entity.get("name") or not entity.get("type")):
            raise ToolError("CREATE requiere name y type")
        # GTM PUT replaces the whole resource. Preserve fields omitted by
        # the caller instead of accidentally wiping triggers/parameters.
        entity = {**current, **entity} if operation == "update" else dict(entity)
        if operation == "update":
            for fixed in ("path", "accountId", "containerId", "workspaceId"):
                if fixed in current:
                    entity[fixed] = current[fixed]
            entity["fingerprint"] = current.get("fingerprint")
            # The API requires existing identity; do not let a payload replace it.
            id_key = {"tags": "tagId", "triggers": "triggerId", "variables": "variableId"}[entity_type]
            entity[id_key] = _id(entity_id)
        else:
            # Google assigns these IDs at creation.
            for key in ("path", "tagId", "triggerId", "variableId", "fingerprint", "accountId", "containerId", "workspaceId"):
                entity.pop(key, None)
    details = {
        "category": "gtm_entity", "operation": operation, "path": path,
        "entity_type": entity_type, "entity": entity,
        "fingerprint": current.get("fingerprint") if current else None,
    }
    return {
        "operation": operation, "current": current, "proposed": entity if operation != "delete" else None,
        "approval_token": _make_ticket(details),
        "warning": "SOLO PREVISUALIZACIÓN. No se ha cambiado nada. Pide aprobación explícita.",
    }


@mcp.tool
def gtm_apply_change(approval_token: str, confirmation: str) -> dict:
    """Aplica cambio previamente previsualizado SOLO después de aprobación explícita."""
    _check_approval(confirmation)
    details = _decode_ticket(approval_token, "gtm_entity")
    operation, path, body = details["operation"], details["path"], details["entity"]
    fp = details["fingerprint"]
    if operation in ("update", "delete"):
        current = _gtm("GET", path)
        if current.get("fingerprint") != fp:
            raise ToolError("El recurso cambió desde el preview. No se ha modificado; vuelve a prepararlo.")
    if operation == "create":
        # Avoid accidental duplicates on retry.
        candidates = _gtm("GET", path).get(details["entity_type"], [])
        if any(item.get("name") == body["name"] for item in candidates):
            raise ToolError("Ya existe un recurso con ese nombre en el workspace; no se creará duplicado.")
        result = _gtm("POST", path, body=body)
    elif operation == "update":
        result = _gtm("PUT", path, body=body, params={"fingerprint": fp})
    else:
        result = _gtm("DELETE", path, params={"fingerprint": fp})
    return {"status": "applied_to_workspace", "operation": operation, "result": result,
            "published": False}


@mcp.tool
def gtm_prepare_version(account_id: str, container_id: str,
                        operation: Literal["create", "publish"],
                        workspace_id: str | None = None,
                        version_id: str | None = None,
                        name: str | None = None, notes: str = "") -> dict:
    """Previsualiza creación de versión o publicación; no ejecuta ninguna acción."""
    root = f"accounts/{_id(account_id)}/containers/{_id(container_id)}"
    if operation == "create":
        if not workspace_id or not name:
            raise ToolError("Para crear versión hacen falta workspace_id y name")
        path = f"{root}/workspaces/{_id(workspace_id)}:create_version"
        current = _gtm("GET", f"{root}/workspaces/{_id(workspace_id)}")
        status = _gtm("GET", f"{root}/workspaces/{_id(workspace_id)}/status")
        details = {"category": "gtm_version", "operation": "create", "path": path,
                   "body": {"name": name, "notes": notes},
                   "fingerprint": current.get("fingerprint")}
        preview = {"workspace": current, "status": status}
    else:
        if not version_id:
            raise ToolError("Para publicar hace falta version_id")
        path = f"{root}/versions/{_id(version_id)}:publish"
        version = _gtm("GET", f"{root}/versions/{_id(version_id)}")
        live = _gtm("GET", f"{root}/versions:live")
        details = {"category": "gtm_version", "operation": "publish", "path": path,
                   "body": None, "fingerprint": version.get("fingerprint"),
                   "version_path": f"{root}/versions/{_id(version_id)}"}
        preview = {"version_to_publish": version, "current_live": live}
    return {"preview": preview, "approval_token": _make_ticket(details),
            "warning": "Nada publicado ni creado. Requiere nueva aprobación explícita."}


@mcp.tool
def gtm_apply_version(approval_token: str, confirmation: str) -> dict:
    """Crea versión o publica en producción, solo después de confirmación explícita."""
    _check_approval(confirmation)
    d = _decode_ticket(approval_token, "gtm_version")
    if d["operation"] == "create":
        current = _gtm("GET", d["path"].split(":")[0])
        if current.get("fingerprint") != d["fingerprint"]:
            raise ToolError("Workspace actualizado desde preview; vuelve a preparar versión.")
        result = _gtm("POST", d["path"], body=d["body"])
        if result.get("compilerError"):
            raise ToolError("Google devolvió compilerError: versión no debe publicarse; revisa GTM.")
        return {"status": "version_created_not_published", "result": result}
    current = _gtm("GET", d["version_path"])
    if current.get("fingerprint") != d["fingerprint"]:
        raise ToolError("Versión diferente del preview; no publicada.")
    result = _gtm("POST", d["path"], params={"fingerprint": d["fingerprint"]})
    return {"status": "publish_attempt_result", "result": result,
            "compiler_error": result.get("compilerError", False)}


@mcp.tool
def ga4_list_properties() -> dict:
    """Lista cuentas y propiedades GA4 accesibles con Google OAuth."""
    return _admin("GET", "accountSummaries", params={"pageSize": 200})


@mcp.tool
def ga4_list_data_streams(property_id: str) -> dict:
    """Lista los flujos web/app de una propiedad GA4."""
    return _admin("GET", f"properties/{_id(property_id)}/dataStreams")


@mcp.tool
def ga4_list_key_events(property_id: str) -> dict:
    """Lee eventos clave (conversiones) configurados en GA4."""
    return _admin("GET", f"properties/{_id(property_id)}/keyEvents")


@mcp.tool
def ga4_list_custom_dimensions(property_id: str) -> dict:
    """Lista las dimensiones personalizadas disponibles en GA4."""
    return _admin("GET", f"properties/{_id(property_id)}/customDimensions")


@mcp.tool
def ga4_run_report(property_id: str, dimensions: list[str], metrics: list[str],
                   start_date: str = "28daysAgo", end_date: str = "yesterday",
                   limit: int = 100) -> dict:
    """Informe de GA4 Data API: canales, tráfico, sesiones, eventos, conversiones."""
    if not dimensions or not metrics or not 1 <= limit <= 10000:
        raise ToolError("Indica dimensiones, métricas y límite de 1 a 10000")
    if len(dimensions) > 9 or len(metrics) > 10:
        raise ToolError("Demasiadas dimensiones o métricas")
    body = {
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "limit": limit,
    }
    return _api("POST", DATA_BASE, f"properties/{_id(property_id)}:runReport", body=body)


@mcp.tool
def ga4_prepare_key_event(property_id: str, operation: Literal["create", "delete"],
                          event_name: str | None = None,
                          key_event_id: str | None = None) -> dict:
    """Previsualiza marcar o desmarcar evento clave GA4; NO escribe todavía."""
    root = f"properties/{_id(property_id)}/keyEvents"
    if operation == "create":
        if not event_name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", event_name):
            raise ToolError("Nombre de evento GA4 inválido")
        path, body = root, {"eventName": event_name}
        existing = _admin("GET", root)
        if any(e.get("eventName") == event_name for e in existing.get("keyEvents", [])):
            raise ToolError("El evento ya está marcado como evento clave.")
        current = None
    else:
        if not key_event_id or not re.fullmatch(r"[A-Za-z0-9_-]+", key_event_id):
            raise ToolError("Identificador de evento clave inválido")
        path, body = f"{root}/{key_event_id}", None
        current = _admin("GET", path)
    details = {"category": "ga4_key_event", "operation": operation, "path": path,
               "body": body, "current": current}
    return {"current": current, "proposed": body if operation == "create" else None,
            "approval_token": _make_ticket(details),
            "warning": "Vista previa; no se ha cambiado GA4. Solicita aprobación."}


@mcp.tool
def ga4_apply_key_event(approval_token: str, confirmation: str) -> dict:
    """Modifica el estado de evento clave GA4 tras aprobación explícita."""
    _check_approval(confirmation)
    d = _decode_ticket(approval_token, "ga4_key_event")
    if d["operation"] == "create":
        existing = _admin("GET", d["path"])
        if any(e.get("eventName") == d["body"]["eventName"] for e in existing.get("keyEvents", [])):
            raise ToolError("Ya existe este evento clave. No se creará duplicado.")
        result = _admin("POST", d["path"], body=d["body"])
    else:
        now = _admin("GET", d["path"])
        if now != d["current"]:
            raise ToolError("Evento clave cambió desde preview. No se modificó.")
        result = _admin("DELETE", d["path"])
    return {"status": "applied", "operation": d["operation"], "result": result}


def main() -> None:
    if _client_id:
        mcp.run(transport="streamable-http", host="0.0.0.0",
                port=int(os.getenv("PORT", "8080")),
                uvicorn_config={"access_log": False})
    else:
        mcp.run()


if __name__ == "__main__":
    main()
