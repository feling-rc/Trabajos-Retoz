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

# =========================
# CONFIG GENERAL
# =========================
TZ = ZoneInfo("America/Lima")

URL = os.getenv("ODOO_URL", "https://retoz.odoo.com")
DB = os.getenv("ODOO_DB", "retoz")
USERNAME = os.getenv("ODOO_USERNAME", "retoz2023@gmail.com")
API_KEY = os.getenv("ODOO_API_KEY")

# código supervisor
ACCESS_CODE = os.getenv("ENCARGADO_ACCESS_CODE", "210720").strip()

# archivo HTML
HTML_CANDIDATES = [
    os.path.join(PUBLIC_DIR, "encargadobonito.html"),
    os.path.join(BASE_DIR, "encargadobonito.html"),
]

# requests session
SESSION = requests.Session()
_UID = None
_UID_LOCK = Lock()

# tokens simples en memoria
TOKENS = {}
TOKENS_LOCK = Lock()
TOKEN_TTL_SECONDS = 60 * 60 * 12  # 12 horas

# =========================
# CAMPOS ODOO
# =========================
FIELD_MODELO = "x_studio_modelo_de_par_1"
FIELD_DETALLE = "x_studio_detalles_del_trabajo_1"
FIELD_FECHA_TRABAJADO = "x_studio_fecha_de_trabajado"
FIELD_FECHA_ENTREGA = os.getenv("ODOO_FIELD_FECHA_ENTREGA", "x_studio_fecha_de_entrega")
FIELD_ORDEN = "x_studio_orden_de_venta_1"
FIELD_PASADORES = "x_studio_pasadores_1"
FIELD_PLANTILLAS = "x_studio_plantillas_1"
FIELD_RESPONSABLE = "x_studio_responsable_r"
FIELD_UBICACION = "x_studio_ubicacion_exacta_1"
FIELD_ESTADO = "x_studio_selection_field_3j_1ivn1ho1m"
FIELD_VERIF = "x_studio_verificacion_de_excel"
FIELD_TRABAJADO_POR = "x_studio_trabajado_por"
FIELD_ANDAMIO = "x_studio_andamio"
FIELD_CREATE_DATE = "create_date"

OPTIONAL_FIELDS = {FIELD_FECHA_ENTREGA}

# =========================
# OPCIONES
# =========================
RESPONSABLE_OPTIONS = [
    "PEDRO",
    "FELING",
    "YULI",
    "JORGE",
    "EZER",
    "ALEX",
    "SR COCO",
    "KEVIN",
    "SHINA",
]

UBICACION_OPTIONS = [
    "DEFINIDO",
    "A-1",
    "A-2",
    "A-3",
    "A-4",
    "F-1",
    "F-2",
    "F-3",
    "F-4",
    "F-5",
    "P-1",
    "P-2",
    "P-3",
    "P-4",
    "P-5",
    "EN ANCHEADORA",
    "ABANDONADO 1",
    "ABANDONADO 2",
    "ENTREGADO",
    "COMPLETADO",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "P-6",
    "F-7",
]

TRABAJADO_POR_OPTIONS = [
    "Pedro",
    "Feling",
    "Yuli",
    "Jorge",
    "Even Ezer",
    "Alex",
    "Sr Juan",
    "Sr Coco",
    "Kevin",
    "Shina",
]

TRABAJADO_POR_TO_ANDAMIO = {
    "Pedro": "PEDRO",
    "Feling": "FELING",
    "Yuli": "YULI",
    "Jorge": "JORGE",
    "Even Ezer": "EZER",
    "Alex": "ALEX",
    "Sr Juan": "SR JUAN",
    "Sr Coco": "SR COCO",
    "Kevin": "KEVIN",
    "Shina": "SHINA",
}

ESTADO_LABELS = {
    "TRABAJADO": "Trabajado",
    "03_approved": "En proceso",
    "02_changes_requested": "Sin material",
    "04_waiting_material": "Atrasado",
    "04_waiting_normal": "Atrasado",
    "1_done": "Completado",
    "1_cancelled": "Cancelado",
    "1_canceled": "Cancelado",
    "Entregado": "Entregado",
    "En el Courier": "En el courier",
    "Ya no quiere": "Ya no quiere",
    "Ya no Quiere": "Ya no quiere",
    "Agendar Con Bot": "Agendar con bot",
    "En progreso": "Agendado",
    "in_progress": "Agendado",
    "01_in_progress": "Agendado",
    "in_process": "En proceso",
    "En Ruta": "En ruta",
    "Empaquetado": "Empaquetado",
    "Agendado con Courier": "Agendado con courier",
}

