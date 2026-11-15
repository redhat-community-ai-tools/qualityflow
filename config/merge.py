"""Deep merge of QualityFlow config layers (config/README.md "Repo config layers").

- Mappings merge recursively; the higher layer wins per key.
- Scalars replace.
- Lists replace, except lists whose items are all mappings with an `id` key
  (else all with a `name` key): those merge item by item on that key, a
  matching item deep-merging and a new one appended.
- A list opts out with a directive mapping {merge: append|replace, value: [...]}.
- `null` removes the key: lower layers' value is dropped and the key reads unset.
"""
import copy


def directive(value):
    """(mode, items) for a {merge: append|replace, value: [...]} mapping, else None."""
    if not (isinstance(value, dict) and set(value) == {"merge", "value"}):
        return None
    if value["merge"] not in ("append", "replace") or not isinstance(value["value"], list):
        raise ValueError("a merge directive needs merge: append|replace and a list value")
    return value["merge"], value["value"]


def _item_key(base, over):
    for key in ("id", "name"):
        if all(isinstance(i, dict) and key in i for i in base + over):
            return key
    return None


def merge(base, over):
    """`over` merged onto `base`; neither argument is modified."""
    d = directive(over)
    if d:
        mode, items = d
        head = base if mode == "append" and isinstance(base, list) else []
        return copy.deepcopy(head + items)
    if isinstance(over, dict):
        out = copy.deepcopy(base) if isinstance(base, dict) else {}
        for k, v in over.items():
            if v is None:
                out.pop(k, None)
            else:
                out[k] = merge(out.get(k), v)
        return out
    if isinstance(base, list) and isinstance(over, list) and over and (key := _item_key(base, over)):
        out = copy.deepcopy(base)
        index = {item[key]: i for i, item in enumerate(out)}
        for item in over:
            if item[key] in index:
                out[index[item[key]]] = merge(out[index[item[key]]], item)
            else:
                index[item[key]] = len(out)
                out.append(copy.deepcopy(item))
        return out
    return copy.deepcopy(over)


def leaves(data, prefix=""):
    """Dotted paths of the values a layer sets (a list or a directive is one value)."""
    if isinstance(data, dict) and data and not directive(data):
        for k, v in data.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif prefix:
        yield prefix

