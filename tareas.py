from flask import Blueprint

tareas_bp = Blueprint("tareas_bp", __name__)

@tareas_bp.route("/tareas")
def tareas_home():
    return "<h1>Modulo tareas funcionando ✅</h1>"
