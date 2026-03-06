from flask import Flask, jsonify, request, send_from_directory, send_file, abort
from flask_cors import CORS
import requests
import os

app = Flask(__name__)

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "ngrok-skip-browser-warning"],
    methods=["GET", "POST", "OPTIONS"],
)

# ✅ Evita cache raro (siempre fresco)
@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# 🔹 CONFIG ODOO (si existe env, lo usa)
URL = os.getenv("ODOO_URL", "https://retoz.odoo.com")
DB = os.getenv("ODOO_DB", "retoz")
USERNAME = os.getenv("ODOO_USERNAME", "retoz2023@gmail.com")
API_KEY = os.getenv("ODOO_API_KEY")

# ✅ Session para estabilidad/velocidad
SESSION = requests.Session()

# ✅ Cache UID para no loguear a cada request
_UID = None


# =========================
# ✅ FRONTEND (pantalla bonita)
# =========================
def find_index_file():
    p1 = os.path.join(PUBLIC_DIR, "index.html")
    p2 = os.path.join(BASE_DIR, "index.html")
    if os.path.isfile(p1):
        return p1
    if os.path.isfile(p2):
        return p2
    return None


@app.route("/")
def web_home():
    index_path = find_index_file()
    if not index_path:
        return (
            "NO ENCUENTRO index.html (ponlo en /public/index.html o junto a app.py)",
            404,
        )
    return send_file(index_path)


@app.route("/public/<path:filename>")
def web_public_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/apple-touch-icon.png")
def apple_icon():
    return "", 204


@app.route("/apple-touch-icon-precomposed.png")
def apple_icon2():
    return "", 204


@app.route("/<path:filename>")
def serve_any_file(filename):
    # ✅ NO tocar endpoints API
    if (
        filename.startswith("tareas")
        or filename.startswith("actualizar_tarea")
        or filename.startswith("terminados")
    ):
        abort(404)

    for folder in [PUBLIC_DIR, BASE_DIR]:
        full = os.path.join(folder, filename)
        if os.path.isfile(full):
            return send_from_directory(folder, filename)

    abort(404)


# =========================
# 🔹 ODOO HELPERS
# =========================
def login_odoo(force=False):
    """✅ Cache UID + retry si falló"""
    global _UID
    if _UID and not force:
        return _UID

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

    r = SESSION.post(f"{URL}/jsonrpc", json=payload, timeout=30)
    r.raise_for_status()

    uid = r.json().get("result")
    if not uid:
        raise Exception("Error login Odoo: UID no obtenido")

    _UID = uid
    return uid


def odoo_execute_kw(model, method, args=None, kwargs=None, req_id=2):
    """✅ execute_kw correcto: args(list) y kwargs(dict)"""
    uid = login_odoo()
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

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

    r = SESSION.post(f"{URL}/jsonrpc", json=payload, timeout=35)
    r.raise_for_status()

    data = r.json()

    if "error" in data:
        err = data["error"]
        msg = (
            err.get("data", {}).get("message")
            or err.get("message")
            or "Error Odoo"
        )
        raise Exception(msg)

    return data.get("result")


def read_task(tarea_id, fields):
    """✅ read correcto"""
    res = odoo_execute_kw(
        "project.task",
        "read",
        args=[[tarea_id], fields],
        kwargs={},
        req_id=9,
    )
    return res[0] if isinstance(res, list) and res else {}


def normalize_iso_to_odoo(val):
    """ISO -> 'YYYY-MM-DD HH:MM:SS' o False"""
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
# ✅ NUEVO (modo taller): QUITAR DE MESA CUANDO YA ESTÁ LISTO
# =========================
def es_listo_para_quitar_de_mesa(rec):
    """
    ✅ Regla industrial:
    - Si ya está LISTO (TRABAJADO) -> NO debe verse en 'Trabajos en Mesa'
    - Si ya está Completado/Entregado -> tampoco
    - Si verificación Excel está True -> también se considera listo
    """
    estado = (rec.get("x_studio_selection_field_3j_1ivn1ho1m") or "").strip()
    verif = rec.get("x_studio_verificacion_de_excel") is True

    if estado in ("TRABAJADO", "1_done", "Entregado"):
        return True
    if verif:
        return True
    return False


