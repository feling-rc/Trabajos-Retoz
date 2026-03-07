from flask import Blueprint, jsonify, request, render_template_string
import sqlite3
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

tareas_bp = Blueprint("tareas_bp", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tareas_simple.db")
TZ = ZoneInfo("America/Lima")
RESPONSABLES = ["Elizabeth", "Shina", "Feling"]


def now_local_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA foreign_keys=ON;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tareas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            responsable TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'programada',
            created_at TEXT NOT NULL,
            done_at TEXT
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas(estado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_responsable ON tareas(responsable)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_created_at ON tareas(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_done_at ON tareas(done_at)")

    conn.commit()
    conn.close()


def row_to_dict(row):
    return {
        "id": row["id"],
        "texto": row["texto"],
        "responsable": row["responsable"],
        "estado": row["estado"],
        "created_at": row["created_at"],
        "done_at": row["done_at"],
    }


def limpiar_linea_tarea(linea: str) -> str:
    linea = (linea or "").strip()
    if not linea:
        return ""

    linea = re.sub(r"^\s*(?:[-*•]+|\d+[.)]|[A-Za-z][.)]|\[\s?[xX]?\s?\])\s*", "", linea).strip()
    linea = re.sub(r"\s+", " ", linea).strip()
    return linea


def extraer_tareas_desde_texto(texto: str):
    if not texto:
        return []

    partes = texto.replace("\r", "\n").split("\n")
    tareas = []

    for parte in partes:
        limpia = limpiar_linea_tarea(parte)
        if limpia:
            tareas.append(limpia)

    # si alguien pegó todo en una sola línea con ";"
    if len(tareas) == 1 and ";" in tareas[0]:
        nuevas = []
        for pedazo in tareas[0].split(";"):
            limpia = limpiar_linea_tarea(pedazo)
            if limpia:
                nuevas.append(limpia)
        tareas = nuevas

    # quitar duplicados vacíos sin alterar mucho
    resultado = []
    for t in tareas:
        if t and len(t) <= 220:
            resultado.append(t)

    return resultado


HTML_TAREAS = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mini Tareas</title>
  <style>
    :root{
      --bg:#f5f7fb;
      --bg2:#eef2ff;
      --card:rgba(255,255,255,.92);
      --line:rgba(15,23,42,.08);
      --text:#182235;
      --muted:#6b7280;
      --primary:#5b5cf0;
      --primary2:#8b5cf6;
      --success:#16a34a;
      --success2:#10b981;
      --danger:#ef4444;
      --danger2:#f97316;
      --shadow:0 14px 34px rgba(37, 55, 95, .12);
      --radius-xl:26px;
      --radius-lg:20px;
      --radius-md:16px;
      --radius-sm:12px;
    }

    *{box-sizing:border-box}

    html,body{
      margin:0;
      padding:0;
      font-family:Inter, Arial, sans-serif;
      color:var(--text);
      background:
        radial-gradient(circle at top left, #e5edff 0%, transparent 26%),
        radial-gradient(circle at top right, #f1e5ff 0%, transparent 24%),
        linear-gradient(180deg,#f9fbff 0%, #f4f7fc 100%);
      min-height:100%;
    }

    body{
      padding:14px;
    }

    .app{
      max-width:760px;
      margin:0 auto;
    }

    .hero{
      position:sticky;
      top:0;
      z-index:50;
      padding-bottom:10px;
      backdrop-filter:blur(12px);
    }

    .hero-card{
      border-radius:30px;
      background:linear-gradient(135deg, rgba(91,92,240,.96), rgba(139,92,246,.96));
      color:white;
      box-shadow:0 18px 44px rgba(91,92,240,.24);
      padding:18px 16px 16px;
    }

    .hero-top{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
    }

    .hero-title{
      margin:0;
      font-size:24px;
      line-height:1.1;
      letter-spacing:-.02em;
      font-weight:900;
    }

    .hero-sub{
      margin:8px 0 0;
      color:rgba(255,255,255,.85);
      font-size:13px;
      line-height:1.45;
    }

    .clock{
      background:rgba(255,255,255,.16);
      border:1px solid rgba(255,255,255,.18);
      border-radius:999px;
      padding:9px 12px;
      font-size:12px;
      white-space:nowrap;
      font-weight:700;
    }

    .chips{
      display:flex;
      gap:8px;
      overflow:auto;
      scrollbar-width:none;
      margin-top:14px;
      padding-bottom:2px;
    }

    .chips::-webkit-scrollbar{display:none}

    .chip{
      border:none;
      border-radius:999px;
      padding:11px 14px;
      font-size:13px;
      font-weight:800;
      cursor:pointer;
      white-space:nowrap;
      transition:.18s ease;
      background:rgba(255,255,255,.16);
      border:1px solid rgba(255,255,255,.20);
      color:white;
    }

    .chip.active{
      background:white;
      color:var(--primary);
      transform:translateY(-1px);
    }

    .section{
      background:var(--card);
      border:1px solid var(--line);
      border-radius:var(--radius-xl);
      box-shadow:var(--shadow);
      padding:14px;
      margin-bottom:12px;
      backdrop-filter:blur(10px);
    }

    .tabs{
      display:grid;
      grid-template-columns:1fr 1fr;
      gap:8px;
    }

    .tab-btn{
      border:none;
      border-radius:16px;
      padding:12px 14px;
      background:#eef2ff;
      color:#61708a;
      font-size:14px;
      font-weight:900;
      cursor:pointer;
      transition:.18s ease;
    }

    .tab-btn.active{
      color:white;
      background:linear-gradient(135deg,var(--primary),var(--primary2));
      box-shadow:0 12px 24px rgba(91,92,240,.20);
    }

    .head-row{
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:10px;
      margin-bottom:12px;
    }

    .title{
      margin:0;
      font-size:16px;
      font-weight:900;
      letter-spacing:-.02em;
    }

    .pill{
      background:#f4f6fb;
      border:1px solid var(--line);
      color:var(--muted);
      border-radius:999px;
      padding:8px 10px;
      font-size:12px;
      font-weight:800;
      white-space:nowrap;
    }

    .composer-label{
      font-size:12px;
      color:var(--muted);
      font-weight:800;
      margin-bottom:8px;
      display:block;
    }

    textarea{
      width:100%;
      min-height:138px;
      resize:vertical;
      border:1px solid var(--line);
      border-radius:18px;
      padding:15px;
      background:white;
      font:inherit;
      color:var(--text);
      outline:none;
      transition:.18s ease;
      box-shadow:inset 0 1px 1px rgba(31,41,55,.03);
    }

    textarea:focus,
    select:focus,
    input:focus{
      border-color:rgba(91,92,240,.45);
      box-shadow:0 0 0 4px rgba(91,92,240,.10);
    }

    .helper{
      font-size:12px;
      color:var(--muted);
      margin-top:8px;
      line-height:1.45;
    }

    .composer-actions{
      display:flex;
      gap:8px;
      margin-top:12px;
    }

    .btn{
      border:none;
      border-radius:16px;
      padding:14px 16px;
      font-size:14px;
      font-weight:900;
      cursor:pointer;
      transition:.18s ease;
      min-height:48px;
    }

    .btn:active{
      transform:scale(.985);
    }

    .btn-primary{
      flex:1;
      color:white;
      background:linear-gradient(135deg,var(--primary),var(--primary2));
      box-shadow:0 12px 24px rgba(91,92,240,.22);
    }

    .btn-soft{
      background:#f3f5fb;
      color:#51607a;
      border:1px solid var(--line);
    }

    .btn-success{
      color:white;
      background:linear-gradient(135deg,var(--success2),var(--success));
      box-shadow:0 12px 24px rgba(22,163,74,.18);
    }

    .btn-danger{
      color:white;
      background:linear-gradient(135deg,var(--danger),var(--danger2));
      box-shadow:0 12px 24px rgba(239,68,68,.18);
    }

    .filters{
      display:grid;
      gap:10px;
    }

    .field{
      display:grid;
      gap:6px;
    }

    .field label{
      font-size:12px;
      color:var(--muted);
      font-weight:800;
    }

    select,input[type="date"],input[type="month"]{
      width:100%;
      border:1px solid var(--line);
      background:white;
      border-radius:16px;
      padding:13px 14px;
      font:inherit;
      color:var(--text);
      outline:none;
    }

    .grid-2{
      display:grid;
      gap:10px;
    }

    .cards{
      display:grid;
      gap:10px;
    }

    .card{
      background:white;
      border:1px solid var(--line);
      border-radius:22px;
      padding:14px;
      box-shadow:0 10px 24px rgba(31,41,55,.05);
      position:relative;
      overflow:hidden;
    }

    .card::after{
      content:"";
      position:absolute;
      left:0;
      right:0;
      bottom:0;
      height:3px;
      background:linear-gradient(90deg, rgba(91,92,240,.18), rgba(139,92,246,.35), rgba(16,185,129,.22));
    }

    .card-top{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
      margin-bottom:10px;
    }

    .resp-badge{
      display:inline-flex;
      align-items:center;
      gap:6px;
      border-radius:999px;
      padding:7px 10px;
      background:#eef2ff;
      color:var(--primary);
      font-size:12px;
      font-weight:900;
      white-space:nowrap;
    }

    .time{
      text-align:right;
      font-size:12px;
      color:var(--muted);
      white-space:nowrap;
    }

    .task-text{
      margin:0 0 12px;
      font-size:15px;
      font-weight:800;
      line-height:1.5;
      white-space:pre-wrap;
      word-break:break-word;
    }

    .card-actions{
      display:flex;
      gap:8px;
      align-items:center;
    }

    .card-actions .btn{
      flex:1;
    }

    .icon-btn{
      width:48px;
      min-width:48px;
      height:48px;
      border:none;
      border-radius:15px;
      background:#fff1f2;
      color:var(--danger);
      font-size:18px;
      cursor:pointer;
      border:1px solid rgba(239,68,68,.10);
    }

    .meta{
      margin-top:8px;
      font-size:12px;
      color:var(--muted);
      display:flex;
      justify-content:space-between;
      gap:10px;
      flex-wrap:wrap;
    }

    .empty{
      text-align:center;
      padding:20px 16px;
      border:1px dashed rgba(91,92,240,.18);
      border-radius:20px;
      background:linear-gradient(180deg,#fff,#f7f9ff);
      color:var(--muted);
      font-size:14px;
      line-height:1.55;
    }

    .hidden{
      display:none !important;
    }

    .toast{
      position:fixed;
      left:50%;
      bottom:20px;
      transform:translateX(-50%) translateY(20px);
      opacity:0;
      pointer-events:none;
      transition:.22s ease;
      background:rgba(17,24,39,.96);
      color:white;
      padding:14px 16px;
      border-radius:16px;
      font-size:14px;
      box-shadow:0 18px 40px rgba(0,0,0,.24);
      z-index:999;
      text-align:center;
      max-width:calc(100vw - 30px);
      min-width:220px;
    }

    .toast.show{
      opacity:1;
      pointer-events:auto;
      transform:translateX(-50%) translateY(0);
    }

    .loading{
      opacity:.65;
      pointer-events:none;
    }

    @media (min-width: 640px){
      body{padding:20px}

      .hero-card{
        padding:22px 20px 18px;
      }

      .hero-title{
        font-size:28px;
      }

      .grid-2{
        grid-template-columns:1fr 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <div class="hero">
      <div class="hero-card">
        <div class="hero-top">
          <div>
            <h1 class="hero-title">Mini Tareas</h1>
            <p class="hero-sub">
              Súper rápida para celular. Escribe una tarea o pega una lista completa.
              Cada línea se guarda como tarea separada.
            </p>
          </div>
          <div class="clock" id="clockNow">--:--</div>
        </div>

        <div class="chips" id="responsableChips"></div>
      </div>
    </div>

    <div class="section">
      <div class="tabs">
        <button id="tabProgramadas" class="tab-btn active" onclick="cambiarVista('programadas')">Tareas del día</button>
        <button id="tabHechas" class="tab-btn" onclick="cambiarVista('hechas')">Tareas hechas</button>
      </div>
    </div>

    <div class="section" id="composerSection">
      <div class="head-row">
        <h2 class="title">Agregar para <span id="responsableActualTexto">Elizabeth</span></h2>
        <div class="pill" id="countProgramadas">0 tareas</div>
      </div>

      <label class="composer-label">Escribe una tarea o pega varias líneas</label>
      <textarea
        id="taskInput"
        placeholder="- Llamar a cliente\\n- Revisar pedido\\n- Coordinar entrega\\n\\nTambién acepta listas con números o [ ]"
      ></textarea>

      <div class="helper">
        Consejo: si pegas varias líneas, cada línea se guardará como una tarea separada.
      </div>

      <div class="composer-actions">
        <button class="btn btn-primary" id="btnAgregar" onclick="agregarTareas()">+ Agregar</button>
        <button class="btn btn-soft" onclick="limpiarCaja()">Limpiar</button>
      </div>
    </div>

    <div class="section hidden" id="doneFiltersSection">
      <div class="head-row">
        <h2 class="title">Filtro de tareas hechas</h2>
        <div class="pill" id="countHechas">0 tareas</div>
      </div>

      <div class="filters">
        <div class="field">
          <label for="tipoFiltro">Tipo de filtro</label>
          <select id="tipoFiltro" onchange="cambiarTipoFiltro()">
            <option value="dia">La fecha es</option>
            <option value="rango">La fecha es entre</option>
            <option value="mes">El mes es</option>
          </select>
        </div>

        <div id="wrapDia" class="field">
          <label for="fechaDia">Fecha</label>
          <input type="date" id="fechaDia" onchange="aplicarFiltroHechas()">
        </div>

        <div id="wrapRango" class="grid-2 hidden">
          <div class="field">
            <label for="fechaDesde">Desde</label>
            <input type="date" id="fechaDesde" onchange="aplicarFiltroHechas()">
          </div>

          <div class="field">
            <label for="fechaHasta">Hasta</label>
            <input type="date" id="fechaHasta" onchange="aplicarFiltroHechas()">
          </div>
        </div>

        <div id="wrapMes" class="field hidden">
          <label for="mesFiltro">Mes</label>
          <input type="month" id="mesFiltro" onchange="aplicarFiltroHechas()">
        </div>

        <div class="composer-actions">
          <button class="btn btn-danger" onclick="vaciarHechas()">Vaciar terminadas</button>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="head-row">
        <h2 class="title" id="listTitle">Tareas del día</h2>
        <div class="pill" id="currentResponsablePill">Elizabeth</div>
      </div>

      <div class="cards" id="cardsWrap"></div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

  <script>
    const RESPONSABLES = {{ responsables|tojson }};
    let responsableActual = RESPONSABLES[0];
    let vistaActual = "programadas";
    let programadas = [];
    let hechas = [];

    function escapeHtml(texto) {
      return String(texto || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function showToast(msg) {
      const el = document.getElementById("toast");
      el.textContent = msg;
      el.classList.add("show");
      clearTimeout(showToast._timer);
      showToast._timer = setTimeout(() => el.classList.remove("show"), 2200);
    }

    function setLoading(isLoading) {
      const btn = document.getElementById("btnAgregar");
      if (isLoading) {
        btn.classList.add("loading");
        btn.disabled = true;
      } else {
        btn.classList.remove("loading");
        btn.disabled = false;
      }
    }

    async function api(url, options = {}) {
      const res = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Ocurrió un error");
      }

      return data;
    }

    function renderResponsables() {
      const wrap = document.getElementById("responsableChips");
      wrap.innerHTML = RESPONSABLES.map(nombre => `
        <button class="chip ${nombre === responsableActual ? "active" : ""}" onclick="cambiarResponsable('${nombre}')">
          ${escapeHtml(nombre)}
        </button>
      `).join("");

      document.getElementById("responsableActualTexto").textContent = responsableActual;
      document.getElementById("currentResponsablePill").textContent = responsableActual;
    }

    function cambiarResponsable(nombre) {
      responsableActual = nombre;
      renderResponsables();
      recargarVista();
    }

    function cambiarVista(vista) {
      vistaActual = vista;

      document.getElementById("tabProgramadas").classList.toggle("active", vista === "programadas");
      document.getElementById("tabHechas").classList.toggle("active", vista === "hechas");

      document.getElementById("composerSection").classList.toggle("hidden", vista !== "programadas");
      document.getElementById("doneFiltersSection").classList.toggle("hidden", vista !== "hechas");

      document.getElementById("listTitle").textContent =
        vista === "programadas" ? "Tareas del día" : "Tareas hechas";

      recargarVista();
    }

    function formatDateTime(fechaStr) {
      if (!fechaStr) return "-";
      const parts = fechaStr.split(" ");
      const date = parts[0] || "";
      const time = parts[1] || "";
      const d = date.split("-");
      if (d.length !== 3) return fechaStr;
      return `${d[2]}/${d[1]}/${d[0]} ${time}`;
    }

    function onlyDate(fechaStr) {
      return String(fechaStr || "").split(" ")[0] || "";
    }

    function monthPart(fechaStr) {
      return onlyDate(fechaStr).slice(0, 7);
    }

    function limpiarCaja() {
      document.getElementById("taskInput").value = "";
      document.getElementById("taskInput").focus();
    }

    async function agregarTareas() {
      const input = document.getElementById("taskInput");
      const texto = input.value.trim();

      if (!texto) {
        showToast("Escribe una tarea primero");
        input.focus();
        return;
      }

      try {
        setLoading(true);

        const data = await api("/tareas/api/crear", {
          method: "POST",
          body: JSON.stringify({
            texto,
            responsable: responsableActual
          })
        });

        input.value = "";
        showToast(data.message || "Tareas agregadas");
        await cargarProgramadas();
        input.focus();
      } catch (err) {
        showToast(err.message);
      } finally {
        setLoading(false);
      }
    }

    async function marcarHecha(id) {
      try {
        await api(`/tareas/api/${id}/hecho`, {
          method: "POST"
        });

        showToast("Tarea marcada como hecha ✅");
        await cargarProgramadas();
      } catch (err) {
        showToast(err.message);
      }
    }

    async function deshacerTarea(id) {
      try {
        await api(`/tareas/api/${id}/deshacer`, {
          method: "POST"
        });

        showToast("Tarea devuelta a pendientes");
        await cargarHechas();
      } catch (err) {
        showToast(err.message);
      }
    }

    async function eliminarTarea(id) {
      const ok = confirm("¿Eliminar esta tarea?");
      if (!ok) return;

      try {
        await api(`/tareas/api/${id}/eliminar`, {
          method: "POST"
        });

        showToast("Tarea eliminada");
        await recargarVista();
      } catch (err) {
        showToast(err.message);
      }
    }

    async function vaciarHechas() {
      const ok = confirm(`¿Vaciar todas las terminadas de ${responsableActual}?`);
      if (!ok) return;

      try {
        await api("/tareas/api/vaciar_hechas", {
          method: "POST",
          body: JSON.stringify({ responsable: responsableActual })
        });

        showToast("Terminadas vaciadas");
        await cargarHechas();
      } catch (err) {
        showToast(err.message);
      }
    }

    async function cargarProgramadas() {
      const data = await api(`/tareas/api/programadas?responsable=${encodeURIComponent(responsableActual)}`);
      programadas = data.result || [];
      renderProgramadas();
    }

    async function cargarHechas() {
      const data = await api(`/tareas/api/hechas?responsable=${encodeURIComponent(responsableActual)}`);
      hechas = data.result || [];
      aplicarFiltroHechas();
    }

    function renderProgramadas() {
      document.getElementById("countProgramadas").textContent =
        `${programadas.length} ${programadas.length === 1 ? "tarea" : "tareas"}`;

      const wrap = document.getElementById("cardsWrap");

      if (!programadas.length) {
        wrap.innerHTML = `
          <div class="empty">
            No hay tareas pendientes para <b>${escapeHtml(responsableActual)}</b>.<br>
            Agrega una arriba y aparecerá aquí.
          </div>
        `;
        return;
      }

      wrap.innerHTML = programadas.map(item => `
        <div class="card">
          <div class="card-top">
            <div class="resp-badge">• ${escapeHtml(item.responsable)}</div>
            <div class="time">#${item.id}<br>${formatDateTime(item.created_at)}</div>
          </div>

          <p class="task-text">${escapeHtml(item.texto)}</p>

          <div class="card-actions">
            <button class="btn btn-success" onclick="marcarHecha(${item.id})">Hecho</button>
            <button class="icon-btn" onclick="eliminarTarea(${item.id})" title="Eliminar">✕</button>
          </div>
        </div>
      `).join("");
    }

    function cambiarTipoFiltro() {
      const tipo = document.getElementById("tipoFiltro").value;

      document.getElementById("wrapDia").classList.toggle("hidden", tipo !== "dia");
      document.getElementById("wrapRango").classList.toggle("hidden", tipo !== "rango");
      document.getElementById("wrapMes").classList.toggle("hidden", tipo !== "mes");

      aplicarFiltroHechas();
    }

    function aplicarFiltroHechas() {
      const tipo = document.getElementById("tipoFiltro").value;
      const fechaDia = document.getElementById("fechaDia").value;
      const fechaDesde = document.getElementById("fechaDesde").value;
      const fechaHasta = document.getElementById("fechaHasta").value;
      const mesFiltro = document.getElementById("mesFiltro").value;

      let filtradas = [...hechas];

      if (tipo === "dia" && fechaDia) {
        filtradas = filtradas.filter(x => onlyDate(x.done_at) === fechaDia);
      }

      if (tipo === "rango" && fechaDesde && fechaHasta) {
        filtradas = filtradas.filter(x => {
          const f = onlyDate(x.done_at);
          return f >= fechaDesde && f <= fechaHasta;
        });
      }

      if (tipo === "mes" && mesFiltro) {
        filtradas = filtradas.filter(x => monthPart(x.done_at) === mesFiltro);
      }

      renderHechas(filtradas);
    }

    function renderHechas(items) {
      document.getElementById("countHechas").textContent =
        `${items.length} ${items.length === 1 ? "tarea" : "tareas"}`;

      const wrap = document.getElementById("cardsWrap");

      if (!items.length) {
        wrap.innerHTML = `
          <div class="empty">
            No hay tareas hechas para <b>${escapeHtml(responsableActual)}</b> con ese filtro.
          </div>
        `;
        return;
      }

      wrap.innerHTML = items.map(item => `
        <div class="card">
          <div class="card-top">
            <div class="resp-badge">✓ ${escapeHtml(item.responsable)}</div>
            <div class="time">#${item.id}<br>${formatDateTime(item.done_at)}</div>
          </div>

          <p class="task-text">${escapeHtml(item.texto)}</p>

          <div class="card-actions">
            <button class="btn btn-soft" onclick="deshacerTarea(${item.id})">Deshacer</button>
            <button class="icon-btn" onclick="eliminarTarea(${item.id})" title="Eliminar">✕</button>
          </div>

          <div class="meta">
            <div>Creada: ${formatDateTime(item.created_at)}</div>
            <div>Hecha: ${formatDateTime(item.done_at)}</div>
          </div>
        </div>
      `).join("");
    }

    async function recargarVista() {
      if (vistaActual === "programadas") {
        await cargarProgramadas();
      } else {
        await cargarHechas();
      }
    }

    function setClock() {
      const now = new Date();
      const fecha = now.toLocaleDateString("es-PE");
      const hora = now.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });
      document.getElementById("clockNow").textContent = `${fecha} · ${hora}`;
    }

    function initFilters() {
      const hoy = "{{ hoy }}";
      const mes = "{{ mes_actual }}";

      document.getElementById("fechaDia").value = hoy;
      document.getElementById("fechaDesde").value = hoy;
      document.getElementById("fechaHasta").value = hoy;
      document.getElementById("mesFiltro").value = mes;
    }

    document.addEventListener("keydown", function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        if (vistaActual === "programadas") {
          agregarTareas();
        }
      }
    });

    function init() {
      renderResponsables();
      initFilters();
      setClock();
      setInterval(setClock, 30000);
      recargarVista();
      setInterval(recargarVista, 15000);
      document.getElementById("taskInput").focus();
    }

    init();
  </script>
</body>
</html>
"""


@tareas_bp.route("/tareas")
def tareas_home():
    return render_template_string(
        HTML_TAREAS,
        responsables=RESPONSABLES,
        hoy=datetime.now(TZ).strftime("%Y-%m-%d"),
        mes_actual=datetime.now(TZ).strftime("%Y-%m")
    )


@tareas_bp.route("/tareas/api/programadas")
def api_programadas():
    responsable = (request.args.get("responsable") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    if responsable and responsable in RESPONSABLES:
        cur.execute("""
            SELECT * FROM tareas
            WHERE estado = 'programada' AND responsable = ?
            ORDER BY id DESC
        """, (responsable,))
    else:
        cur.execute("""
            SELECT * FROM tareas
            WHERE estado = 'programada'
            ORDER BY id DESC
        """)

    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({"result": rows})


@tareas_bp.route("/tareas/api/hechas")
def api_hechas():
    responsable = (request.args.get("responsable") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    if responsable and responsable in RESPONSABLES:
        cur.execute("""
            SELECT * FROM tareas
            WHERE estado = 'hecha' AND responsable = ?
            ORDER BY done_at DESC, id DESC
        """, (responsable,))
    else:
        cur.execute("""
            SELECT * FROM tareas
            WHERE estado = 'hecha'
            ORDER BY done_at DESC, id DESC
        """)

    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({"result": rows})


@tareas_bp.route("/tareas/api/crear", methods=["POST"])
def api_crear_tareas():
    data = request.get_json(silent=True) or {}
    texto = (data.get("texto") or "").strip()
    responsable = (data.get("responsable") or "").strip()

    if responsable not in RESPONSABLES:
        return jsonify({"error": "Responsable inválido"}), 400

    tareas = extraer_tareas_desde_texto(texto)

    if not tareas:
        return jsonify({"error": "No hay tareas válidas para guardar"}), 400

    conn = get_db()
    cur = conn.cursor()
    ahora = now_local_str()

    for tarea in tareas:
        cur.execute("""
            INSERT INTO tareas (texto, responsable, estado, created_at, done_at)
            VALUES (?, ?, 'programada', ?, NULL)
        """, (tarea, responsable, ahora))

    conn.commit()
    conn.close()

    cantidad = len(tareas)
    mensaje = f"{cantidad} {'tarea agregada' if cantidad == 1 else 'tareas agregadas'}"

    return jsonify({"message": mensaje, "count": cantidad}), 201


@tareas_bp.route("/tareas/api/<int:tarea_id>/hecho", methods=["POST"])
def api_marcar_hecha(tarea_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Tarea no encontrada"}), 404

    cur.execute("""
        UPDATE tareas
        SET estado = 'hecha',
            done_at = ?
        WHERE id = ?
    """, (now_local_str(), tarea_id))

    conn.commit()
    conn.close()

    return jsonify({"message": "OK"})


@tareas_bp.route("/tareas/api/<int:tarea_id>/deshacer", methods=["POST"])
def api_deshacer_tarea(tarea_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Tarea no encontrada"}), 404

    cur.execute("""
        UPDATE tareas
        SET estado = 'programada',
            done_at = NULL
        WHERE id = ?
    """, (tarea_id,))

    conn.commit()
    conn.close()

    return jsonify({"message": "OK"})


@tareas_bp.route("/tareas/api/<int:tarea_id>/eliminar", methods=["POST"])
def api_eliminar_tarea(tarea_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM tareas WHERE id = ?", (tarea_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "Tarea no encontrada"}), 404

    cur.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "OK"})


@tareas_bp.route("/tareas/api/vaciar_hechas", methods=["POST"])
def api_vaciar_hechas():
    data = request.get_json(silent=True) or {}
    responsable = (data.get("responsable") or "").strip()

    conn = get_db()
    cur = conn.cursor()

    if responsable and responsable in RESPONSABLES:
        cur.execute("""
            DELETE FROM tareas
            WHERE estado = 'hecha' AND responsable = ?
        """, (responsable,))
    else:
        cur.execute("""
            DELETE FROM tareas
            WHERE estado = 'hecha'
        """)

    borradas = cur.rowcount
    conn.commit()
    conn.close()

    return jsonify({"message": f"{borradas} tareas eliminadas"})


init_db()
