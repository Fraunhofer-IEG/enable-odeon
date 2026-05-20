from typing import Dict, Any, TYPE_CHECKING, List, Tuple, Union
from enum import Enum

import pandas as pd
import odeon.model as om
import json
import logging
import networkx as nx


logger = logging.getLogger(f"enable.{__name__}")

if TYPE_CHECKING:
    from odeon.model import Object, Temporal, Branch


def get_class_plain_attrs(cls: type) -> Dict[str, Any]:
    """
    Get all non-callable, non-dunder, non-property/static/class attributes
    defined directly on the class.
    """
    return {
        k: v
        for k, v in cls.__dict__.items()
        if not (k.startswith("__") and k.endswith("__"))  # skip dunders
        and not callable(v)  # skip functions
        and not isinstance(v, (property, staticmethod, classmethod))
    }


def get_all_plain_class_attrs(cls: type) -> Dict[str, Any]:
    """
    Get all non-callable, non-dunder, non-property/static/class attributes
    defined on the class and its superclasses, with precedence to the most
    derived class in case of name clashes.
    """
    seen = {}
    for base in reversed(cls.__mro__):
        for k, v in base.__dict__.items():
            if k in seen:
                continue
            if (
                (k.startswith("__") and k.endswith("__"))
                or callable(v)
                or isinstance(v, (property, staticmethod, classmethod))
            ):
                continue
            seen[k] = v
    return seen


def get_instance_plain_attrs(obj: object) -> Dict[str, Any]:
    """
    Get all non-callable, non-dunder, non-property/static/class attributes
    defined on the instance. Also includes class-level plain attributes not
    shadowed by instance attributes.
    """
    # start with instance-specific (works even if shadowing class attrs)
    data = {k: v for k, v in getattr(obj, "__dict__", {}).items() if not (k.startswith("__") and k.endswith("__"))}
    # add class-level plain attrs not already present
    for k, v in obj.__class__.__dict__.items():
        if k in data:
            continue
        if (
            (k.startswith("__") and k.endswith("__"))
            or type(v).__name__ == "_abc_data"  # skip abc data
            or callable(v)
            or isinstance(v, (property, staticmethod, classmethod))
        ):
            continue
        data[k] = v
    return data


def object_to_json_dict(obj: "Object") -> Dict:
    """
    Convert an Object to a JSON-serializable dictionary.

    This function handles special attributes like temporal attributes,
    children, and associated objects by representing them as <ClassName id=...>.
    The objects corresponding to these attributes won't be serialized.


    Example
    -------
    >>> from odeon.model import Building, Household
    >>> b = Building(name="My Building")
    >>> b.add_household(Household(name="HH1"))
    >>> json_ = object_to_json_dict(b)
    >>> print(json_)
    {
        "id": 0,
        "class": "Building",
        "name": "My Building",
        "building_units": ["<Household id=1>"],
        ...
    }
    """
    str_ = object_to_json_str(obj=obj)
    data = json.loads(str_)
    return data


