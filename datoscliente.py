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

ALLOWED_PROJECT_NAMES = [
    "Envios de Productos",
    "Recoger Calzados",
]

MODEL_NAME = "project.task"
FIELD_DATOS_CLIENTE = "x_studio_datos_del_cliente"

CHECK_EVERY_SECONDS = 180
PAGE_SIZE = 100

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


def is_probable_phone(text: str) -> bool:
    if not text:
        return False
    t = re.sub(r"[^\d+]", "", str(text))
    return bool(re.fullmatch(r"\+?\d{7,15}", t))


def only_digits_or_plus(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^\d+]", "", str(text)).strip()


def smart_title(s: str) -> str:
    s = clean_value(s)
    if not s:
        return ""
    return s.title()


def normalize_compare_text(s: str) -> str:
    s = s or ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalize_person_compare(s: str) -> str:
    s = normalize_text(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def same_person(a: str, b: str) -> bool:
    return normalize_person_compare(a) != "" and normalize_person_compare(a) == normalize_person_compare(b)


def strip_generated_footer(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = html.unescape(str(raw_text))
    m = re.search(r"(?im)^\s*por cobrar\s*:\s*$", text)
    if m:
        text = text[:m.start()]
    return text


def extract_first_group(text: str, patterns) -> str:
    if not text:
        return ""
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_value(m.group(1))
    return ""


def value_after_colon(line: str) -> str:
    if ":" not in line:
        return ""
    return clean_value(line.split(":", 1)[1])


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
        "destinatario",
        "persona que recibira el pedido",
        "persona que recibirá el pedido",
        "persona que recoge",
        "quien recibe",
        "quién recibe",
        "nombre y apellido",
        "nombres",
    ],
    "celular": [
        "numero de celular",
        "número de celular",
        "celular",
        "telefono",
        "teléfono",
        "whatsapp",
        "numero de contacto",
        "número de contacto",
        "telefono de contacto",
        "teléfono de contacto",
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
    "departamento": [
        "departamento",
    ],
    "agencia_shalom": [
        "direccion de agencia de shalom",
        "dirección de agencia de shalom",
        "agencia de shalom",
        "direccion agencia shalom",
        "dirección agencia shalom",
    ],
}

LABEL_TO_FIELD = {}
for field_name, aliases in FIELD_ALIASES.items():
    for alias in aliases:
        LABEL_TO_FIELD[normalize_label(alias)] = field_name


def field_from_label(label_norm: str):
    if not label_norm:
        return None
    return LABEL_TO_FIELD.get(normalize_label(label_norm))


def extract_label_value(line: str):
    if ":" not in line:
        return None, None
    left, right = line.split(":", 1)
    return normalize_label(left), clean_value(right)


# =========================
# 4) PARSEO DE TEXTO
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
    text = re.sub(r"<.*?>", "", text)
    text = text.replace("\r", "\n")

    lines = []
    for ln in text.split("\n"):
        ln = clean_value(ln)
        if ln:
            lines.append(ln)
    return lines


def assign_if_empty(data: dict, key: str, value: str):
    value = clean_value(value)
    if key in data and value and not data[key]:
        data[key] = value


def detect_is_provincia(data: dict, raw_text: str) -> bool:
    if clean_value(data.get("departamento")):
        return True
    if clean_value(data.get("agencia_shalom")):
        return True

    text = normalize_text(raw_text).lower()
    if "departamento" in text:
        return True
    if "agencia de shalom" in text:
        return True
    if "direccion de agencia de shalom" in text:
        return True
    if "dirección de agencia de shalom" in text:
        return True

    return False


def extract_fields_from_description_html(desc_html: str) -> dict:
    data = {
        "nombre": "",
        "celular": "",
        "dni": "",
        "distrito": "",
        "direccion": "",
        "referencia": "",
        "productos": "",
        "departamento": "",
        "agencia_shalom": "",
        "is_provincia": False,
    }

    if not desc_html:
        return data

    data["nombre"] = extract_first_group(
        desc_html,
        [
            r"Nombre\s*Completo\s*:\s*([^<\n\r]+)",
            r"Nombre\s*del\s*cliente\s*:\s*([^<\n\r]+)",
            r"Nombre\s*y\s*apellido\s*:\s*([^<\n\r]+)",
            r"Nombres\s*y\s*apellidos\s*:\s*([^<\n\r]+)",
            r"Cliente\s*:\s*([^<\n\r]+)",
            r"Nombre\s*:\s*([^<\n\r]+)",
        ],
    )

    data["celular"] = extract_first_group(
        desc_html,
        [
            r"Numero\s*de\s*celular\s*:\s*([^<\n\r]+)",
            r"Número\s*de\s*celular\s*:\s*([^<\n\r]+)",
            r"Celular\s*:\s*([^<\n\r]+)",
            r"Telefono\s*:\s*([^<\n\r]+)",
            r"Teléfono\s*:\s*([^<\n\r]+)",
            r"Whatsapp\s*:\s*([^<\n\r]+)",
        ],
    )

    data["productos"] = extract_first_group(
        desc_html,
        [
            r"¿?\s*Qué\s*productos\s*est[aá]s\s*comprando\s*\??\s*:\s*([^<\n\r]+)",
            r"Que\s*productos\s*estas\s*comprando\s*:\s*([^<\n\r]+)",
            r"Productos\s*:\s*([^<\n\r]+)",
        ],
    )

    data["departamento"] = extract_first_group(
        desc_html,
        [
            r"Departamento\s*:\s*([^<\n\r]+)",
        ],
    )

    data["agencia_shalom"] = extract_first_group(
        desc_html,
        [
            r"Direcci[oó]n\s*de\s*Agencia\s*de\s*Shalom\s*:\s*([^<\n\r]+)",
            r"Agencia\s*de\s*Shalom\s*:\s*([^<\n\r]+)",
        ],
    )

    text = desc_html.replace("&nbsp;", " ")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    text = text.replace("\r", "\n")

    lines = [clean_value(ln) for ln in text.split("\n") if clean_value(ln)]

    for ln in lines:
        low = normalize_label(ln)

        if low.startswith("dni"):
            data["dni"] = value_after_colon(ln)
            continue

        if low.startswith("distrito"):
            data["distrito"] = value_after_colon(ln)
            continue

        if low.startswith("direccion de agencia de shalom") or low.startswith("dirección de agencia de shalom"):
            data["agencia_shalom"] = value_after_colon(ln)
            continue

        if low.startswith("agencia de shalom"):
            data["agencia_shalom"] = value_after_colon(ln)
            continue

        if low.startswith("departamento"):
            data["departamento"] = value_after_colon(ln)
            continue

        if low.startswith("direccion") or low.startswith("dirección"):
            label_norm, value = extract_label_value(ln)
            if field_from_label(label_norm) == "direccion":
                data["direccion"] = clean_value(value)
                continue

        if low.startswith("referencia"):
            data["referencia"] = value_after_colon(ln)
            continue

        if low.startswith("productos") or low.startswith("que productos estas comprando") or low.startswith("qué productos estás comprando"):
            data["productos"] = value_after_colon(ln)
            continue

        label_norm, value = extract_label_value(ln)

        if not data["nombre"] and field_from_label(label_norm) == "nombre":
            data["nombre"] = clean_value(value)

        if not data["celular"] and field_from_label(label_norm) == "celular":
            data["celular"] = clean_value(value)

        if not data["productos"] and field_from_label(label_norm) == "productos":
            data["productos"] = clean_value(value)

        if not data["departamento"] and field_from_label(label_norm) == "departamento":
            data["departamento"] = clean_value(value)

        if not data["agencia_shalom"] and field_from_label(label_norm) == "agencia_shalom":
            data["agencia_shalom"] = clean_value(value)

    data["is_provincia"] = detect_is_provincia(data, desc_html)
    return data


def extract_fields_from_structured_text(raw_text: str) -> dict:
    data = {
        "nombre": "",
        "celular": "",
        "dni": "",
        "distrito": "",
        "direccion": "",
        "referencia": "",
        "productos": "",
        "departamento": "",
        "agencia_shalom": "",
        "is_provincia": False,
    }

    if not raw_text:
        return data

    lines = html_to_plain_lines(raw_text)

    i = 0
    while i < len(lines):
        ln = clean_value(lines[i])

        label_norm, value = extract_label_value(ln)
        field_name = field_from_label(label_norm)
        if field_name:
            assign_if_empty(data, field_name, value)
            i += 1
            continue

        standalone_field = field_from_label(ln)
        if standalone_field:
            if i + 1 < len(lines):
                next_line = clean_value(lines[i + 1])
                next_label_norm, _ = extract_label_value(next_line)
                next_is_field = field_from_label(next_label_norm) or field_from_label(next_line)
                if not next_is_field:
                    assign_if_empty(data, standalone_field, next_line)
                    i += 2
                    continue
            i += 1
            continue

        i += 1

    data["is_provincia"] = detect_is_provincia(data, raw_text)
    return data


def merge_fields(primary: dict, fallback: dict) -> dict:
    result = {}
    for key in [
        "nombre",
        "celular",
        "dni",
        "distrito",
        "direccion",
        "referencia",
        "productos",
        "departamento",
        "agencia_shalom",
    ]:
        result[key] = clean_value(primary.get(key)) or clean_value(fallback.get(key))

    result["is_provincia"] = bool(primary.get("is_provincia")) or bool(fallback.get("is_provincia"))
    return result


# =========================
# 5) ODOO: PROYECTOS Y TAREAS
# =========================
def find_allowed_project_ids(uid: int) -> dict:
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
                "project.project",
                "search_read",
                [[["name", "in", ALLOWED_PROJECT_NAMES]]],
                {"fields": ["id", "name"], "limit": 20},
            ],
        },
        "id": 2,
    }

    rows = odoo_call(payload).get("result", [])
    if not rows:
        raise RuntimeError("No se encontraron los proyectos permitidos.")

    mapping = {}
    for row in rows:
        mapping[row["id"]] = row.get("name", "")

    found_names = set(mapping.values())
    missing = [x for x in ALLOWED_PROJECT_NAMES if x not in found_names]
    if missing:
        print("⚠️ Proyectos no encontrados:", missing)

    return mapping


