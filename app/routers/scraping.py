from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.scraping_schema import ScrapingStatusRead
from app.services.scraping_status_service import get_scraping_status


router = APIRouter(prefix="/scraping", tags=["scraping"])


@router.get("/status", response_model=ScrapingStatusRead)
def read_scraping_status(db: Session = Depends(get_db)) -> ScrapingStatusRead:
    return get_scraping_status(db)
