"""
Collection of general helper functions that don't depend on the content of
odeon.model.
"""

import os
from typing import Callable, Literal, Any
import math
from collections import defaultdict

from tqdm import tqdm


def convert_unit(
    value: int | float | str | None,
    from_: str = None,
    to_: str = None,
) -> int | float | str | None:
    """
    Convert a value from one unit to another.

    Possible units are:
    
    - Temperature: 'K', '°C'
    - Energy: 'J', 'kWh', 'kJ', 'cal', 'kcal', 'BTU', 'Wh', 'MJ'
    - Power: 'W', 'kW'
    - Area: 'cm²', 'm²'
    - Length: 'mm', 'm', 'cm', 'km'
    - Time: 's', 'h', 'min'
    - Volume: 'cm³', 'm³', 'L'
    - Mass: 'g', 'kg', 'ton'
    - Pressure: 'Pa', 'bar'

    Parameters
    ----------
    value : Union[int, float, str]
        The value to convert. If a string is provided, it will be converted to
        float. If the value is None, it will be returned as None.
    from_ : str
        The unit to convert from. Must be one of the supported units.
    to_ : str
        The unit to convert to. Must be one of the supported units.

    Returns
    -------
    Union[int, float, str]
        The converted value. If the input was a string, the output will also be
        a string. If the input was an integer, the output will be an integer if
        the result is an integer, otherwise it will be a float. If the input was
        a float, the output will always be a float.

    Raises
    ------
    ValueError
        If the conversion is not supported.
    """

    method = f"{from_}_to_{to_}"

    input_type = type(value)

    if isinstance(value, str):
        value = float(value)

    elif value is None:
        return value

    conversions = {
        # Temperature Conversions
        "K_to_°C": lambda k: k - 273.15,
        "°C_to_K": lambda c: c + 273.15,
        # Energy Conversions
        "J_to_kWh": lambda j: j / 3.6e6,
        "kJ_to_kWh": lambda kj: kj / 3600,
        "cal_to_J": lambda cal: cal * 4.184,
        "kcal_to_J": lambda kcal: kcal * 4184,
        "BTU_to_J": lambda btu: btu * 1055.06,
        "Wh_to_J": lambda wh: wh * 3600,
        "MJ_to_J": lambda mj: mj * 1e6,
        "J_to_cal": lambda j: j / 4.184,
        "J_to_kcal": lambda j: j / 4184,
        "J_to_BTU": lambda j: j / 1055.06,
        "J_to_Wh": lambda j: j / 3600,
        "J_to_MJ": lambda j: j / 1e6,
        "kWh_to_J": lambda kwh: kwh * 3.6e6,
        "kWh_to_kJ": lambda kwh: kwh * 3600,
        "cal_to_kcal": lambda cal: cal / 1000,
        "kcal_to_cal": lambda kcal: kcal * 1000,
        "BTU_to_kWh": lambda btu: btu / 3412.142,
        "kWh_to_BTU": lambda kwh: kwh * 3412.142,
        # Power Conversions
        "W_to_kW": lambda w: w / 1000,
        "kW_to_W": lambda kw: kw * 1000,
        # Area Conversions
        "cm²_to_m²": lambda cm2: cm2 / 10000,
        "m²_to_cm²": lambda m2: m2 * 10000,
        # Length Conversions
        "mm_to_m": lambda mm: mm / 1000,
        "m_to_mm": lambda m: m * 1000,
        "cm_to_m": lambda cm: cm / 100,
        "m_to_cm": lambda m: m * 100,
        "km_to_m": lambda km: km * 1000,
        "m_to_km": lambda m: m / 1000,
        # Time Conversions
        "s_to_h": lambda s: s / 3600,
        "h_to_s": lambda h: h * 3600,
        "min_to_h": lambda min: min / 60,
        "h_to_min": lambda h: h * 60,
        # Volume Conversions
        "cm³_to_m³": lambda cm3: cm3 / 1e6,
        "m³_to_cm³": lambda m3: m3 * 1e6,
        "L_to_m³": lambda l: l / 1000,
        "m³_to_L": lambda m3: m3 * 1000,
        # Mass Conversions
        "g_to_kg": lambda g: g / 1000,
        "kg_to_g": lambda kg: kg * 1000,
        "ton_to_kg": lambda ton: ton * 1000,
        "kg_to_ton": lambda kg: kg / 1000,
        # pressure Conversions
        "Pa_to_bar": lambda pa: pa * 1e-5,
        "bar_to_Pa": lambda bar: bar * 1e5,
    }

    if method in conversions:
        result = conversions[method](value)
        if input_type is int:
            return int(result)
        elif input_type is str:
            return str(result)
        else:
            return result
    else:
        raise ValueError(f"Conversion '{method}' not supported.")

    # z.B. print(convert_unit(273.15, 'K', '°C')) soll 0.0 ausgeben


