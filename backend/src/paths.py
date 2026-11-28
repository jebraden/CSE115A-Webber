import os

BASE_DIR = os.path.join(os.getenv("HOME"), ".webber")  # type: ignore[arg-type]
DB_PATH = os.path.join(BASE_DIR, "archive.db")
