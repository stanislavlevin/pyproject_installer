from pyproject_installer.deps_cmd.collectors import (
    get_collector,
    MetadataCollector,
    SUPPORTED_COLLECTORS,
)
from pyproject_installer.deps_cmd.collectors.collector import Collector


def test_get_collector_missing():
    collector = get_collector("foo")
    assert collector is None


def test_get_collector():
    collector = get_collector("metadata")
    assert collector is MetadataCollector


def test_supported_collectors():
    assert isinstance(SUPPORTED_COLLECTORS, dict)
    for k, v in SUPPORTED_COLLECTORS.items():
        assert isinstance(k, str)
        assert issubclass(v, Collector)
