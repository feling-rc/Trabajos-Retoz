import os
import sys
import time
import json
import html
import re
import unicodedata
import tempfile
import requests

from server import API_KEY

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

MODEL_TASK = "project.task"
MODEL_MESSAGE = "mail.message"

FIELD_DATOS_CLIENTE = "x_studio_datos_del_cliente"
FIELD_FORCE_FILL = "x_studio_llenar_informacion"

ALLOWED_PROJECT_IDS = [12, 13, 17]

FOOTER_YAPE_PHONE = "927 598 985"
FOOTER_CONTACT_NAME = "Feling Reyes Calderon"

CHECK_EVERY_SECONDS = 15
FULL_RESCAN_EVERY_SECONDS = 3600

TASK_PAGE_SIZE = 200
MESSAGE_PAGE_SIZE = 300
MESSAGE_CHUNK_SIZE = 100

LOCKFILE = os.path.join(os.environ.get("TEMP", "/tmp"), "retoz_datoscliente.lock")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datoscliente_state.json")

_lock_handle = None
SESSION = requests.Session()


# =========================
# 2) HELPERS GENERALES
# =========================
def single_instance_or_exit():
    global _lock_handle

    lock_dir = os.path.dirname(LOCKFILE) or "."
    os.makedirs(lock_dir, exist_ok=True)

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
        print("Ya hay una instancia corriendo. Cierro esta ejecución duplicada.", flush=True)
        sys.exit(0)


def odoo_call(payload):
    response = SESSION.post(f"{URL}/jsonrpc", json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

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


def clean_value(value):
    if value is None:
        return ""

    text = html.unescape(str(value))
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n:-")


def normalize_text(value):
    text = clean_value(value)
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip()


def normalize_label(value):
    text = normalize_text(value).lower()
    text = re.sub(r"[¿?]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .:-")


def normalize_compare_text(value):
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def only_digits_or_plus(value):
    if not value:
        return ""

    text = re.sub(r"[^\d+]", "", str(value))
    text = text.strip()

    digits_only = re.sub(r"\D", "", text)
    if len(digits_only) < 7:
        return ""

    return text


def add_line_if_value(lines, label, value):
    value = clean_value(value)
    if value:
        lines.append(f"{label}: {value}")


def has_any_client_data(data):
    for key in (
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
    ):
        if clean_value(data.get(key)):
            return True
    return False


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "last_task_write_date": "",
            "last_full_rescan_epoch": 0,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("STATE inválido")

        return {
            "last_task_write_date": clean_value(data.get("last_task_write_date")),
            "last_full_rescan_epoch": int(data.get("last_full_rescan_epoch") or 0),
        }

    except Exception:
        return {
            "last_task_write_date": "",
            "last_full_rescan_epoch": 0,
        }


def save_state(state):
    folder = os.path.dirname(STATE_FILE) or "."
    os.makedirs(folder, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(prefix="datoscliente_", suffix=".json", dir=folder)

    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, STATE_FILE)

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


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
        "producto",
        "que productos estas comprando",
        "qué productos estás comprando",
        "que producto estas comprando",
        "qué producto estás comprando",
        "productos que estas comprando",
        "productos que estás comprando",
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
        "numero orden",
        "número orden",
        "orden",
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


def field_from_label(label):
    return LABEL_TO_FIELD.get(normalize_label(label))


# =========================
# 4) PARSEO DEL CHATTER
# =========================
def html_to_plain_lines(raw_text):
    if not raw_text:
        return []

    text = html.unescape(str(raw_text))
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")

    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)

    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r", "\n")

    lines = []
    for line in text.split("\n"):
        line = clean_value(line)
        if line:
            lines.append(line)

    return lines


def extract_fields_from_chatter_body(body):
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

    processed_lines = []

    for line in lines:
        line_clean = clean_value(line)
        if not line_clean:
            continue

        # Si la misma línea viene así:
        # "Otra información Nombre Completo: Juan ..."
        # quitamos solo "Otra información" y conservamos "Nombre Completo: Juan ..."
        if "otra informacion" in normalize_label(line_clean):
            line_clean = re.sub(r"(?i)^.*?otra\s+informaci[oó]n\s*", "", line_clean)
            line_clean = clean_value(line_clean)

            if not line_clean:
                continue

        processed_lines.append(line_clean)

    for line in processed_lines:
        if ":" not in line:
            continue

        left, right = line.split(":", 1)
        field_name = field_from_label(left)
        if not field_name:
            continue

        value = clean_value(right)
        if value and not data[field_name]:
            data[field_name] = value

    return data


# =========================
# 5) ODOO: TAREAS Y MENSAJES
# =========================
def fetch_tasks(uid, changed_since=None):
    rows = []
    offset = 0

    domain = [
        ["project_id", "in", ALLOWED_PROJECT_IDS],
    ]

    if changed_since:
        domain.append(["write_date", ">=", changed_since])

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
                    [domain],
                    {
                        "fields": [
                            "id",
                            "name",
                            "project_id",
                            FIELD_DATOS_CLIENTE,
                            FIELD_FORCE_FILL,
                            "write_date",
                        ],
                        "limit": TASK_PAGE_SIZE,
                        "offset": offset,
                        "order": "write_date asc, id asc",
                    },
                ],
            },
            "id": 2,
        }

        page = odoo_call(payload).get("result", [])
        if not page:
            break

        rows.extend(page)

        if len(page) < TASK_PAGE_SIZE:
            break

        offset += TASK_PAGE_SIZE

    return rows