# TODO this is odeon specific!
def _get_protected_attributes_values(object):
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    return [(k, v) for k, v, in vars(object).items() if k.startswith("_") and k != "_parent"]


def _get_public_attributes_values(object):
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    return [(k, v) for k, v, in vars(object).items() if not k.startswith("_")]


def _get_readable_properties_values(object):
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    readable_properties = []
    for k, v in vars(object.__class__).items():
        if type(v) is property and v.fget is not None:
            readable_properties.append((k, v.fget(object)))  # calling the property getter could be costly!
    return readable_properties


def _get_writable_properties_values(object):
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    writable_properties = []
    for k, v in vars(object.__class__).items():
        if type(v) is property and v.fset is not None:
            writable_properties.append((k, v))
    return writable_properties


def collect(
    objects: list | object,
    check_collect: Callable = None,
    check_descend: Callable = None,
    check_single_underscore: bool = True,
    check_properties: bool = True,
    n_descend: int = -1,
) -> list:
    """
    get all objects that satisfy `check_collect`. These can be hidden in public
    or protected attributes or properties (plain, lists or dicts) that satisfy
    `check_descend`
    """
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")

    def f_recursive(object, check, res, checked_pyids: set[int], n_descend_pending: int = -1):
        sub_objects = []
        new = set()
        kv_tuples = _get_public_attributes_values(object=object)
        if check_single_underscore:
            kv_tuples += _get_protected_attributes_values(object=object)
        # TODO for some reason, checking properties does not work.
        # Leads to false higher number of objects. Takes much longer
        # if check_properties:
        #     kv_tuples += _get_readable_properties_values(object=object)
        for k, v in kv_tuples:
            if check_collect(v):
                new.add(v)
            if check_descend(v):
                sub_objects.append(v)
            if type(v) is list:
                new.update([i for i in v if check_collect(i)])
                sub_objects.extend([i for i in v if check_descend(i)])
            if type(v) is dict:
                new.update([i for i in v.values() if check_collect(i)])
                sub_objects.extend([i for i in v.values() if check_descend(i)])
        res |= new
        checked_pyids.add(id(object))
        if n_descend_pending != 0:
            for so in sub_objects:
                if id(so) not in checked_pyids:
                    f_recursive(
                        object=so,
                        check=check,
                        res=res,
                        checked_pyids=checked_pyids,
                        n_descend_pending=n_descend_pending - 1,
                    )

    res = set()
    if not isinstance(objects, list):
        objects = [objects]
    for object in tqdm(objects):
        if check_collect(object) and not any([object is o for o in res]):
            res.add(object)
        f_recursive(object=object, check=check_collect, res=res, checked_pyids=set(), n_descend_pending=n_descend)
    return res


def collect_by_isinstance(
    objects: list | object, types_collect: list[type], types_descend: list[type], n_descend: int = -1
):
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    return collect(
        objects=objects,
        check_collect=lambda x: isinstance(x, tuple(types_collect)),
        check_descend=lambda x: isinstance(x, tuple(types_descend)),
        check_single_underscore=True,
        check_properties=False,
        n_descend=n_descend,
    )


