"""
RPM %files-compatible filelist generation for `install_wheel`.

Requires `sys.pycache_prefix` to be at its default (`None`):
`cache_from_source` respects it, so any non-default value would
silently shift every .pyc path in the filelist under that prefix.
Enforced at render time.

Internal helper; the public contract is
`install_wheel(..., rpm_filelist=...)` in `_install.py`. Callers
collect installed file paths into a set and hand it, along with the
destdir and the scheme (as returned by `get_installation_scheme()`),
to `write_rpm_filelist`.
"""

import sys
from importlib.util import cache_from_source
from itertools import chain
from pathlib import Path

# Standard CPython optimization levels per PEP 488; argument to
# importlib.util.cache_from_source. Not exposed as a stdlib constant,
# so duplicated here with a single source of truth.
PYC_OPTIMIZATION_LEVELS = ("", "1", "2")

# Compression extensions brp-compress decompresses on a man page.
# If the wheel ships the page with one of these, brp will then
# recompress with the distro's configured method, and the on-disk
# extension may not match the wheel's. Stripping these suffixes
# before appending the `*` glob lets the filelist line cover whichever
# target the BRP picks. Other extensions (.xz, .zst, .lz, ...) are
# left alone by brp-compress and so are kept as-is.
MAN_COMPRESSION_SUFFIXES = frozenset({".gz", ".bz2", ".Z"})


