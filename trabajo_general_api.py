from flask import Blueprint, jsonify, request

from encargado import (
    ACCESS_CODE,
    COMMON_TASK_FIELDS,
    ESTADO_CHOICES_FALLBACK,
    FIELD_ANDAMIO,
    FIELD_CREATE_DATE,
    FIELD_ESTADO,
    FIELD_FECHA_TRABAJADO,
    FIELD_MODELO,
    FIELD_RESPONSABLE,
    FIELD_TRABAJADO_POR,
    FIELD_UBICACION_ALIAS_OLD,
    FIELD_VERIF,
    RESPONSABLE_CHOICES_FALLBACK,
    TOKENS,
    TOKENS_LOCK,
    TRABAJADO_POR_CHOICES_FALLBACK,
    UBICACION_CHOICES_FALLBACK,
    apply_state_coherence,
    choices_to_json,
    create_token,
    get_live_options,
    json_error,
    log,
    normalize_iso_to_odoo,
    normalize_state,
    now_lima_str,
    read_task,
    require_token,
    search_read_tasks,
    search_tasks_by_query,
    task_to_payload,
    write_task,
)


trabajo_general_api_bp = Blueprint("trabajo_general_api_bp", __name__)


@trabajo_general_api_bp.route("/trabajo-general/api/login", methods=["POST"])
def trabajo_general_login():
    body = request.get_json(silent=True) or {}
    code = str(body.get("code", "")).strip()

    if not code:
        return json_error("Ingresa el codigo.", 400)

    if code != ACCESS_CODE:
        return json_error("Codigo invalido.", 401)

    token = create_token()
    return jsonify({
        "ok": True,
        "token": token,
        "user": "Trabajo general",
    })


@trabajo_general_api_bp.route("/trabajo-general/api/logout", methods=["POST"])
def trabajo_general_logout():
    token = request.headers.get("X-Encargado-Token", "").strip()
    if token:
        with TOKENS_LOCK:
            TOKENS.pop(token, None)
    return jsonify({"ok": True})


@trabajo_general_api_bp.route("/trabajo-general/api/health")
def trabajo_general_health():
    return jsonify({"ok": True}), 200


@trabajo_general_api_bp.route("/trabajo-general/api/options")
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


@trabajo_general_api_bp.route("/trabajo-general/api/tasks")
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

        if q:
            result = search_tasks_by_query(q, limit, COMMON_TASK_FIELDS)
        else:
            base_domain = [[FIELD_MODELO, "!=", False]]
            result = search_read_tasks(
                base_domain,
                COMMON_TASK_FIELDS,
                order=f"{FIELD_CREATE_DATE} desc",
                limit=limit,
                req_id=70 if mode == "latest" else 72,
            )

        payload = [task_to_payload(r, estado_labels) for r in (result or [])]
        return jsonify({"result": payload})

    except Exception as e:
        log("ERROR /tasks =", str(e))
        return jsonify({"error": str(e), "result": []}), 500


@trabajo_general_api_bp.route("/trabajo-general/api/terminados")
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


@trabajo_general_api_bp.route("/trabajo-general/api/task/<int:tarea_id>/update", methods=["POST"])
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
                return json_error(f"Responsable no valido: {responsable}", 400)
            update_data[FIELD_RESPONSABLE] = responsable or False

        if FIELD_ANDAMIO in data or FIELD_UBICACION_ALIAS_OLD in data:
            raw_ubi = data.get(FIELD_ANDAMIO, data.get(FIELD_UBICACION_ALIAS_OLD))
            ubicacion = str(raw_ubi or "").strip()
            if ubicacion and ubicacion not in ubicacion_values:
                return json_error(f"Ubicacion no valida: {ubicacion}", 400)
            update_data[FIELD_ANDAMIO] = ubicacion or False

        if FIELD_TRABAJADO_POR in data:
            trabajado_por = str(data.get(FIELD_TRABAJADO_POR) or "").strip()
            if trabajado_por and trabajado_por not in trabajado_por_values:
                return json_error(f"Trabajado por no valido: {trabajado_por}", 400)
            update_data[FIELD_TRABAJADO_POR] = trabajado_por or False

        if FIELD_ESTADO in data:
            estado = normalize_state(data.get(FIELD_ESTADO))
            if estado and estado not in valid_estado_values:
                return json_error(f"Estado no valido: {estado}", 400)
            update_data[FIELD_ESTADO] = estado or False
            apply_state_coherence(update_data, estado, current)

        if FIELD_FECHA_TRABAJADO in data:
            update_data[FIELD_FECHA_TRABAJADO] = normalize_iso_to_odoo(data.get(FIELD_FECHA_TRABAJADO))

        if not update_data:
            return json_error("No hay campos validos para actualizar.", 400)

        ok = write_task(tarea_id, update_data, req_id=90)
        if ok is not True:
            return json_error("Odoo no confirmo la actualizacion.", 500)

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


@trabajo_general_api_bp.route("/trabajo-general/api/task/<int:tarea_id>/toggle_listo", methods=["POST"])
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
                return json_error(f'Valor de "Trabajado por" no valido: {trabajado_por}', 400)

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
            return json_error("Odoo no confirmo el cambio.", 500)

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


@trabajo_general_api_bp.route("/trabajo-general/api/task/<int:tarea_id>/complete", methods=["POST"])
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
            return json_error("Odoo no confirmo el completado.", 500)

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
