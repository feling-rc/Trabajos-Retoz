from server import app
import os
import threading
from datoscliente import main as datoscliente_main
from tareas import tareas_bp
from trabajo_general_api import trabajo_general_api_bp
from trabajo_general_frontend import trabajo_general_frontend_bp

# registrar modulos
app.register_blueprint(tareas_bp)
app.register_blueprint(trabajo_general_frontend_bp)
app.register_blueprint(trabajo_general_api_bp)

# arrancar bot
threading.Thread(target=datoscliente_main, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
