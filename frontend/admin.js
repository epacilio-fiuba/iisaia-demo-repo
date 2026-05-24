const API = "http://localhost:8000";
const MAX_BYTES = 1_048_576;

const $ = (id) => document.getElementById(id);
const form = $("import-form");
const tokenInput = $("token");
const fileInput = $("file");
const submitBtn = $("submit-btn");
const resultSection = $("result");
const banner = $("banner");
const summary = $("summary");
const insertedBody = $("inserted-body");
const skippedBody = $("skipped-body");

// Restore token from sessionStorage.
const stored = sessionStorage.getItem("demo-bearer");
if (stored) tokenInput.value = stored;
tokenInput.addEventListener("change", () => {
  sessionStorage.setItem("demo-bearer", tokenInput.value);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError(null);

  const token = tokenInput.value.trim();
  const resource = form.querySelector('input[name="resource"]:checked').value;
  const mode = form.querySelector('input[name="mode"]:checked').value;
  const file = fileInput.files[0];

  if (!token) return showError("Falta el bearer token.");
  if (!file) return showError("Elegí un archivo CSV.");
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return showError("El archivo debe terminar en .csv.");
  }
  if (file.size > MAX_BYTES) return showError("El archivo supera 1 MB.");

  const data = new FormData();
  data.append("file", file);
  data.append("mode", mode);

  setLoading(true);
  try {
    const res = await fetch(`${API}/import/${resource}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: data,
    });
    const body = await res.json().catch(() => ({}));

    if (res.status === 200 || res.status === 422) {
      renderResult(body, res.status === 422);
    } else {
      showError(body.detail || `Error ${res.status}`);
    }
  } catch (err) {
    showError("No se pudo contactar al servidor.");
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.textContent = loading ? "Importando…" : "Importar";
}

function showError(msg) {
  if (!msg) {
    banner.hidden = true;
    return;
  }
  resultSection.hidden = false;
  banner.hidden = false;
  banner.className = "banner-error";
  banner.textContent = msg;
  insertedBody.innerHTML = "";
  skippedBody.innerHTML = "";
  summary.textContent = "";
}

function renderResult(body, rolledBack) {
  resultSection.hidden = false;

  if (rolledBack) {
    banner.hidden = false;
    banner.className = "banner-error";
    banner.textContent = "Rollback · ningún ítem se insertó.";
  } else {
    banner.hidden = true;
  }

  summary.textContent =
    `Total: ${body.total_rows} · Insertadas: ${body.inserted.length} · ` +
    `Descartadas: ${body.skipped.length} · Modo: ${body.mode}`;

  insertedBody.innerHTML = body.inserted
    .map((r) => `<tr><td>${r.row}</td><td>${r.id}</td></tr>`)
    .join("");

  skippedBody.innerHTML = body.skipped
    .map(
      (r) =>
        `<tr><td>${r.row}</td><td>${escape(r.reason)}</td><td>${escape(r.detail)}</td></tr>`
    )
    .join("");
}

function escape(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
