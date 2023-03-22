class RunCommandError(Exception):
    """Command fails in venv"""


class RunCommandEnvError(Exception):
    """Venv creation or usage fails"""


class WheelFileError(Exception):
    """Invalid wheel file"""

class DepsVerifyError(Exception):
    """Mismatched stored and actual dependencies"""
