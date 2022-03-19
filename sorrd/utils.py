def tryint(val, default=None) -> int:
    try:
        return int(val)
    except:
        return default