def fetch_all_tasks(uid: int, allowed_project_ids: list):
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
                    MODEL_NAME,
                    "search_read",
                    [
                        [
                            ["project_id", "in", allowed_project_ids],
                        ]
                    ],
                    {
                        "fields": [
                            "id",
                            "name",
                            "description",
                            "project_id",
                            "partner_id",
                            FIELD_DATOS_CLIENTE,
                        ],
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "order": "id asc",
                    },
                ],
            },
            "id": 3,
        }

        rows = odoo_call(payload).get("result", [])
        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return all_rows


def write_task_datos_cliente(uid: int, task_id: int, texto: str):
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
                MODEL_NAME,
                "write",
                [[task_id], {FIELD_DATOS_CLIENTE: texto}],
            ],
        },
        "id": 4,
    }
    return odoo_call(payload).get("result")


# =========================
# 6) CONSTRUCCIÓN DEL TEXTO FINAL
# =========================
def is_recojo_project(project_name: str) -> bool:
    low = (project_name or "").strip().lower()
    return "recoger calzados" == low or "recojo" in low or "recoger" in low


def get_partner_name(task: dict) -> str:
    partner = task.get("partner_id")
    if isinstance(partner, list) and len(partner) > 1:
        return clean_value(partner[1])
    return ""


def choose_best_client_name(task: dict, from_description: dict, from_current_field: dict) -> str:
    task_name = clean_value(task.get("name") or "")
    partner_name = get_partner_name(task)

    candidates = [
        clean_value(from_description.get("nombre")),
        clean_value(from_current_field.get("nombre")),
        partner_name,
        (task_name if not is_probable_phone(task_name) else ""),
    ]

    for candidate in candidates:
        if candidate and not same_person(candidate, FOOTER_CONTACT_NAME):
            return candidate

    return ""


