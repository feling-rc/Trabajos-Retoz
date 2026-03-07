from server import app
from tareas import tareas_bp
import os

app.register_blueprint(tareas_bp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
