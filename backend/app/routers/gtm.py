import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.config import settings
from app.models.user import User
from app.schemas.responses import StrategyContent, StrategyFile

router = APIRouter(prefix="/admin/gtm", tags=["gtm-strategy"])

_ALLOWED_EXTENSIONS = {".md", ".txt"}
_STRATEGY_DIRS: List[tuple] = []


def _get_strategy_dirs() -> List[tuple]:
    """Returns list of (prefix, Path) for all strategy directories."""
    global _STRATEGY_DIRS
    if _STRATEGY_DIRS:
        return _STRATEGY_DIRS

    project_root = Path(__file__).resolve().parents[3]
    dirs = []

    if settings.strategy_dir:
        for d in settings.strategy_dir.split(";"):
            p = Path(d.strip())
            if p.exists():
                dirs.append((p.name, p))

    final_planning = project_root / "Final planning"
    if final_planning.exists():
        dirs.append(("Final planning", final_planning))

    if not dirs:
        dirs.append(("strategies", project_root))

    _STRATEGY_DIRS = dirs
    return _STRATEGY_DIRS


def _is_safe_path(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


@router.get("/strategies", response_model=List[StrategyFile])
def list_strategies(
    _: User = Depends(get_current_user),
):
    files: List[StrategyFile] = []
    for prefix, base in _get_strategy_dirs():
        if not base.exists():
            continue
        for root, _dirs, filenames in os.walk(base):
            for fname in sorted(filenames):
                fpath = Path(root) / fname
                if fpath.suffix.lower() not in _ALLOWED_EXTENSIONS:
                    continue
                rel = fpath.relative_to(base)
                display_path = f"{prefix}/{rel}".replace("\\", "/")
                directory = str(rel.parent) if str(rel.parent) != "." else ""
                if directory:
                    directory = f"{prefix}/{directory}"
                else:
                    directory = prefix
                files.append(StrategyFile(
                    name=fname,
                    directory=directory,
                    path=display_path,
                    modified_at=datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc),
                    size_bytes=fpath.stat().st_size,
                ))

    return sorted(files, key=lambda f: f.path)


@router.get("/strategy/{path:path}", response_model=StrategyContent)
def get_strategy(
    path: str,
    _: User = Depends(get_current_user),
):
    for prefix, base in _get_strategy_dirs():
        if not path.startswith(prefix + "/"):
            continue
        rel_path = path[len(prefix) + 1:]
        target = base / rel_path
        if not _is_safe_path(base, target):
            raise HTTPException(status_code=400, detail="Invalid path")
        if target.exists() and target.is_file():
            if target.suffix.lower() not in _ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail="File type not allowed")
            content = target.read_text(encoding="utf-8", errors="replace")
            return StrategyContent(path=path, name=target.name, content=content)

    raise HTTPException(status_code=404, detail="Strategy file not found")
