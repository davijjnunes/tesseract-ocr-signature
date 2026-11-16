from pydantic import BaseModel, Field


class SignatureDetection(BaseModel):
    """Formato que o modelo de visão deve devolver (enviado ao Ollama)."""

    has_signature: bool = Field(
        description="True se o documento tem assinatura manuscrita.",
    )


class AnalysisDetails(BaseModel):
    """Como a análise foi feita: OCR, recorte e modelo."""

    ocr: str = Field(description="Motor de OCR, idioma e configuração.")
    ancora: str = Field(description="Palavra usada para localizar a assinatura.")
    recortes: int = Field(description="Quantos recortes foram enviados ao modelo.")
    modelo: str = Field(description="Modelo de visão do Ollama.")


class SignatureDetectionResponse(BaseModel):
    """Resposta do POST /signature-detections."""

    nome_arquivo: str = Field(description="Nome do arquivo enviado.")
    ocr_recorte_modelo_usado: AnalysisDetails
    tem_assinatura: bool = Field(
        description="True se o documento tem assinatura manuscrita.",
    )
