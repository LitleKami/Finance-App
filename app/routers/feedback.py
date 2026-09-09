from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", response_model=schemas.FeedbackOut)
def create_feedback(payload: schemas.FeedbackCreate, db: Session = Depends(get_db)):
    if not (1 <= payload.rating <= 5):
        raise HTTPException(400, "Rating must be between 1 and 5")
    fb = models.Feedback(**payload.dict())
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb
