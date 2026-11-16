import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from ollama import ResponseError
from pydantic import ValidationError

from src.api.config import (
    ANCORA,
    CROPS_DIR,
    LOG_FILE,
    MODEL,
    OCR_CONFIG,
    OCR_LANG,
    TAMANHO_MAXIMO,
    TIPOS_PERMITIDOS,
)
from src.schemas.signature import (
    AnalysisDetails,
    SignatureDetection,
    SignatureDetectionResponse,
)
from src.services.image_service import decode_image, encode_png, resize_max, upscale_min
from src.services.ollama_service import SYSTEM_PROMPT, USER_PROMPT, ollama_ask
from src.services.tesseract_service import crop_signature

router = APIRouter(prefix="/signature-detections", tags=["signature-detections"])

# grava no terminal do uvicorn e em logs/signature.log
CROPS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("signature")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ):
        handler.setFormatter(formatter)
        logger.addHandler(handler)


@router.post("", response_model=SignatureDetectionResponse)
async def detect_signature(
    image: Annotated[UploadFile, File()],
) -> SignatureDetectionResponse:
    """Recebe o documento inteiro e responde se ele tem assinatura manuscrita."""
    name = (
        image.filename or "sem-nome"
    )  # identifica as linhas de log de cada requisição
    logger.info("[%s] Recebido (%s)", name, image.content_type)
    if image.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=415, detail="Envie uma imagem PNG, JPG ou WEBP."
        )

    # lê 1 byte além do limite: se vier, o arquivo é grande demais
    content = await image.read(TAMANHO_MAXIMO + 1)
    if len(content) > TAMANHO_MAXIMO:
        raise HTTPException(status_code=413, detail="A imagem passa de 10 MB.")

    # 1. Pegar a imagem: bytes -> array do OpenCV
    try:
        page = decode_image(content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    # 2. Recorte com Tesseract (bloqueia: roda numa thread)
    crops = await run_in_threadpool(
        crop_signature, page, (ANCORA,), OCR_LANG, OCR_CONFIG
    )
    logger.info(
        "[%s] Imagem %sx%s, recortes: %d",
        name,
        page.shape[1],
        page.shape[0],
        len(crops),
    )
    if not crops:
        logger.warning("[%s] Âncora não encontrada: respondendo 422", name)
        raise HTTPException(
            status_code=422, detail="Região da assinatura não encontrada."
        )

    def build_response(tem_assinatura: bool) -> SignatureDetectionResponse:
        return SignatureDetectionResponse(
            nome_arquivo=image.filename or "",
            ocr_recorte_modelo_usado=AnalysisDetails(
                ocr=f"tesseract ({OCR_LANG}, {OCR_CONFIG})",
                ancora=ANCORA,
                recortes=len(crops),
                modelo=MODEL,
            ),
            tem_assinatura=tem_assinatura,
        )

    # 3. Perguntar ao Ollama sobre cada recorte
    for n, crop in enumerate(crops):
        crop_png = resize_max(encode_png(upscale_min(crop)))
        crop_path = CROPS_DIR / f"{Path(name).stem}_{n}.png"
        crop_path.write_bytes(crop_png)  # exatamente o que vai para o modelo
        logger.info("[%s] Recorte %d salvo em %s", name, n, crop_path)
        try:
            response = await run_in_threadpool(
                ollama_ask,
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT, "images": [crop_png]},
                ],
                format=SignatureDetection.model_json_schema(),
            )
            logger.info(
                "[%s] Recorte %d: Ollama respondeu %s",
                name,
                n,
                response.message.content,
            )
            answer = SignatureDetection.model_validate_json(
                response.message.content or ""
            )
        except (ResponseError, ConnectionError) as error:
            logger.error("[%s] Erro no Ollama: %s", name, error)
            raise HTTPException(
                status_code=502, detail=f"Erro no Ollama: {error}"
            ) from error
        except ValidationError as error:
            logger.error("[%s] Resposta inválida do modelo: %s", name, error)
            raise HTTPException(
                status_code=502, detail="Resposta inválida do modelo."
            ) from error

        # 4. Retornar true/false: basta um recorte com assinatura
        if answer.has_signature:
            logger.info("[%s] Resultado: tem_assinatura=true", name)
            return build_response(True)

    logger.info("[%s] Resultado: tem_assinatura=false", name)
    return build_response(False)
