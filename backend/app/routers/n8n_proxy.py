import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from app.auth import get_current_user, require_operator
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/proxy/n8n", tags=["n8n-proxy"])

_N8N_TIMEOUT = 10.0


def _n8n_headers() -> dict:
    if not settings.n8n_api_key:
        raise HTTPException(status_code=503, detail="n8n API key not configured")
    return {"X-N8N-API-KEY": settings.n8n_api_key, "Content-Type": "application/json"}


@router.get("/workflows", summary="List workflows from n8n")
def list_n8n_workflows(
    _: User = Depends(get_current_user),
):
    try:
        resp = httpx.get(
            f"{settings.n8n_base_url}/api/v1/workflows",
            headers=_n8n_headers(),
            timeout=_N8N_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="n8n unavailable: timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="n8n error")
    except Exception:
        raise HTTPException(status_code=503, detail="n8n unavailable")


@router.get("/workflows/{workflow_id}", summary="Get a single n8n workflow")
def get_n8n_workflow(
    workflow_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    _: User = Depends(get_current_user),
):
    try:
        resp = httpx.get(
            f"{settings.n8n_base_url}/api/v1/workflows/{workflow_id}",
            headers=_n8n_headers(),
            timeout=_N8N_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="n8n unavailable: timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="n8n error")
    except Exception:
        raise HTTPException(status_code=503, detail="n8n unavailable")


@router.post("/workflows/{workflow_id}/execute", summary="Trigger an n8n workflow execution")
def execute_n8n_workflow(
    workflow_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    _: User = Depends(require_operator),
):
    try:
        resp = httpx.post(
            f"{settings.n8n_base_url}/api/v1/executions",
            headers=_n8n_headers(),
            json={"workflowId": workflow_id},
            timeout=_N8N_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"status": "triggered", "workflow_id": workflow_id, "execution": data}
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="n8n unavailable: timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="n8n error")
    except Exception:
        raise HTTPException(status_code=503, detail="n8n unavailable")


@router.post("/workflows/{workflow_id}/activate", summary="Activate an n8n workflow")
def activate_n8n_workflow(
    workflow_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    _: User = Depends(require_operator),
):
    try:
        resp = httpx.post(
            f"{settings.n8n_base_url}/api/v1/workflows/{workflow_id}/activate",
            headers=_n8n_headers(),
            timeout=_N8N_TIMEOUT,
        )
        resp.raise_for_status()
        return {"status": "activated", "workflow_id": workflow_id}
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="n8n unavailable: timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="n8n error")
    except Exception:
        raise HTTPException(status_code=503, detail="n8n unavailable")


@router.post("/workflows/{workflow_id}/deactivate", summary="Deactivate an n8n workflow")
def deactivate_n8n_workflow(
    workflow_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,64}$"),
    _: User = Depends(require_operator),
):
    try:
        resp = httpx.post(
            f"{settings.n8n_base_url}/api/v1/workflows/{workflow_id}/deactivate",
            headers=_n8n_headers(),
            timeout=_N8N_TIMEOUT,
        )
        resp.raise_for_status()
        return {"status": "deactivated", "workflow_id": workflow_id}
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="n8n unavailable: timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="n8n error")
    except Exception:
        raise HTTPException(status_code=503, detail="n8n unavailable")
