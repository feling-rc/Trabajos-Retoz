from flask import Blueprint, jsonify, request, send_file
import os
import time
import secrets
from threading import Lock
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


encargado_bp = Blueprint("encargado_bp", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

TZ = ZoneInfo("America/Lima")

URL = os.getenv("ODOO_URL", "https://retoz.odoo.com").strip()
DB = os.getenv("ODOO_DB", "retoz").strip()
USERNAME = os.getenv("ODOO_USERNAME", "retoz2023@gmail.com").strip()
API_KEY = (os.getenv("ODOO_API_KEY") or "").strip()

ACCESS_CODE = (os.getenv("ENCARGADO_ACCESS_CODE") or "210720").strip()
AUTH_REQUIRED = (os.getenv("ENCARGADO_AUTH_REQUIRED") or "false").strip().lower() in {"1", "true", "yes", "on"}

HTML_CANDIDATES = [
    os.path.join(PUBLIC_DIR, "encargadobonito.html"),
    os.path.join(BASE_DIR, "encargadobonito.html"),
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TrabajoGeneral/3.0"})

_UID = None
_UID_LOCK = Lock()

TOKENS = {}
TOKENS_LOCK = Lock()
TOKEN_TTL_SECONDS = 60 * 60 * 12

_OPTIONS_CACHE = {"ts": 0, "data": None}
_OPTIONS_CACHE_LOCK = Lock()
OPTIONS_CACHE_SECONDS = 120


# =========================
# CAMPOS ODOO
# =========================
MODEL_TASK = "project.task"
MODEL_ORDER = "sale.order"

FIELD_MODELO = "x_studio_modelo_de_par_1"
FIELD_DETALLE = "x_studio_detalles_del_trabajo_1"
FIELD_FECHA_TRABAJADO = "x_studio_fecha_de_trabajado"
FIELD_FECHA_A_TRABAJAR = os.getenv("ODOO_FIELD_FECHA_A_TRABAJAR", "x_studio_fecha_a_trabajarlo_2")
FIELD_FECHA_ENTREGA = os.getenv("ODOO_FIELD_FECHA_ENTREGA", "x_studio_fecha_de_entrega_1_1")
FIELD_ORDEN = "x_studio_orden_de_venta_1"
FIELD_PASADORES = "x_studio_pasadores_1"
FIELD_PLANTILLAS = "x_studio_plantillas_1"
FIELD_RESPONSABLE = "x_studio_responsable_r"
FIELD_ESTADO = "x_studio_selection_field_3j_1ivn1ho1m"
FIELD_VERIF = "x_studio_verificacion_de_excel"
FIELD_TRABAJADO_POR = "x_studio_trabajado_por"
FIELD_ANDAMIO = "x_studio_andamio"
FIELD_PRECIO_TRABAJO = "x_studio_precio_de_trabajo"
FIELD_CREATE_DATE = "create_date"

# Compatibilidad con código viejo
FIELD_UBICACION_ALIAS_OLD = "x_studio_ubicacion_exacta_1"

OPTIONAL_FIELDS = {
    FIELD_FECHA_A_TRABAJAR,
    FIELD_FECHA_ENTREGA,
    FIELD_PRECIO_TRABAJO,
}

COMMON_TASK_FIELDS = [
    "id",
    FIELD_MODELO,
    FIELD_DETALLE,
    FIELD_FECHA_TRABAJADO,
    FIELD_FECHA_A_TRABAJAR,
    FIELD_FECHA_ENTREGA,
    FIELD_ORDEN,
    FIELD_PASADORES,
    FIELD_PLANTILLAS,
    FIELD_RESPONSABLE,
    FIELD_ESTADO,
    FIELD_VERIF,
    FIELD_TRABAJADO_POR,
    FIELD_ANDAMIO,
    FIELD_PRECIO_TRABAJO,
    FIELD_CREATE_DATE,
]


# =========================
# FALLBACKS
# =========================
RESPONSABLE_CHOICES_FALLBACK = [
    ("PEDRO 1", "PEDRO"),
    ("FELING 1", "FELING"),
    ("YULI", "YULI"),
    ("JORGE", "JORGE"),
    ("EZER", "EZER"),
    ("ALEX", "ALEX"),
    ("SR COCO", "SR COCO"),
    ("KEVIN", "KEVIN"),
    ("SHINA", "SHINA"),
    ("Ninguno", "Ninguno"),
]

UBICACION_CHOICES_FALLBACK = [
    ("A-1", "A-1"),
    ("F-1", "F-1"),
    ("F-2", "F-2"),
    ("F-3", "F-3"),
    ("F-4", "F-4"),
    ("F-5", "F-5"),
    ("F-6", "F-6"),
    ("F-7", "F-7"),
    ("P-1", "P-1"),
    ("P-2", "P-2"),
    ("P-3", "P-3"),
    ("P-4", "P-4"),
    ("P-5", "P-5"),
    ("RECOGIDO", "RECOGIDO"),
    ("ABANDONADO 1", "ABANDONADO 1"),
    ("ABANDONADO 2", "ABANDONADO 2"),
    ("EN ANCHADORA", "EN ANCHADORA"),
    ("JORGE", "JORGE"),
    ("PEDRO", "PEDRO"),
    ("ALEX", "ALEX"),
    ("ELIZABETH", "ELIZABETH"),
    ("EZER", "EZER"),
    ("KEVIN", "KEVIN"),
    ("YULI", "YULI"),
    ("SR COCO", "SR COCO"),
    ("FELING", "FELING"),
    ("A", "A"),
    ("B", "B"),
    ("C", "C"),
    ("D", "D"),
    ("E", "E"),
    ("F", "F"),
    ("G", "G"),
    ("H", "H"),
    ("I", "I"),
    ("J", "J"),
    ("K", "K"),
    ("A-2", "A-2"),
    ("ENTREGADO", "ENTREGADO"),
    ("COMPLETADO", "COMPLETADO"),
    ("Esperando ser guardado", "ESPERANDO SER GUARDADO"),
]

TRABAJADO_POR_CHOICES_FALLBACK = [
    ("Ezer", "Ezer"),
    ("Feling", "Feling"),
    ("Pedro", "Pedro"),
    ("Sr Juan", "Sr Juan"),
    ("Sr Coco", "Sr Coco"),
    ("Alex", "Alex"),
    ("Jorge", "Jorge"),
    ("Even Ezer", "Even Ezer"),
    ("Kevin", "Kevin"),
    ("Yuli", "Yuli"),
    ("Shina", "Shina"),
]

ESTADO_CHOICES_FALLBACK = [
    ("01_in_progress", "Agendado"),
    ("En Ruta", "En ruta"),
    ("02_changes_requested", "Sin material"),
    ("03_approved", "En proceso"),
    ("04_waiting_material", "Atrasado"),
    ("04_waiting_normal", "Atrasado"),
    ("1_cancelled", "Cancelado"),
    ("1_canceled", "Cancelado"),
    ("1_done", "Completado"),
    ("Entregado", "Entregado"),
    ("Ya no Quiere", "Ya no quiere"),
    ("Ya no quiere", "Ya no quiere"),
    ("Agendar Con Bot", "Agendar con bot"),
    ("TRABAJADO", "Trabajado"),
    ("Empaquetado", "Empaquetado"),
    ("Agendado con Courier", "Agendado con courier"),
    ("En Shalon", "En Shalon"),
    ("En progreso", "Agendado"),
    ("in_progress", "Agendado"),
    ("in_process", "En proceso"),
]

RESET_COHERENCE_STATES = {
    "01_in_progress",
    "02_changes_requested",
    "03_approved",
    "04_waiting_material",
    "04_waiting_normal",
    "1_canceled",
    "1_cancelled",
    "Ya no Quiere",
    "Ya no quiere",
    "Agendar Con Bot",
    "En progreso",
    "in_progress",
    "in_process",
}


# =========================
# HELPERS GENERALES
# =========================
def log(*args):
    print("[ENCARGADO]", *args, flush=True)


def json_error(message, status=400):
    return jsonify({"error": str(message)}), status


def now_lima_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def normalize_state(value):
    return str(value or "").strip()


def limpiar_numero(texto):
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def extract_order_text(value):
    if isinstance(value, list) and len(value) >= 2:
        return value[1] or ""
    return ""


def normalize_iso_to_odoo(val):
    if val in (None, "", "null", False):
        return False

    if isinstance(val, str):
        s = val.replace("Z", "")
        if "T" in s:
            s = s.replace("T", " ")
        if "." in s:
            s = s.split(".")[0]
        return s

    return val


def find_html_file():
    for path in HTML_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def cleanup_tokens():
    now_ts = time.time()
    with TOKENS_LOCK:
        expired = [token for token, meta in TOKENS.items() if meta["exp"] < now_ts]
        for token in expired:
            TOKENS.pop(token, None)


def create_token():
    cleanup_tokens()
    token = secrets.token_urlsafe(32)
    with TOKENS_LOCK:
        TOKENS[token] = {
            "exp": time.time() + TOKEN_TTL_SECONDS,
            "created": time.time(),
        }
    return token


def require_token():
    if not AUTH_REQUIRED:
        return None, None

    cleanup_tokens()
    token = request.headers.get("X-Encargado-Token", "").strip()

    if not token:
        return None, json_error("Acceso no autorizado.", 401)

    with TOKENS_LOCK:
        meta = TOKENS.get(token)
        if not meta:
            return None, json_error("Acceso inválido o vencido.", 401)

        if meta["exp"] < time.time():
            TOKENS.pop(token, None)
            return None, json_error("Tu sesión venció.", 401)

        meta["exp"] = time.time() + TOKEN_TTL_SECONDS

    return token, None


def extract_invalid_optional_fields(error_text, fields):
    bad = []
    msg = str(error_text or "")
    for field in OPTIONAL_FIELDS:
        if field in fields and field in msg:
            bad.append(field)
    return bad


def choices_to_json(choices):
    return [{"value": value, "label": label} for value, label in choices]


# =========================
# ODOO
# =========================
def login_odoo(force=False):
    global _UID

    if _UID and not force:
        return _UID

    with _UID_LOCK:
        if _UID and not force:
            return _UID

        if not API_KEY:
            raise Exception("Falta ODOO_API_KEY en variables de entorno.")

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "login",
                "args": [DB, USERNAME, API_KEY],
            },
            "id": 1,
        }

        resp = SESSION.post(f"{URL}/jsonrpc", json=payload, timeout=30)
        resp.raise_for_status()
        uid = resp.json().get("result")

        if not uid:
            raise Exception("No se pudo iniciar sesión en Odoo.")

        _UID = uid
        return _UID


