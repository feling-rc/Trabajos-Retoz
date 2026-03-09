import os
import sys
import time
import html
import re
import unicodedata
import ctypes
import requests

from datetime import datetime
from server import API_KEY  # usa la misma API_KEY protegida de server.py

# =========================
# LOCK CROSS-PLATFORM
# =========================
try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None

try:
    import fcntl  # Linux / Render
except ImportError:
    fcntl = None


# =========================
# 1) CONFIG
# =========================
URL = "https://retoz.odoo.com"
DB = "retoz"
USERNAME = "retoz2023@gmail.com"

if not API_KEY:
    raise RuntimeError("Falta la variable de entorno ODOO_API_KEY")

# Proyectos donde aplica este llenado
# Ajusta estos IDs si en tu Odoo cambian.
ALLOWED_PROJECT_IDS = [12, 13, 17]

MODEL_TASK = "project.task"
MODEL_MESSAGE = "mail.message"

FIELD_DATOS_CLIENTE = "x_studio_datos_del_cliente"
FIELD_FORCE_FILL = "x_studio_llenar_informacion"

CHECK_EVERY_SECONDS = 180
PAGE_SIZE = 100
CHATTER_FETCH_LIMIT = 20

HIDE_CONSOLE = False

LOCKFILE = os.path.join(os.environ.get("TEMP", "/tmp"), "retoz_ordenar_datos_cliente.lock")
_lock_handle = None

FOOTER_YAPE_PHONE = "927 598 985"
FOOTER_CONTACT_NAME = "Feling Reyes Calderon"


# =========================
# 2) HELPERS GENERALES
# =========================
def single_instance_or_exit():
    global _lock_handle
    os.makedirs(os.path.dirname(LOCKFILE), exist_ok=True)
    _lock_handle = open(LOCKFILE, "a+")

    try:
        _lock_handle.seek(0)

        if msvcrt:
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        elif fcntl:
            fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        _lock_handle.seek(0)
        _lock_handle.truncate(0)
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()

    except OSError:
        print("Ya hay una instancia corriendo. Cierro esta ejecución duplicada.")
        sys.exit(0)


def hide_console():
    try:
        if os.name == "nt":
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
                ctypes.windll.kernel32.CloseHandle(hwnd)
    except Exception:
        pass


