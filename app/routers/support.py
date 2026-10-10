from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_admin
from app.models import TicketStatus

router = APIRouter(prefix="/support", tags=["Support"])


@router.post("/tickets", response_model=schemas.TicketOut)
def create_ticket(payload: schemas.TicketCreate, db: Session = Depends(get_db)):
    """Open to anyone — a user or merchant filing an issue shouldn't need admin credentials."""
    ticket = models.SupportTicket(**payload.dict())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/tickets", response_model=list[schemas.TicketOut])
def list_tickets(status: TicketStatus = None, db: Session = Depends(get_db),
                  current_admin: models.Admin = Depends(get_current_admin)):
    q = db.query(models.SupportTicket)
    if status:
        q = q.filter(models.SupportTicket.status == status)
    return q.order_by(models.SupportTicket.created_at.desc()).all()


@router.post("/tickets/{ticket_id}/investigate", response_model=schemas.TicketOut)
def investigate_ticket(ticket_id: str, db: Session = Depends(get_db),
                        current_admin: models.Admin = Depends(get_current_admin)):
    ticket = db.query(models.SupportTicket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    ticket.status = TicketStatus.investigating
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/resolve", response_model=schemas.TicketOut)
def resolve_ticket(ticket_id: str, payload: schemas.TicketResolve, db: Session = Depends(get_db),
                    current_admin: models.Admin = Depends(get_current_admin)):
    ticket = db.query(models.SupportTicket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    ticket.status = TicketStatus.resolved
    ticket.resolution_note = payload.resolution_note
    db.commit()
    db.refresh(ticket)
    return ticket
