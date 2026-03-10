from flask import Blueprint, jsonify, request, render_template_string
import sqlite3
import os
import re
from drive_tasks_backup import (
    backup_db_to_drive_safely,
    restore_db_from_drive_if_missing_safely
)
from datetime import datetime
from zoneinfo import ZoneInfo

tareas_bp = Blueprint("tareas_bp", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.environ.get("TAREAS_DB_PATH", os.path.join(DATA_DIR, "tareas_simple.db"))
TZ = ZoneInfo("America/Lima")
RESPONSABLES = ["Elizabeth", "Shina", "Feling"]


def now_local_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
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

    if len(tareas) == 1 and ";" in tareas[0]:
        nuevas = []
        for pedazo in tareas[0].split(";"):
            limpia = limpiar_linea_tarea(pedazo)
            if limpia:
                nuevas.append(limpia)
        tareas = nuevas

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
  <title>RETOZ · Tareas</title>
  <style>
    :root{
      --orange:#D66C0E;
      --orange-dark:#B85C0C;
      --orange-soft:#F5E2D0;
      --black:#111111;
      --black-2:#1B1B1B;
      --white:#FFFFFF;
      --bg:#F5F5F4;
      --bg-soft:#FBFAF8;
      --line:rgba(17,17,17,.08);
      --muted:#6B6B6B;
      --success:#16A34A;
      --danger:#E64B3C;
      --shadow:0 14px 36px rgba(0,0,0,.08);
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
      background:
        radial-gradient(circle at top left, rgba(214,108,14,.08), transparent 28%),
        linear-gradient(180deg, #FBFAF8 0%, #F4F3F1 100%);
      color:var(--black);
      min-height:100%;
    }

    body{
      padding:14px;
    }

    .app{
      max-width:780px;
      margin:0 auto;
    }

    .topbar{
      position:sticky;
      top:0;
      z-index:50;
      padding-bottom:10px;
      backdrop-filter:blur(14px);
    }

    .topbar-card{
      background:rgba(255,255,255,.86);
      border:1px solid rgba(17,17,17,.06);
      box-shadow:var(--shadow);
      border-radius:28px;
      padding:14px;
    }

    .brand-row{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
    }

    .brand-wrap{
      display:flex;
      align-items:center;
      min-height:56px;
    }

    .brand-logo{
      height:54px;
      width:auto;
      object-fit:contain;
      display:block;
    }

    .brand-fallback{
      display:none;
      font-size:40px;
      line-height:1;
      font-family:Georgia, "Times New Roman", serif;
      letter-spacing:-.04em;
      color:#111;
      user-select:none;
    }

    .brand-fallback .o{
      color:var(--orange);
    }

    .clock{
      background:var(--black);
      color:var(--white);
      border-radius:999px;
      padding:9px 12px;
      font-size:12px;
      font-weight:800;
      white-space:nowrap;
      box-shadow:0 10px 20px rgba(0,0,0,.14);
    }

    .chips{
      display:flex;
      gap:8px;
      margin-top:14px;
      overflow:auto;
      scrollbar-width:none;
      padding-bottom:2px;
    }

    .chips::-webkit-scrollbar{display:none}

    .chip{
      border:1px solid rgba(17,17,17,.08);
      background:#fff;
      color:var(--black);
      border-radius:999px;
      padding:11px 14px;
      font-size:13px;
      font-weight:900;
      cursor:pointer;
      white-space:nowrap;
      transition:.18s ease;
    }

    .chip.active{
      background:var(--orange);
      color:var(--white);
      border-color:var(--orange);
      transform:translateY(-1px);
      box-shadow:0 12px 24px rgba(214,108,14,.22);
    }

    .section{
      background:rgba(255,255,255,.88);
      border:1px solid var(--line);
      box-shadow:var(--shadow);
      border-radius:var(--radius-xl);
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
      background:#F2F0EC;
      color:#4A4A4A;
      font-size:14px;
      font-weight:900;
      cursor:pointer;
      transition:.18s ease;
    }

    .tab-btn.active{
      background:var(--black);
      color:var(--white);
      box-shadow:0 12px 24px rgba(0,0,0,.16);
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
      background:#F5F3EF;
      color:var(--muted);
      border:1px solid var(--line);
      border-radius:999px;
      padding:8px 10px;
      font-size:12px;
      font-weight:900;
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
      min-height:80px;
      resize:vertical;
      border:1px solid rgba(17,17,17,.08);
      border-radius:18px;
      padding:15px;
      background:#fff;
      font:inherit;
      color:var(--black);
      outline:none;
      transition:.18s ease;
      box-shadow:inset 0 1px 1px rgba(0,0,0,.02);
    }

    textarea:focus,
    select:focus,
    input:focus{
      border-color:rgba(214,108,14,.42);
      box-shadow:0 0 0 4px rgba(214,108,14,.10);
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

    .btn:active{transform:scale(.985)}

    .btn-primary{
      flex:1;
      color:var(--white);
      background:linear-gradient(135deg,var(--orange),var(--orange-dark));
      box-shadow:0 12px 24px rgba(214,108,14,.22);
    }

    .btn-soft{
      background:#F4F3F1;
      color:var(--black);
      border:1px solid rgba(17,17,17,.08);
    }

    .btn-success{
      color:var(--white);
      background:linear-gradient(135deg,var(--black),#2B2B2B);
      box-shadow:0 12px 24px rgba(0,0,0,.16);
    }

    .btn-danger{
      color:var(--white);
      background:linear-gradient(135deg,var(--danger),#F97316);
      box-shadow:0 12px 24px rgba(230,75,60,.18);
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
      border:1px solid rgba(17,17,17,.08);
      background:#fff;
      border-radius:16px;
      padding:13px 14px;
      font:inherit;
      color:var(--black);
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
      background:#fff;
      border:1px solid rgba(17,17,17,.08);
      border-radius:22px;
      padding:14px;
      box-shadow:0 10px 24px rgba(0,0,0,.05);
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
      background:linear-gradient(90deg, rgba(214,108,14,.18), rgba(214,108,14,.55), rgba(17,17,17,.20));
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
      background:var(--orange-soft);
      color:var(--orange-dark);
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
      background:#FFF1F0;
      color:var(--danger);
      font-size:18px;
      cursor:pointer;
      border:1px solid rgba(230,75,60,.10);
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
      border:1px dashed rgba(214,108,14,.20);
      border-radius:20px;
      background:linear-gradient(180deg,#fff,#FBF8F4);
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
      background:rgba(17,17,17,.96);
      color:#fff;
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

    @media (min-width:640px){
      body{padding:20px}
      .topbar-card{padding:16px}
      .grid-2{grid-template-columns:1fr 1fr}
      .brand-logo{height:60px}
      .brand-fallback{font-size:46px}
    }
  </style>
</head>
<body>
  <div class="app">
    <div class="topbar">
      <div class="topbar-card">
        <div class="brand-row">
          <div class="brand-wrap">
            <img
              id="brandLogo"
              class="brand-logo"
              src="/retoz-logo.png"
              alt="RETOZ"
              onerror="fallbackLogo()"
            >
            <div id="brandFallback" class="brand-fallback">
              Ret<span class="o">o</span>z
            </div>
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

      <label class="composer-label">Escribe una tarea o pega una lista completa</label>
      <textarea
        id="taskInput"
        placeholder="- Llamar a cliente
- Revisar pedido
- Coordinar entrega

También acepta listas con números o [ ]"
      ></textarea>

      <div class="helper">
        Cada línea se guarda como una tarea separada. También puedes separar por punto y coma (;).
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

    function fallbackLogo() {
      const img = document.getElementById("brandLogo");
      const fb = document.getElementById("brandFallback");
      if (img) img.style.display = "none";
      if (fb) fb.style.display = "block";
    }

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
    backup_db_to_drive_safely(DB_PATH)

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
    backup_db_to_drive_safely(DB_PATH)

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
    backup_db_to_drive_safely(DB_PATH)

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
    backup_db_to_drive_safely(DB_PATH)

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
    backup_db_to_drive_safely(DB_PATH)

      return jsonify({"message": f"{borradas} tareas eliminadas"})


@tareas_bp.route("/tareas/api/backup_test")
def api_backup_test():
    print("[DEBUG] BACKUP_TEST INICIO")
    backup_db_to_drive_safely(DB_PATH)
    print("[DEBUG] BACKUP_TEST FIN")
    return jsonify({"message": "backup test lanzado"})


restore_db_from_drive_if_missing_safely(DB_PATH)
init_db()
