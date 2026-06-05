"""Meeting-prep file explorer + uploader — fully Supabase-backed.

Every folder and file lives in the `strategy_assets` table on the ops DB. The
configured `MEET_DIR` (disk) is only used as a one-shot seed source: when
the table is empty AND the directory has content, we walk it once and import.
After that, all CRUD goes to the DB and survives container/volume churn.

Endpoints
  GET    /admin/meets/strategies          → flat list (legacy compat)
  GET    /admin/meets/tree                → nested tree, single root
  GET    /admin/meets/strategy/{path}     → read a text file
  GET    /admin/meets/download/{path}     → any file → bytes
  POST   /admin/meets/upload              → multipart files
  POST   /admin/meets/folder              → empty folder
  DELETE /admin/meets/{path}              → file or folder (recursive)
  POST   /admin/meets/sync                → admin-only: re-walk MEET_DIR and
                                          insert anything missing (idempotent)
"""
import io
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, defer

from app.auth import require_admin
from app.config import settings
from app.database import engine, get_db
from app.models.meet_asset import MeetAsset
from app.models.user import User
from app.schemas.responses import (
    StrategyContent,
    StrategyFile,
    StrategyTreeNode,
    StrategyUploadResult,
)

router = APIRouter(prefix="/admin/meets", tags=["meet-prep"])

# The single user-visible root in the tree.
ROOT_LABEL = "Meet Prep"

_TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}
_ALLOWED_UPLOAD = {
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv",
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".zip", ".log",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-\s]")

# Used only during the one-shot disk seed.
_SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    ".next", ".nuxt", ".turbo", ".cache", ".vite",
    "dist", "build", "out", "coverage",
    ".idea", ".vscode",
}
_SEED_MAX_DEPTH = 6
_SEED_MAX_PER_DIR = 250

# Ensure the table exists at import time (cheap, idempotent).
try:
    MeetAsset.__table__.create(bind=engine, checkfirst=True)
except Exception:  # pragma: no cover — db may be unreachable at import time
    pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sanitize_name(name: str) -> str:
    n = _SAFE_NAME_RE.sub("", (name or "").strip())
    n = n.lstrip(".")
    return n[:200] or "untitled"


def _sanitize_relpath(rel: str) -> str:
    if not rel:
        return ""
    parts = []
    for seg in rel.replace("\\", "/").split("/"):
        seg = seg.strip()
        if not seg or seg in (".", ".."):
            continue
        parts.append(_sanitize_name(seg))
    return "/".join(parts)


def _is_text_name(name: str) -> bool:
    return Path(name).suffix.lower() in _TEXT_EXTENSIONS


def _strip_root_prefix(path: str) -> str:
    """`GTM Strategy/foo/bar` → `foo/bar`. Empty when path == root."""
    p = path.replace("\\", "/")
    if p == ROOT_LABEL:
        return ""
    prefix = f"{ROOT_LABEL}/"
    if not p.startswith(prefix):
        raise HTTPException(status_code=400, detail=f"Path must start with '{ROOT_LABEL}/'")
    return p[len(prefix):]


def _asset_node(a: MeetAsset, children: Optional[List[StrategyTreeNode]] = None) -> StrategyTreeNode:
    return StrategyTreeNode(
        name=a.name,
        type="folder" if a.is_folder else "file",
        path=f"{ROOT_LABEL}/{a.relative_path}",
        size_bytes=a.size_bytes or 0,
        modified_at=a.updated_at,
        is_text=(not a.is_folder) and _is_text_name(a.name),
        children=children,
    )


def _build_tree(db: Session) -> StrategyTreeNode:
    # Defer the content BLOB — we only need metadata for the tree.
    rows: List[MeetAsset] = (
        db.query(MeetAsset).options(defer(MeetAsset.content)).all()
    )
    by_parent: dict = {}
    for r in rows:
        by_parent.setdefault(r.parent_path or "", []).append(r)

    def build(parent: str) -> List[StrategyTreeNode]:
        sorted_kids = sorted(
            by_parent.get(parent, []),
            key=lambda a: (not a.is_folder, a.name.lower()),
        )
        out = []
        for a in sorted_kids:
            kids = build(a.relative_path) if a.is_folder else None
            out.append(_asset_node(a, kids))
        return out

    return StrategyTreeNode(
        name=ROOT_LABEL,
        type="folder",
        path=ROOT_LABEL,
        size_bytes=0,
        modified_at=None,
        is_text=False,
        children=build(""),
    )