def odoo_execute_kw(model, method, args=None, kwargs=None, req_id=2, retry=True):
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

    uid = login_odoo()

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [DB, uid, API_KEY, model, method, args, kwargs],
        },
        "id": req_id,
    }

    try:
        resp = SESSION.post(f"{URL}/jsonrpc", json=payload, timeout=35)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        if retry:
            login_odoo(force=True)
            return odoo_execute_kw(model, method, args, kwargs, req_id=req_id, retry=False)
        raise Exception(f"Error de conexión con Odoo: {e}")

    if "error" in data:
        err = data["error"]
        msg = err.get("data", {}).get("message") or err.get("message") or "Error en Odoo"

        if retry and ("Access denied" in msg or "Session" in msg or "login" in msg.lower()):
            login_odoo(force=True)
            return odoo_execute_kw(model, method, args, kwargs, req_id=req_id, retry=False)

        raise Exception(msg)

    return data.get("result")


def get_field_selection(model, field_name, fallback):
    try:
        meta = odoo_execute_kw(
            model,
            "fields_get",
            args=[[field_name]],
            kwargs={"attributes": ["selection", "string", "type"]},
            req_id=30,
        ) or {}

        field_meta = meta.get(field_name) or {}
        selection = field_meta.get("selection") or []

        cleaned = []
        for item in selection:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                cleaned.append((str(item[0]), str(item[1])))

        return cleaned or fallback
    except Exception as e:
        log(f"fields_get fallback en {field_name}:", str(e))
        return fallback


