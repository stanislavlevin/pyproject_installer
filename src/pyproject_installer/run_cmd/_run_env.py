from importlib.metadata import distributions
from pathlib import Path
from venv import EnvBuilder
import logging
import os
import site
import subprocess
import sys

from pyproject_installer.lib.normalization import pep503_normalized_name
from pyproject_installer.lib.scripts import generate_entrypoints_scripts
from pyproject_installer.lib.wheel import parse_name
from pyproject_installer.errors import RunCommandError, RunCommandEnvError

__all__ = ["PyprojectVenv"]

logger = logging.getLogger(__name__)


class PyprojectVenv(EnvBuilder):
    def __init__(self, wheel):
        """
        Build Python virtual environment
        - clean up existed environment on filesystem
        - create virtual environment with stdlib's venv
        - generate console scripts of system site packages
        - install package (wheel) into venv
        """
        self.context = None
        self.wheel = Path(wheel)
        venv_kwargs = {
            "system_site_packages": True,
            "clear": True,
            "upgrade": False,
            "with_pip": False,
        }
        if sys.version_info > (3, 9):
            # New in version 3.9: Added the upgrade_deps parameter
            venv_kwargs["upgrade_deps"] = False
        super().__init__(**venv_kwargs)

    def ensure_directories(self, *args, **kwargs):
        # save context for reusage
        self.context = super().ensure_directories(*args, **kwargs)
        # env_exec_cmd requires Python3.9+ (https://bugs.python.org/issue45337),
        # for non-windows systems: context.env_exec_cmd = context.env_exe
        if not hasattr(self.context, "env_exec_cmd"):
            self.context.env_exec_cmd = self.context.env_exe
        return self.context

    def install_console_scripts(self, context):
        """
        Install console_scripts of system and user site packages

        All python scripts should point to virtual env's Python interpreter to
        be run in correct environment.

        According to
        https://peps.python.org/pep-0405/#isolation-from-system-site-packages:
        PEP 370 user-level site-packages are considered part of the system
        site-packages for venv purposes: they are not available from an
        isolated venv, but are available from an
        include-system-site-packages = true venv.

        1) install console scripts of packages:
        system site packages - user site packages - wheel
        2) install console scripts of packages:
        user site packages - wheel
        3) console scripts of wheel will be installed with the wheel
        """
        logger.info("Installing console scripts")

        ssp_paths = site.getsitepackages([sys.base_prefix])
        ssds = distributions(path=ssp_paths)

        def distr_name(distr):
            """`name` added in importlib.metadata 3.3.0 and Python 3.10"""
            try:
                return distr.name
            except AttributeError:
                return distr.metadata["Name"]

        ssds_norm = {pep503_normalized_name(distr_name(x)): x for x in ssds}

        # user site packages can be either a string or None
        usp_path = site.getusersitepackages()
        usp_paths = [] if usp_path is None else [usp_path]
        usds = distributions(path=usp_paths)
        usds_norm = {pep503_normalized_name(distr_name(x)): x for x in usds}

        wd_name, _ = parse_name(str(self.wheel.name))
        wd_norm_name = pep503_normalized_name(wd_name)

        ssds_only = ssds_norm.keys() - usds_norm.keys() - {wd_norm_name}
        if ssds_only:
            logger.debug("Installing console scripts of system site packages")
            for name in ssds_only:
                generate_entrypoints_scripts(
                    ssds_norm[name],
                    python=context.env_exec_cmd,
                    scriptsdir=Path(context.bin_path).resolve(),
                    destdir="/",
                )

        usds_only = usds_norm.keys() - {wd_norm_name}
        if usds_only:
            logger.debug("Installing console scripts of user site packages")
            for name in usds_only:
                generate_entrypoints_scripts(
                    usds_norm[name],
                    python=context.env_exec_cmd,
                    scriptsdir=Path(context.bin_path).resolve(),
                    destdir="/",
                )

    def install_package(self, context):
        """Install wheel into venv"""
        logger.info("Installing package: %s", self.wheel)
        install_args = [
            context.env_exec_cmd,
            "-m",
            "pyproject_installer",
            "install",
            str(self.wheel),
        ]
        try:
            self.run(install_args, capture_output=True)
        except RunCommandError as e:
            raise RunCommandEnvError("Installation of package failed") from e

    def create(self, *args, **kwargs):
        """Calls `post_create` hook after `venv` creation

        base implementation of `create` disables system_site_packages
        via pyvenv.cfg due to https://bugs.python.org/issue24875 (unable to
        install pip with --system-site-packages if pip is already installed
        globally).

        Thereby, python in `post_setup` phase has no access to system site
        packages and can't use `pyproject_installer` to install a wheel into
        `venv`. Thus another one hook is called right after `venv` creation.
        """
        logger.info("Creating venv")
        super().create(*args, **kwargs)
        self.post_create(self.context)

    def post_create(self, context):
        """
        - generate console scripts of system and user site packages
        - install a wheel into venv
        """
        self.install_console_scripts(context)
        self.install_package(context)

    def venv_environ(self):
        """Prepare environ for venv"""
        env = os.environ.copy()
        try:
            current_path = env["PATH"]
        except KeyError:
            env["PATH"] = self.context.bin_path
        else:
            env["PATH"] = os.pathsep.join([self.context.bin_path, current_path])
        env["VIRTUAL_ENV"] = self.context.env_dir
        return env

    def run(self, command, capture_output=False):
        """Run a command in subprocess within venv"""
        logger.info("Running command: %r", command)
        try:
            result = subprocess.run(
                command,
                env=self.venv_environ(),
                check=True,
                capture_output=capture_output,
            )
        except subprocess.CalledProcessError as e:
            err_msg = str(e)
            for out_src in ["stdout", "stderr"]:
                out_bytes = getattr(e, out_src)
                if out_bytes:
                    out_text = out_bytes.decode(
                        encoding="utf-8", errors="replace"
                    )
                    err_msg += f"\n\nCommand's {out_src}:\n{out_text}"
            raise RunCommandError(err_msg) from None
        except Exception as e:
            raise RunCommandError(str(e)) from e
        return result
