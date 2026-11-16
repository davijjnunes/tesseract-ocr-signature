import re
import sys
from pathlib import Path

import cv2
import imutils
import matplotlib.pyplot as plt
import numpy as np
import pytesseract
from pytesseract.pytesseract import Output


def load_image(name: str):
    """Carrega uma imagem da pasta ``src/images/images-example``.

    Args:
        name: nome do arquivo dentro da pasta, por exemplo ``"teste02.jpg"``.

    Returns:
        A imagem como array do NumPy, com as cores na ordem BGR (padrão do OpenCV).

    Encerra o programa com uma mensagem de erro se o arquivo não puder ser lido.
    """
    path = Path(__file__).resolve().parents[1] / "images" / "images-example" / name
    image =Ped cv2.imread(str(path))

    if image is None:
        sys.exit(f"Could not read the image: {path}")

    return image


def display_image(image):
    """Converte a imagem para tons de cinza e a mostra numa janela.

    A janela fica aberta até uma tecla ser pressionada com ela em foco.

    Args:
        image: imagem colorida em BGR, como a retornada por ``load_image``.

    Returns:
        A imagem em tons de cinza (um único canal), pronta para o OCR.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cv2.imshow("Display window", gray)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return gray


def display_image_plot(image):
    """Mostra a imagem com o Matplotlib, sem os eixos.

    Args:
        image: imagem colorida em BGR (3 canais) ou em tons de cinza (1 canal).
    """
    _fig, ax = plt.subplots(figsize=(16, 8))
    ax.axis("off")

    if image.ndim == 2:  # 1 canal: tons de cinza
        ax.imshow(image, cmap="gray")
    else:  # 3 canais: o OpenCV usa BGR, o Matplotlib espera RGB
        ax.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    plt.show()


def get_text_document(image):
    """Extrai o texto da imagem com o Tesseract, usando o idioma português.

    Args:
        image: imagem em BGR, RGB ou tons de cinza.

    Returns:
        O texto reconhecido, com as quebras de linha da imagem.
    """
    return pytesseract.image_to_string(image, lang="por", config="--psm 6")


def get_box_document(image):
    """Retorna os dados de cada palavra reconhecida na imagem.

    Para cada palavra, o Tesseract informa a posição da caixa que a envolve
    (``left``, ``top``, ``width``, ``height``, em pixels), a confiança
    (``conf``, de 0 a 100) e o próprio texto (``text``).

    Args:
        image: imagem em BGR, RGB ou tons de cinza.

    Returns:
        Uma string no formato TSV (colunas separadas por tab), com uma linha por item.
    """
    return pytesseract.image_to_data(image)


def get_pandas_documents(image):
    """Mostra as linhas de texto reconhecidas e a confiança média do OCR.

    Usa só as palavras com confiança acima de 60 e junta as palavras que o
    Tesseract colocou na mesma linha.

    Args:
        image: imagem em BGR, RGB ou tons de cinza.
    """
    df = pytesseract.image_to_data(image, lang="por", output_type=Output.DATAFRAME)
    df = df.dropna(subset=["text"])  # tira as linhas sem texto
    words = df[(df.conf > 60) & (df.text.astype(str).str.strip() != "")]
    rows = words.groupby(["block_num", "par_num", "line_num"])["text"].apply(
        lambda t: " ".join(map(str, t))
    )
    print(rows.tolist())
    print(words.conf.mean())


def get_location(conts):
    """Procura o primeiro contorno com a forma de um quadrilátero convexo.

    Args:
        conts: contornos ordenados do maior para o menor.

    Returns:
        Os 4 cantos do maior quadrilátero encontrado, ou ``None`` se nenhum
        contorno tiver essa forma.
    """
    location = None

    for c in conts:
        peri = cv2.arcLength(c, True)
        aprox = cv2.approxPolyDP(c, 0.03 * peri, True)
        if cv2.isContourConvex(aprox) and len(aprox) == 4:
            location = aprox
            break

    return location


def detect_document(image):
    """Encontra o documento (certificado, diploma, folha) na foto e o recorta.

    Procura a maior forma de 4 cantos da imagem. Funciona bem quando o papel
    é o maior retângulo da foto e contrasta com o fundo.

    Args:
        image: foto colorida em BGR, como a retornada por ``load_image``.

    Returns:
        O recorte do documento em tons de cinza, ou ``None`` se nenhuma forma
        de 4 cantos for encontrada.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 11, 17, 17)
    edged = cv2.Canny(blur, 30, 200)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)

    conts = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    conts = imutils.grab_contours(conts)
    conts = sorted(conts, key=cv2.contourArea, reverse=True)[:8]

    location = get_location(conts)
    if location is None:
        print("Nenhum documento encontrado na imagem.")
        return None

    mask = np.zeros(gray.shape, np.uint8)
    cv2.drawContours(mask, [location], 0, 255, -1)  # altera a mask diretamente

    (y, x) = np.where(mask == 255)
    (beginX, beginY) = (np.min(x), np.min(y))
    (endX, endY) = (np.max(x), np.max(y))

    document = gray[beginY : endY + 1, beginX : endX + 1]

    return document


def read_document(document, min_conf=60):
    """Lê o texto do documento recortado, descartando o que parece lixo.

    Certificados têm brasões e arabescos que o Tesseract tenta ler como letras.
    Para limpar o resultado:

    - descarta palavras com confiança menor que ``min_conf``;
    - descarta "palavras" sem nenhuma letra ou número (como ``|`` ou ``=``);
    - descarta linhas com menos de 4 letras (restos dos enfeites).

    Args:
        document: recorte do documento, como o de ``detect_document``.
        min_conf: confiança mínima de cada palavra, de 0 a 100.

    Returns:
        O texto reconhecido, uma linha do documento por linha.
    """
    df = pytesseract.image_to_data(
        document, lang="por", config="--psm 6", output_type=Output.DATAFRAME
    )
    df = df.dropna(subset=["text"])
    df["text"] = df.text.astype(str).str.strip()

    words = df[(df.conf > min_conf) & df.text.str.contains(r"\w")]
    lines = words.groupby(["block_num", "par_num", "line_num"])["text"].apply(" ".join)

    # [^\W\d_] = uma letra (com ou sem acento), sem contar números e "_"
    lines = [line for line in lines if len(re.findall(r"[^\W\d_]", line)) >= 4]
    return "\n".join(lines)


def read_plate(plate):
    """Prepara o recorte da placa e lê os caracteres com o Tesseract.

    Args:
        plate: recorte da placa em tons de cinza, como o de ``detect_document``.

    Returns:
        O texto da placa, só com letras maiúsculas e números.
    """
    # amplia 3x: a placa original é pequena demais para o Tesseract
    plate = cv2.resize(plate, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    # preto e branco puro; o OTSU escolhe o limite sozinho
    _, plate = cv2.threshold(plate, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # margem branca: o Tesseract lê melhor quando o texto não encosta na borda
    plate = cv2.copyMakeBorder(plate, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

    # --psm 7: uma linha só de texto; whitelist: só letras maiúsculas e números
    config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return pytesseract.image_to_string(plate, config=config).strip()
