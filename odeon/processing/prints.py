"""
Routines for transforming Odeon systems to lists of string ready for printing,
saving etc.
"""

from typing import List, Tuple, Any, Callable, Dict, Union
import pandas as pd

from ..model import Project, Branch, Object, Parent


def print_project_stats(project: Project):
    """
    Print statistics about a project and its branches in a tree structure.
    """
    # TODO Identical versions exist in vista and odeon! To be resolved later

    def payload_func(obj: Union[Project, Branch]):
        if isinstance(obj, Project):
            return []
        elif isinstance(obj, Branch):
            return [
                f"- description = {[f'{k}:{v}' for k,v in obj.description.items()]}",
                f"- validity year = {obj.year}",
                f"- no. of base objects = {len(obj.objects)}",
                f"- no. of objects = {len(obj.offspring)}",
            ]

    def str_func(obj: Union[Project, Branch]):
        if isinstance(obj, Project):
            return f"<Project>: {project.name}"
        elif isinstance(obj, Branch):
            branch = project.branches.index(obj)
            obj_name = obj.name if obj.name is not None else "(no name)"
            if obj is project.main_branch:
                return f"<Project>.branch[{branch}](main): {obj_name}"
            else:
                return f"<Project>.branches[{branch}]: {obj_name}"

    tuples = []
    for b in project.branches:
        reference = b.reference_branch
        reference = reference or project
        tuples.append((reference, b))
    _print_tree(
        parent_child_tuples=tuples,
        root=project,
        payload_func=payload_func,
        str_func=str_func,
    )


def print_object_tree(root: Object, max_levels: int = -1):
    """
    Print the tree of objects starting from `root`.

    Parameters
    ----------
    root : Object
        The root object from which to start printing the tree.
    max_levels: int
        The maximum depth of the tree to print. If -1, print all levels.
    """
    # TODO Identical versions exist in vista and odeon! To be resolved later

    def str_func(obj: Object):
        return str(obj)

    tuples = [(p.parent, p) for p in root.offspring]
    _print_tree(
        parent_child_tuples=tuples,
        root=root,
        payload_func=None,
        str_func=str_func,
        max_levels=max_levels,
    )


def print_object_counts(objects: Union[Object, List[Object]]):
    """
    Print the count per object type in a human-readable table format.
    """
    # TODO Identical versions exist in vista and odeon! To be resolved later

    srs = _object_count_series(objects=objects)
    if len(srs) > 0:
        print(srs.to_string(header=True, name=True))
    else:
        print("no objects")


def _object_count_series(objects: Union[Parent, List[Parent]]) -> pd.Series:
    """
    Get a Series with the count of all object types in `objects` and their
    offspring.

    Returns
    -------
    Series with index "Object type" and name "Count"
    """
    # TODO Identical versions exist in vista and odeon! To be resolved later

    if isinstance(objects, Parent):
        objects = [objects]
    offsprings = []
    for obj in objects:
        offsprings += obj.offspring
    offsprings += objects
    offsprings = list(set(offsprings))
    types_objects = {}
    for offspring in offsprings:
        if offspring.__class__.__name__ in types_objects:
            types_objects[offspring.__class__.__name__] += 1
        else:
            types_objects[offspring.__class__.__name__] = 1
    srs = pd.Series(types_objects)
    srs.index.name = "Object type"
    srs.name = "Count"
    return srs


def _print_tree(
    parent_child_tuples,
    root,
    str_func=str,
    payload_func=None,
    newline_after_payload=True,
    payload_kwargs=None,
    max_levels=-1,
    skipped_children_placeholder="...",
):
    # TODO Identical versions exist in vista and odeon! To be resolved later
    def _pprint(
        obj,
        prefix="",
        last_element=True,
        level=0,
    ):
        FOLDING_PREFIX = "├─"
        LAST_FOLDING_PREFIX = "└─"
        CONTINUATION_PREFIX = "│ "
        EMPTY_PREFIX = "  "
        lines = [f"{prefix}{LAST_FOLDING_PREFIX if last_element else FOLDING_PREFIX}{str_func(obj)}"]

        children = [child for parent, child in parent_child_tuples if parent is obj]

        # Payload
        if payload_func is not None:
            pk = {} if payload_kwargs is None else dict(payload_kwargs)
            pk.update({"obj": obj})
            extras = payload_func(**pk) or []
            prefix_after_obj = EMPTY_PREFIX if last_element else CONTINUATION_PREFIX
            prefix_for_payload = EMPTY_PREFIX if not children else CONTINUATION_PREFIX
            if newline_after_payload:
                extras = list(extras) + [""]
            for e in extras:
                lines.append(f"{prefix}{prefix_after_obj}{prefix_for_payload}{e}")

        # Max level handling
        if max_levels != -1 and level >= max_levels - 1:
            if children:
                # Show a single placeholder entry for hidden subtree
                branch_prefix = EMPTY_PREFIX if last_element else CONTINUATION_PREFIX
                lines.append(
                    f"{prefix}{branch_prefix}{LAST_FOLDING_PREFIX if last_element else FOLDING_PREFIX}{skipped_children_placeholder}"
                )
            return lines

        # Recurse
        next_prefix_base = EMPTY_PREFIX if last_element else CONTINUATION_PREFIX
        for i, child in enumerate(children):
            lines.extend(
                _pprint(
                    child,
                    prefix=f"{prefix}{next_prefix_base}",
                    last_element=i == len(children) - 1,
                    level=level + 1,
                )
            )
        return lines

    print(
        "\n".join(
            _pprint(
                root,
                prefix="",
                last_element=True,
                level=0,
            )
        )
    )