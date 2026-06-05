"""User management (admin only).

CRUD on the `users` table backing JWT auth. Self-destruct and last-admin
deletion are blocked so the system never locks itself out.
"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/admin/users", tags=["users"])

_VALID_ROLES = {"admin", "operator", "readonly"}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._\-]{3,64}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _check_email(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email")
    return v


class UserOut(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[str] = None

    @classmethod
    def from_orm_user(cls, u: User) -> "UserOut":
        return cls(
            id=str(u.id),
            username=u.username or "",
            email=u.email,
            role=u.role or "readonly",
            is_active=bool(u.is_active),
            created_at=u.created_at.isoformat() if u.created_at else None,
        )


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    role: str = Field("readonly")
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return _check_email(v) or v


class UserUpdate(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: Optional[str]) -> Optional[str]:
        return _check_email(v)


def _normalize_role(role: str) -> str:
    r = (role or "").strip().lower()
    if r == "viewer":  # legacy alias
        r = "readonly"
    if r not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {sorted(_VALID_ROLES)}")
    return r


def _audit(db: Session, level: str, message: str, current_user: User, target_id) -> None:
    db.add(AuditLog(
        level=level,
        source="admin_users",
        message=message,
        entity_id=target_id,
        entity_type="user",
        user_id=current_user.username,
    ))


@router.get("", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc().nullslast(), User.username.asc()).all()
    return [UserOut.from_orm_user(u) for u in users]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not _USERNAME_RE.match(payload.username):
        raise HTTPException(status_code=400, detail="username must be 3-64 chars, [A-Za-z0-9._-]")
    role = _normalize_role(payload.role)

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="username already exists")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    _audit(db, "INFO", f"User created: {user.username} ({role})", current_user, user.id)
    db.commit()
    db.refresh(user)
    return UserOut.from_orm_user(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    payload: UserUpdate,
    user_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    changes: List[str] = []
    if payload.email and payload.email != user.email:
        if db.query(User).filter(User.email == payload.email, User.id != user.id).first():
            raise HTTPException(status_code=409, detail="email already in use")
        user.email = payload.email
        changes.append("email")
    if payload.role is not None:
        new_role = _normalize_role(payload.role)
        if new_role != user.role:
            # Don't let the last admin demote themselves out of admin.
            if user.role == "admin" and new_role != "admin":
                admins_left = db.query(User).filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
                if admins_left == 0:
                    raise HTTPException(status_code=400, detail="cannot demote the last active admin")
            user.role = new_role
            changes.append(f"role→{new_role}")
    if payload.is_active is not None and bool(payload.is_active) != bool(user.is_active):
        if user.role == "admin" and not payload.is_active:
            admins_left = db.query(User).filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
            if admins_left == 0:
                raise HTTPException(status_code=400, detail="cannot deactivate the last active admin")
        user.is_active = bool(payload.is_active)
        changes.append("active" if user.is_active else "deactivated")
    if payload.password:
        user.hashed_password = hash_password(payload.password)
        changes.append("password")

    if changes:
        _audit(db, "INFO", f"User updated ({user.username}): {', '.join(changes)}", current_user, user.id)
    db.commit()
    db.refresh(user)
    return UserOut.from_orm_user(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    if user.role == "admin":
        admins_left = db.query(User).filter(User.role == "admin", User.is_active.is_(True), User.id != user.id).count()
        if admins_left == 0:
            raise HTTPException(status_code=400, detail="cannot delete the last active admin")

    _audit(db, "WARN", f"User deleted: {user.username}", current_user, user.id)
    db.delete(user)
    db.commit()
    return None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(require_admin)):
    """Admin's own row — useful for the UI to disable destructive actions on self."""
    return UserOut.from_orm_user(current_user)
