"""
Collection of helper functions that depend only on model/base.py.
"""

from ..model.base import Object
from .utils import utils



def group_objects(
    objects: list[Object],
    group_ancestors: list[Object | list[Object]],
) -> list[list[Object]]:
    """
    Split `objects` into 0 or more groups. The ith group contains all
    objects that are offspring (including same) of any of the ith element from
    `group_ancestors`. This requires all elements from `group_ancestors` to
    be not in a hierarchical relation with each other.
    """
    group_ancestors = [[ga] if isinstance(ga, Object) else ga for ga in group_ancestors]
    flat_ancestors = [a for a in group_ancestors for a in a]

    # assert they are unique:
    assert len(set(flat_ancestors)) == len(flat_ancestors)

    # assert they are not hierarchically dependent:
    for a in flat_ancestors:
        for a2 in flat_ancestors:
            if a is not a2:
                assert a not in a2.ancestors and a2 not in a.ancestors

    res = []
    for a in group_ancestors:
        res_a = []
        for obj in objects:
            if obj in a or any(a in obj.ancestors for a in a):
                res_a.append(obj)
        res.append(res_a)

    return res


def collect_exclude_objects(
    objects: Object | list[Object],
    exclude_objects: Object | list[Object] | None = None,
    type_: type | list[type] | None = None,
    exact_type: bool = False,
) -> list[Object]:
    """
    Collect all objects and their offspring from `objects`. From the result,
    remove all objects and their offsrping from `exclude_objects`. From the
    result, return the ones that are an instance of `type` (if given).
    """
    if type_ is None:
        type_ = Object
    else:
        type_ = utils.type_typetuple_or_typelist_to_typetuple(type_)
    objects = utils.none_object_or_list_to_list(objects)
    exclude_objects = utils.none_object_or_list_to_list(exclude_objects)
    include = [o for o in objects for o in o._get_offspring_by_type(type_)]
    include += [o for o in objects if isinstance(o, type_)]
    exclude = [o for o in exclude_objects for o in o._get_offspring_by_type(type_)]
    exclude += [o for o in exclude_objects if isinstance(o, type_)]
    res = list(set(include) - set(exclude))
    if exact_type:
        res = [o for o in res if type_(o) == type_]
    return res


def valueerror_if_not_common_branch(objects: list[Object]):
    """
    Raise ValueError if the objects are not in a common branch. None as branch
    will also raise ValueError.
    """
    if not objects:
        raise ValueError("No objects provided.")
    common_branch = objects[0].branch
    for obj in objects[1:]:
        if obj.branch is None or common_branch is None:
            raise ValueError("Not all objects have a branch.")
        if obj.branch != common_branch:
            raise ValueError(
                f"Objects do not share a common branch ({obj} in {obj.branch} vs. {objects[0]} in {common_branch})."
            )