FINAL_STATES = {"1_done", "Entregado"}

# =========================
# HELPERS
# =========================
def json_error(message, status=400):
    return jsonify({"error": str(message)}), status


def now_lima_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def normalize_state(value):
    return str(value or "").strip()


def estado_bonito(code):
    key = normalize_state(code)
    return ESTADO_LABELS.get(key, key or "-")


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

        # renueva TTL al usarlo
        meta["exp"] = time.time() + TOKEN_TTL_SECONDS

    return token, None


def limpiar_numero(texto):
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


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


# =========================
# ODOO HELPERS
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

        # si caducó algo, reintenta 1 vez
        if retry and ("Access denied" in msg or "Session" in msg or "login" in msg.lower()):
            login_odoo(force=True)
            return odoo_execute_kw(model, method, args, kwargs, req_id=req_id, retry=False)

        raise Exception(msg)

    return data.get("result")


def read_task(tarea_id, fields):
    result = odoo_execute_kw(
        "project.task",
        "read",
        args=[[tarea_id], fields],
        kwargs={},
        req_id=9,
    )
    return result[0] if isinstance(result, list) and result else {}


def search_read_tasks(domain, fields, order="create_date desc", limit=500):
    try:
        return odoo_execute_kw(
            "project.task",
            "search_read",
            args=[domain],
            kwargs={"fields": fields, "order": order, "limit": limit},
            req_id=5,
        )
    except Exception as e:
        msg = str(e)
        invalid_optionals = [f for f in OPTIONAL_FIELDS if f in msg]

        if not invalid_optionals:
            raise

        fallback_fields = [f for f in fields if f not in invalid_optionals]

        rows = odoo_execute_kw(
            "project.task",
            "search_read",
            args=[domain],
            kwargs={"fields": fallback_fields, "order": order, "limit": limit},
            req_id=6,
        )

        for row in rows:
            for missing in invalid_optionals:
                row[missing] = False

        return rows


def task_to_payload(rec):
    orden_texto = ""
    if isinstance(rec.get(FIELD_ORDEN), list) and len(rec.get(FIELD_ORDEN)) >= 2:
        orden_texto = rec[FIELD_ORDEN][1] or ""

    payload = {
        "id": rec.get("id"),
        "modelo": rec.get(FIELD_MODELO) or "",
        "detalle": rec.get(FIELD_DETALLE) or "",
        "estado_code": rec.get(FIELD_ESTADO) or "",
        "estado_label": estado_bonito(rec.get(FIELD_ESTADO)),
        "fecha_trabajado": rec.get(FIELD_FECHA_TRABAJADO) or False,
        "fecha_entrega": rec.get(FIELD_FECHA_ENTREGA) or False,
        "orden_texto": orden_texto,
        "orden_numero": limpiar_numero(orden_texto),
        "pasadores": bool(rec.get(FIELD_PASADORES)),
        "plantillas": bool(rec.get(FIELD_PLANTILLAS)),
        "responsable": rec.get(FIELD_RESPONSABLE) or "",
        "ubicacion_seguimiento": rec.get(FIELD_UBICACION) or "",
        "trabajado_por": rec.get(FIELD_TRABAJADO_POR) or "",
        "andamio": rec.get(FIELD_ANDAMIO) or "",
        "verificacion": bool(rec.get(FIELD_VERIF)),
    }
    return payload


def options_to_json(values):
    return [{"value": v, "label": v} for v in values]


# =========================
# RUTAS HTML
# =========================
@encargado_bp.route("/trabajo-general")
def trabajo_general_home():
    html_path = find_html_file()
    if not html_path:
        return "No encuentro encargadobonito.html", 404
    return send_file(html_path)


