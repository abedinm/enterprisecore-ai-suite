from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.init_db import MODULE_CATALOG
from app.db.session import get_db
from app.models.finance import Expense, Invoice
from app.models.hr import Employee
from app.models.projects import Project, Task
from app.models.user import Notification, User

router = APIRouter()


@router.get("")
def dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoices_total = db.scalar(select(func.coalesce(func.sum(Invoice.total), 0))) or 0
    expenses_total = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0))) or 0
    return {
        "user": {"name": current_user.full_name, "role": current_user.role.value},
        "kpis": [
            {"label": "Revenue", "value": float(invoices_total), "format": "currency"},
            {"label": "Expenses", "value": float(expenses_total), "format": "currency"},
            {"label": "Employees", "value": db.scalar(select(func.count(Employee.id))) or 0, "format": "number"},
            {"label": "Open Tasks", "value": db.scalar(select(func.count(Task.id)).where(Task.status != "done")) or 0, "format": "number"},
        ],
        "modules": MODULE_CATALOG,
        "projects": db.scalar(select(func.count(Project.id))) or 0,
        "unread_notifications": db.scalar(select(func.count(Notification.id)).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))) or 0,
        "offline_ready": True,
    }
