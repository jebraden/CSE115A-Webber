from unittest.mock import Mock

import pytest
import requests

from frontend.src.archive_client import get_file_data


@pytest.mark.parametrize("status", [200, 404, 500])
def test_archived_errors_are_returned(status):
    session = Mock()
    session.get.return_value.status_code = status
    response = get_file_data("file-1", client=session)
    assert response.status_code == status
    session.get.assert_called_once_with("http://127.0.0.1:3000/files/file-1/data", timeout=5)
    response.raise_for_status.assert_not_called()


def test_connection_failure_is_distinct():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("offline")
    with pytest.raises(requests.ConnectionError):
        get_file_data("file-1", client=session)


def test_invalid_id():
    with pytest.raises(ValueError):
        get_file_data("../file")