def object_to_json_str(obj: "Object") -> str:
    """
    Convert an Object to a JSON string.

    This function handles special attributes like temporal attributes,
    children, and associated objects by representing them as <ClassName id=...>.
    The objects corresponding to these attributes won't be serialized.

    Example
    -------
    >>> from odeon.model import Building, Household
    >>> b = Building(name="My Building")
    >>> b.add_household(Household(name="HH1"))
    >>> json_ = object_to_json(b)
    >>> print(json_)
    {
        "id": 0,
        "class": "Building",
        "name": "My Building",
        "building_units": ["<Household id=1>"],
        ...
    }
    """

    # what types can we expect here to be present in an object?
    # ---------------------------------------------------------
    # - children attributes: Object or List[Object]
    # - associated attributes: Object or List[Object]
    # - temporal attributes: Temporal
    # - temporal dict attributes: Dict[str, Temporal]
    # - other attributes:
    #   - atomic types: int, float, str, bool, None
    #   - Odeon types that are not Objects: e.g. Medium, Enums -> these need to
    #     implement from_json and to_json methods
    #   - containers of the above: List, Dict
    #   - shapely geometries

    # how will we parse this?
    # -----------------------
    # - for children and associated attributes, we just store a string reference
    #   "<ClassName id=...>"
    # - for temporal attributes, we store a string reference "<ClassName id=...>"
    # - for other attributes, we try to serialize them directly, and if that fails,
    #   we fall back to the default serializer which will call __json__ if available,
    #   otherwise store a "warning" string.

    def object_to_str(o: "Object") -> str:
        return f"<{o.__class__.__name__} id={o.id}>"

    def temporal_to_str(t: om.Temporal) -> str:
        return f"<{t.__class__.__name__} id={t.id}>"

    def default_serializer(o: Any) -> str:

        s = None

        # call the object's own __json__ method if it has one:
        if hasattr(o, "__json__") and callable(o.__json__):
            s = o.__json__()

        if hasattr(o, "to_json") and callable(o.to_json):
            s = o.to_json()

        if s is not None:
            return f"<{o.__class__.__name__} {s}>"

        logger.warning("Can't serialize object of type %s", type(o).__name__)
        return f"<unserialisable:{type(o).__name__}>"

    # don't serialize reserved attributes:
    RESERVED_ATTRS = {
        # handle this one separately:
        "id",
        # stored reversely as the children of the parent:
        "_parent",
        # class attributes, or instance attributes derived from them -
        # will be provided by the class' init when deserializing:
        "_temporal_attributes",
        "_temporal_dict_attributes",
        "_children_attributes",
        "_associated_attributes",
        "_ASSOCIATED_ATTRIBUTES",
        "_CHILDREN_ATTRIBUTES",
        "_TEMPORAL_ATTRIBUTES",
        "_TEMPORAL_DICT_ATTRIBUTES",
        # derived from the branch's organizers -
        # will be provided by the branch when deserializing:
        "_affiliations",
    }

    data: Dict[str, Any] = {
        "id": obj.id,
        "class": obj.__class__.__name__,  # to be able to deserialize later
    }

    for attr, value in get_instance_plain_attrs(obj=obj).items():
        # TODO performance boost: cache get_instance_plain_attrs results per class?

        if "__" in attr:
            continue  # skip private attributes

        elif attr in RESERVED_ATTRS:
            continue  # skip reserved attributes

        # temporal attributes = Temporal:
        elif attr in obj._temporal_attributes:
            assert isinstance(value, om.Temporal)
            data[attr] = temporal_to_str(value)

        # temporal dict attributes = Dict[str, Temporal]:
        elif attr in obj._temporal_dict_attributes:
            assert isinstance(value, dict)
            assert all(isinstance(t, om.Temporal) for t in value.values())
            data[attr] = {k: temporal_to_str(t) for k, t in value.items()}

        # children attributes - either Object or List[Object]:
        elif attr in obj._children_attributes:
            if isinstance(value, list):
                assert all(isinstance(c, om.Object) for c in value)
                data[attr] = [object_to_str(c) for c in value]
            elif isinstance(value, om.Object):
                data[attr] = object_to_str(value)
            elif value is not None:
                raise ValueError(f"Unexpected value for children attribute {attr}: {value}")

        # associated attributes - either Object or List[Object]:
        elif attr in obj._associated_attributes:
            if isinstance(value, list):
                assert all(isinstance(c, om.Object) for c in value)
                data[attr] = [object_to_str(c) for c in value]
            elif isinstance(value, om.Object):
                data[attr] = object_to_str(value)
            elif value is not None:
                raise ValueError(f"Unexpected value for associated attribute {attr}: {value}")

        # other attributes:
        else:
            try:
                # Manually catch StrEnum to avoid serializing as plain string
                if isinstance(value, Enum) and isinstance(value, str):
                    data[attr] = default_serializer(value)
                else:
                    # check whether value is JSON serializable, but store original value in dict:
                    _ = json.dumps(value, default=default_serializer)
                    data[attr] = value  # store original value
            except Exception:
                logger.warning("Can't serialize object of type %s", type(value).__name__)
                data[attr] = f"<unserialisable:{type(value).__name__}>"
    try:
        json_ = json.dumps(data, default=default_serializer)
        return json_

    except Exception as e:
        logger.warning("Failed to serialize object %s: %s", obj, e)
        json_ = json.dumps({"error": f"serialization_failed: {e}"})
        return json_


