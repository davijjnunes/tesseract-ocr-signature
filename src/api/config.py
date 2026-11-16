from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # src/
STATIC_DIR = BASE_DIR / "views" / "static"

OLLAMA_HOST = "http://localhost:11434"
MODEL = "qwen2.5vl:3b"

# OCR e recorte: a assinatura fica acima da âncora
OCR_LANG = "por"
OCR_CONFIG = "--psm 6"
ANCORA = "Diretora"

TIPOS_PERMITIDOS = {"image/png", "image/jpeg", "image/webp"}
TAMANHO_MAXIMO = 10 * 1024 * 1024  # 10 MB

LOG_FILE = BASE_DIR.parent / "logs" / "signature.log"
CROPS_DIR = LOG_FILE.parent / "recortes"  # cada recorte enviado ao modelo
