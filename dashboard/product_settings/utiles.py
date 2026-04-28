"""
key_caster.py
=============
Utility that walks any dict and casts values to str when their key
starts with or ends with a specified prefix / suffix.

Usage
-----
    from key_caster import cast_matching_keys

    data = {
        'variant_id':   9,
        'id_user':      42,
        'price':        19.99,
        'is_active':    True,
        'name':         'Widget',
    }

    # Cast keys that START with 'variant_'
    cast_matching_keys(data, startswith='variant_')
    # → {'variant_id': '9', 'id_user': 42, 'price': 19.99, ...}

    # Cast keys that END with '_id'
    cast_matching_keys(data, endswith='_id')
    # → {'variant_id': '9', 'id_user': 42, ...}

    # Both conditions at once (either match triggers the cast)
    cast_matching_keys(data, startswith='variant_', endswith='_id')
"""
import json


def cast_matching_keys(
    data: dict,
    *,
    startswith: str | tuple[str, ...] | None = None,
    endswith:   str | tuple[str, ...] | None = None,
    match:      str = 'any',        # 'any'  → start OR end must match
                                    # 'all'  → start AND end must match
    recursive:  bool = False,       # also walk nested dicts
    # mutate the original dict (False = new dict)
    inplace:    bool = True,
    wanted_type: str = 'str'
) -> dict:
    """
    Walk *data* and cast values to ``str`` wherever the key satisfies
    the start/end conditions.

    Parameters
    ----------
    data        : dict to process
    startswith  : prefix string (or tuple of strings) the key must start with
    endswith    : suffix string (or tuple of strings) the key must end with
    match       : ``'any'``  – cast if the key matches EITHER condition (default)
                  ``'all'``  – cast only if the key matches BOTH conditions
    recursive   : if True, descend into nested dict values
    inplace     : if True (default), mutate *data* and return it;
                  if False, return a new dict (shallow copy + replacements)

    Returns
    -------
    The (possibly new) dict with matching values cast to str.

    Raises
    ------
    ValueError  if neither *startswith* nor *endswith* is provided.
    TypeError   if *data* is not a dict.
    """
    if not isinstance(data, dict):
        raise TypeError(
            f'cast_matching_keys expects a dict, got {type(data).__name__!r}')

    if startswith is None and endswith is None:
        raise ValueError('Provide at least one of: startswith, endswith.')

    if match not in ('any', 'all'):
        raise ValueError(f"match must be 'any' or 'all', got {match!r}")

    result = data if inplace else {}

    for key, value in data.items():
        # ── Evaluate conditions ───────────────────────────────────────────
        start_ok = key.startswith(
            startswith) if startswith is not None else False
        end_ok = key.endswith(endswith) if endswith is not None else False

        if match == 'any':
            should_cast = start_ok or end_ok
        else:   # 'all'
            # When only one side is provided, treat the missing side as True
            # so 'all' still works sensibly with a single condition.
            if startswith is None:
                should_cast = end_ok
            elif endswith is None:
                should_cast = start_ok
            else:
                should_cast = start_ok and end_ok

        # ── Recurse into nested dicts (optional) ─────────────────────────
        if isinstance(value, dict) and recursive:
            nested = cast_matching_keys(
                value,
                startswith=startswith,
                endswith=endswith,
                match=match,
                recursive=recursive,
                inplace=inplace,
            )
            result[key] = nested
            continue

        # try json casting

        try:
            value = json.loads(value) if value != None else None
        except:
            pass
        # ── Cast or pass through ──────────────────────────────────────────
        if should_cast:

            #  result[key] = caster(
            #         loaded_v) if loaded_v is not None else None
            #     print(result[key], '====================>',
            #           str(result[key]), type(result[key]), type(loaded_v))
            if type(value) == wanted_type:
                result[key] = value
            else:
                result[key] = caster(value[0], wanted_type) if type(
                    value) == 'list' else value
            print(result[key], '==========================')
        elif not inplace:
            result[key] = value

    return result


# ── Convenience wrappers ──────────────────────────────────────────────────────

def cast_keys_startswith(data: dict, prefix: str | tuple[str, ...], **kwargs) -> dict:
    """Cast values to str for every key that starts with *prefix*."""
    return cast_matching_keys(data, startswith=prefix, **kwargs)


def cast_keys_endswith(data: dict, suffix: str | tuple[str, ...], **kwargs) -> dict:
    """Cast values to str for every key that ends with *suffix*."""
    return cast_matching_keys(data, endswith=suffix, **kwargs)


def caster(values, wanted_type):
    if wanted_type == 'bool':
        return bool(values)
    if wanted_type == 'int':
        return int(values)
    return str(values)