def get_live_options(force=False):
    now_ts = time.time()

    with _OPTIONS_CACHE_LOCK:
        if (
            not force
            and _OPTIONS_CACHE["data"] is not None
            and (now_ts - _OPTIONS_CACHE["ts"]) < OPTIONS_CACHE_SECONDS
        ):
            return _OPTIONS_CACHE["data"]

    data = {
        "responsables": get_field_selection(MODEL_TASK, FIELD_RESPONSABLE, RESPONSABLE_CHOICES_FALLBACK),
        "ubicaciones": get_field_selection(MODEL_TASK, FIELD_ANDAMIO, UBICACION_CHOICES_FALLBACK),
        "trabajado_por": get_field_selection(MODEL_TASK, FIELD_TRABAJADO_POR, TRABAJADO_POR_CHOICES_FALLBACK),
        "estados": get_field_selection(MODEL_TASK, FIELD_ESTADO, ESTADO_CHOICES_FALLBACK),
    }

    with _OPTIONS_CACHE_LOCK:
        _OPTIONS_CACHE["ts"] = now_ts
        _OPTIONS_CACHE["data"] = data

    return data


def read_task(tarea_id, fields):
    try:
        result = odoo_execute_kw(
            MODEL_TASK,
            "read",
            args=[[tarea_id], fields],
            kwargs={},
            req_id=9,
        )
    except Exception as e:
        bad = extract_invalid_optional_fields(str(e), fields)
        if not bad:
            raise

        fallback_fields = [f for f in fields if f not in bad]
        result = odoo_execute_kw(
            MODEL_TASK,
            "read",
            args=[[tarea_id], fallback_fields],
            kwargs={},
            req_id=10,
        )
        rec = result[0] if isinstance(result, list) and result else {}
        for missing in bad:
            rec[missing] = False
        return rec

    return result[0] if isinstance(result, list) and result else {}


