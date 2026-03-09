from server import app
import os
import threading
from datoscliente import main as datoscliente_main
from tareas import tareas_bp

# registrar modulo de tareas
app.register_blueprint(tareas_bp)

# arrancar bot de datoscliente tambien en Render
threading.Thread(target=datoscliente_main, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
