import base64
import mimetypes
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def image_to_base_64(image_path: str | Path) -> str:
    image_path = Path(image_path)

    with image_path.open("rb") as image_file:
        return base64.b64encode(image_file.read()).decode()


def image_to_data_url(image_path: str | Path) -> str:
    image_path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(image_path)

    if mime_type is None:
        mime_type = "image/jpeg"

    image_base64 = image_to_base_64(image_path)
    return f"data:{mime_type};base64,{image_base64}"


def save_base_64(path: str | Path, data: str) -> None:
    with open(file=path, mode="w", encoding="utf-8") as file:
        file.write(data)


def read_base_64(path: str) -> str:
    with open(file=path, mode="r", encoding="utf-8") as file:
        return file.read()


def blur_region(
    image: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    ksize: int = 51,
) -> np.ndarray:
    """Retorna uma cópia da imagem com a região (x, y, w, h) borrada.

    Args:
        image: imagem do OpenCV (BGR ou tons de cinza).
        x, y: canto superior esquerdo da região, em pixels.
        w, h: largura e altura da região, em pixels.
        ksize: tamanho do kernel do blur; quanto maior, mais forte. Precisa ser ímpar.
    """
    if ksize % 2 == 0:
        ksize += 1

    blurred = image.copy()
    region = blurred[y : y + h, x : x + w]
    blurred[y : y + h, x : x + w] = cv2.GaussianBlur(region, (ksize, ksize), 0)
    return blurred


def resize_max(content: bytes, max_side: int = 1024) -> bytes:
    """Reduz a imagem para que o maior lado tenha no máximo ``max_side`` pixels.

    Imagens menores que o limite não são ampliadas. Retorna a imagem em PNG.

    Raises:
        ValueError: se os bytes não forem uma imagem que o OpenCV consiga ler.
    """
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Arquivo não é uma imagem válida.")

    h, w = image.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        new_size = (int(w * scale), int(h * scale))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)

    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Não foi possível codificar a imagem.")
    return buffer.tobytes()


def decode_image(content: bytes) -> np.ndarray:
    """Converte os bytes de um arquivo de imagem num array BGR do OpenCV.

    Raises:
        ValueError: se os bytes não forem uma imagem que o OpenCV consiga ler.
    """
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Arquivo não é uma imagem válida.")
    return image


def encode_png(image: np.ndarray) -> bytes:
    """Converte um array do OpenCV nos bytes de um arquivo PNG."""
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Não foi possível codificar a imagem.")
    return buffer.tobytes()


def upscale_min(image: np.ndarray, min_side: int = 448) -> np.ndarray:
    """Amplia a imagem para que o maior lado tenha pelo menos ``min_side`` pixels.

    Recortes muito pequenos (rubrica numa foto de baixa resolução) ficam
    ilegíveis para o modelo de visão. Imagens maiores não são alteradas.
    """
    h, w = image.shape[:2]
    scale = min_side / max(h, w)
    if scale <= 1:
        return image
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