def search_read_tasks(domain, fields, order="create_date desc", limit=500, req_id=5):
    try:
        return odoo_execute_kw(
            MODEL_TASK,
            "search_read",
            args=[domain],
            kwargs={"fields": fields, "order": order, "limit": limit},
            req_id=req_id,
        )
    except Exception as e:
        bad = extract_invalid_optional_fields(str(e), fields)
        if not bad:
            raise

        fallback_fields = [f for f in fields if f not in bad]
        rows = odoo_execute_kw(
            MODEL_TASK,
            "search_read",
            args=[domain],
            kwargs={"fields": fallback_fields, "order": order, "limit": limit},
            req_id=req_id + 1,
        )

        for row in rows:
            for missing in bad:
                row[missing] = False

        return rows


def search_sale_order_ids(query, limit=80):
    q = str(query or "").strip()
    if not q:
        return []

    try:
        ids = odoo_execute_kw(
            MODEL_ORDER,
            "search",
            args=[[["name", "ilike", q]]],
            kwargs={"limit": limit},
            req_id=41,
        )
        return ids or []
    except Exception as e:
        log("search_sale_order_ids fallback:", str(e))
        return []


def write_task(tarea_id, update_data, req_id=20):
    log("WRITE tarea_id =", tarea_id)
    log("WRITE data =", update_data)

    ok = odoo_execute_kw(
        MODEL_TASK,
        "write",
        args=[[tarea_id], update_data],
        kwargs={},
        req_id=req_id,
    )

    log("WRITE ok =", ok)
    return ok


# =========================
# LÓGICA DE NEGOCIO
# =========================
def estado_bonito(code, estado_labels):
    key = normalize_state(code)
    return estado_labels.get(key, key or "-")


