from server import app
import os
import threading
from datoscliente import main as datoscliente_main
from tareas import tareas_bp

# Registrar blueprint una sola vez
if "tareas_bp" not in app.blueprints:
    app.register_blueprint(tareas_bp)

_bot_thread = None
_bot_lock = threading.Lock()


def _run_datoscliente():
    print(">>> iniciando datoscliente", flush=True)
    try:
        datoscliente_main()
    except Exception as e:
        print(f">>> ERROR datoscliente: {e}", flush=True)
        raise


def start_background_threads():
    global _bot_thread

    with _bot_lock:
        if _bot_thread is None or not _bot_thread.is_alive():
            _bot_thread = threading.Thread(
                target=_run_datoscliente,
                name="datoscliente-thread",
                daemon=True,
            )
            _bot_thread.start()
            print(">>> hilo datoscliente lanzado", flush=True)


# Arrancar bot también cuando Render importa este archivo
start_background_threads()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