def odoo_call(payload):
    r = requests.post(f"{URL}/jsonrpc", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data


def login_odoo():
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
    uid = odoo_call(payload).get("result")
    if not uid:
        raise RuntimeError("Login Odoo falló.")
    return uid


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(str(s))
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip()


def clean_value(s: str) -> str:
    s = html.unescape(str(s or ""))
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = re.sub(r"\s+", " ", s).strip(" :-\n\r\t")
    return s.strip()


def normalize_label(s: str) -> str:
    s = normalize_text(s).lower()
    s = re.sub(r"\s+", " ", s).strip(" :.-¿?")
    return s


def only_digits_or_plus(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^\d+]", "", str(text)).strip()


def normalize_compare_text(s: str) -> str:
    s = s or ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_label_value(line: str):
    if ":" not in line:
        return None, None
    left, right = line.split(":", 1)
    return normalize_label(left), clean_value(right)


def add_line_if_value(lines: list, label: str, value: str):
    value = clean_value(value)
    if value:
        lines.append(f"{label}: {value}")


def task_project_name(task: dict) -> str:
    project = task.get("project_id")
    if isinstance(project, list) and len(project) > 1:
        return clean_value(project[1])
    return ""


# =========================
# 3) MAPEO DE CAMPOS
# =========================
FIELD_ALIASES = {
    "nombre": [
        "nombre completo",
        "nombre",
        "nombres y apellidos",
        "apellidos y nombres",
        "nombre del cliente",
        "cliente",
    ],
    "dni": [
        "dni",
        "documento",
        "numero de dni",
        "número de dni",
        "doc",
    ],
    "distrito": [
        "distrito",
    ],
    "direccion": [
        "direccion",
        "dirección",
        "direccion exacta",
        "dirección exacta",
        "direccion de entrega",
        "dirección de entrega",
        "domicilio",
    ],
    "referencia": [
        "referencia",
        "referencias",
        "punto de referencia",
    ],
    "productos": [
        "productos",
        "que productos estas comprando",
        "qué productos estás comprando",
        "que producto estas comprando",
        "qué producto estás comprando",
        "productos que estas comprando",
        "productos que estás comprando",
        "producto",
    ],
    "maps": [
        "link google maps",
        "google maps",
        "maps",
        "mapa",
        "ubicacion",
        "ubicación",
    ],
    "orden": [
        "numero de orden",
        "número de orden",
        "orden",
        "numero orden",
        "número orden",
    ],
    "departamento": [
        "departamento",
    ],
    "agencia": [
        "direccion de agencia de shalom",
        "dirección de agencia de shalom",
        "agencia de shalom",
        "direccion agencia shalom",
        "dirección agencia shalom",
        "agencia",
    ],
}

OUTPUT_LABELS = {
    "nombre": "Nombre",
    "celular": "Celular",
    "dni": "DNI",
    "distrito": "Distrito",
    "direccion": "Dirección",
    "referencia": "Referencia",
    "productos": "Productos",
    "maps": "Maps",
    "orden": "Orden",
    "departamento": "Departamento",
    "agencia": "Agencia",
}

LABEL_TO_FIELD = {}
for field_name, aliases in FIELD_ALIASES.items():
    for alias in aliases:
        LABEL_TO_FIELD[normalize_label(alias)] = field_name


def field_from_label(label_norm: str):
    if not label_norm:
        return None
    return LABEL_TO_FIELD.get(normalize_label(label_norm))


# =========================
# 4) PARSEO DE CHATTER
# =========================
def html_to_plain_lines(raw_text: str):
    if not raw_text:
        return []

    text = html.unescape(str(raw_text))
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    text = text.replace("\r", "\n")

    lines = []
    for ln in text.split("\n"):
        ln = clean_value(ln)
        if ln:
            lines.append(ln)
    return lines


def extract_fields_from_chatter_body(body: str) -> dict:
    data = {
        "nombre": "",
        "dni": "",
        "distrito": "",
        "direccion": "",
        "referencia": "",
        "productos": "",
        "maps": "",
        "orden": "",
        "departamento": "",
        "agencia": "",
    }

    if not body:
        return data

    lines = html_to_plain_lines(body)
    if not lines:
        return data

    # Si existe el título "Otra información", empezamos desde ahí hacia abajo
    start_index = 0
    for i, ln in enumerate(lines):
        if "otra informacion" in normalize_label(ln):
            start_index = i + 1
            break

    lines = lines[start_index:] if start_index < len(lines) else lines

    for ln in lines:
        label_norm, value = extract_label_value(ln)
        if not label_norm:
            continue

        field_name = field_from_label(label_norm)
        if not field_name:
            continue

        value = clean_value(value)
        if value and not data[field_name]:
            data[field_name] = value

    return data


def has_any_client_data(data: dict) -> bool:
    for key in [
        "nombre",
        "dni",
        "distrito",
        "direccion",
        "referencia",
        "productos",
        "maps",
        "orden",
        "departamento",
        "agencia",
    ]:
        if clean_value(data.get(key)):
            return True
    return False


# =========================
# 5) ODOO: TAREAS Y MENSAJES
# =========================
def fetch_all_tasks(uid: int):
    all_rows = []
    offset = 0

    while True:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    DB,
                    uid,
                    API_KEY,
                    MODEL_TASK,
                    "search_read",
                    [
                        [
                            ["project_id", "in", ALLOWED_PROJECT_IDS],
                        ]
                    ],
                    {
                        "fields": [
                            "id",
                            "name",
                            "project_id",
                            FIELD_DATOS_CLIENTE,
                            FIELD_FORCE_FILL,
                        ],
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "order": "id asc",
                    },
                ],
            },
            "id": 2,
        }

        rows = odoo_call(payload).get("result", [])
        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return all_rows


def fetch_recent_messages_for_task(uid: int, task_id: int):
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                DB,
                uid,
                API_KEY,
                MODEL_MESSAGE,
                "search_read",
                [
                    [
                        ["model", "=", MODEL_TASK],
                        ["res_id", "=", task_id],
                    ]
                ],
                {
                    "fields": ["id", "body", "date"],
                    "limit": CHATTER_FETCH_LIMIT,
                    "order": "id desc",
                },
            ],
        },
        "id": 3,
    }
    return odoo_call(payload).get("result", [])


def fetch_latest_client_data_from_chatter(uid: int, task_id: int) -> dict:
    messages = fetch_recent_messages_for_task(uid, task_id)

    for msg in messages:
        body = msg.get("body") or ""
        parsed = extract_fields_from_chatter_body(body)
        if has_any_client_data(parsed):
            return parsed

    return {
        "nombre": "",
        "dni": "",
        "distrito": "",
        "direccion": "",
        "referencia": "",
        "productos": "",
        "maps": "",
        "orden": "",
        "departamento": "",
        "agencia": "",
    }


def write_task_fields(uid: int, task_id: int, values: dict):
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                DB,
                uid,
                API_KEY,
                MODEL_TASK,
                "write",
                [[task_id], values],
            ],
        },
        "id": 4,
    }
    return odoo_call(payload).get("result")


