from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.system import System


def get_system(system_slug: str, db: Session = Depends(get_db)) -> System:
    system = db.query(System).filter(System.slug == system_slug, System.is_active == True).first()
    if not system:
        raise HTTPException(status_code=404, detail=f"System '{system_slug}' not found")
    return system
