from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app


def main():
    """Main entrypoint."""
    app = create_app()
    app.run(host="127.0.0.1", port=3000, debug=False)
