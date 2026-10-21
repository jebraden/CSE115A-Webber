"""Retrieve archived bytes for the search UI without interpreting HTTP errors.

An archived 404/500 is valid content, so callers must not use raise_for_status.
The data API alone cannot distinguish archived errors from backend errors.
"""
from urllib.parse import quote

import requests


def get_file_data(file_id, server="http://127.0.0.1:3000", *, client=None):
    """Return the response, including original status, headers and raw bytes.

The UI can display response.text with QTextEdit.setPlainText(), or save
response.content without a text conversion. Transport errors propagate so
that the UI can report a connection failure separately.
"""
    if not isinstance(file_id, str) or not file_id or "/" in file_id:
        raise ValueError("Expected a nonempty file ID without slashes")
    url = f"{server.rstrip('/')}/files/{quote(file_id, safe='')}/data"
    if client is not None:
        return client.get(url, timeout=5)
    with requests.Session() as session:
        return session.get(url, timeout=5)
