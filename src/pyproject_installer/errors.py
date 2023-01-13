class RunCommandError(Exception):
    """Command fails in venv"""


class RunCommandEnvError(Exception):
    """Venv creation or usage fails"""


class WheelFileError(Exception):
    """Invalid wheel file"""


class DepsUnsyncedError(Exception):
    """Stored and actual dependencies are not synced"""


class DepsSourcesConfigError(Exception):
    """Wrong format or data of deps config"""
