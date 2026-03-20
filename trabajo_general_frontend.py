from flask import Blueprint, send_file

from encargado import find_html_file


trabajo_general_frontend_bp = Blueprint("trabajo_general_frontend_bp", __name__)


@trabajo_general_frontend_bp.route("/trabajo-general")
def trabajo_general_home():
    html_path = find_html_file()
    if not html_path:
        return "No encuentro encargadobonito.html", 404
    return send_file(html_path)