# =========================
# 🔹 TRAER TAREAS (MISMO DOMAIN) + ✅ FILTRO POST (NO TOCA DOMAIN)
# =========================
@app.route("/tareas/<ubicacion>")
def traer_tareas(ubicacion):
    try:
        # ✅ MISMO domain (NO TOCADO)
        domain = [
            ["x_studio_andamio", "=", ubicacion],
            ["x_studio_modelo_de_par_1", "!=", False],
            "!",
            "&",
            ["x_studio_selection_field_3j_1ivn1ho1m", "in", ["1_done", "Entregado"]],
            ["x_studio_fecha_de_trabajado", "!=", False],
            "!",
            "&",
            "&",
            ["x_studio_selection_field_3j_1ivn1ho1m", "=", "1_done"],
            [
                "x_studio_andamio",
                "in",
                [
                    "JORGE",
                    "PEDRO",
                    "JUAN",
                    "ALEX",
                    "ELIZABETH",
                    "EZER",
                    "KEVIN",
                    "YULI",
                    "SR COCO",
                    "FELING",
                ],
            ],
            ["x_studio_verificacion_de_excel", "=", False],
        ]

        fields = [
            "id",
            "x_studio_modelo_de_par_1",
            "x_studio_pasadores_1",
            "x_studio_plantillas_1",
            "x_studio_orden_de_venta_1",
            "create_date",
            "x_studio_verificacion_de_excel",
            "x_studio_fecha_de_trabajado",
            "x_studio_selection_field_3j_1ivn1ho1m",
            "x_studio_andamio",
            "x_studio_trabajado_por",
        ]

        result = odoo_execute_kw(
            "project.task",
            "search_read",
            args=[domain],
            kwargs={"fields": fields, "order": "create_date desc", "limit": 300},
            req_id=2,
        )

        # ✅ CAMBIO NUEVO (sin tocar domain): si ya está listo, se quita de Mesa
        result_filtrado = [r for r in (result or []) if not es_listo_para_quitar_de_mesa(r)]

        return jsonify({"result": result_filtrado})

    except Exception as e:
        return jsonify({"error": str(e), "result": []}), 500


# =========================
# ✅ TERMINADOS (HISTORIAL) — compatible con el último frontend
# =========================
@app.route("/terminados/<trabajado_por>")
def traer_terminados(trabajado_por):
    """
    Historial:
    - aparece aunque cambie estado o andamio
    - se basa en trabajado_por + fecha_de_trabajado
    - NO muestra EN PROCESO (03_approved) para evitar “falsos terminados”
    - ✅ incluye x_studio_verificacion_de_excel (para el botón del último frontend)
    """
    try:
        trabajado_por = (trabajado_por or "").strip()

        domain = [
            ["x_studio_modelo_de_par_1", "!=", False],
            ["x_studio_trabajado_por", "!=", False],
            ["x_studio_fecha_de_trabajado", "!=", False],
            ["x_studio_selection_field_3j_1ivn1ho1m", "!=", "03_approved"],
        ]

        if trabajado_por.upper() != "ALL":
            domain.append(["x_studio_trabajado_por", "=", trabajado_por])

        fields = [
            "id",
            "x_studio_modelo_de_par_1",
            "x_studio_pasadores_1",
            "x_studio_plantillas_1",
            "x_studio_orden_de_venta_1",
            "x_studio_fecha_de_trabajado",
            "x_studio_verificacion_de_excel",          # ✅ NUEVO para el frontend
            "x_studio_selection_field_3j_1ivn1ho1m",
            "x_studio_andamio",
            "x_studio_trabajado_por",
        ]

        result = odoo_execute_kw(
            "project.task",
            "search_read",
            args=[domain],
            kwargs={
                "fields": fields,
                "order": "x_studio_fecha_de_trabajado desc",
                "limit": 500,
            },
            req_id=7,
        )

        return jsonify({"result": result})

    except Exception as e:
        return jsonify({"error": str(e), "result": []}), 500


