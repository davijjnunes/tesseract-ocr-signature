from pathlib import Path

import cv2
import fitz
import matplotlib.pyplot as plt
import pytesseract
from pytesseract import Output

from src.schemas.signature import SignatureDetection
from src.services.ollama_service import ollama_ask
from src.services.tesseract_service import crops_target, load_page, show, show_box

PATH_DEFAULT = "src/images/certificadoDavi.pdf"
PATH = Path(__file__).resolve().parent / PATH_DEFAULT

SYSTEM_PROMPT = "Você analisa documentos e responde só com base na imagem."

USER_PROMPT = (
    "Há alguma assinatura manuscrita (rabisco ou rubrica feita à caneta) nesta imagem? "
    'Responda em JSON: {"has_signature": true} ou {"has_signature": false}.'
)

RECORTES_DIR = Path(__file__).resolve().parent / "src" / "images" / "recortes"
IMAGE_PATH = RECORTES_DIR / "target_0.png"


def main():
    config = "--psm 6"
    doc = fitz.open(PATH)
    image = load_page(doc, 0)
    show("Certificado", image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(
        gray, lang="por", config=config, output_type=Output.DICT
    )
    show_box(data, image)

    plt.imshow(gray, cmap="gray")
    plt.axis("off")
    plt.show()

    crops = crops_target(data, image)
    output_dir = RECORTES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    if not crops:
        print("Target não encontrado")
    else:
        for n, (crop, bbox) in enumerate(crops):
            print(n, bbox)
            show(f"Target {n}", crop)
            cv2.imwrite(str(output_dir / f"target_{n}.png"), crop)

    response = ollama_ask(
        model="qwen2.5vl:3b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT, "images": [IMAGE_PATH]},
        ],
        format=SignatureDetection.model_json_schema(),
    )

    content = response.message.content
    if content is None:
        raise RuntimeError("O modelo não retornou conteúdo.")

    answer = SignatureDetection.model_validate_json(content)
    print(f"Tem assinatura: {answer}")


if __name__ == "__main__":
    main()
