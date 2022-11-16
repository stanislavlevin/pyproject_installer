def parse_entry_points(distr, group):
    """
    Compat only.
    - module and attr attributes of ep are available since Python 3.9
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

    for ep in eps:
        try:
            # module is available since Python 3.9
            ep_module = ep.module
        except AttributeError:
            ep_match = ep.pattern.match(ep.value)
            ep_module = ep_match.group("module")

        try:
            # attr is available since Python 3.9
            ep_attr = ep.attr
        except AttributeError:
            ep_attr = ep_match.group("attr")

        yield (ep.name, ep.value, ep_module, ep_attr)
