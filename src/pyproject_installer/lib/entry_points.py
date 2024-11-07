def parse_entry_points(distr, group):
    """
    Compat only.
    - "selectable" entry points were introduced in Python 3.10
    """
    distr_eps = distr.entry_points
    try:
        # since Python3.10
        distr_eps.select
    except AttributeError:
        eps = (ep for ep in distr_eps if ep.group == group)
    else:
        eps = distr_eps.select(group=group)

    yield from ((ep.name, ep.value, ep.module, ep.attr) for ep in eps)