def objects_from_json_strs(datas: List[str], temporals: List["Temporal"]) -> List["Object"]:
    """
    Reconstruct Objects from their JSON string representations. Link to
    provided Temporal instances by their IDs.
    """

    # ----------------------------------------------------------------------
    # helper functions for parsing special strings
    # ----------------------------------------------------------------------

    def is_obj_str(s: str) -> bool:
        return isinstance(s, str) and s.startswith("<") and s.endswith(">") and " " in s

    def obj_str_to_class_name_and_payload(s: str) -> Tuple[str, str]:
        # expected format: "<ClassName ...>"
        if not is_obj_str(s):
            raise Exception(f"Invalid object reference string: {s}")
        parts = s[1:-1].split(" ")
        assert len(parts) == 2
        return parts[0], parts[1]  # class name, payload

    def is_identified_str(s: str) -> bool:
        # expected format: "<ClassName id=123>"
        return isinstance(s, str) and s.startswith("<") and s.endswith(">") and " id=" in s

    def identified_str_to_object(s: str) -> "Object":
        # expected format: "<ClassName id=123>"
        if not is_identified_str(s):
            raise Exception(f"Invalid object reference string: {s}")
        parts = s[1:-1].split(" id=")
        if len(parts) == 2:
            oid = int(parts[1])
            object = ids_objects.get(oid, None)
            if object is None:
                raise Exception(f"Referenced object id={oid} not found")
        return object

    def identified_str_to_id(s: str) -> int:
        # expected format: "<ClassName id=123>"
        if not is_identified_str(s):
            raise Exception(f"Invalid object reference string: {s}")
        parts = s[1:-1].split(" id=")
        if len(parts) == 2:
            oid = int(parts[1])
            return oid
        raise Exception(f"Invalid object reference string: {s}")

    def temporal_str_to_object(s: str) -> "Temporal":
        # expected format: "<Temporal id=123>"
        if not is_identified_str(s):
            raise Exception(f"Invalid temporal reference string: {s}")
        parts = s[1:-1].split(" id=")
        if len(parts) == 2:
            tid = int(parts[1])
            temporal = ids_temporals.get(tid, None)
            if temporal is None:
                raise Exception(f"Referenced temporal id={tid} not found")
        return temporal

    def object_hook(s: str) -> Any:
        """
        Custom object hook for json.loads to parse special classes.

        Handles:
        - Odeon objects (not inheriting from Identified),
        - Identified objects: "<ClassName id=...>" (e.g. Object, Temporal)
        """
        # parse special Odeon objects (not inheriting from Identified),
        # e.g. Medium or Enums. These will be stored in the form
        # "<ClassName [payload]>". The corresponding class needs to
        # implement a from_json class method to deserialize from the payload:
        if is_obj_str(s) and not is_identified_str(s):
            class_name, payload = obj_str_to_class_name_and_payload(s)
            cls = getattr(om, class_name, None)
            obj = cls.from_json(payload)
            return obj

        # parse everything else:
        # - identified objects: "<ClassName id=...>"
        else:
            try:
                # this will work for normal JSON strings:
                return json.loads(s)
            except Exception:
                # instances of Object, Temporal will raise the exception
                # and stay as strings for further processing:
                return s

    def add_list_child(parent: "Object", attr: str, child: Union["Object", "Temporal"]):
        """
        Add a child to a list-type children attribute and set its parent.
        """
        getattr(parent, attr).append(child)
        # child._set_parent(parent)
        if isinstance(child, om.Object):
            child._Object__parent = parent
        elif isinstance(child, om.Temporal):
            child._Temporal__parent = parent
        else:
            raise Exception(f"Invalid child type: {type(child)}")

    def set_plain_child(parent: "Object", attr: str, child: Union["Object", "Temporal"]):
        """
        Set a plain child attribute and set its parent.
        """
        setattr(parent, attr, child)
        # child._set_parent(parent)
        if isinstance(child, om.Object):
            child._Object__parent = parent
        elif isinstance(child, om.Temporal):
            child._Temporal__parent = parent
        else:
            raise Exception(f"Invalid child type: {type(child)}")

    def object_from_json_str(
        data: str,
    ) -> Tuple[
        "Object",
        Dict[str, Union[int, List[int]]],
        Dict[str, Union[int, List[int]]],
    ]:
        """
        Get an object instance from its JSON string representation.
        Returns the object instance, a mapping of children attributes to
        their IDs, and a mapping of associated attributes to their IDs.
        Temporals will be linked, children and associated won't.
        """

        # parse JSON string to dict, use object_hook to parse special classes.
        # this will leave Identified objects as strings for further processing:
        data = json.loads(data, object_hook=object_hook)

        # build the object instance:
        class_name = data.get("class", None)
        if class_name is None:
            raise Exception(f"Missing 'class' in object data: {data}")
        cls = getattr(om, class_name, None)
        if cls is None or not issubclass(cls, om.Object):
            raise Exception(f"Unknown or invalid class '{class_name}' in object data: {data}")
        # call init:
        obj = cls()
        # set id to original value - we might want to change that later:
        id = data.get("id", None)
        if id is None:
            raise Exception(f"Missing 'id' in object data: {data}")
        obj._Identified__id = id

        # key: attribute name
        # value: child ID (if single child attribute) or list of child IDs to link later
        children_attributes_and_ids: Dict[str, Union[int, List[int]]] = {}

        # key: attribute name
        # value: associated object ID (if single associated attribute) or list of associated IDs to
        # link later
        associated_attributes_and_ids: Dict[str, Union[int, List[int]]] = {}

        # set attributes:
        for attr, value in data.items():

            if attr in ("id", "class"):
                # already handled
                continue

            if attr in obj._children_attributes:
                # don't link, only collect ids:

                # list of children:
                if isinstance(value, list):
                    ids = [identified_str_to_id(x) for x in value]
                    children_attributes_and_ids[attr] = ids

                # plain child:
                elif is_identified_str(value):
                    oid = identified_str_to_id(s=value)
                    children_attributes_and_ids[attr] = oid

                else:
                    raise Exception(f"Invalid child attribute value for {obj}.{attr}: {value}")

            elif attr in obj._associated_attributes:
                # don't link, only collect ids:

                # list of associated:
                if isinstance(value, list):
                    ids = [identified_str_to_id(x) for x in value]
                    associated_attributes_and_ids[attr] = ids

                # plain associated:
                elif is_identified_str(value):
                    oid = identified_str_to_id(s=value)
                    associated_attributes_and_ids[attr] = oid

                else:
                    raise Exception(f"Invalid associated attribute value for {obj}.{attr}: {value}")

            elif attr in obj._temporal_attributes + obj._temporal_dict_attributes:
                # get the temporals and link them:

                if isinstance(value, dict):
                    for k, v in value.items():
                        t = temporal_str_to_object(s=v)
                        tid = t.id  # temporary store id

                        # try to convert key to int if possible
                        try:
                            k = int(k)
                        except:
                            pass
                        obj._set_dict_temporal(attr=attr, key=k, temporal=t)
                        t._Identified__id = tid  # ensure id is correct

                elif is_identified_str(value):
                    t = temporal_str_to_object(s=value)
                    tid = t.id  # temporary store id
                    obj._set_simple_temporal(attr=attr, temporal=t)
                    t._Identified__id = tid  # ensure id is correct

                else:
                    raise Exception(f"Invalid temporal attribute value for {obj}.{attr}: {value}")

            else:
                try:
                    setattr(obj, attr, object_hook(value))
                except:
                    setattr(obj, attr, value)

        return obj, children_attributes_and_ids, associated_attributes_and_ids

    def link_object(
        object: "Object",
        children_attributes_and_ids: Dict[str, Union[int, List[int]]],
        associated_attributes_and_ids: Dict[str, Union[int, List[int]]],
    ):
        """
        Link objects by their IDs based on the provided mapping of object IDs
        to their children's IDs.
        """

        for attr, value in children_attributes_and_ids.items():
            if attr in object._children_attributes:
                # list of children:
                if isinstance(value, list):
                    existing_linked_objects = getattr(object, attr)
                    setattr(object, attr, [])  # initialize list
                    # remove parent for all previously linked children:
                    for o2 in existing_linked_objects:
                        o2._set_parent(None, error_if_not_found=False)

                    # add new children:
                    objects = [ids_objects[x] for x in value]
                    for o2 in objects:
                        add_list_child(object, attr, o2)  # will ensure both forward and reverse connection

                # plain child:
                else:
                    assert isinstance(value, int)
                    o2 = ids_objects[value]
                    set_plain_child(object, attr, o2)  # will ensure both forward and reverse connection

            else:
                raise Exception(f"Invalid child attribute value for {object}.{attr}: {value}")

        for attr, value in associated_attributes_and_ids.items():
            if attr in object._associated_attributes:
                # list of associated:
                if isinstance(value, list):
                    objects = [identified_str_to_object(x) for x in value]
                    for o2 in objects:
                        getattr(object, attr).append(o2)  # don't need to link back

                # plain associated:
                else:
                    assert isinstance(value, int)
                    o2 = ids_objects[value]
                    setattr(object, attr, o2)  # don't need to link back

            else:
                raise Exception(f"Invalid associated attribute value for {object}.{attr}: {value}")

    # ------------------------------------------------------------------------
    # reconstruct all objects
    # ------------------------------------------------------------------------

    ids_temporals: Dict[int, "Temporal"] = {t.id: t for t in temporals}

    ids_objects: Dict[int, "Object"] = {}

    # key: object id
    # value: dict of children attributes to their IDs
    ids_children_attributes_and_ids: Dict[int, Dict[str, Union[int, List[int]]]] = {}

    # key: object id
    # value: dict of associated attributes to their IDs
    ids_associated_attributes_and_ids: Dict[int, Dict[str, Union[int, List[int]]]] = {}

    # --------------------------------

    # first pass:
    # - parse all objects
    # - store them by id (without linking references)
    # - collect children ids for later linking:
    for data in datas:
        object, children_attributes_and_ids, associated_attributes_and_ids = object_from_json_str(data=data)
        ids_objects[object.id] = object
        ids_children_attributes_and_ids[object.id] = children_attributes_and_ids
        ids_associated_attributes_and_ids[object.id] = associated_attributes_and_ids

    # --------------------------------

    # prepare second pass:
    # sort objects from most parent to most child to ensure parents are linked before children
    # (important for setting _parent attributes correctly):
    G = nx.DiGraph()
    for oid, child_attrs in ids_children_attributes_and_ids.items():
        for attr, ids in child_attrs.items():
            if isinstance(ids, list):
                for cid in ids:
                    G.add_edge(oid, cid)
            else:
                G.add_edge(oid, ids)

    # TODO test! whether this works correctly
    # sorted_oids = list(nx.topological_sort(G))

    # --------------------------------

    # second pass: link all references (children, associated)
    # for oid in sorted_oids:
    for oid in ids_children_attributes_and_ids.keys():
        object = ids_objects[oid]
        link_object(
            object=object,
            children_attributes_and_ids=ids_children_attributes_and_ids[oid],
            associated_attributes_and_ids=ids_associated_attributes_and_ids[oid],
        )

    return list(ids_objects.values())