def render_rpm_filelist(files, *, destdir, scheme, dist_info):
    """
    Return an RPM %files-compatible filelist body for ``files``.

    Inputs
    ------
    ``files``
        Iterable of absolute filesystem paths, each under ``destdir``.
    ``destdir``
        Buildroot root; stripped from every path so the filelist holds
        target-system (post-install) paths.
    ``scheme``
        Mapping from ``get_installation_scheme()``. ``purelib``,
        ``platlib``, ``headers``, and ``data`` are consumed; other
        keys ignored.
    ``dist_info``
        Target-system absolute path of the ``.dist-info`` directory.

    Four **anchors** are derived: ``dist_info``, ``headers``,
    ``purelib``, ``platlib``. Each input file is classified by its
    deepest matching anchor (by ``len(Path.parts)``), or left
    unclassified if it lives outside all four.

    Emitted file lines
    ------------------
    1. Every input file, with ``destdir`` stripped.
    2. Three computed ``.pyc`` paths per PEP 3147 / PEP 488
       optimisation level (``0``, ``1``, ``2``) for every ``.py`` file
       whose deepest anchor is ``purelib`` or ``platlib``.
       ``.py`` files elsewhere (scripts, data, headers, dist-info) are
       not expanded - RPM's bytecompile step does not compile them.

    Emitted ``%dir`` lines
    ----------------------
    1. ``dist_info`` unconditionally - the installer creates it even
       when stripped down to ``METADATA``.
    2. ``headers`` only when at least one input file lives under it.
    3. For every classified input file: each strict ancestor of the
       file that is also a strict descendant of its anchor (i.e. the
       intermediate directories between the file and its anchor,
       open on both ends). The anchors themselves are never added via
       this rule - site roots are owned by the Python runtime package;
       ``dist_info`` and ``headers`` are handled by rules 1 and 2.
    4. The sibling ``__pycache__`` for every ``.py`` file classified
       under ``purelib``/``platlib`` whose parent is *not* the anchor
       itself (the shared site-level ``__pycache__`` is never owned).

    Files outside every anchor (e.g. ``scheme["scripts"]``,
    ``scheme["data"]``) are emitted file-only: no ``%dir`` ownership is
    claimed on their ancestors, so the filelist does not conflict with
    FHS-standard directories owned by the ``filesystem`` package
    (``/usr/bin``, ``/usr/share`` etc.).

    Man pages under ``scheme["data"]/share/man/`` are emitted with a
    trailing ``*`` because RPM's ``brp-compress`` runs after
    ``%install`` and compresses uncompressed pages with the distro's
    configured method, which appends a compression extension to the
    filename. A literal path no longer matches once that happens; the
    ``*`` lets a single line match the file regardless of which
    compression extension (if any) ends up on disk.

    Suffixes in ``MAN_COMPRESSION_SUFFIXES`` (``.gz``, ``.bz2``,
    ``.Z`` -- the formats ``brp-compress`` decompresses before the
    recompression pass) are stripped before the glob is appended,
    because the resulting on-disk extension may differ from the
    wheel's. Other suffixes (``.xz``, ``.zst``, ``.lz``, ...) are
    kept literal -- ``brp-compress`` doesn't touch them, so
    ``<name>.<section>.<ext>*`` matches the wheel's untouched output
    exactly.

    Output
    ------
    All emitted lines - files and ``%dir`` - merged into one list and
    sorted ASCII-ascending. ``%dir`` lines precede plain file lines
    at the same prefix (``%`` < ``/``). Body ends with a single
    trailing newline.

    Raises
    ------
    ``ValueError`` if ``sys.pycache_prefix`` is non-default:
    ``cache_from_source`` honours the prefix, so every computed
    ``.pyc`` path would be silently shifted out of the install tree.
    """
    if sys.pycache_prefix is not None:
        raise ValueError(
            "rpm-filelist requires sys.pycache_prefix to be at its "
            "default (None); PYTHONPYCACHEPREFIX / -X pycache_prefix "
            "would redirect computed .pyc paths and corrupt the "
            "filelist",
        )

    destdir = Path(destdir)
    dist_info = Path(dist_info)
    purelib, platlib, headers = (
        Path(scheme[n]) for n in ("purelib", "platlib", "headers")
    )
    anchors = (dist_info, headers, purelib, platlib)
    man_root = Path(scheme["data"]) / "share" / "man"

    out_files = set()
    # always own .dist-info dir
    dirs = {dist_info}

    for raw in files:
        f = Path("/") / Path(raw).relative_to(destdir)
        out_files.add(f)

        # deepest match
        anchor = max(
            (a for a in anchors if a in f.parents),
            key=lambda a: len(a.parts),
            default=None,
        )

        # file is outside every anchor (scripts, data),
        # its parents are not processed
        if anchor is None:
            continue

        # own the headers root (per-dist namespaced) once occupied
        if anchor == headers:
            dirs.add(headers)

        # directories between anchor and file's direct parent
        for p in f.parents:
            if p == anchor:
                break
            dirs.add(p)

        # compiled cache in sitepackages
        if anchor in (purelib, platlib) and f.suffix == ".py":
            # own __pycache__ dir unless it's the sitepackages root
            if f.parent != anchor:
                dirs.add(f.parent / "__pycache__")
            # .py files expand to .pyc paths
            out_files.update(
                Path(cache_from_source(str(f), optimization=o))
                for o in PYC_OPTIMIZATION_LEVELS
            )

    def render_file(p):
        rp = str(p)

        # brp-compress compresses uncompressed man pages after %install
        # returns (foo.1 -> foo.1.xz), and decompresses-then-recompresses
        # pages that arrive with .gz/.bz2/.Z (foo.1.gz -> foo.1.xz).
        # Emit the name-plus-section stem with a trailing * so the line
        # matches both compressed and uncompressed forms. If the wheel
        # shipped an already-compressed page, drop that extension first
        # so the glob isn't tied to the source format.
        if man_root in p.parents:
            if p.suffix in MAN_COMPRESSION_SUFFIXES:
                rp = f"{p.parent}/{p.stem}*"
            else:
                rp = f"{p}*"
        return rp

    lines = sorted(
        chain(
            (render_file(p) for p in out_files),
            (f"%dir {p}" for p in dirs),
        ),
    )
    return "\n".join(lines) + "\n"


def write_rpm_filelist(out_path, files, *, destdir, scheme, dist_info):
    """
    Render the filelist for ``files`` and write it to ``out_path``.
    Permissions follow the process umask.
    """
    Path(out_path).write_text(
        render_rpm_filelist(
            files,
            destdir=destdir,
            scheme=scheme,
            dist_info=dist_info,
        ),
        encoding="utf-8",
    )