def _ensure_parents(db: Session, rel_path: str, uploader: str) -> None:
    """Create folder rows for every ancestor of `rel_path`."""
    if not rel_path or "/" not in rel_path:
        return
    parts = rel_path.split("/")[:-1]
    accum = ""
    for seg in parts:
        accum = f"{accum}/{seg}" if accum else seg
        existing = db.query(MeetAsset).filter(MeetAsset.relative_path == accum).first()
        if existing:
            if not existing.is_folder:
                raise HTTPException(status_code=409, detail=f"`{accum}` exists as a file")
            continue
        parent = "/".join(accum.split("/")[:-1])
        db.add(MeetAsset(
            relative_path=accum,
            parent_path=parent,
            name=accum.split("/")[-1],
            is_folder=True,
            mime_type="inode/directory",
            uploaded_by=uploader,
        ))


# ─── Disk → DB seed ──────────────────────────────────────────────────────────

def _disk_seed_roots() -> List[Path]:
    """Roots configured in MEET_DIR — used only for the one-shot seed."""
    out: List[Path] = []
    if not settings.meet_dir:
        return out
    for d in settings.meet_dir.split(";"):
        p = Path(d.strip())
        if p.exists() and p.is_dir():
            out.append(p)
    return out


def _seed_from_disk(db: Session, *, uploader: str = "system_seed") -> int:
    """Walk every MEET_DIR root and insert missing assets. Returns # rows added.

    The walk may produce duplicate folder paths (multiple roots; parent
    rebuilds). We dedupe via an in-memory `seen` set seeded with the rows
    already in the DB.
    """
    roots = _disk_seed_roots()
    if not roots:
        return 0

    seen: set = {
        r[0] for r in db.query(MeetAsset.relative_path).all()
    }

    def _add_folder(rel_sane: str) -> int:
        if not rel_sane or rel_sane in seen:
            return 0
        # ensure ancestors first
        accum = ""
        ancestors_added = 0
        for seg in rel_sane.split("/")[:-1]:
            accum = f"{accum}/{seg}" if accum else seg
            if accum in seen:
                continue
            parent = "/".join(accum.split("/")[:-1])
            db.add(MeetAsset(
                relative_path=accum,
                parent_path=parent,
                name=accum.split("/")[-1],
                is_folder=True,
                mime_type="inode/directory",
                uploaded_by=uploader,
            ))
            seen.add(accum)
            ancestors_added += 1
        parent = "/".join(rel_sane.split("/")[:-1])
        db.add(MeetAsset(
            relative_path=rel_sane,
            parent_path=parent,
            name=rel_sane.split("/")[-1],
            is_folder=True,
            mime_type="inode/directory",
            uploaded_by=uploader,
        ))
        seen.add(rel_sane)
        return ancestors_added + 1

    added = 0
    for root in roots:
        for current, dirs, files in os.walk(root):
            cur_path = Path(current)
            depth = len(cur_path.relative_to(root).parts)
            if depth >= _SEED_MAX_DEPTH:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            dirs.sort(key=str.lower)
            files = sorted(files, key=str.lower)[:_SEED_MAX_PER_DIR]

            if cur_path != root:
                rel_sane = _sanitize_relpath(cur_path.relative_to(root).as_posix())
                added += _add_folder(rel_sane)

            for fname in files:
                if fname.startswith("."):
                    continue
                ext = Path(fname).suffix.lower()
                if ext not in _ALLOWED_UPLOAD:
                    continue
                fpath = cur_path / fname
                try:
                    if fpath.stat().st_size > _MAX_UPLOAD_BYTES:
                        continue
                except OSError:
                    continue
                rel_sane = _sanitize_relpath(fpath.relative_to(root).as_posix())
                if not rel_sane or rel_sane in seen:
                    continue
                try:
                    data = fpath.read_bytes()
                except OSError:
                    continue
                # ensure ancestor folders for the file
                accum = ""
                for seg in rel_sane.split("/")[:-1]:
                    accum = f"{accum}/{seg}" if accum else seg
                    if accum in seen:
                        continue
                    parent = "/".join(accum.split("/")[:-1])
                    db.add(MeetAsset(
                        relative_path=accum,
                        parent_path=parent,
                        name=accum.split("/")[-1],
                        is_folder=True,
                        mime_type="inode/directory",
                        uploaded_by=uploader,
                    ))
                    seen.add(accum)
                    added += 1
                parent = "/".join(rel_sane.split("/")[:-1])
                mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
                db.add(MeetAsset(
                    relative_path=rel_sane,
                    parent_path=parent,
                    name=rel_sane.split("/")[-1],
                    is_folder=False,
                    mime_type=mime,
                    size_bytes=len(data),
                    content=data,
                    uploaded_by=uploader,
                ))
                seen.add(rel_sane)
                added += 1
    db.commit()
    return added


