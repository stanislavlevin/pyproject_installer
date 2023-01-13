from .deps_config import DepsSourcesConfig


def deps_command(action, depsconfig, **kwargs):
    config = DepsSourcesConfig(depsconfig)
    return getattr(config, action)(**kwargs)
