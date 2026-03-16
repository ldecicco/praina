from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.schemas.my_work import MyWorkResponse
from app.services.my_work_service import MyWorkService

router = APIRouter()


@router.get("/my-work", response_model=MyWorkResponse)
def my_work(
    include_closed: bool = Query(default=False),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyWorkResponse:
    service = MyWorkService(db, current_user.id)
    return service.get_my_work(include_closed=include_closed)