def closest_common_ancestor_class(classes: list[type]) -> type | None:
    # https://stackoverflow.com/questions/67368701/find-a-common-class-python
    mros = [list(cls.__mro__) for cls in classes]
    ancestry_counts = defaultdict(int)
    while mros:
        for mro in mros:
            current = mro.pop(0)
            ancestry_counts[current] += 1
            if ancestry_counts[current] == len(classes):
                return current
            if len(mro) == 0:
                mros.remove(mro)
    return None


def closest_parent_class(type_or_object: object | type, candidates: list[type]) -> type | None:
    """
    from candidates classes `candidates`, get the closest parent of
    `type_or_object` in terms of MRO. If none of the candidates is a parent,
    `None` will be returned. If multiple candidates are parents of the same
    level (e.g. when using multiple inheritance), the first will be returned
    """
    mro = type_or_object.__mro__ if type(type_or_object) is type else type_or_object.__class__.__mro__
    distances = [mro.index(c) if c in mro else math.inf for c in candidates]
    min_distance = min(distances)
    if min_distance < math.inf:
        return candidates[distances.index(min_distance)]


def _typeerror_if_not_isinstance(x, types_: type | tuple[type], none_ok: bool = True, msg: str = None):
    if isinstance(types_, type):
        types_ = tuple([types_])
    if isinstance(types_, list):
        types_ = tuple(types_)
    if not isinstance(x, types_):
        if not none_ok:
            if msg is None:
                msg = f"{x} is not an instance of {[t.__name__ for t in types_]} (type is: {type(x)})"
            raise TypeError(msg)
        elif x is not None:
            if msg is None:
                msg = f"{x} is not an instance of {[t.__name__ for t in types_]} or None (type is: {type(x)})"
            raise TypeError(msg)


def typeerror_if_not_isinstance(x, types_: type | tuple[type], msg: str = None):
    return _typeerror_if_not_isinstance(x=x, types_=types_, none_ok=False, msg=msg)


def typeerror_if_not_isinstance_or_none(x, types_: type | tuple[type], msg: str = None):
    return _typeerror_if_not_isinstance(x=x, types_=types_, none_ok=True, msg=msg)


def _typeerror_if_not_list_isinstance(x, types_: type | tuple[type], none_ok: bool = True):
    if isinstance(types_, type):
        types_ = tuple([types_])
    if isinstance(types_, list):
        types_ = tuple(types_)
    if x is None:
        if not none_ok:
            raise TypeError(f"{x} is not a list of instances of {[t.__name__ for t in types_]}")
    else:
        if not isinstance(x, list):
            raise TypeError(f"{x} is not a list of instances of {[t.__name__ for t in types_]}")
        for element in x:
            _typeerror_if_not_isinstance(x=element, types_=types_, none_ok=False)


def typeerror_if_not_list_isinstance(x, types_: type | tuple[type]):
    return _typeerror_if_not_list_isinstance(x=x, types_=types_, none_ok=False)


def typeerror_if_not_list_isinstance_or_none(x, types_: type | tuple[type]):
    return _typeerror_if_not_list_isinstance(x=x, types_=types_, none_ok=True)


def type_typetuple_or_typelist_to_typetuple(x: type | list[type] | tuple[type]) -> tuple[type]:
    if isinstance(x, type):
        x = [x]
    if isinstance(x, list):
        x = tuple(x)
    if isinstance(x, tuple):
        assert all(isinstance(x, type) for x in x)
        return x


def none_object_or_list_to_list(x: Literal[None] | list | Any) -> list:
    if x is None:
        return []
    elif isinstance(x, list):
        return x
    elif isinstance(x, tuple):
        return list(x)
    else:
        return [x]


def find_objects_(objects, types=(object,)):
    """
    Get all objects and offspring with type of any in `types`.
    """
    raise DeprecationWarning("collect_by_isinstance is deprecated. Will be removed in a future version.")
    if isinstance(types, list):
        types = tuple(types)
    ret = []
    for o in objects:
        if isinstance(o, types):
            ret.append(o)
        ret += o.get_offspring_of_type(types)
    unique_list = list(set(ret))
    unique_list.sort(key=lambda x: x.id)
    return unique_list