# =========================
# 6) CONSTRUCCIÓN DEL TEXTO FINAL
# =========================
def build_structured_text(task: dict, chatter_data: dict) -> str:
    celular = only_digits_or_plus(task.get("name") or "")

    nombre = clean_value(chatter_data.get("nombre"))
    dni = clean_value(chatter_data.get("dni"))
    distrito = clean_value(chatter_data.get("distrito"))
    direccion = clean_value(chatter_data.get("direccion"))
    referencia = clean_value(chatter_data.get("referencia"))
    productos = clean_value(chatter_data.get("productos"))
    maps = clean_value(chatter_data.get("maps"))
    orden = clean_value(chatter_data.get("orden"))
    departamento = clean_value(chatter_data.get("departamento"))
    agencia = clean_value(chatter_data.get("agencia"))

    lines = []

    add_line_if_value(lines, OUTPUT_LABELS["nombre"], nombre)
    add_line_if_value(lines, OUTPUT_LABELS["celular"], celular)
    add_line_if_value(lines, OUTPUT_LABELS["dni"], dni)
    add_line_if_value(lines, OUTPUT_LABELS["distrito"], distrito)
    add_line_if_value(lines, OUTPUT_LABELS["direccion"], direccion)
    add_line_if_value(lines, OUTPUT_LABELS["referencia"], referencia)
    add_line_if_value(lines, OUTPUT_LABELS["productos"], productos)
    add_line_if_value(lines, OUTPUT_LABELS["maps"], maps)
    add_line_if_value(lines, OUTPUT_LABELS["orden"], orden)
    add_line_if_value(lines, OUTPUT_LABELS["departamento"], departamento)
    add_line_if_value(lines, OUTPUT_LABELS["agencia"], agencia)

    # Si Departamento tiene información, NO va el bloque de cobro.
    if not departamento and lines:
        lines.append("Por cobrar:")
        lines.append(f"Yape: {FOOTER_YAPE_PHONE}")
        lines.append(f"Nombre: {FOOTER_CONTACT_NAME}")

    return "\n".join(lines).strip()


def should_process_task(task: dict) -> bool:
    actual = task.get(FIELD_DATOS_CLIENTE)
    force_fill = bool(task.get(FIELD_FORCE_FILL))

    actual_limpio = normalize_compare_text(actual or "")
    return (not actual_limpio) or force_fill


# =========================
# 7) PROCESO PRINCIPAL
# =========================
def process_all_tasks(uid: int):
    tasks = fetch_all_tasks(uid)

    checked = 0
    updated = 0
    skipped = 0

    for task in tasks:
        checked += 1

        if not should_process_task(task):
            skipped += 1
            continue

        task_id = task["id"]
        project_name = task_project_name(task)
        force_fill = bool(task.get(FIELD_FORCE_FILL))
        actual_texto = task.get(FIELD_DATOS_CLIENTE) or ""

        chatter_data = fetch_latest_client_data_from_chatter(uid, task_id)

        # Si no hay datos reales en chatter, no escribimos basura.
        if not has_any_client_data(chatter_data):
            print(f"⏭️ Sin data en chatter | task {task_id} | Proyecto: {project_name} | Name: {task.get('name')}")
            continue

        nuevo_texto = build_structured_text(task, chatter_data)

        if not normalize_compare_text(nuevo_texto):
            print(f"⏭️ Texto final vacío | task {task_id} | Proyecto: {project_name} | Name: {task.get('name')}")
            continue

        values_to_write = {}

        if normalize_compare_text(nuevo_texto) != normalize_compare_text(actual_texto):
            values_to_write[FIELD_DATOS_CLIENTE] = nuevo_texto

        # Si se forzó el llenado, al terminar lo apagamos.
        if force_fill:
            values_to_write[FIELD_FORCE_FILL] = False

        if values_to_write:
            write_task_fields(uid, task_id, values_to_write)
            updated += 1
            print(f"✅ Actualizado task {task_id} | Proyecto: {project_name} | Name: {task.get('name')}")
        else:
            print(f"⏭️ Sin cambios task {task_id} | Proyecto: {project_name} | Name: {task.get('name')}")

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"Revisadas: {checked} | Actualizadas: {updated} | Omitidas: {skipped}"
    )


def main():
    if HIDE_CONSOLE:
        hide_console()

    single_instance_or_exit()

    uid = login_odoo()

    print("✅ BOT ACTIVO - Datos del cliente desde chatter")
    print(f"✅ Proyectos permitidos: {ALLOWED_PROJECT_IDS}")

    while True:
        try:
            process_all_tasks(uid)
            time.sleep(CHECK_EVERY_SECONDS)
        except Exception as e:
            print("❌ Error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