def _ensure_seeded(db: Session) -> None:
    """Seed on first access — only when the DB is empty and a disk root is configured."""
    if db.query(MeetAsset).limit(1).count() > 0:
        return
    _seed_from_disk(db)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/strategies", response_model=List[StrategyFile])
def list_strategies(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> List[StrategyFile]:
    _ensure_seeded(db)
    out: List[StrategyFile] = []
    for a in db.query(MeetAsset).options(defer(MeetAsset.content)).filter(MeetAsset.is_folder.is_(False)).all():
        if not _is_text_name(a.name):
            continue
        directory = f"{ROOT_LABEL}/{a.parent_path}" if a.parent_path else ROOT_LABEL
        out.append(StrategyFile(
            name=a.name,
            directory=directory,
            path=f"{ROOT_LABEL}/{a.relative_path}",
            modified_at=a.updated_at,
            size_bytes=a.size_bytes or 0,
        ))
    return sorted(out, key=lambda f: f.path)


@router.get("/tree", response_model=List[StrategyTreeNode])
def get_tree(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> List[StrategyTreeNode]:
    _ensure_seeded(db)
    return [_build_tree(db)]


@router.get("/strategy/{path:path}", response_model=StrategyContent)
def get_strategy(
    path: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StrategyContent:
    rel = _strip_root_prefix(path)
    asset = db.query(MeetAsset).filter(MeetAsset.relative_path == rel).first()
    if not asset or asset.is_folder:
        raise HTTPException(status_code=404, detail="Strategy file not found")
    if not _is_text_name(asset.name):
        raise HTTPException(status_code=400, detail="File type not previewable — use /download")
    content = (asset.content or b"").decode("utf-8", errors="replace")
    return StrategyContent(path=path, name=asset.name, content=content)


@router.get("/download/{path:path}")
def download_strategy(
    path: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rel = _strip_root_prefix(path)
    asset = db.query(MeetAsset).filter(MeetAsset.relative_path == rel).first()
    if not asset or asset.is_folder:
        raise HTTPException(status_code=404, detail="File not found")
    return StreamingResponse(
        io.BytesIO(asset.content or b""),
        media_type=asset.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{asset.name}"'},
    )


@router.post("/upload", response_model=StrategyUploadResult)
async def upload_files(
    files: List[UploadFile] = File(...),
    folder: str = Form(""),
    paths: List[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> StrategyUploadResult:
    """Save uploaded files into Supabase.

    - `folder`: optional sub-path (with or without `GTM Strategy/` prefix).
    - `paths[]`: per-file relative path from `webkitRelativePath` (folder upload).
    """
    if folder:
        if folder.startswith(f"{ROOT_LABEL}/"):
            folder = folder[len(ROOT_LABEL) + 1:]
        elif folder == ROOT_LABEL:
            folder = ""
    safe_folder = _sanitize_relpath(folder)

    uploaded: List[str] = []
    skipped: List[str] = []

    for idx, f in enumerate(files):
        rel_in = (paths[idx] if idx < len(paths) else "").replace("\\", "/").lstrip("/")
        if "/" in rel_in:
            sub_dir, name = rel_in.rsplit("/", 1)
            sub_dir = _sanitize_relpath(sub_dir)
        else:
            sub_dir, name = "", rel_in or (f.filename or "")
        name = _sanitize_name(name or f.filename or "")
        if not name:
            skipped.append(f.filename or "<unnamed>")
            continue
        if Path(name).suffix.lower() not in _ALLOWED_UPLOAD:
            skipped.append(name)
            continue

        parts = [p for p in (safe_folder, sub_dir) if p]
        rel_dir = "/".join(parts)
        rel_path = f"{rel_dir}/{name}" if rel_dir else name

        data = await f.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            skipped.append(f"{name} (too large)")
            continue

        try:
            _ensure_parents(db, rel_path, user.username)
            existing = db.query(MeetAsset).filter(MeetAsset.relative_path == rel_path).first()
            mime = f.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
            if existing:
                if existing.is_folder:
                    skipped.append(f"{name} (folder with same name)")
                    continue
                existing.content = data
                existing.size_bytes = len(data)
                existing.mime_type = mime
                existing.uploaded_by = user.username
            else:
                db.add(MeetAsset(
                    relative_path=rel_path,
                    parent_path=rel_dir,
                    name=name,
                    is_folder=False,
                    mime_type=mime,
                    size_bytes=len(data),
                    content=data,
                    uploaded_by=user.username,
                ))
            uploaded.append(f"{ROOT_LABEL}/{rel_path}")
        except HTTPException:
            db.rollback()
            skipped.append(name)
            continue

    db.commit()
    folder_display = f"{ROOT_LABEL}/{safe_folder}" if safe_folder else ROOT_LABEL
    return StrategyUploadResult(uploaded=uploaded, skipped=skipped, folder=folder_display)


@router.post("/folder", response_model=StrategyTreeNode)
def create_folder(
    path: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> StrategyTreeNode:
    rel = _sanitize_relpath(_strip_root_prefix(path))
    if not rel:
        raise HTTPException(status_code=400, detail="Folder name required")
    existing = db.query(MeetAsset).filter(MeetAsset.relative_path == rel).first()
    if existing:
        if existing.is_folder:
            return _asset_node(existing, [])
        raise HTTPException(status_code=409, detail="A file with that name already exists")
    # _ensure_parents creates ancestor folders only — never the leaf — because it
    # iterates `rel.split("/")[:-1]`. We then add the leaf folder ourselves.
    _ensure_parents(db, rel, user.username)
    parent = "/".join(rel.split("/")[:-1])
    asset = MeetAsset(
        relative_path=rel,
        parent_path=parent,
        name=rel.split("/")[-1],
        is_folder=True,
        mime_type="inode/directory",
        uploaded_by=user.username,
    )
    db.add(asset)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Create folder failed: {exc.__class__.__name__}: {exc}")
    db.refresh(asset)
    return _asset_node(asset, [])


@router.delete("/{path:path}")
def delete_node(
    path: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Delete a file or an entire folder (recursive). Admin-only."""
    try:
        rel = _strip_root_prefix(path)
    except HTTPException:
        raise
    if not rel:
        raise HTTPException(status_code=400, detail="Cannot delete the root")

    asset = db.query(MeetAsset).filter(MeetAsset.relative_path == rel).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset not found: {rel}")

    is_folder = bool(asset.is_folder)
    affected = 0
    try:
        if is_folder:
            # Escape LIKE meta-chars so names with '_' or '%' don't act as wildcards.
            escaped = rel.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            affected = (
                db.query(MeetAsset)
                .filter(
                    (MeetAsset.relative_path == rel)
                    | (MeetAsset.relative_path.like(f"{escaped}/%", escape="\\"))
                )
                .delete(synchronize_session=False)
            )
        else:
            db.delete(asset)
            affected = 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc.__class__.__name__}: {exc}")

    return {"deleted": path, "type": "folder" if is_folder else "file", "affected": affected}


@router.post("/sync")
def sync_from_disk(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Re-walk every MEET_DIR root and add anything not yet in the DB."""
    added = _seed_from_disk(db, uploader="manual_sync")
    total = db.query(MeetAsset).count()
    return {"added": added, "total_assets": total, "roots": [str(p) for p in _disk_seed_roots()]}