# =========================
# API AUTH
# =========================
@encargado_bp.route("/trabajo-general/api/login", methods=["POST"])
def trabajo_general_login():
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


# =========================
# API OPCIONES
# =========================
@encargado_bp.route("/trabajo-general/api/options")
def trabajo_general_options():
    _, err = require_token()
    if err:
        return err

    return jsonify({
        "responsables": options_to_json(RESPONSABLE_OPTIONS),
        "ubicaciones": options_to_json(UBICACION_OPTIONS),
        "trabajado_por": options_to_json(TRABAJADO_POR_OPTIONS),
    })


# =========================
# API LISTADO
# =========================
@encargado_bp.route("/trabajo-general/api/tasks")
def trabajo_general_tasks():
    _, err = require_token()
    if err:
        return err

    try:
        domain = [
            [FIELD_MODELO, "!=", False],
            [FIELD_ESTADO, "not in", list(FINAL_STATES)],
        ]

        fields = [
            "id",
            FIELD_MODELO,
            FIELD_DETALLE,
            FIELD_FECHA_TRABAJADO,
            FIELD_FECHA_ENTREGA,
            FIELD_ORDEN,
            FIELD_PASADORES,
            FIELD_PLANTILLAS,
            FIELD_RESPONSABLE,
            FIELD_UBICACION,
            FIELD_ESTADO,
            FIELD_VERIF,
            FIELD_TRABAJADO_POR,
            FIELD_ANDAMIO,
            FIELD_CREATE_DATE,
        ]

        result = search_read_tasks(domain, fields, order=f"{FIELD_CREATE_DATE} desc", limit=500)

        q = (request.args.get("q", "") or "").strip().lower()
        payload = [task_to_payload(r) for r in (result or [])]

        if q:
            filtered = []
            for row in payload:
                blob = " ".join([
                    str(row.get("modelo", "")),
                    str(row.get("detalle", "")),
                    str(row.get("estado_label", "")),
                    str(row.get("fecha_trabajado", "")),
                    str(row.get("fecha_entrega", "")),
                    str(row.get("orden_texto", "")),
                    str(row.get("orden_numero", "")),
                    str(row.get("responsable", "")),
                    str(row.get("ubicacion_seguimiento", "")),
                ]).lower()
                if q in blob:
                    filtered.append(row)
            payload = filtered

        return jsonify({"result": payload})

    except Exception as e:
        return jsonify({"error": str(e), "result": []}), 500