def apply_state_coherence(update_data, estado_in, current):
    estado = normalize_state(estado_in)
    if not estado:
        return

    if estado in RESET_COHERENCE_STATES:
        update_data[FIELD_VERIF] = False
        update_data[FIELD_FECHA_TRABAJADO] = False
        update_data[FIELD_TRABAJADO_POR] = False
        return

    if estado == "TRABAJADO":
        tp = update_data.get(FIELD_TRABAJADO_POR)
        if tp in (None, "", False):
            tp = current.get(FIELD_TRABAJADO_POR)

        if not tp:
            raise Exception("Primero debes seleccionar Trabajado por.")

        update_data[FIELD_VERIF] = True

        if FIELD_FECHA_TRABAJADO not in update_data or not update_data.get(FIELD_FECHA_TRABAJADO):
            update_data[FIELD_FECHA_TRABAJADO] = current.get(FIELD_FECHA_TRABAJADO) or now_lima_str()

        update_data[FIELD_TRABAJADO_POR] = tp
        # NO cambiamos andamio automáticamente.
        # El botón Marcar listo debe conservar la lógica original.


def task_to_payload(rec, estado_labels):
    orden_texto = extract_order_text(rec.get(FIELD_ORDEN))

    return {
        "id": rec.get("id"),
        "modelo": rec.get(FIELD_MODELO) or "",
        "detalle": rec.get(FIELD_DETALLE) or "",
        "estado_code": rec.get(FIELD_ESTADO) or "",
        "estado_label": estado_bonito(rec.get(FIELD_ESTADO), estado_labels),
        "fecha_trabajado": rec.get(FIELD_FECHA_TRABAJADO) or False,
        "fecha_a_trabajarlo": rec.get(FIELD_FECHA_A_TRABAJAR) or False,
        "fecha_entrega": rec.get(FIELD_FECHA_ENTREGA) or False,
        "orden_texto": orden_texto,
        "orden_numero": limpiar_numero(orden_texto),
        "pasadores": bool(rec.get(FIELD_PASADORES)),
        "plantillas": bool(rec.get(FIELD_PLANTILLAS)),
        "responsable": rec.get(FIELD_RESPONSABLE) or "",
        "ubicacion_seguimiento": rec.get(FIELD_ANDAMIO) or "",
        "trabajado_por": rec.get(FIELD_TRABAJADO_POR) or "",
        "andamio": rec.get(FIELD_ANDAMIO) or "",
        "verificacion": bool(rec.get(FIELD_VERIF)),
        "precio_trabajo": rec.get(FIELD_PRECIO_TRABAJO) if rec.get(FIELD_PRECIO_TRABAJO) not in (None, False) else "",
        "create_date": rec.get(FIELD_CREATE_DATE) or "",
    }


def sort_rows_by_create_date_desc(rows):
    def key_fn(row):
        return str(row.get(FIELD_CREATE_DATE) or "")

    return sorted(rows, key=key_fn, reverse=True)


def unique_rows_by_id(rows):
    seen = set()
    out = []
    for row in rows:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out


def search_tasks_by_query(query, limit, fields):
    q = str(query or "").strip()
    if not q:
        return []

    base_domain = [[FIELD_MODELO, "!=", False]]
    buckets = []

    # 1) Buscar por orden de venta (robusto)
    order_ids = search_sale_order_ids(q, limit=limit)
    if order_ids:
        buckets.extend(
            search_read_tasks(
                base_domain + [[FIELD_ORDEN, "in", order_ids]],
                fields,
                order=f"{FIELD_CREATE_DATE} desc",
                limit=limit,
                req_id=50,
            )
        )

    # 2) Buscar por modelo
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_MODELO, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=52,
        )
    )

    # 3) Buscar por detalle
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_DETALLE, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=54,
        )
    )

    # 4) Buscar por responsable
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_RESPONSABLE, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=56,
        )
    )

    # 5) Buscar por trabajado por
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_TRABAJADO_POR, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=58,
        )
    )

    # 6) Buscar por andamio / ubicación
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_ANDAMIO, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=60,
        )
    )

    # 7) Buscar por estado
    buckets.extend(
        search_read_tasks(
            base_domain + [[FIELD_ESTADO, "ilike", q]],
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=limit,
            req_id=62,
        )
    )

    rows = unique_rows_by_id(sort_rows_by_create_date_desc(buckets))

    # 8) Fallback adicional por texto completo en Python
    if len(rows) < limit:
        text_q = q.lower()
        fallback_rows = search_read_tasks(
            base_domain,
            fields,
            order=f"{FIELD_CREATE_DATE} desc",
            limit=max(limit * 3, 200),
            req_id=64,
        )

        filtered = []
        for row in fallback_rows:
            orden_texto = extract_order_text(row.get(FIELD_ORDEN))
            blob = " ".join([
                str(row.get(FIELD_MODELO, "")),
                str(row.get(FIELD_DETALLE, "")),
                str(orden_texto),
                str(row.get(FIELD_RESPONSABLE, "")),
                str(row.get(FIELD_TRABAJADO_POR, "")),
                str(row.get(FIELD_ANDAMIO, "")),
                str(row.get(FIELD_ESTADO, "")),
            ]).lower()

            if text_q in blob:
                filtered.append(row)

        rows = unique_rows_by_id(sort_rows_by_create_date_desc(rows + filtered))

    return rows[:limit]