def build_structured_text(task: dict, project_name: str) -> str:
    descripcion = task.get("description") or ""
    actual = task.get(FIELD_DATOS_CLIENTE) or ""
    task_name = clean_value(task.get("name") or "")

    from_description = extract_fields_from_description_html(descripcion)

    actual_sin_footer = strip_generated_footer(actual)
    from_current_field = extract_fields_from_structured_text(actual_sin_footer)

    merged = merge_fields(from_description, from_current_field)

    nombre = choose_best_client_name(task, from_description, from_current_field)

    celular = clean_value(merged.get("celular"))
    if not celular and is_probable_phone(task_name):
        celular = task_name

    dni = clean_value(merged.get("dni"))
    distrito = smart_title(merged.get("distrito"))
    direccion = clean_value(merged.get("direccion"))
    referencia = clean_value(merged.get("referencia"))
    productos = clean_value(merged.get("productos"))
    departamento = smart_title(merged.get("departamento"))
    agencia = clean_value(merged.get("agencia_shalom"))

    nombre = nombre.upper() if nombre else ""
    celular = only_digits_or_plus(celular) if celular else ""
    dni = only_digits_or_plus(dni) if dni else ""

    encabezado = "Recojo:" if is_recojo_project(project_name) else "Pedido:"

    lineas = [
        encabezado,
        f"Nombre: {nombre}",
        f"Celular: {celular}",
        f"DNI: {dni}",
        f"Distrito: {distrito}",
        f"Dirección: {direccion}",
        f"Referencia: {referencia}",
        f"Productos: {productos}",
    ]

    if departamento:
        lineas.append(f"Departamento: {departamento}")

    if agencia:
        lineas.append(f"Agencia: {agencia}")

    lineas.extend([
        "Por cobrar:",
        f"Yape: {FOOTER_YAPE_PHONE}",
        f"Nombre: {FOOTER_CONTACT_NAME}",
    ])

    return "\n".join(lineas).strip()


