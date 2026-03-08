from server import app
import os
import threading
from datoscliente import main as datoscliente_main
from tareas import main as tareas_main

if __name__ == "__main__":
    threading.Thread(target=datoscliente_main, daemon=True).start()
    threading.Thread(target=tareas_main, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