# =========================
# API UPDATE CAMPOS DIRECTOS
# =========================
@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/update", methods=["POST"])
def trabajo_general_update_task(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        body = request.get_json(silent=True) or {}
        data = body.get("data", {}) or {}

        update_data = {}

        if FIELD_RESPONSABLE in data:
            responsable = str(data.get(FIELD_RESPONSABLE) or "").strip()
            if responsable and responsable not in RESPONSABLE_OPTIONS:
                return json_error("Responsable no válido.", 400)
            update_data[FIELD_RESPONSABLE] = responsable or False

        if FIELD_UBICACION in data:
            ubicacion = str(data.get(FIELD_UBICACION) or "").strip()
            if ubicacion and ubicacion not in UBICACION_OPTIONS:
                return json_error("Ubicación no válida.", 400)
            update_data[FIELD_UBICACION] = ubicacion or False

        if not update_data:
            return json_error("No hay campos válidos para actualizar.", 400)

        ok = odoo_execute_kw(
            "project.task",
            "write",
            args=[[tarea_id], update_data],
            kwargs={},
            req_id=11,
        )

        if ok is not True:
            return json_error("Odoo no confirmó la actualización.", 500)

        updated = read_task(
            tarea_id,
            [
                "id",
                FIELD_MODELO,
                FIELD_DETALLE,
                FIELD_FECHA_TRABAJADO,
                FIELD_FECHA_ENTREGA,
                FIELD_ORDEN,
                FIELD_PASADORES,
                FIELD_PLANTILLAS,
                FIELD_RESPONSABLE,
                FIELD_UBICACION,
                FIELD_ESTADO,
                FIELD_VERIF,
                FIELD_TRABAJADO_POR,
                FIELD_ANDAMIO,
            ],
        )

        return jsonify({
            "ok": True,
            "message": "Actualizado correctamente.",
            "task": task_to_payload(updated),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# API TOGGLE LISTO
# =========================
@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/toggle_listo", methods=["POST"])
def trabajo_general_toggle_listo(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        body = request.get_json(silent=True) or {}

        actual = read_task(
            tarea_id,
            [
                "id",
                FIELD_ESTADO,
                FIELD_FECHA_TRABAJADO,
                FIELD_VERIF,
                FIELD_TRABAJADO_POR,
                FIELD_ANDAMIO,
                FIELD_MODELO,
                FIELD_DETALLE,
                FIELD_FECHA_ENTREGA,
                FIELD_ORDEN,
                FIELD_PASADORES,
                FIELD_PLANTILLAS,
                FIELD_RESPONSABLE,
                FIELD_UBICACION,
            ],
        )

        estado_actual = normalize_state(actual.get(FIELD_ESTADO))
        estaba_listo = (estado_actual == "TRABAJADO")

        if not estaba_listo:
            trabajado_por = str(body.get("trabajado_por", "")).strip()
            if not trabajado_por:
                return json_error("Debes seleccionar “Trabajado por”.", 400)

            if trabajado_por not in TRABAJADO_POR_OPTIONS:
                return json_error("Valor de “Trabajado por” no válido.", 400)

            data_to_update = {
                FIELD_ESTADO: "TRABAJADO",
                FIELD_VERIF: True,
                FIELD_FECHA_TRABAJADO: now_lima_str(),
                FIELD_TRABAJADO_POR: trabajado_por,
                FIELD_ANDAMIO: TRABAJADO_POR_TO_ANDAMIO.get(trabajado_por, False),
            }
            msg = "Marcado como listo."
        else:
            # mismo comportamiento lógico de desmarcar listo
            data_to_update = {
                FIELD_ESTADO: "03_approved",
                FIELD_VERIF: False,
                FIELD_FECHA_TRABAJADO: False,
                FIELD_TRABAJADO_POR: False,
            }
            msg = "Listo desmarcado."

        ok = odoo_execute_kw(
            "project.task",
            "write",
            args=[[tarea_id], data_to_update],
            kwargs={},
            req_id=12,
        )

        if ok is not True:
            return json_error("Odoo no confirmó el cambio.", 500)

        updated = read_task(
            tarea_id,
            [
                "id",
                FIELD_MODELO,
                FIELD_DETALLE,
                FIELD_FECHA_TRABAJADO,
                FIELD_FECHA_ENTREGA,
                FIELD_ORDEN,
                FIELD_PASADORES,
                FIELD_PLANTILLAS,
                FIELD_RESPONSABLE,
                FIELD_UBICACION,
                FIELD_ESTADO,
                FIELD_VERIF,
                FIELD_TRABAJADO_POR,
                FIELD_ANDAMIO,
            ],
        )

        return jsonify({
            "ok": True,
            "message": msg,
            "task": task_to_payload(updated),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# API COMPLETAR
# =========================
@encargado_bp.route("/trabajo-general/api/task/<int:tarea_id>/complete", methods=["POST"])
def trabajo_general_complete(tarea_id):
    _, err = require_token()
    if err:
        return err

    try:
        data_to_update = {
            FIELD_ESTADO: "1_done",
        }

        ok = odoo_execute_kw(
            "project.task",
            "write",
            args=[[tarea_id], data_to_update],
            kwargs={},
            req_id=13,
        )

        if ok is not True:
            return json_error("Odoo no confirmó el completado.", 500)

        updated = read_task(
            tarea_id,
            [
                "id",
                FIELD_MODELO,
                FIELD_DETALLE,
                FIELD_FECHA_TRABAJADO,
                FIELD_FECHA_ENTREGA,
                FIELD_ORDEN,
                FIELD_PASADORES,
                FIELD_PLANTILLAS,
                FIELD_RESPONSABLE,
                FIELD_UBICACION,
                FIELD_ESTADO,
                FIELD_VERIF,
                FIELD_TRABAJADO_POR,
                FIELD_ANDAMIO,
            ],
        )

        return jsonify({
            "ok": True,
            "message": "Tarea marcada como completado.",
            "task": task_to_payload(updated),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
