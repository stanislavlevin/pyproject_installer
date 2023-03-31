import json

import pytest


@pytest.fixture
def mock_build(mocker):
    mocker.patch(
        "pyproject_installer.lib.build_backend.os.pipe", return_value=(3, 4)
    )
    mock_os_read = mocker.patch("pyproject_installer.lib.build_backend.os.read")
    mock_os_read.side_effect = [
        json.dumps({"result": "foo.whl"}).encode("utf-8"),
        b"",
    ]
    mocker.patch("pyproject_installer.lib.build_backend.os.close")
    return mocker.patch("pyproject_installer.lib.build_backend.subprocess.run")
