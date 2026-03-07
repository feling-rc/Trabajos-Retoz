from server import app
import os
import threading
from datoscliente import main as datoscliente_main

threading.Thread(target=datoscliente_main, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