# =========================
# RUTAS
# =========================
@encargado_bp.route("/trabajo-general")
def trabajo_general_home():
    html_path = find_html_file()
    if not html_path:
        return "No encuentro encargadobonito.html", 404
    return send_file(html_path)


@encargado_bp.route("/trabajo-general/api/login", methods=["POST"])
def trabajo_general_login():
    if not AUTH_REQUIRED:
        return jsonify({
            "ok": True,
            "token": "",
            "user": "Trabajo general",
        })

    body = request.get_json(silent=True) or {}
    code = str(body.get("code", "")).strip()

    if not code:
        return json_error("Ingresa el código.", 400)

    if code != ACCESS_CODE:
        return json_error("Código inválido.", 401)

    token = create_token()
    return jsonify({
        "ok": True,
        "token": token,
        "user": "Trabajo general",
    })


@encargado_bp.route("/trabajo-general/api/logout", methods=["POST"])
def trabajo_general_logout():
    token = request.headers.get("X-Encargado-Token", "").strip()
    if token:
        with TOKENS_LOCK:
            TOKENS.pop(token, None)
    return jsonify({"ok": True})


@encargado_bp.route("/trabajo-general/api/health")
def trabajo_general_health():
    return jsonify({"ok": True}), 200


@encargado_bp.route("/trabajo-general/api/options")
def trabajo_general_options():
    _, err = require_token()
    if err:
        return err

    try:
        opts = get_live_options(force=False)
        return jsonify({
            "responsables": choices_to_json(opts["responsables"]),
            "ubicaciones": choices_to_json(opts["ubicaciones"]),
            "trabajado_por": choices_to_json(opts["trabajado_por"]),
            "estados": choices_to_json(opts["estados"]),
        })
    except Exception as e:
        log("ERROR /options =", str(e))
        return jsonify({
            "responsables": choices_to_json(RESPONSABLE_CHOICES_FALLBACK),
            "ubicaciones": choices_to_json(UBICACION_CHOICES_FALLBACK),
            "trabajado_por": choices_to_json(TRABAJADO_POR_CHOICES_FALLBACK),
            "estados": choices_to_json(ESTADO_CHOICES_FALLBACK),
        })


@encargado_bp.route("/trabajo-general/api/tasks")
def trabajo_general_tasks():
    _, err = require_token()
    if err:
        return err

    try:
        opts = get_live_options(force=False)
        estado_labels = {value: label for value, label in opts["estados"]}

        q = (request.args.get("q", "") or "").strip()
        mode = (request.args.get("mode", "") or "").strip().lower()
        limit_raw = request.args.get("limit", "20")

        try:
            limit = int(limit_raw)
        except Exception:
            limit = 20

        if limit <= 0:
            limit = 20
        if limit > 300:
            limit = 300

        base_fields = COMMON_TASK_FIELDS

        if q:
            result = search_tasks_by_query(q, limit, base_fields)
        else:
            base_domain = [[FIELD_MODELO, "!=", False]]
            if mode == "latest":
                result = search_read_tasks(
                    base_domain,
                    base_fields,
                    order=f"{FIELD_CREATE_DATE} desc",
                    limit=limit,
                    req_id=70,
                )
            else:
                result = search_read_tasks(
                    base_domain,
                    base_fields,
                    order=f"{FIELD_CREATE_DATE} desc",
                    limit=limit,
                    req_id=72,
                )

        payload = [task_to_payload(r, estado_labels) for r in (result or [])]

        return jsonify({"result": payload})

    except Exception as e:
        log("ERROR /tasks =", str(e))
        return jsonify({"error": str(e), "result": []}), 500


