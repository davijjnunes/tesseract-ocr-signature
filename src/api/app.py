from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.config import STATIC_DIR
from src.api.routers import pages, signature

app = FastAPI(title="Verificação de assinatura")

app.include_router(pages.router)
app.include_router(signature.router)

# por último: serve style.css e main.js sem tomar o lugar das rotas acima
app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
