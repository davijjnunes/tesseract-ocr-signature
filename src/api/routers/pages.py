from fastapi import APIRouter
from fastapi.responses import FileResponse

from src.api.config import STATIC_DIR

router = APIRouter(tags=["páginas"])


@router.get("/")
def index_page():
    return FileResponse(STATIC_DIR / "index.html")
