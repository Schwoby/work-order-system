import os
from flask import Flask

from db import init_db
from helpers import env_bool
from users import users_bp
from workorders import workorders_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["TEMPLATES_AUTO_RELOAD"] = env_bool("TEMPLATES_AUTO_RELOAD", False)

app.register_blueprint(users_bp)
app.register_blueprint(workorders_bp)

os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
init_db()

@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    debug = env_bool("FLASK_DEBUG", False)
    app.run(host="0.0.0.0", port=8080, debug=debug)