# =========================
# 7) PROCESO PRINCIPAL
# =========================
def process_all_tasks(uid: int, project_map: dict):
    allowed_project_ids = list(project_map.keys())
    tasks = fetch_all_tasks(uid, allowed_project_ids)

    updated = 0
    checked = 0

    for task in tasks:
        checked += 1

        proj = task.get("project_id") or []
        proj_id = proj[0] if isinstance(proj, list) and len(proj) > 0 else None
        proj_name = proj[1] if isinstance(proj, list) and len(proj) > 1 else project_map.get(proj_id, "")

        if proj_name not in ALLOWED_PROJECT_NAMES:
            continue

        nuevo_texto = build_structured_text(task, proj_name)
        actual_texto = task.get(FIELD_DATOS_CLIENTE) or ""

        if normalize_compare_text(nuevo_texto) != normalize_compare_text(actual_texto):
            write_task_datos_cliente(uid, task["id"], nuevo_texto)
            updated += 1
            print(f"✅ Actualizado task {task['id']} | Proyecto: {proj_name} | Name: {task.get('name')}")
        else:
            print(f"⏭️ Sin cambios task {task['id']} | Proyecto: {proj_name} | Name: {task.get('name')}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Revisadas: {checked} | Actualizadas: {updated}")


def main():
    if HIDE_CONSOLE:
        hide_console()

    single_instance_or_exit()

    uid = login_odoo()
    project_map = find_allowed_project_ids(uid)

    print("✅ BOT ACTIVO - Ordenando Datos del cliente")
    print("✅ Proyectos permitidos:", ", ".join(ALLOWED_PROJECT_NAMES))

    while True:
        try:
            process_all_tasks(uid, project_map)
            time.sleep(CHECK_EVERY_SECONDS)
        except Exception as e:
            print("❌ Error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