def objects_from_json_dicts(datas: List[Dict], temporals: List["Temporal"]) -> List["Object"]:
    """
    Reconstruct Objects from their JSON dictionary representations. Link to
    provided Temporal instances by their IDs.
    """
    json_strs = [json.dumps(data) for data in datas]
    objects = objects_from_json_strs(datas=json_strs, temporals=temporals)
    return objects


def branch_to_json_str(
    branch: "Branch",
) -> str:
    """
    Convert a Branch to its JSON string representation.
    """
    data_dict = {
        "id": branch.id,
        "objects": [obj.id for obj in branch.objects],
        "year": branch.year,
    }
    return json.dumps(data_dict)


def branch_from_json_str(
    data: str,
    objects: List["Object"],
) -> "om.Branch":
    """
    Reconstruct a Branch from its JSON string representation.
    Set its objects from the provided list of Objects if they are direct
    children of the Branch (ignore all others).
    """

    # stuff to handle:

    # - __timeindex: pd.DatetimeIndex
    # - __project: "Project"
    # - __objects: Set[Object]
    # - __reference_branch: Union["Branch", None]
    # - __mapping: Dict[Object, Object]
    # - __organizers: List[Organizer]
    # - __weather: "om.Weather"
    # - __financing: "om.Financing"
    # - holidays: List[datetime]
    # - description: Dict
    # - history: CallTracker

    ids_objects = {obj.id: obj for obj in objects}

    data_dict = json.loads(data)

    branch = om.Branch()
    branch._Identified__id = data_dict.get("id", None)

    IGNORED_ATTRS = {
        # handled separately:
        "id",
        # set reversely from the project:
        "project",
        # ignored for now -> no referencing for deserialized branches:
        "reference_branch",
        "mapping",
    }

    for attr, value in data_dict.items():

        if attr in IGNORED_ATTRS:
            continue

        elif attr == "objects":
            ...  # TODO

        elif attr == "year":
            branch.year = value
            branch.__timeindex = pd.date_range(start=f"{value}-01-01", end=f"{value}-12-31", freq="D")

        elif attr == "organizers":
            ...  # TODO

        else:
            setattr(branch, attr, value)


def temporal_metadata_to_json(temporal: "Temporal") -> str:
    """
    Convert the metadata of a Temporal to its JSON string representation.

    This includes:
    - id
    - class
    - constraints
    - master id
    - year (may be used to restore timeindex later)

    This doesn't include the series itself.
    """
    raise NotImplementedError("temporal_metadata_to_json not implemented yet")
    # TODO


def temporal_from_json_str(data: str) -> "Temporal":
    """
    Reconstruct a Temporal from its JSON string representation.

    This only reconstructs the metadata, not the series itself.
    """
    raise NotImplementedError("temporal_from_json_str not implemented yet")
    # TODO