@encargado_bp.route("/trabajo-general/api/terminados")
def trabajo_general_terminados():
    _, err = require_token()
    if err:
        return err

    try:
        trabajado_por = (request.args.get("trabajado_por", "") or "").strip()
        limit_raw = request.args.get("limit", "500")

        try:
            limit = int(limit_raw)
        except Exception:
            limit = 500

        if limit <= 0:
            limit = 500
        if limit > 1000:
            limit = 1000

        opts = get_live_options(force=False)
        estado_labels = {value: label for value, label in opts["estados"]}

        domain = [
            [FIELD_MODELO, "!=", False],
            [FIELD_TRABAJADO_POR, "!=", False],
            [FIELD_FECHA_TRABAJADO, "!=", False],
            [FIELD_ESTADO, "!=", "03_approved"],
        ]

        if trabajado_por and trabajado_por.upper() != "ALL":
            domain.append([FIELD_TRABAJADO_POR, "=", trabajado_por])

        result = search_read_tasks(
            domain,
            COMMON_TASK_FIELDS,
            order=f"{FIELD_FECHA_TRABAJADO} desc",
            limit=limit,
            req_id=80,
        )

        payload = [task_to_payload(r, estado_labels) for r in (result or [])]
        return jsonify({"result": payload})

    except Exception as e:
        log("ERROR /terminados =", str(e))
        return jsonify({"error": str(e), "result": []}), 500