def task_needs_processing(task):
    current_text = normalize_compare_text(task.get(FIELD_DATOS_CLIENTE) or "")
    force_fill = bool(task.get(FIELD_FORCE_FILL))
    return force_fill or (not current_text)


def fetch_messages_for_task_ids(uid, task_ids):
    messages_by_task = {}

    if not task_ids:
        return messages_by_task

    for task_chunk in chunked(task_ids, MESSAGE_CHUNK_SIZE):
        offset = 0

        while True:
            domain = [
                ["model", "=", MODEL_TASK],
                ["res_id", "in", task_chunk],
                ["body", "!=", False],
            ]

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
                        [domain],
                        {
                            "fields": ["id", "res_id", "body", "date"],
                            "limit": MESSAGE_PAGE_SIZE,
                            "offset": offset,
                            "order": "res_id asc, id desc",
                        },
                    ],
                },
                "id": 3,
            }

            page = odoo_call(payload).get("result", [])
            if not page:
                break

            for row in page:
                task_id = row.get("res_id")
                if task_id:
                    messages_by_task.setdefault(task_id, []).append(row)

            if len(page) < MESSAGE_PAGE_SIZE:
                break

            offset += MESSAGE_PAGE_SIZE

    return messages_by_task


def write_task_fields(uid, task_id, values):
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
def build_structured_text(task, chatter_data):
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

    lines = ["Pedido:"]

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

    # Regla final pedida:
    # Si Departamento tiene información, NO va el bloque extra.
    if not departamento:
        lines.append("Por cobrar:")
        lines.append(f"Yape: {FOOTER_YAPE_PHONE}")
        lines.append(f"Nombre: {FOOTER_CONTACT_NAME}")

    return "\n".join(lines).strip()


def choose_latest_relevant_data(messages):
    if not messages:
        return None

    for msg in messages:
        body = msg.get("body") or ""
        parsed = extract_fields_from_chatter_body(body)
        if has_any_client_data(parsed):
            return parsed

    return None


# =========================
# 7) PROCESO PRINCIPAL
# =========================
def process_all_tasks(uid):
    state = load_state()
    now_epoch = int(time.time())

    last_task_write_date = clean_value(state.get("last_task_write_date"))
    last_full_rescan_epoch = int(state.get("last_full_rescan_epoch") or 0)

    do_full_rescan = (
        not last_task_write_date
        or (now_epoch - last_full_rescan_epoch >= FULL_RESCAN_EVERY_SECONDS)
    )

    if do_full_rescan:
        tasks = fetch_tasks(uid, changed_since=None)
    else:
        tasks = fetch_tasks(uid, changed_since=last_task_write_date)

    checked = 0
    candidate_tasks = []
    max_write_date = last_task_write_date

    for task in tasks:
        checked += 1

        task_write_date = clean_value(task.get("write_date"))
        if task_write_date and (not max_write_date or task_write_date > max_write_date):
            max_write_date = task_write_date

        if task_needs_processing(task):
            candidate_tasks.append(task)

    updated = 0
    skipped = 0

    if candidate_tasks:
        task_ids = [task["id"] for task in candidate_tasks]
        messages_by_task = fetch_messages_for_task_ids(uid, task_ids)

        for task in candidate_tasks:
            task_id = task["id"]
            current_text = task.get(FIELD_DATOS_CLIENTE) or ""
            force_fill = bool(task.get(FIELD_FORCE_FILL))

            chatter_data = choose_latest_relevant_data(messages_by_task.get(task_id, []))
            if not chatter_data or not has_any_client_data(chatter_data):
                skipped += 1
                print(f"⏭️ Sin data útil en chatter | task {task_id}", flush=True)
                continue

            new_text = build_structured_text(task, chatter_data)
            new_text_norm = normalize_compare_text(new_text)
            current_text_norm = normalize_compare_text(current_text)

            values_to_write = {}

            if new_text_norm and new_text_norm != current_text_norm:
                values_to_write[FIELD_DATOS_CLIENTE] = new_text

            if force_fill and new_text_norm:
                values_to_write[FIELD_FORCE_FILL] = False

            if values_to_write:
                write_task_fields(uid, task_id, values_to_write)
                updated += 1
                print(f"✅ Actualizado task {task_id}", flush=True)
            else:
                skipped += 1
                print(f"⏭️ Sin cambios task {task_id}", flush=True)

    new_state = {
        "last_task_write_date": max_write_date,
        "last_full_rescan_epoch": now_epoch if do_full_rescan else last_full_rescan_epoch,
    }
    save_state(new_state)

    print(
        f"[datoscliente] revisadas={checked} candidatas={len(candidate_tasks)} "
        f"actualizadas={updated} omitidas={skipped} full_rescan={do_full_rescan}",
        flush=True,
    )


def main():
    single_instance_or_exit()
    uid = login_odoo()

    print("✅ BOT ACTIVO - Datos del cliente", flush=True)
    print(f"✅ Proyectos permitidos: {ALLOWED_PROJECT_IDS}", flush=True)

    while True:
        try:
            process_all_tasks(uid)
            time.sleep(CHECK_EVERY_SECONDS)
        except Exception as e:
            print(f"❌ Error en datoscliente: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
