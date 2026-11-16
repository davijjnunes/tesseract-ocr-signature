import re
import unicodedata
from pathlib import Path

import cv2
import fitz
import matplotlib.pyplot as plt
import numpy as np
import pytesseract
from pytesseract import Output

PATH_DEFAULT = r"images/certificadoDavi.pdf"


def load_page(doc, page_num=0, scale=2, dpi=300):
    """Carrega a página como imagem BGR, com a melhor qualidade possível.

    PDF escaneado (uma imagem ocupando a página): extrai a imagem original,
    sem reamostrar. Renderizar com get_pixmap(dpi=300) só estica o JPEG de
    150 DPI, borrando as letras e aumentando os artefatos de compressão.
    Depois tira o ruído do JPEG e amplia com Lanczos, que preserva melhor
    as bordas das letras para o Tesseract.

    PDF digital (texto vetorial): renderiza no ``dpi`` pedido.
    """
    page = doc[page_num]
    images = page.get_images(full=True)
    covers_page, upright = 0, 0

    if len(images) == 1 and page.rotation == 0:
        xref = images[0][0]
        rects = page.get_image_rects(xref, transform=True)
        if rects:
            rect, m = rects[0]
            # só é escaneado se a imagem cobrir a página; senão é logo/assinatura
            covers_page = rect.get_area() / page.rect.get_area() > 0.8
            # matriz sem rotação/espelhamento: a imagem crua já está "em pé"
            upright = m.b == 0 and m.c == 0 and m.a > 0 and m.d > 0
        if rects and covers_page and upright:
            data = doc.extract_image(xref)["image"]
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if image is not None:
                image = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
                if scale != 1:
                    image = cv2.resize(
                        image,
                        None,
                        fx=scale,
                        fy=scale,
                        interpolation=cv2.INTER_LANCZOS4,
                    )
                return image

    # RGB sem canal alfa: evita erro de conversão com pixmaps em cinza ou RGBA
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def show(title, image, height_max=900):
    h, w = image.shape[:2]
    scale = height_max / h
    if scale < 1:
        image = cv2.resize(
            image, (int(w * scale), height_max), interpolation=cv2.INTER_AREA
        )
    cv2.imshow(title, image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def show_box(result, image):
    boxed = image.copy()

    for index in range(len(result["text"])):
        word = result["text"][index].strip()

        if normalize(word) == "declaração":
            print(index, word)
            print(f"result left: {result['left'][index]}")
            print(f"result top: {result['top'][index]}")
            print(f"result width: {result['width'][index]}")
            print(f"result height: {result['height'][index]}")
            print(f"result conf: {result['conf'][index]}")

        conf = float(result["conf"][index])

        if word and conf > 60:
            x, y, boxed = box(result, boxed, index)
            cv2.putText(
                boxed,
                word,
                (x, max(y - 5, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
            )

    show("Caixas", boxed)


def box(result, image, index, color=(0, 0, 255)):
    x = result["left"][index]
    y = result["top"][index]
    w = result["width"][index]
    h = result["height"][index]

    cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)

    return x, y, image


def normalize(word: str) -> str:
    """remove pontuação nas bordas ("DECLARAÇÃO:" -> "declaração") e padroniza acentos"""
    word = unicodedata.normalize("NFC", word)
    return re.sub(r"^\W+|\W+$", "", word).lower()


def crops_target(
    result,
    image,
    target=("Diretora",),
    min_conf=60,
    up=8,
    down=1,
    side=12,
):
    """Retorna uma lista de (recorte, (x, y, w, h)) para cada ocorrência do target."""
    targets = [normalize(t) for t in target]
    H, W = image.shape[:2]
    crops = []

    for i, word in enumerate(result["text"]):
        word = normalize(word)
        if not word or not any(t in word for t in targets):  # 1. substring
            continue
        if float(result["conf"][i]) < min_conf:
            continue

        x, y = result["left"][i], result["top"][i]
        w, h = result["width"][i], result["height"][i]
        cx = x + w // 2  # centro da âncora

        # margem, sem sair dos limites da imagem
        x0, y0 = max(cx - side * h, 0), max(y - up * h, 0)
        x1, y1 = min(cx + side * h, W), min(y + h + down * h, H)

        crop = image[y0:y1, x0:x1].copy()
        crops.append((crop, (x0, y0, x1 - x0, y1 - y0)))

    return crops


def _words(result, min_conf=60):
    """Palavras confiáveis do OCR, com caixa e linha (bloco, parágrafo, linha)."""
    words = []
    for i, text in enumerate(result["text"]):
        text = text.strip()
        if text and float(result["conf"][i]) >= min_conf and re.search(r"\w", text):
            words.append(
                {
                    "text": text,
                    "x": result["left"][i],
                    "y": result["top"][i],
                    "w": result["width"][i],
                    "h": result["height"][i],
                    "line": (
                        result["block_num"][i],
                        result["par_num"][i],
                        result["line_num"][i],
                    ),
                }
            )
    return words


def _span(words):
    """Caixa (x0, y0, x1, y1) que envolve todas as palavras."""
    x0 = min(w["x"] for w in words)
    y0 = min(w["y"] for w in words)
    x1 = max(w["x"] + w["w"] for w in words)
    y1 = max(w["y"] + w["h"] for w in words)
    return x0, y0, x1, y1


def _segment(words, anchor, gap=3):
    """Palavras vizinhas da âncora na mesma linha.

    Separa signatários lado a lado: um vão maior que ``gap`` alturas de
    letra marca o começo de outra coluna.
    """
    line = sorted((w for w in words if w["line"] == anchor["line"]), key=lambda w: w["x"])
    i = line.index(anchor)
    left = right = i
    limit = gap * anchor["h"]
    while left > 0 and line[left]["x"] - (line[left - 1]["x"] + line[left - 1]["w"]) < limit:
        left -= 1
    while (
        right < len(line) - 1
        and line[right + 1]["x"] - (line[right]["x"] + line[right]["w"]) < limit
    ):
        right += 1
    return line[left : right + 1]


def crop_signature(
    image,
    target=("Diretora",),
    lang="por",
    config="--psm 6",
    up=5,
    pad=0.15,
    ink_threshold=150,
):
    """Roda o OCR na página inteira e recorta a rubrica de quem assina.

    Para cada ocorrência da âncora (o cargo, como "Diretora"):

    1. pega a coluna do signatário: o trecho do cargo e o nome logo acima;
    2. procura tinta (pixels escuros) acima do cargo, ignorando o texto
       impresso que o OCR reconheceu;
    3. recorta justo em volta da tinta, incluindo a linha do nome, por onde
       a rubrica costuma passar, e parando antes do cargo.

    Se não houver tinta suficiente (assinatura ausente ou borrada), devolve
    a coluna inteira acima do cargo, para o modelo confirmar que está vazia.

    Args:
        image: página inteira em BGR.
        target: palavras do cargo que fica logo abaixo da assinatura.
        up: quantas alturas de letra acima do nome procurar a rubrica.
        pad: margem do recorte, em fração do tamanho da rubrica.
        ink_threshold: tons de cinza abaixo deste valor contam como tinta.

    Returns:
        Lista de recortes BGR, um por âncora encontrada (vazia se nenhuma).
    """
    H, W = image.shape[:2]
    bx0 = bx1 = by1 = 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    result = pytesseract.image_to_data(
        gray, lang=lang, config=config, output_type=Output.DICT
    )
    words = _words(result)
    targets = [normalize(t) for t in target]
    crops = []

    for anchor in words:
        if not any(t in normalize(anchor["text"]) for t in targets):
            continue

        # 1. coluna do signatário: trecho do cargo + nome logo acima
        segment = _segment(words, anchor)
        sx0, sy0, sx1, sy1 = _span(segment)
        h = sy1 - sy0
        name = [
            w
            for w in words
            if sy0 - 2.5 * h <= w["y"]
            and w["y"] + w["h"] <= sy0 + 0.3 * h
            and w["x"] < sx1 + h
            and w["x"] + w["w"] > sx0 - h
        ]
        cx0, cy0, cx1, _ = _span(segment + name)
        name_bottom = cy0 + h if name else sy0  # fim da linha do nome

        # 2. região de busca: da altura de várias linhas acima até o cargo
        rx0, rx1 = max(cx0 - 2 * h, 0), min(cx1 + 2 * h, W)
        ry0, ry1 = max(cy0 - up * h, 0), sy0
        ink = (gray[ry0:ry1, rx0:rx1] < ink_threshold).astype(np.uint8) * 255
        for w in words:  # apaga o texto impresso: só sobra o que é à mão
            x0, y0 = max(w["x"] - rx0 - 3, 0), max(w["y"] - ry0 - 3, 0)
            ink[y0 : max(w["y"] - ry0 + w["h"] + 3, 0), x0 : max(w["x"] - rx0 + w["w"] + 3, 0)] = 0

        n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
        strokes = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 20]

        # 3. recorte justo na rubrica; sujeira ou resto de borrão não conta
        if strokes:
            bx0 = min(stats[i, cv2.CC_STAT_LEFT] for i in strokes)
            by0 = min(stats[i, cv2.CC_STAT_TOP] for i in strokes)
            bx1 = max(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] for i in strokes)
            by1 = max(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] for i in strokes)
        if strokes and bx1 - bx0 >= 3 * h:
            by1 = max(by1, name_bottom - ry0)
            margin = int(pad * max(bx1 - bx0, by1 - by0))
            x0, y0 = max(rx0 + bx0 - margin, 0), max(ry0 + by0 - margin, 0)
            x1, y1 = min(rx0 + bx1 + margin, W), min(ry0 + by1 + margin, sy0)
        else:
            x0, y0, x1, y1 = rx0, ry0, rx1, min(name_bottom, H)

        crops.append(image[y0:y1, x0:x1].copy())

    return crops
