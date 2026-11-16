const form = document.getElementById("form");
const input = document.getElementById("image");
const preview = document.getElementById("preview");
const status = document.getElementById("status");
const button = form.querySelector("button");

const TAMANHO_MAXIMO = 10 * 1024 * 1024; // 10 MB, o mesmo limite da API

function main() {
  showPreview();
  sendSubmit();
}

const showPreview = () => {
  input.addEventListener("change", () => {
    const file = input.files[0];
    showStatus("");

    if (!file) {
      preview.hidden = true;
      return;
    }

    if (preview.src) URL.revokeObjectURL(preview.src); // libera a prévia anterior
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  });
};

const sendSubmit = () => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = input.files[0];
    if (!file) return;

    if (file.size > TAMANHO_MAXIMO) {
      showStatus("A imagem passa de 10 MB.", "erro");
      return;
    }

    // o nome do campo precisa ser "image", igual ao parâmetro do endpoint
    const body = new FormData();
    body.append("image", file);

    button.disabled = true;
    showStatus("Analisando o documento...");

    await sendRequest(body);
  });
};

async function sendRequest(body){
  try {
    const response = await fetch("/signature-detections", { method: "POST", body });
    const data = await response.json();

    if (!response.ok) {
      // o FastAPI devolve o erro em "detail" (texto ou lista, no 422 de validação)
      const detail = typeof data.detail === "string" ? data.detail : "Requisição inválida.";
      showStatus(detail, "erro");
      return;
    }

    if (data.tem_assinatura) {
      showStatus("O documento tem assinatura.", "ok");
    } else {
      showStatus("O documento não tem assinatura.", "erro");
    }
  } catch {
    showStatus("Não foi possível falar com o servidor.", "erro");
  } finally {
    button.disabled = false;
  }

}

function showStatus(message, type = "") {
  status.textContent = message;
  status.className = type; // "ok", "erro" ou "" (neutro)
}

main();