# =========================
# 🔹 ACTUALIZAR TAREA (marcar / desmarcar) — modo taller industrial
# =========================
@app.route("/actualizar_tarea/<int:tarea_id>", methods=["POST"])
def actualizar_tarea(tarea_id):
    """
    ✅ Reglas industriales:
    - Al marcar LISTO:
        estado=TRABAJADO, verif=True, fecha=ahora, trabajado_por = según andamio
    - Al desmarcar (QC lo devuelve):
        estado=03_approved, verif=False, fecha=False
        ✅ NO se modifica trabajado_por (se conserva historial del último)
    """
    try:
        body = request.get_json(silent=True) or {}
        if "data" not in body:
            return jsonify({"error": "No data received or data key missing"}), 400

        tarea_data = body["data"] or {}

        # ✅ Normaliza fecha (borrar / ISO)
        if "x_studio_fecha_de_trabajado" in tarea_data:
            tarea_data["x_studio_fecha_de_trabajado"] = normalize_iso_to_odoo(
                tarea_data.get("x_studio_fecha_de_trabajado")
            )

        # Determina acción (marca o desmarca)
        verif_in = tarea_data.get("x_studio_verificacion_de_excel", None)
        esta_marcando = (verif_in is True)
        esta_desmarcando = (verif_in is False)

        # ✅ Puente: andamio (solo si hace falta)
        andamio = tarea_data.get("x_studio_andamio", "")
        if not andamio:
            actual = read_task(tarea_id, ["x_studio_andamio"])
            andamio = actual.get("x_studio_andamio", "") or ""

        trabajado_por_map = {
            "PEDRO": "Pedro",
            "FELING": "Feling",
            "YULI": "Yuli",
            "JORGE": "Jorge",
            "JUAN": "Sr Juan",
            "SR JUAN": "Sr Juan",
            "ALEX": "Alex",
            "EZER": "Even Ezer",
            "KEVIN": "Kevin",
            "SR COCO": "Sr Coco",
            # ✅ ELIZABETH NO TIENE EQUIVALENTE (pedido)
        }

        # ✅ CAMBIO CLAVE para tu último frontend:
        # - Si DESMARCA: NO tocar trabajado_por (aunque el front lo mande)
        if esta_desmarcando:
            if "x_studio_trabajado_por" in tarea_data:
                del tarea_data["x_studio_trabajado_por"]  # ✅ conserva el anterior
        else:
            # Si está MARCANDO o cualquier otro update, si viene vacío lo calculamos
            if esta_marcando:
                tarea_data["x_studio_trabajado_por"] = trabajado_por_map.get(andamio, "")
            else:
                # si no viene y existe en Odoo, lo dejamos (no lo forzamos)
                if not tarea_data.get("x_studio_trabajado_por"):
                    pass

        # ✅ Write
        ok = odoo_execute_kw(
            "project.task",
            "write",
            args=[[tarea_id], tarea_data],
            kwargs={},
            req_id=3,
        )
        if ok is not True:
            return jsonify({"error": "Odoo no confirmó la actualización"}), 500

        # ✅ Devuelve actualizado (compatible con último frontend)
        actualizado = read_task(
            tarea_id,
            [
                "x_studio_verificacion_de_excel",
                "x_studio_fecha_de_trabajado",
                "x_studio_selection_field_3j_1ivn1ho1m",
                "x_studio_andamio",
                "x_studio_trabajado_por",
            ],
        )

        return jsonify({"message": "OK", "updated": actualizado}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ✅ Healthcheck rápido (opcional, útil para ngrok)
@app.route("/health")
def health():
    return jsonify({"ok": True}), 200


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)