@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/update", methods=["POST"])
def trabajo_general_update_task(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        body = request.get_json(silent=True) or {}
        data = body.get("data", {}) or {}

        current = read_task(tarea_id, COMMON_TASK_FIELDS)
        if not current:
            return json_error("Tarea no encontrada.", 404)

        opts = get_live_options(force=True)
        responsable_values = {value for value, _ in opts["responsables"]}
        ubicacion_values = {value for value, _ in opts["ubicaciones"]}
        trabajado_por_values = {value for value, _ in opts["trabajado_por"]}
        valid_estado_values = {value for value, _ in opts["estados"]}
        estado_labels = {value: label for value, label in opts["estados"]}

        update_data = {}

        if FIELD_RESPONSABLE in data:
            responsable = str(data.get(FIELD_RESPONSABLE) or "").strip()
            if responsable and responsable not in responsable_values:
                return json_error(f"Responsable no válido: {responsable}", 400)
            update_data[FIELD_RESPONSABLE] = responsable or False

        if FIELD_ANDAMIO in data or FIELD_UBICACION_ALIAS_OLD in data:
            raw_ubi = data.get(FIELD_ANDAMIO, data.get(FIELD_UBICACION_ALIAS_OLD))
            ubicacion = str(raw_ubi or "").strip()
            if ubicacion and ubicacion not in ubicacion_values:
                return json_error(f"Ubicación no válida: {ubicacion}", 400)
            update_data[FIELD_ANDAMIO] = ubicacion or False

        if FIELD_TRABAJADO_POR in data:
            trabajado_por = str(data.get(FIELD_TRABAJADO_POR) or "").strip()
            if trabajado_por and trabajado_por not in trabajado_por_values:
                return json_error(f"Trabajado por no válido: {trabajado_por}", 400)
            update_data[FIELD_TRABAJADO_POR] = trabajado_por or False

        if FIELD_ESTADO in data:
            estado = normalize_state(data.get(FIELD_ESTADO))
            if estado and estado not in valid_estado_values:
                return json_error(f"Estado no válido: {estado}", 400)
            update_data[FIELD_ESTADO] = estado or False
            apply_state_coherence(update_data, estado, current)

        if FIELD_FECHA_TRABAJADO in data:
            update_data[FIELD_FECHA_TRABAJADO] = normalize_iso_to_odoo(data.get(FIELD_FECHA_TRABAJADO))

        if not update_data:
            return json_error("No hay campos válidos para actualizar.", 400)

        ok = write_task(tarea_id, update_data, req_id=90)
        if ok is not True:
            return json_error("Odoo no confirmó la actualización.", 500)

        updated = read_task(tarea_id, COMMON_TASK_FIELDS)
        log("UPDATED =", updated)

        return jsonify({
            "ok": True,
            "message": "Actualizado correctamente.",
            "task": task_to_payload(updated, estado_labels),
        })

    except Exception as e:
        log("ERROR /update =", str(e))
        return jsonify({"error": str(e)}), 500


@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/toggle_listo", methods=["POST"])
def trabajo_general_toggle_listo(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        body = request.get_json(silent=True) or {}

        actual = read_task(tarea_id, COMMON_TASK_FIELDS)
        if not actual:
            return json_error("Tarea no encontrada.", 404)

        opts = get_live_options(force=True)
        trabajado_por_values = {value for value, _ in opts["trabajado_por"]}
        estado_labels = {value: label for value, label in opts["estados"]}

        estado_actual = normalize_state(actual.get(FIELD_ESTADO))
        estaba_listo = (estado_actual == "TRABAJADO")

        if not estaba_listo:
            trabajado_por = str(
                body.get("trabajado_por", "") or actual.get(FIELD_TRABAJADO_POR) or ""
            ).strip()

            if not trabajado_por:
                return json_error("Primero debes seleccionar Trabajado por.", 400)

            if trabajado_por not in trabajado_por_values:
                return json_error(f'Valor de "Trabajado por" no válido: {trabajado_por}', 400)

            data_to_update = {
                FIELD_ESTADO: "TRABAJADO",
                FIELD_VERIF: True,
                FIELD_FECHA_TRABAJADO: actual.get(FIELD_FECHA_TRABAJADO) or now_lima_str(),
                FIELD_TRABAJADO_POR: trabajado_por,
                FIELD_ANDAMIO: actual.get(FIELD_ANDAMIO) or False,
            }
            msg = "Marcado como listo."
        else:
            data_to_update = {
                FIELD_ESTADO: "03_approved",
                FIELD_VERIF: False,
                FIELD_FECHA_TRABAJADO: False,
                FIELD_TRABAJADO_POR: False,
                FIELD_ANDAMIO: actual.get(FIELD_ANDAMIO) or False,
            }
            msg = "Listo desmarcado."

        ok = write_task(tarea_id, data_to_update, req_id=92)
        if ok is not True:
            return json_error("Odoo no confirmó el cambio.", 500)

        updated = read_task(tarea_id, COMMON_TASK_FIELDS)
        log("UPDATED =", updated)

        return jsonify({
            "ok": True,
            "message": msg,
            "task": task_to_payload(updated, estado_labels),
        })

    except Exception as e:
        log("ERROR /toggle_listo =", str(e))
        return jsonify({"error": str(e)}), 500


@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/complete", methods=["POST"])
def trabajo_general_complete(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        actual = read_task(tarea_id, COMMON_TASK_FIELDS)
        if not actual:
            return json_error("Tarea no encontrada.", 404)

        opts = get_live_options(force=False)
        estado_labels = {value: label for value, label in opts["estados"]}

        data_to_update = {
            FIELD_ESTADO: "1_done",
        }

        ok = write_task(tarea_id, data_to_update, req_id=94)
        if ok is not True:
            return json_error("Odoo no confirmó el completado.", 500)

        updated = read_task(tarea_id, COMMON_TASK_FIELDS)
        log("UPDATED =", updated)

        return jsonify({
            "ok": True,
            "message": "Tarea marcada como completado.",
            "task": task_to_payload(updated, estado_labels),
        })

    except Exception as e:
        log("ERROR /complete =", str(e))
        return jsonify({"error": str(e)}), 500