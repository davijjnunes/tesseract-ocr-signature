# Verificação de assinatura

API em FastAPI que recebe a imagem de um documento inteiro (certificado,
declaração, diploma) e responde se ele tem **assinatura manuscrita**.

O Tesseract encontra a região da assinatura e um modelo de visão local
(Ollama) decide se essa região tem assinatura.

## Como funciona

```
imagem do documento
   │
   ▼
Tesseract (OCR, por)            ← procura a palavra-âncora ("Diretora")
   │
   ▼
recorte em volta da âncora       ← a assinatura fica logo acima do nome/cargo
   │
   ▼
Ollama (qwen2.5vl:3b)            ← "tem assinatura manuscrita neste recorte?"
   │
   ▼
{"nome_arquivo", "ocr_recorte_modelo_usado", "tem_assinatura"}
```

1. O OCR roda na imagem do tamanho original, porque reduzir antes atrapalha a leitura da âncora.
2. Cada ocorrência da âncora gera um recorte focado na rubrica, ou seja, nos traços de tinta acima do nome
   (`crop_signature` em `src/services/tesseract_service.py`). Se quase não houver tinta, o recorte
   pega a coluna inteira de quem assina.
3. Cada recorte é ampliado se for pequeno (mínimo de 448 px), reduzido para no máximo 1024 px,
   salvo em `logs/recortes/` e enviado ao modelo.
4. Se algum recorte tiver assinatura, `tem_assinatura` é `true`. Se nenhum tiver, é `false`.

## Requisitos

- Python 3.13 e [uv](https://docs.astral.sh/uv/)
- Tesseract com o idioma português:
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-por
  ```
- [Ollama](https://ollama.com) rodando em `http://localhost:11434` com o modelo:
  ```bash
  ollama pull qwen2.5vl:3b
  ```

## Como rodar

```bash
uv sync
uv run uvicorn src.api.app:app --reload
```

A documentação interativa fica em <http://localhost:8000/docs>.

## Endpoint

### `POST /signature-detections`

Recebe o documento inteiro como `multipart/form-data`.

| Parâmetro | Onde  | Tipo    | Obrigatório | Descrição |
|-----------|-------|---------|-------------|-----------|
| `image`   | form  | arquivo | sim         | Imagem PNG, JPEG ou WEBP com no máximo 10 MB. |

#### Exemplos

```bash
curl -X POST http://localhost:8000/signature-detections \
  -F "image=@certificado.png"
```

#### Resposta `200`

```json
{
  "nome_arquivo": "certificado.png",
  "ocr_recorte_modelo_usado": {
    "ocr": "tesseract (por, --psm 6)",
    "ancora": "Diretora",
    "recortes": 1,
    "modelo": "qwen2.5vl:3b"
  },
  "tem_assinatura": true
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `nome_arquivo` | texto | Nome do arquivo enviado. |
| `ocr_recorte_modelo_usado.ocr` | texto | Motor de OCR, idioma e configuração. |
| `ocr_recorte_modelo_usado.ancora` | texto | Palavra usada para localizar a assinatura. |
| `ocr_recorte_modelo_usado.recortes` | número | Quantos recortes foram encontrados e enviados ao modelo. |
| `ocr_recorte_modelo_usado.modelo` | texto | Modelo de visão do Ollama. |
| `tem_assinatura` | booleano | `true` se o documento tem assinatura manuscrita. |

#### Erros

| Status | Quando |
|--------|--------|
| `400`  | O arquivo não é uma imagem válida. |
| `413`  | A imagem passa de 10 MB. |
| `415`  | O tipo não é PNG, JPEG ou WEBP. |
| `422`  | A âncora "Diretora" não foi encontrada no documento, então não há onde procurar a assinatura. Também acontece quando falta o campo `image`. |
| `502`  | O Ollama está fora do ar, deu erro ou devolveu uma resposta fora do formato. |

Os erros vêm no formato padrão do FastAPI:

```json
{ "detail": "Região da assinatura não encontrada." }
```

## Configuração

Fica em `src/api/config.py`:

| Constante          | Padrão                            | Uso |
|--------------------|-----------------------------------|-----|
| `MODEL`            | `qwen2.5vl:3b`                    | Modelo de visão do Ollama. |
| `OCR_LANG`         | `por`                             | Idioma do Tesseract. |
| `OCR_CONFIG`       | `--psm 6`                         | Configuração do Tesseract. |
| `ANCORA`           | `Diretora`                        | Palavra logo abaixo da assinatura. |
| `OLLAMA_HOST`      | `http://localhost:11434`          | Endereço do Ollama. |
| `LOG_FILE`         | `logs/signature.log`              | Arquivo de log de cada requisição. |
| `CROPS_DIR`        | `logs/recortes/`                  | Recortes enviados ao modelo. |
| `TIPOS_PERMITIDOS` | `image/png`, `image/jpeg`, `image/webp` | Tipos aceitos no upload. |
| `TAMANHO_MAXIMO`   | 10 MB                             | Tamanho máximo do arquivo. |

O recorte é ajustado pelos parâmetros de `crop_signature`:

- `up`: quanto subir acima da âncora, em múltiplos da altura da palavra;
- `pad`: margem em volta da rubrica;
- `ink_threshold`: o tom abaixo do qual um pixel conta como tinta.

O endereço do Ollama vem de `OLLAMA_HOST` (padrão `http://localhost:11434`).

## Estrutura

```
src/
├── api/
│   ├── app.py                 # cria o FastAPI e registra as rotas
│   ├── config.py              # modelo, tipos e tamanho máximo
│   └── routers/signature.py   # POST /signature-detections
├── schemas/signature.py       # formato do modelo e resposta da API
└── services/
    ├── tesseract_service.py   # OCR e recorte da rubrica (crop_signature)
    ├── image_service.py       # decodificar, codificar e redimensionar
    └── ollama_service.py      # prompts e chamada ao Ollama
```

## Limitações

- O documento precisa ter a palavra-âncora legível abaixo da assinatura. Sem
  ela, a resposta é `422` e não `false`.
- Fotos tortas, com sombra ou em baixa resolução podem impedir o OCR de achar a âncora.
- Só aceita imagens. Para PDF, converta a página antes, por exemplo com `load_page` do `tesseract_service`.
- O `qwen2.5vl:3b` é um modelo pequeno, então carimbos ou rubricas muito
  discretas podem ser classificados errado.
- Assinaturas borradas ou apagadas podem gerar resultados inconsistentes, por
  limitação do modelo.
- Os recortes salvos em `logs/recortes/` são de documentos reais. Não compartilhe essa pasta.