def bytes_as_str(num) -> str:
    """
    Convert a file size in bytes to a human-readable string.
    e.g. 12345678 -> "12.3 MB"
    """
    for x in ["bytes", "KB", "MB", "GB", "TB"]:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0


def file_size_as_str(file_path, factor=1):
    """
    Get the size of a file as a human-readable string.
    """
    if os.path.isfile(file_path):
        file_info = os.stat(file_path)
        return bytes_as_str(file_info.st_size * factor)


def set_tree_greedy(sets: list[set[Any]], root: Any = None) -> dict[Any, dict]:
    """
    Build a compressed item tree from a list of sets where:
      1. Each node is an item.
      2. Root node is the common item A (either provided via `root` or inferred).
      3. For every input set S there is at least one node whose path from root contains all items of S.
      4. Total number of nodes is (greedily) minimized by maximizing shared prefixes.

    Strategy:
      - Choose root (intersection of all sets if not provided).
      - Remove root from each set.
      - Order items inside each set by descending global frequency (then lexicographically for determinism).
      - Insert ordered sequences into a trie; shared prefixes reuse existing nodes.

    Parameters
    ----------
    sets : list[set[Any]]
        List of input sets. Must all contain a common item.
    root : Any, optional
        The designated root item. If None, the first item from the intersection of all sets is used.

    Returns
    -------
    dict[Any, dict]
        Nested dict representing the tree: {root: {child: {...}, ...}}

    Example
    -------
    >>> sets = [set(['a','b','c']), set(['a','c']), set(['a','c','d'])]
    >>> tree = set_tree(sets)
    >>> import pprint; pprint.pprint(tree)
    {'a': {'c': {'d': {}, 'b': {}}}}
    """
    if not sets:
        raise ValueError("sets must be a non-empty list of sets")

    # Validate all are sets and non-empty
    if any(not isinstance(s, set) or not s for s in sets):
        raise ValueError("Each element must be a non-empty set")

    # Determine / validate root
    common = set.intersection(*sets)
    if root is not None:
        if root not in common:
            raise ValueError(f"Provided root '{root}' is not in the intersection of all sets")
    else:
        if not common:
            raise ValueError("No common item across all sets to use as root")
        # deterministic choice: smallest repr
        root = sorted(common, key=lambda x: repr(x))[0]

    # Remove root from sets, build frequency counts
    stripped = [s - {root} for s in sets]
    freq = {}
    for s in stripped:
        for item in s:
            freq[item] = freq.get(item, 0) + 1

    # Order items inside each set for maximal shared prefix (frequency desc, then repr)
    ordered_sets = [sorted(s, key=lambda x: (-freq[x], repr(x))) for s in stripped]

    # Build tree
    tree = {root: {}}
    for seq in ordered_sets:
        node = tree[root]
        for item in seq:
            if item not in node:
                node[item] = {}
            node = node[item]

    return tree


def count_trie_nodes(tree: dict[Any, dict]) -> int:
    """Count total nodes in trie (including root)."""

    def _c(d):
        return sum(1 + _c(v) for v in d.values())

    return 1 + _c(next(iter(tree.values()))) if tree else 0


def collapse_unary_dict_levels(tree: dict) -> dict:
    """
    Collapse unary levels in a nested dict tree by replacing keys with
    frozensets of collapsed levels.

    Example:
    `{'A': {'B': {'C': {}}}}  -->  {'A': {frozenset({'B', 'C'}): {}}}`
    """

    def _collapse(d):
        new_d = {}
        for k, v in d.items():
            if isinstance(v, dict):
                collapsed_v = _collapse(v)
                if len(collapsed_v) == 1:
                    ((child_k, child_v),) = collapsed_v.items()
                    new_key = frozenset({k, *child_k} if isinstance(child_k, frozenset) else {k, child_k})
                    new_d[new_key] = child_v
                else:
                    new_d[frozenset([k])] = collapsed_v
            else:
                new_d[frozenset([k])] = v
        return new_d

    return _collapse(tree)
