from __future__ import annotations
from abc import abstractmethod
from enum import Enum, unique
from numbers import Number
from typing import Any, Literal, TYPE_CHECKING
import copy
import pandas as pd
from shapely.geometry import Polygon, Point
from datetime import datetime
from tqdm import tqdm
from rtree import index
import warnings
import logging
import networkx as nx

from .base_geometry import Projector, switch_xy

from ..metadata import CallTracker
from ..processing.utils.utils import (
    type_typetuple_or_typelist_to_typetuple,
    typeerror_if_not_isinstance,
    none_object_or_list_to_list,
    typeerror_if_not_isinstance_or_none,
)
from ..processing.all import get_class_by_name

import odeon.model as om
import odeon.io as oio

logger = logging.getLogger(name=f"enable.{__name__}")

if TYPE_CHECKING:
    from .geometry import Geometry
    from .environment import Weather
    from .expense import Financing
    from .temporal import Temporal
    from .expense import Expense, ExpenseType, Financing
    from ..io.temporal_manager import TemporalManager
    from ..io.file_adapter import FileAdapter


TypeDescriptor = type | tuple[type] | list[type]


class IdAuthority:
    """Simple monotonic ID generator.

    The authority hands out consecutive integer IDs starting at the
    configured initial value. It is module-global (see `id_authority`) and
    used by `Identified` to assign unique object ids.

    Parameters
    ----------
    last_value : int, optional
        The last value that was handed out (internally). The next call will
        return `last_value + 1`. Default is -1 so the first id is 0.
    """

    def __init__(self, last_value: int = -1):
        self.__last_value = last_value

    def __call__(self):
        """Return the next id and advance the internal counter."""
        self.__last_value += 1
        return self.__last_value

    def last_value_from_objects(self, *objects):
        """Synchronise internal counter with a collection of objects.

        Sets the internal last value to at least the maximum id of the
        provided objects so that subsequent ids remain unique.
        """
        self.__last_value = max(self.__last_value, max(o.id for o in objects))

    def set_last_value(self, last_value: int):
        """Manually force the internal last value (use with care)."""
        self.__last_value = last_value

    @property
    def last_value(self):
        """The most recently issued id."""
        return self.__last_value


# global ID Authority, created once on module load.
# this ID authority will deal IDs to all objects created in an environment at
# runtime. Having a global ID authority means that
# - if two projects are created in the session, they will have distinct IDs
# if a project gets loaded from a pickle, the global ID authority will be adapted
# to the stored ID authority in that pickle. Having multiple projects in a session
# with one of them being loaded from a pickle might lead to serious problems
id_authority = IdAuthority()


@unique
class UniqueEnum(Enum):
    """Enum variant with stricter equality and helper properties."""

    def __contains__(self, v) -> bool:
        return v in self.__members__

    def __eq__(self, v) -> bool:
        return v.value == self.value and v.__class__ == self.__class__

    def __hash__(self):
        try:
            return hash((self.__class__, self.value))
        except TypeError:
            return hash((self.__class__, tuple([tuple(i) for i in self.value])))

    def to_json(self):
        return self.name

    @classmethod
    def from_json(cls, data):
        return cls.__members__[data]

    @property
    def full_value(self) -> str:
        """Fully qualified value string `ClassName.value`."""
        return f"{self.__class__.__name__}.{self.value}"

    @property
    def full_name(self) -> str:
        """Fully qualified enum name `ClassName.MEMBER`."""
        return f"{self.__class__.__name__}.{self.name}"


class StrEnum(str, UniqueEnum):
    """String based Enum with convenience helpers."""

    @classmethod
    def has_member_key(cls, key) -> bool:
        """Return True if `key` is a declared enum member name."""
        return key in cls.__members__


class Identified:
    """
    Mixin adding unique integer id management.

    Provides automatic id assignment via the module level `id_authority`
    and custom deepcopy semantics that always create a fresh id.
    """

    __id: int = None

    def __init__(self, set_id: bool = True):
        self.__id = None
        if set_id:
            self._set_new_id_from_authority()

    def _set_new_id_from_authority(self):
        self.__id = id_authority()

    def __eq__(self, __o: object) -> bool:
        return id(__o) == id(self)

    def __hash__(self) -> int:
        # togehter with __eq__, this allows us to use an Object as a dict key
        return id(self)

    @property
    def id(self) -> int:
        return self.__id

    def __deepcopy__(self, memo):
        """Custom deepcopy generating a fresh id.

        The copied instance receives a new id from the global authority;
        all other attributes are deep copied.
        """
        cls = self.__class__
        res = cls.__new__(cls)
        memo[id(self)] = res
        for k, v in self.__dict__.items():
            if k == "_Identified__id":
                res.__dict__[k] = id_authority()
            else:
                res.__dict__[k] = copy.deepcopy(v, memo)
        return res


# ==============================================================================
# Base
# ==============================================================================


class Base(Identified):
    """Common base for all user facing entities.

    Adds name/labels/custom_data plus affiliation handling and freezes the
    attribute set after initialization to prevent accidental attribute
    creation through typos.
    """

    __frozen: bool = None
    _affiliations: list["Organizer"] = None
    name: str = None
    labels: dict[Any, str] = None
    custom_data: dict = None

    def __init__(
        self,
        name: str | None = None,
        labels: dict[Any, str] | None = None,
        custom_data: dict[str, Any] | None = None,
        **kwargs,
    ):
        """Create a new base entity.

        Parameters
        ----------
        name : str or None, optional
            Human readable name.
        labels : dict, optional
            Arbitrary label mapping (e.g. external ids).
        custom_data : dict, optional
            Free form user data.
        **kwargs : Any
            Additional attribute assignments (validated, non protected).
        """
        super().__init__()
        self.name = name
        self.labels = labels or {}
        self.custom_data = custom_data or {}
        self._affiliations = []
        self.__frozen = True
        if kwargs:
            unconsumed = []
            for kwarg in kwargs:
                if kwarg.startswith("_"):
                    raise Exception(f"Can't set protected attribute by a keyword argument: {kwarg}")
                try:
                    setattr(self, kwarg, kwargs[kwarg])
                except:
                    unconsumed.append(kwarg)
            if unconsumed:
                raise Exception(f"Unconsumed kwargs creating {self.__class__.__name__}: {unconsumed}")

    def __setattr__(self, key, value):
        """Prevent adding new attributes after initialization.

        Only pre-declared / existing attributes (including properties) may
        be set once the object is frozen. This guards against silent typos.
        """
        if self.__frozen and key not in dir(self) and not hasattr(self, key):
            # hasattr also returns properties, dir doesn't
            raise AttributeError(f"Can't set '{key}' for {self.__class__.__name__}: Object is frozen")
        super().__setattr__(key, value)

    def set_attribute(self, key, value):
        """
        Set the existing attribute `key`. If `key` has the prefix `custom_data.`,
        the value will be added to the custom data dictionary (possibly
        overwriting an existing value)
        """
        if key.startswith("custom_data."):
            split = key.split(".")
            assert len(split) == 2
            self.custom_data[split[1]] = value
        else:
            setattr(self, key, value)

    def get_attribute(self, key):
        """
        Get the existing attribute `key`. If `key` has the prefix `custom_data.`,
        the key will be looked up in the custom data dictionary. Will raise an
        exception if `key` is neither an attribute nor a custom data key.
        """
        if key.startswith("custom_data."):
            split = key.split(".")
            assert len(split) == 2
            return self.custom_data[split[1]]
        else:
            return getattr(self, key)

    def __repr__(self):
        if self.name is not None:
            return f"{self.__class__.__name__}(id={self.id}, name='{self.name}')"
        else:
            return f"{self.__class__.__name__}(id={self.id})"

    @property
    def affiliations(self) -> list["Organizer"]:
        return self._affiliations

    @property
    def affiliations_recursive(self) -> list["Organizer"]:
        """
        first and higher order affiliations (affiliations of affiliations)
        """
        ret = []
        for a in self._affiliations:
            if a not in ret:
                ret.append(a)
            for a2 in a.affiliations_recursive:
                if a2 not in ret:
                    ret.append(a2)
        return ret

    @property
    @abstractmethod
    def project(self) -> "Branch": ...

    @property
    @abstractmethod
    def branch(self) -> "Branch": ...

    def add_affiliations(self, affiliations: Organizer | list[Organizer]):
        """Attach organizer(s) to this object.

        Parameters
        ----------
        affiliations : Organizer or list[Organizer]
            Organizer instances to associate (added to `affiliations`).
        """
        if isinstance(affiliations, Organizer):
            affiliations = [affiliations]
        for a in affiliations:
            assert self not in a.members, f"can't add {a} as this would create a circular dependence"
            self._affiliations.append(a)


# ==============================================================================
# Parent
# ==============================================================================


class Parent:
    """
    An object that can have children.

    Abstract base class.

    Implementing classes need to have an attribute or property `children`.
    """

    @property
    def children(self) -> list["Object"]:
        raise Exception("abstract property")

    @children.setter
    def children(self, children: list["Object"]):
        raise Exception("abstract property")

    def add_children(self, child: "Object"):
        """
        Add an object to this object as a child. This will link this object as
        parent in `child`.
        """
        raise Exception("Can't add children to this object")

    def remove_children(self, child: Object | list["Object"]):
        """
        Remove an object from this object as a child. This will unlink this object as
        parent in `child`.
        """
        raise Exception("Can't remove object: This object doesn't support children")

    def _children_as_set(self) -> set["Object"]:
        """Return direct children as a set (performance helper)."""
        raise Exception("abstract property")

    def _offspring_as_set(self) -> set["Object"]:
        """Return transitive closure of children (excluding self)."""
        children = self._children_as_set()
        ret = children.copy()
        for c in children:
            ret |= c._offspring_as_set()
        return ret

    @property
    def offspring(self):
        """
        Object's children, their children and so on. Not including self.
        """
        ret = list(self._offspring_as_set())
        ret.sort(key=lambda x: x.id)
        return ret

    def classes_and_ids(self) -> dict[type, set[int]]:
        """
        Get deep dictionary of types and ids of any objects contained in the
        branch (direct objects and their offspring). Each object will only added
        to the key of its direct class, not to keys of parent classes.
        """
        res = {}
        for object in self._children_as_set():
            for obj in [object, *object._offspring_as_set()]:
                cls = obj.__class__
                if cls not in res:
                    res[cls] = set()
                res[cls].add(obj.id)
        return res

    def ids_and_objects(self) -> dict[int, "Object"]:
        """Return mapping of descendant ids to object instances."""
        res = {}
        for object in self.children:
            for obj in [object, *object._offspring_as_set()]:
                if obj.id not in res:
                    res[obj.id] = obj
        return res

    def to_digraph(self, with_data: bool = True) -> nx.DiGraph:
        """
        Return an nx.DiGraph tree with self as root and all offspring
        as nodes. Edges point from parent to child. Nodes are identified by their
        IDs.

        Parameters
        ----------
        with_data : bool
            If True, the objects will receive the following data:
            - "class_name": The class name of the object
            - "object": The object instance itself
        """
        g = nx.DiGraph()
        tuples = self._to_digraph_tuples(lst=[])
        for obj, children in tuples:
            g.add_node(obj.id)
            if with_data:
                g.nodes[obj.id]["class_name"] = obj.__class__.__name__
                g.nodes[obj.id]["object"] = obj
            for child in children:
                g.add_edge(obj.id, child.id)
        return g

    def _to_digraph_tuples(self, lst: list[tuple] = []) -> list[tuple]:
        """
        Create a list of tuples (object, children sets) for all offspring including self.
        """
        tpl = (self, self._children_as_set())
        lst.append(tpl)
        for child in self._children_as_set():
            child._to_digraph_tuples(lst=lst)
        return lst

    def _get_offspring_by_type(self, types: TypeDescriptor) -> list["Object"]:
        """
        Type check will also accept subclasses. Not including self.
        """
        types = type_typetuple_or_typelist_to_typetuple(types)
        if len(types) == 1 and types[0] is Object:
            ret = list(self._offspring_as_set())
        else:
            ret = [o for o in self._offspring_as_set() if isinstance(o, types)]
        ret.sort(key=lambda x: x.id)
        return ret

    def _get_offspring_by_id(self, id: int) -> Object | None:
        """Return first offspring whose id matches `id`, if present."""
        typeerror_if_not_isinstance(id, int)
        for o in self._offspring_as_set():
            if o.id == id:
                return o

    def _get_offspring_by_name(self, name: str) -> list["Object"]:
        """Return offspring objects with matching `name` (ordered by id)."""
        typeerror_if_not_isinstance(name, str)
        ret = []
        for o in self._offspring_as_set():
            if o.name == name:
                ret.append(o)

        ret.sort(key=lambda x: x.id)
        return ret

    def find_objects(
        self,
        type: TypeDescriptor | None = None,
        name: str | list[str] | None = None,
        id: int | list[int] | None = None,
        roots: list["Object"] | None = None,
    ) -> list["Object"]:
        """
        Find all objects that satisfy the given conditions. If no conditions are
        given, all offspring objects are returned. Note that a `name` of `None`
        will not be interpreted as a condition.

        Self is not included in the search.

        Parameters
        ----------
        type : TypeDescriptor | None
            The type(s) of the objects to find. The returned objects will be of
            any of these types, or subclasses.
        name : str | list[str] | None
            The name(s) of the objects to find. None doesn't count as a
            condition.
        id : int | list[int] | None
            The id(s) of the objects to find. None doesn't count as a condition,
            obviously.
        roots : list[Object] | None
            If given, only consider offspring of these objects. The roots
            themselves won't be included in the search.
        """

        if roots is not None:
            ret = []
            for root in roots:
                ret += root.find_objects(type=type, name=name, id=id)
            return ret

        if type is not None:
            candidates = self._get_offspring_by_type(types=type)
        else:
            candidates = self.offspring

        if name is not None:
            if isinstance(name, str):
                name = [name]
            candidates = [r for r in candidates if r.name in name]

        if id is not None:
            if isinstance(id, int):
                id = [id]
            candidates = [r for r in candidates if r.id in id]

        candidates.sort(key=lambda x: x.id)
        return candidates

    def find_object(
        self,
        type: type | list[type] | tuple[type] | None = None,
        name: str | list[str] | None = None,
        id: int | list[int] | None = None,
        not_found: Literal["exception", "none"] = "exception",
        roots: list["Object"] | None = None,
    ) -> Object | None:
        """
        Find the only object that satisfies all given conditions.

        Self is not included in the search.

        Parameters
        ----------
        type : type | list[type] | tuple[type] | None
            The type(s) of the object to find. The returned object will be of
            one of these types, or a subclass.
        name : str | list[str] | None
            The name(s) of the object to find. None doesn't count as a
            condition.
        id : int | list[int] | None
            The id(s) of the object to find. None doesn't count as a condition,
            obviously.
        not_found : Literal["exception", "none"]
            What to do if no object is found.
        roots:
            If given, only consider offspring of these objects. The roots
            themselves won't be included in the search.

        Raises
        ------
        Exception
            If multiple matches are found or `not_found=='exception'` and no
            match exists.
        """

        ret = self.find_objects(type=type, name=name, id=id, roots=roots)

        if len(ret) > 1:
            raise Exception(f"more than one object found (n={len(ret)})")

        elif len(ret) == 0:
            if not_found == "exception":
                raise Exception("no object found")
            elif not_found == "none":
                return None
            else:
                raise ValueError(f"not_found must be 'exception' or 'none', got {not_found}")

        else:
            return ret[0]

    def find_objects_filtered(
        self,
        type: TypeDescriptor,
        name: str | list[str] | None = None,
        only_reachable_through: type | tuple[type] | None = None,
        omit_reachable_through: type | tuple[type] | None = None,
    ) -> list["Object"]:
        """Filtered offspring traversal.

        Only objects reachable through specific intermediate types may be
        included (whitelist) and / or paths through certain types skipped
        (blacklist).

        Parameters
        ----------
        type : type or tuple[type] or list[type]
            Type(s) of the objects you're looking for.
        name : str or list[str] or None, optional
            Name or names of the objects you're looking for.
            None doesn't count as a criterion.
        only_reachable_through : type or tuple[type] or None, optional
            Only objects reachable through at least one object of this type (or
            inherited types) will be included.
        omit_reachable_through : type or tuple[type] or None, optional
            Objects reachable through at least one object of this type (or
            inherited types) will be excluded.

        Examples
        --------
        Heat pumps located in building units::

            b: Building
            b.get_offspring_of_type_filtered(
                Heatpump,
                only_offspring_of_objects_of_type=BuildingUnit,
            )

        Heat pumps directly in a building (excluding unit traversal)::

            b: Building
            b.get_offspring_of_type_filtered(
                Heatpump,
                omit_offspring_of_objects_of_type=BuildingUnit,
            )
        """

        if only_reachable_through is not None:
            only_reachable_through = type_typetuple_or_typelist_to_typetuple(only_reachable_through)
            seeds = self.find_objects(type=only_reachable_through)
            candidates = [o for s in seeds for o in s.find_objects(type=type, name=name)]
            candidates = list(set(candidates))

        else:
            type = type_typetuple_or_typelist_to_typetuple(type)
            candidates = self.find_objects(type=type, name=name)

        if omit_reachable_through is not None:
            omit_reachable_through = type_typetuple_or_typelist_to_typetuple(omit_reachable_through)
            remove_seeds = self.find_objects(type=omit_reachable_through)
            remove_candidates = [o for s in remove_seeds for o in s.offspring]
            candidates = list(set(candidates) - set(remove_candidates))

        candidates.sort(key=lambda x: x.id)
        return candidates

    def find_objects_by_ref_geometry(
        self,
        type: TypeDescriptor,
        geometry: Polygon | Point,
        from_srid: int,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
        overlap_ratio: float = 0.25,
    ) -> list["Object"]:
        """
        Find children objects that match to the passed reference geometry.

        Parameters
        ----------
        type : Type
            Type of the objects you're looking for (must have a geometry).
        geometry : Polygon | Point
            The reference geometry.
        from_srid : int
            The SRID of the geometry's coordinates (e.g., WGS84 = 4326).
        order : Literal["lat_lon", "lon_lat"]
            Order of the coordinates passed. Default is "lat_lon".
        overlap_ratio : float
            For polygons, required overlap ratio for a match. 1 means full
            coverage. Default is 0.25.

        Returns
        -------
        list[Object]
            list of objects matching to the passed reference geometry.
        """

        objects = self.find_objects(type=type)
        idx = index.Index()
        for i, obj in enumerate(objects):
            idx.insert(i, obj.geometry.shape.bounds)

        geometry = self.project.projector.from_crs(geometry, from_srid, order=order)
        possible_matches_index = list(idx.intersection(geometry.bounds))
        possible_matches = [objects[i] for i in possible_matches_index]

        if isinstance(geometry, Point):
            match = possible_matches
            if len(match) > 1:
                warnings.warn("The passed point matches more than one geometry!")

        elif isinstance(geometry, Polygon):
            match = []
            for obj in possible_matches:
                intersection_area = geometry.intersection(obj.geometry.shape).area
                shape_area = [geometry.area, obj.geometry.shape.area]
                overlap_percentage = [intersection_area / area for area in shape_area]
                if any(overlap > overlap_ratio for overlap in overlap_percentage):
                    match.append(obj)

        return match

    def temporals_recursive(self) -> list[Temporal]:
        """
        All the Temporals contained in self and in objects that are offspring.
        """
        ret = []
        for object in [self, *self._offspring_as_set()]:
            if isinstance(object, Object):
                ret += object.temporals
        return ret


# ==============================================================================
# Object
# ==============================================================================


def _typing_str_to_type(typing_str: str) -> tuple[list[type], bool]:
    """
    Convert a typing string like 'Type', '[Type1, Type2]' or 'Type[]' to a tuple
    ( [Type], is_list )

    Examples
    --------

    - 'Type' -> ( [Type], False )
    - '[Type1, Type2]' -> ( [Type1, Type2], False )
    - 'Type[]' -> ( [Type], True )
    - '[Type1[], Type2[]]' -> ( [Type1, Type2], True )
    - '[Type1, Type2[]]' -> ValueError
    """
    assert isinstance(typing_str, str)
    if typing_str.startswith("[") and typing_str.endswith("]"):
        inner_typing_strs = typing_str[1:-1].split(", ")
        assert len(inner_typing_strs) >= 1
        inner_types_and_bools = [_typing_str_to_type(inner_typing_str) for inner_typing_str in inner_typing_strs]
        types = [t for inner in inner_types_and_bools for t in inner[0]]
        bools = [b for inner in inner_types_and_bools for b in inner[1]]
        if any(bools) and not all(bools):
            raise ValueError(f"Can't mix list and non-list types in typing string: {typing_str}")
        return types, bools[0]
    elif typing_str.endswith("[]"):
        type = get_class_by_name(typing_str[:-2])
        return [type], True
    else:
        type = get_class_by_name(typing_str)
        return [type], False


class Object(Base, Parent):
    """Core hierarchical entity.

    Supports parent/child relations, optional associations, temporal
    attribute containers and controlled graph deepcopy (up/down/sideways).
    """

    __parent: Parent | None = None

    # dict with an attribute name as key and the valid type for this
    # attribute as value. The valid is a tuple composed of two parts:
    # - the accepted types. This means that the attribute can
    #   only hold an object that is an instance of this type
    # - a bool indicating whether accepted values is a list of objects of the
    #   indicated type rather than directly the type
    _children_attributes: dict[str, tuple[list[type], bool]] = None

    # list of attribute names that are associated attributes. These attributes
    # can hold references to other objects, but these objects don't have this
    # object as their parent.
    _associated_attributes: list[str] = None

    # list of attribute names that are temporal attributes. These attributes
    # will be initialized with a Temporal instance on object creation. The
    # values in these attributes must be Temporal instances with this object
    # as their parent.
    _temporal_attributes: list[str] = None

    # list of attribute names that are temporal dict attributes. These attributes
    # will be initialized with an empty dict on object creation. The values
    # in these dicts must be Temporal instances with this object as their parent.
    _temporal_dict_attributes: list[str] = None

    # class level definitions of children/associated/temporal attributes.
    # These will be collected from all classes in the MRO on object creation.
    _CHILDREN_ATTRIBUTES = {}
    _ASSOCIATED_ATTRIBUTES = []
    _TEMPORAL_ATTRIBUTES = []
    _TEMPORAL_DICT_ATTRIBUTES = []

    def __init__(self, branch: Branch | None = None, **kwargs):
        """Create a new `Object` and optionally attach to a branch.

        Parameters
        ----------
        branch : Branch or None, optional
            Branch to add this object to (parent will be set).
        **kwargs : Any
            Forwarded to `Base` for attribute initialization.
        """
        self._children_attributes = {}
        self._associated_attributes = []
        self._temporal_attributes = []
        self._temporal_dict_attributes = []

        # compile lists of children/associated/temporal attributes from
        # all classes in the MRO:
        for cls in self.__class__.__mro__:
            if hasattr(cls, "_CHILDREN_ATTRIBUTES"):
                for ca in cls._CHILDREN_ATTRIBUTES.keys():
                    types, is_list = _typing_str_to_type(cls._CHILDREN_ATTRIBUTES[ca])
                    if ca not in self._children_attributes:
                        self._children_attributes[ca] = (types, is_list)

            if hasattr(cls, "_ASSOCIATED_ATTRIBUTES"):
                for aa in cls._ASSOCIATED_ATTRIBUTES:
                    if aa not in self._associated_attributes:
                        self._associated_attributes.append(aa)

            if hasattr(cls, "_TEMPORAL_ATTRIBUTES"):
                for ta in cls._TEMPORAL_ATTRIBUTES:
                    # assert ta in self.__class__.__dict__  # will get initialized later
                    if ta not in self._temporal_attributes:
                        self._temporal_attributes.append(ta)

            if hasattr(cls, "_TEMPORAL_DICT_ATTRIBUTES"):
                for tda in cls._TEMPORAL_DICT_ATTRIBUTES:
                    # assert tda in self.__class__.__dict__  # will get initialized later
                    if tda not in self._temporal_dict_attributes:
                        self._temporal_dict_attributes.append(tda)

        for temporal_dict_attribute in self._temporal_dict_attributes:
            setattr(self, temporal_dict_attribute, {})

        for temporal_attribute in self._temporal_attributes:
            temporal = om.Temporal()
            setattr(self, temporal_attribute, temporal)
            temporal._set_parent(self)

        if branch is not None:
            branch.add_objects(self)

        super().__init__(**kwargs)

    @property
    def parent(self) -> Parent | None:
        """Parent `Object` or `Branch` (None if unattached)."""
        return self.__parent

    @parent.setter
    def parent(self, parent: Parent | None):
        """
        Set the parent of this object. This will also add this object to the
        parent's children (if the parent is an Object) or objects (if the parent
        is a Branch).

        This will raise an exception if the type of this object is not
        unambiguous among the parent's children attributes.
        """
        typeerror_if_not_isinstance_or_none(parent, Parent)
        if parent is None:
            self.remove_from_parent()
        else:
            parent.add_children(self)

    def _set_parent(self, parent: Parent | None, error_if_not_found: bool = True):
        """
        Set the parent of this object.

        This will

        - remove the knowledge of this object in a currently present parent
        - remove the knowledge of the currently present parent
        - create the new relationship on the child side
        - NOT create the new relationship on the parent side

        Don't call this method manually. Should only be called from children
        adding methods just after the connection parent->child has been set.

        Parameters
        ----------
        error_if_not_found : bool
            If True, an exception will be raised if during uncoupling the
            current relationship, it turns out that the parent doesn't know the
            child (i.e. this object). Set to False if you dissolve the current
            relationship manually (e.g. for performance reasons)
        """
        typeerror_if_not_isinstance_or_none(parent, Parent)

        if isinstance(self.__parent, Branch):
            # when an organizer is set as a child, it needs to be removed as organizer (can't be both):
            if isinstance(self, Organizer):
                assert self in self.branch._Branch__organizers
            else:
                assert self in self.branch._Branch__objects

        previous_parent = self.__parent

        # forget the child in any currently present parent if it differs (but prevent any reverse action):
        if previous_parent is not None and previous_parent is not parent:
            if isinstance(previous_parent, Branch):
                previous_parent._remove_objects(
                    self,
                    error_if_not_found=error_if_not_found,
                    reverse=False,
                )
            elif isinstance(previous_parent, Object):
                previous_parent._remove_children(
                    self,
                    error_if_not_found=error_if_not_found,
                    reverse=False,
                )

        # set the new parent
        self.__parent = parent

        # self may contain timeseries (directly, or in offspring) that may have
        # an explicit timeindex set. When setting a parent, we need to make sure
        # that these timeindices don't contradict. By refreshing the existing
        # connections, this will be checked in the setter method:
        if previous_parent is None:
            for t in self.temporals_recursive():
                t._set_parent(t.parent)

    def remove_from_parent(self):
        """
        Remove the object from its parent and set the parent to None. If the
        parent is a branch, the object will be removed from the branch's objects.
        If the parent is an Object, the object will be removed from the branch's
        children.
        """
        self._set_parent(None)

    def add_children(
        self,
        objects: Object | list["Object"],
        error_if_already_in_list: bool = True,
        error_if_already_set: bool = False,
    ):
        """
        Add a child object to this object's children. This will also set the
        reverse relationship (`parent` attribute).

        Notes
        -----
        If the class of this object has multiple children attributes with
        overlapping types, it is not possible to unambiguously add a child. An
        exception will be raised in this case. Use a more specific method
        (e.g., `add_buildings`) to add children in this case.

        Parameters
        ----------
        objects : Object
            The child object to add.
        error_if_already_in_list : bool
            If True and the object is already contained in the list of children
            of this type, raise an error.
        error_if_already_set : bool
            If True, raise an error if the child is already set as a single
            child.
        """

        if isinstance(objects, list):
            if not all(isinstance(o, Object) for o in objects):
                raise TypeError("Can only add Object instances as children")
        elif isinstance(objects, Object):
            if not isinstance(objects, Object):
                raise TypeError("Can only add Object instances as children")
            objects = [objects]
        else:
            raise TypeError("Can only add Object instances as children")

        # check whether it's unambiguous to add this object:
        direct_types = [v[0] for v in self._children_attributes.values() if not v[1]]  # list of lists
        list_types = [v[0] for v in self._children_attributes.values() if v[1]]  # list of lists
        types = [t for sublist in direct_types + list_types for t in sublist]
        if any(issubclass(x, y) for i, x in enumerate(types) for j, y in enumerate(types) if i != j):
            msg = [
                f"Class {self.__class__.__name__} has child attributes",
                f"with overlapping types. Please use a more specific method for",
                "adding children.",
            ]
            raise Exception(" ".join(msg))

        for object in objects:

            # loop over attributes and find out where to add the object:
            for attr, types_and_bool in self._children_attributes.items():
                types, is_list = types_and_bool

                if is_list:
                    # add as list element if type matches:
                    if isinstance(object, tuple(types)):
                        if object not in getattr(self, attr):
                            getattr(self, attr).append(object)
                            object._set_parent(self)
                            return
                        elif error_if_already_in_list:
                            raise Exception(f"Can't add {object} to children of {self}: already a child")

                else:
                    # single child attribute, can only add if not already set

                    # add as single child if type matches:
                    if isinstance(object, tuple(types)):
                        if getattr(self, attr) is None:
                            setattr(self, attr, object)
                            object._set_parent(self)
                            return
                        elif error_if_already_set:
                            raise Exception(f"Can't set {object} as child of {self}: already a child")

            raise TypeError(f"Can't add {object} to children of {self}: no matching child attribute for this type")

    def remove_children(
        self,
        objects: Object | list["Object"],
    ):
        """
        Remove a child object from this object's children. This will also set
        the reverse relationship (`parent` attribute) to None.

        Parameters
        ----------
        objects : Object or list[Object]
            The child object(s) to remove.
        """
        self._remove_children(objects=objects, error_if_not_found=True, reverse=True)

    def _remove_children(
        self,
        objects: Object | list["Object"],
        error_if_not_found: bool = True,
        reverse: bool = True,
    ):
        """
        Remove a child object from this object's children. Also remove the
        reverse relationship if `reverse` is True.

        Parameters
        ----------
        objects : Object or list[Object]
            The child object(s) to remove.
        error_if_not_found : bool
            If True and the object is not contained in the list of children,
            raise an exception.
        """

        if isinstance(objects, list):
            if not all(isinstance(o, Object) for o in objects):
                raise TypeError("Can only remove Object instances as children")
        elif isinstance(objects, Object):
            if not isinstance(objects, Object):
                raise TypeError("Can only remove Object instances as children")
            objects = [objects]
        else:
            raise TypeError("Can only remove Object instances as children")

        for object in objects:
            found = False
            for attr in self._children_attributes.keys():

                if isinstance(getattr(self, attr), list):
                    if object in getattr(self, attr):
                        getattr(self, attr).remove(object)
                        if reverse:
                            object._set_parent(None, error_if_not_found=error_if_not_found)
                        found = True
                        break

                else:
                    # single child attribute, can only remove if already set:
                    if getattr(self, attr) is object:
                        setattr(self, attr, None)
                        if reverse:
                            object._set_parent(None, error_if_not_found=error_if_not_found)
                        found = True
                        break

            if not found and error_if_not_found:
                raise Exception(f"Can't remove {object} from children of {self}: not a child")

    @property
    def ancestors(self):
        """
        All parents, their parents and so on. Not including self.
        """
        ret = []
        if isinstance(self.__parent, Object):
            ret.append(self.parent)
            ret += self.parent.ancestors
        return ret

    def get_ancestors_of_type(self, type: TypeDescriptor) -> list["Object"]:
        """
        Return ancestors that are instances of `types`. This will not include
        the object itself.

        Parameters
        ----------
        types : Type or tuple/list of Type
            Accepted ancestor types.
        """
        types = type_typetuple_or_typelist_to_typetuple(type)
        return [a for a in self.ancestors if isinstance(a, types)]

    def get_closest_ancestor_of_type(
        self,
        type: TypeDescriptor,
        not_found: Literal["exception", "none"] = "none",
    ) -> Object | None:
        types = type_typetuple_or_typelist_to_typetuple(type)
        ret = next((a for a in self.ancestors if isinstance(a, types)), None)
        if ret is None and not_found == "exception":
            raise Exception(f"Object {self} doesn't have an ancestor of indicated type")
        else:
            return ret

    @property
    def root(self) -> "Object":
        """
        The "root" object (upmost ancestor) which will have either a `Branch`
        or `None` as parent. This can also be the object itself.
        """
        if self.__parent is None:
            return self
        if isinstance(self.__parent, Branch):
            return self
        if isinstance(self.__parent, Object):
            return self.__parent.root

    @property
    def project(self) -> Project | None:
        branch = self.branch
        if branch is not None:
            return self.branch.project

    @property
    def branch(self) -> Branch | None:
        if self.__parent is None:
            return None
        if isinstance(self.__parent, Branch):
            return self.__parent
        if isinstance(self.__parent, Object):
            return self.__parent.branch

    @property
    def year(self) -> int | None:
        if self.branch is not None:
            return self.branch.year

    @property
    def timeindex(self) -> pd.DatetimeIndex | None:
        """
        Return a copy of the Object's validity timeindex as set in the branch,
        if present.
        """
        if self.branch is not None:
            return self.branch.timeindex

    @property
    def affiliations_recursive(self) -> list["Organizer"]:
        """
        first and higher order affiliations (affiliations of affiliations),
        and first and higher order affiliations of ancestors
        """
        ret = super().affiliations_recursive
        for ancestor in self.ancestors:
            for aff in ancestor.affiliations_recursive:
                if aff not in ret:
                    ret.append(aff)
        return ret

    @property
    def reference(self):
        """Object referenced in another branch (if any).

        Returns
        -------
        Object or None
            The reference target of this object in the source branch.
        """
        if self.branch is None:
            return None
        return self.branch.mapping.get(self, None)

    def reference_chain(self) -> list["Object"]:
        """
        Return the reference of the object, that object's reference, and so on.
        None won't be contained.
        """
        ret = []
        if isinstance(self.reference, Object):
            ret.append(self.reference)
            ret += self.reference.reference_chain
        return ret

    def _children_as_set(self) -> set["Object"]:
        """
        Return the set of all children of this Object. Provided for performance
        reasons.
        """

        def collect(x) -> set[Object]:
            ret = set()
            if isinstance(x, Object):
                assert x.parent is self
                ret.add(x)
            elif isinstance(x, list):
                ret |= set([a for b in x for a in collect(b)])
            elif isinstance(x, dict):
                ret |= collect(x for x in x for x in x.values())
            return ret

        vs = set()
        for a in self._children_attributes.keys():
            assert hasattr(self, a)
            vs |= collect(getattr(self, a))
        return vs

    # implementation of abstract method in <Parent>
    @property
    def children(self):
        """List of direct child objects (hierarchical relation)."""
        ret = list(self._children_as_set())
        ret.sort(key=lambda x: x.id)
        return ret

    @property
    def associated(self):
        """Non-child objects referenced from this object (associations)."""

        def collect(x):
            ret = []
            if isinstance(x, Object):
                assert x.parent is not self
                ret.append(x)
            elif isinstance(x, list):
                ret += [a for b in x for a in collect(b)]
            elif isinstance(x, dict):
                ret += [collect(x for x in x for x in x.values())]
            return ret

        vs = []
        for a in self._associated_attributes:
            assert hasattr(self, a)
            vs += collect(getattr(self, a))
        vs = list(set(vs))
        return vs

    def get_closest_ancestor_geometry(self, stop_at_none: bool = False) -> Geometry | None:
        """
        Get the geometry of the closest ancestor, or self, that has an
        attribute "geometry" of type `Geometry`.

        Parameters
        ----------
        stop_at_none : bool
            If True, None will be returned if the closest ancestor (including
            self) has None as `geometry`. Otherwise, search continues with
            further ancestors.

        Remarks
        -------
        This function also finds the Geometry of Buildings and Structures
        (which aren't GeometryObjects but have an attribute `geometry`).
        """
        ancestors = [self, *self.ancestors]
        for ancestor in ancestors:
            if hasattr(ancestor, "geometry"):
                if isinstance(ancestor.geometry, om.Geometry) or stop_at_none:
                    return ancestor.geometry

    def _collect_ids(self, down: bool, up: bool, sideways: bool, seen_ids: set[int]):
        """
        Collect the ids of all objects that are either hierarchically related
        to this object (ancestors and/or offspring) or associated objects,
        depending on the parameters. Used to determine which objects need to
        be copied in the deepcopy method.
        """
        seen_ids.add(id(self))
        copy_ids = set([id(self)])

        if up:
            if isinstance(self.__parent, Object):
                if id(self.__parent) not in seen_ids:
                    copy_ids |= self.__parent._collect_ids(
                        down=down,
                        sideways=sideways,
                        up=up,
                        seen_ids=seen_ids,
                    )

        if down:
            for children_attribute in self._children_attributes.keys():
                child = getattr(self, children_attribute)
                if id(child) not in seen_ids:
                    seen_ids.add(id(child))
                    if isinstance(child, Object):
                        copy_ids |= child._collect_ids(
                            down=down,
                            up=up,
                            sideways=sideways,
                            seen_ids=seen_ids,
                        )
                    elif isinstance(child, list):
                        for element in child:
                            if id(element) not in seen_ids:
                                seen_ids.add(id(element))
                                if isinstance(element, Object):
                                    copy_ids |= element._collect_ids(
                                        down=down,
                                        up=up,
                                        sideways=sideways,
                                        seen_ids=seen_ids,
                                    )
                    elif child is None:
                        ...
                    else:
                        raise ValueError

        if sideways:
            for associated_attribute in self._associated_attributes:
                associated = getattr(self, associated_attribute)
                if id(associated) not in seen_ids:
                    seen_ids.add(id(associated))
                    if isinstance(associated, Object):
                        copy_ids |= associated._collect_ids(
                            down=down,
                            up=up,
                            sideways=sideways,
                            seen_ids=seen_ids,
                        )
                    elif isinstance(associated, list):
                        for element in associated:
                            if id(element) not in seen_ids:
                                seen_ids.add(id(element))
                                if isinstance(element, Object):
                                    copy_ids |= element._collect_ids(
                                        down=down,
                                        up=up,
                                        sideways=sideways,
                                        seen_ids=seen_ids,
                                    )
                    elif associated is None:
                        ...
                    else:
                        raise ValueError
        return copy_ids

    def deepcopy(self, down: bool, up: bool, sideways: bool) -> "Object":
        """
        Create a deep copy of the Object. Attributes that are not `Object`s
        will be copied in any case (e.g. int, float, pd.Series, ...).

        The returned object will receive a new `id`.

        Parameters
        ----------
        down : bool
            If True, all offspring of this object will also be copied
            (children and their children etc.).
        up : bool
            If True, all parents of this object will also be copied, except
            for the branch. In combination with `down==True`, this will copy
            all offspring of this object's root object. If False, the parent
            of the copy will be None.
        sideways : bool
            If True, all associated objects (not parent or children) will
            also be copied (e.g. the attachment of a network). If `down` and/or
            `up` are also True, the strategy will also be applied to all such
            associated objects.

        Remarks
        -------
        Attributes with `Object`s set that won't get copied according to
        `down`, `up` and `sideways` will be set to None.
        """
        seen_ids = set()
        copy_ids = self._collect_ids(down=down, up=up, sideways=sideways, seen_ids=seen_ids)
        memo = {"DEEPCOPY_copy_ids": copy_ids}
        return copy.deepcopy(self, memo=memo)

    def __deepcopy__(self, memo: dict[int, Any]) -> "Object":
        copy_ids = memo.get("DEEPCOPY_copy_ids", None)
        if copy_ids is None:  # = deepcopy has been called directly
            msg = (
                "Deepcopy of an Object is ambiguous and can not be called ",
                "by copy.deepcopy(<Object>). Use <Object>.deepcopy() ",
                "specifying further parameters.",
            )
            raise Exception("".join(msg))

        cls = self.__class__
        res = cls.__new__(cls)
        memo[id(self)] = res

        for attr, orig_value in self.__dict__.items():

            if attr == "_Identified__id":
                res.__dict__[attr] = id_authority()

            elif attr == "_affiliations":
                res.__dict__[attr] = []

            elif id(orig_value) in memo:
                res.__dict__[attr] = memo[id(orig_value)]

            elif attr in self._children_attributes.keys() or attr in self._associated_attributes:
                if orig_value is not None and id(orig_value) in copy_ids:
                    res.__dict__[attr] = copy.deepcopy(orig_value, memo)
                else:
                    if isinstance(orig_value, list):
                        lst = []
                        for v_sub in orig_value:
                            r = copy.deepcopy(v_sub, memo)
                            if r is not None:
                                lst.append(r)
                        res.__dict__[attr] = lst
                    else:
                        res.__dict__[attr] = None

            elif attr == "_Object__parent":
                if id(orig_value) in copy_ids:
                    res.__dict__[attr] = copy.deepcopy(orig_value, memo)
                else:
                    res.__dict__[attr] = None

            elif attr in self._temporal_attributes:
                # same as isinstance(v, Temporal). Temporals can't be deepcopied
                # directly because they have an attribute "_parent" with an entity
                # of type <Object> set. Instead, we need to call the Temporal's
                # copy-method and set the parent manually from the memo:
                assert isinstance(orig_value, om.Temporal)
                copied_temporal = orig_value.copy()
                new_parent = memo[id(orig_value.parent)]
                new_parent.set_temporal(attr=attr, x=copied_temporal)  # will set parent in temporal

            elif attr in self._temporal_dict_attributes:
                assert isinstance(orig_value, dict)
                if orig_value:
                    assert all(isinstance(x, om.Temporal) for x in orig_value.values())
                    for temporal_dict_key, temporal in orig_value.items():
                        copied_temporal = temporal.copy()
                        new_parent = memo[id(temporal.parent)]
                        new_parent.set_temporal(attr=attr, x=copied_temporal, key=temporal_dict_key)
                else:
                    res.__dict__[attr] = {}

            else:  # = plain attribute
                res.__dict__[attr] = copy.deepcopy(orig_value, memo)

        return res

    # methods for temporals
    # --------------------------------------------------------------------------

    @property
    def temporals(self) -> list["Temporal"]:
        """List of all temporal objects attached to this object."""
        temporals = []
        for a in self._temporal_attributes:
            if hasattr(self, a):
                x = getattr(self, a)
                temporals.append(x)
        for a in self._temporal_dict_attributes:
            if hasattr(self, a):
                d = getattr(self, a)
                if d is not None:
                    # only known case when d is None: during __new__ in deepcopy of an object
                    # before any dict_temporal_attribute has been created
                    for k, v in d.items():
                        temporals.append(v)
        return temporals

    def _set_simple_temporal(self, attr: str, temporal: "Temporal"):
        """
        Internal setter for simple temporal attributes. Will establish the
        parent-child relationship between self and the temporal in both
        directions.
        """
        if attr not in self._temporal_attributes:
            raise ValueError(f"Object of class {self.__class__.__name__} doesn't have a temporal attribute '{attr}'")

        # get what is currently stored in the attribute:
        current_value = getattr(self, attr)
        assert (
            isinstance(current_value, om.Temporal)
            or current_value is None  # None should only occur when initing in deepcopy
        )

        # clear current connections:
        if temporal is not current_value:
            # remove the link betwen the current parent and the temporal:
            if temporal is not None and temporal.has_parent:
                temporal.parent.remove_temporal(temporal=temporal)
            # remove the link between self and the current temporal:
            if current_value is not None:
                setattr(self, attr, None)
                current_value._set_parent(None)

        # create new link:
        setattr(self, attr, temporal)
        temporal._set_parent(self)
        temporal.set_swap_mode_from_branch()

    def _set_dict_temporal(self, attr: str, key: Any, temporal: Temporal | None):
        """
        Internal setter for dict-based temporal collections. Will establish the
        parent-child relationship between self and the temporal in both
        directions.
        """
        if attr not in self._temporal_dict_attributes:
            msg = f"Object of class {self.__class__.__name__} doesn't have a temporal dict attribute '{attr}'"
            raise ValueError(msg)

        # get the current dictionary or create a new one
        current_dict = getattr(self, attr)
        if current_dict is None:  # may occur when initing in deepcopy
            current_dict = {}
            setattr(self, attr, current_dict)
        assert isinstance(current_dict, dict)

        # clear current connections:
        if key not in current_dict or temporal is not current_dict[key]:
            # remove the link betwen the current parent and the temporal:
            if temporal is not None and temporal.has_parent:
                temporal.parent.remove_temporal(temporal=temporal)
            # remove the link between self and the current temporal:
            if key in current_dict:
                current_temporal = current_dict[key]
                current_dict[key] = None
                current_temporal._set_parent(None)

        # if None, forget the key:
        if temporal is None:
            current_dict.pop(key, None)
        else:
            current_dict[key] = temporal
            temporal._set_parent(self)
            temporal.set_swap_mode_from_branch()

    def set_temporal(
        self,
        attr: str,
        x: Temporal | Number | pd.Series | None,
        key: Any = None,
        error_if_values_below: float = None,
        error_if_values_above: float = None,
    ):
        """
        Set a temporal. If `x` is a Temporal, it will be copied. If `x` is a
        Number or pd.Series, a new Temporal will be created.

        Parameters
        ----------
        attr : str
            Name of the temporal attribute.
        x : Temporal | Number | pd.Series | None
            Value to set as temporal.
        key : Any, optional
            Key for temporal dict attributes (default: None).
        error_if_values_below : float, optional
            Raise error if temporal values are below this threshold (default:
            None).
        error_if_values_above : float, optional
            Raise error if temporal values are above this threshold (default:
            None).
        """

        def make_temporal(x) -> "Temporal":
            if isinstance(x, om.Temporal):
                temporal = x.copy()
            elif isinstance(x, Number):
                temporal = om.Temporal(fix=float(x))
            elif isinstance(x, pd.Series):
                if isinstance(x.index, pd.DatetimeIndex):
                    temporal = om.Temporal(timeseries=x)
                else:
                    temporal = om.Temporal(series=x)
            elif x is None:
                temporal = om.Temporal()
            else:
                raise TypeError()
            return temporal

        def assert_in_bounds(temporal):
            if error_if_values_below is not None:
                temporal: Temporal
                if temporal.is_temporal and temporal.series.min() < error_if_values_below:
                    raise ValueError(f"Value below acceptable minimum ({error_if_values_below})")
            if error_if_values_above is not None:
                if temporal.is_temporal and temporal.series.max() > error_if_values_above:
                    raise ValueError(f"Value above acceptable minimum ({error_if_values_above})")

        if key is None:
            temporal = make_temporal(x)
            assert_in_bounds(temporal)
            self._set_simple_temporal(attr=attr, temporal=temporal)
        else:
            if x is not None:
                temporal = make_temporal(x)
                assert_in_bounds(temporal)
            else:
                temporal = None  # will remove the key from dict
            self._set_dict_temporal(attr=attr, key=key, temporal=temporal)

    def remove_temporal(self, attr: str = None, key: str = None, temporal: "Temporal" = None):
        """
        Remove the temporal that is currently set as an attribute, either
        described by an attribute and possibly a key, or by the temporal itself.

        If the temporal is currently in a dict attribute, this method will set
        the temporal's parent to None and remove the key from the dict. If the
        temporal is currently a direct attribute, this method will set the
        temporal's parent to None and replace it with a newly created Temporal.
        """
        # get the temporal and the attribute:
        if temporal is not None:
            if attr is not None or key is not None:
                raise Exception()
            for a in self._temporal_attributes:
                if getattr(self, a) is temporal:
                    attr = a
                    break
            for a in self._temporal_dict_attributes:
                for k, t in a.items():
                    if t is temporal:
                        attr = a
                        key = k
                        break

            # we must have an attribute by now:
            if attr is None:
                raise Exception()

        elif attr is not None:
            if key is not None:
                if attr not in self._temporal_dict_attributes:
                    raise Exception()
                if key not in getattr(self, attr):
                    raise Exception()
                temporal = getattr(self, attr)[key]

            else:
                if attr not in self._temporal_attributes:
                    raise Exception()
                temporal = getattr(self, attr)

        if key is None:  # = simple attribute
            setattr(self, attr, None)
            temporal._set_parent(None)
            new_temporal = om.Temporal()
            setattr(self, attr, new_temporal)
            new_temporal._set_parent(self)

        else:
            getattr(self, attr).pop(key)
            temporal._set_parent(None)

    def get_dict_temporal(self, attr: str, key: Any, add_empty_if_missing: bool = True):
        assert attr in self._temporal_dict_attributes
        d = getattr(self, attr)
        if key in d:
            return d[key]
        elif add_empty_if_missing:
            temporal = om.Temporal()
            self._set_dict_temporal(attr=attr, key=key, temporal=temporal)
            return temporal


class GeometryObject(Object):
    """`Object` extended with a `Geometry` attribute (may be None)."""

    geometry: "Geometry" = None

    def __init__(self, geometry: "Geometry" = None, **kwargs):
        typeerror_if_not_isinstance_or_none(geometry, om.Geometry)
        self.geometry = geometry
        super().__init__(**kwargs)


class Organizer(Object):
    """
    An Object that is rather an organizational idea than a physical entity,
    e.g. a group of buildings or a clustering

    Attributes
    ----------
    members : list[Object]
        Objects that are linked to this organizer. These Objects will
        have the Organizer in `affiliations`.
    """

    _MEMBER_ATTRIBUTES = []
    _member_attributes: list[str] = None

    def __init__(self, branch: Branch | None = None, **kwargs):
        self._member_attributes = []
        super().__init__(**kwargs)  # don't pass branch here as that could add the organizer to branch.objects
        for cls in self.__class__.__mro__:
            if hasattr(cls, "_MEMBER_ATTRIBUTES"):
                for ma in cls._MEMBER_ATTRIBUTES:
                    if ma not in self._member_attributes:
                        self._member_attributes.append(ma)
        if branch is not None:
            branch.add_organizers(self)

    @property
    def members(self) -> list[Base]:
        """Direct member objects associated with this organizer."""

        def collect(x):
            ret = []
            if isinstance(x, Object):
                # assert self in x.affiliations
                ret.append(x)
            elif isinstance(x, list):
                ret += [a for b in x for a in collect(b)]
            elif isinstance(x, dict):
                ret += [collect(x for x in x for x in x.values())]
            return ret

        vs = []
        for a in self._member_attributes:
            if hasattr(self, a):
                vs += collect(getattr(self, a))
        vs = list(set(vs))
        return vs

    @property
    def members_all(self) -> list[Object]:
        """All members including nested organizer members (recursive)."""
        ret = []
        for m in self.members:
            ret.append(m)
            if isinstance(m, Organizer):
                ret += m.offspring
        return list(set(ret))

    @property
    def dependents(self) -> list[Object]:
        """Members, their members and hierarchical offspring recursively."""
        ret = []
        ret += self.members
        ret += self.children
        for r in ret:
            ret += r.children
            if isinstance(r, Organizer):
                ret += r.dependents
        return list(set(ret))

    def get_dependents_of_type(self, type_: TypeDescriptor) -> list[Object]:
        """Filter dependents by type(s)."""
        if isinstance(type_, list):
            type_ = tuple(type_)
        return [d for d in self.dependents if isinstance(d, type_)]


# ==============================================================================
# ProjectOrBranch
# ==============================================================================


class ProjectOrBranch:
    """
    A mixin class for classes Project and Branch.

    # TODO Find better name later.
    """

    _temporal_manager: "TemporalManager" = None

    def __init__(self, temporal_manager: TemporalManager | None = None, **kwargs):
        super().__init__(**kwargs)
        typeerror_if_not_isinstance_or_none(temporal_manager, oio.TemporalManager)
        if temporal_manager is not None and temporal_manager.target is not None:
            raise Exception("Can't set temporal manager: The temporal manager already has a target branch or project")
        self._temporal_manager = temporal_manager
        if temporal_manager is not None:
            temporal_manager._target = self

    @property
    def temporal_manager(self) -> TemporalManager | None:
        """
        The temporal manager of this object if present, or else of a parenting
        object if present.
        """
        if self._temporal_manager is not None:
            return self._temporal_manager
        if hasattr(self, "project") and self.project is not None:  # TODO knowledge of subclasses, find better solution
            return self.project._temporal_manager

    @temporal_manager.setter
    def temporal_manager(self, temporal_manager: TemporalManager | None):
        typeerror_if_not_isinstance_or_none(temporal_manager, oio.TemporalManager)
        if temporal_manager is not None and temporal_manager.target is not None:
            raise Exception("Can't set temporal manager: The temporal manager already has a target branch or project")
        if self._temporal_manager is not None:
            self._temporal_manager._target = None
        self._temporal_manager = temporal_manager
        if temporal_manager is not None:
            temporal_manager._target = self


# ==============================================================================
# Branch
# ==============================================================================


class Branch(Parent, ProjectOrBranch, Base):
    """
    Scenario container holding objects for a single year.

    Can reference objects from another branch (bifurcation) and maintains own
    weather/financing/holiday context plus organizers.
    """

    # the timeindex providing the temporal validity of the branch. Created from
    # the passed year
    __timeindex: pd.DatetimeIndex = None

    __project: "Project" = None

    # Direct children of the branch. These children will have set this Branch as
    # parent:
    __objects: set[Object] = None

    __reference_branch: Branch | None = None

    # key = object (in this branch), value = reference (object in another branch).
    # main branch will have None as value everywhere:
    __mapping: dict[Object, Object] = None

    __organizers: list[Organizer] = None

    __weather: "om.Weather" = None

    __financing: "om.Financing" = None

    holidays: list[datetime] = None

    # Can be used for custom attributes that describe the branch, e.g.
    # `{"weather": "medium", "costs": "high}`:
    description: dict = None

    history: CallTracker = None

    def __init__(
        self,
        year: int | None = None,
        name: str | None = None,
        description: dict | None = None,
        weather: Weather | None = None,
        financing: Financing | None = None,
        temporal_manager: TemporalManager | None = None,
        project: Project | None = None,
    ) -> None:
        """
        Initialize a branch instance with temporal, financial, and weather context.

        Parameters
        ----------
        year : int
            Calendar year associated with the branch. Must not be None; a
            ValueError is raised otherwise.
        name : str, optional
            Human-readable identifier for the branch.
        description : dict, optional
            Free-form metadata describing the branch. If None, an empty
            dictionary is assigned. The provided dictionary will be copied.
        weather : Weather, optional
            Weather configuration object associated with this branch.
        financing : Financing, optional
            Financing configuration object associated with this branch.
        temporal_manager : TemporalManager, optional
            External temporal manager coordinating swap mode of temporals.
        project : Project, optional
            Project to which this branch will be attached. If provided, the
            branch registers itself via project.add_branches(self).
        """

        self.__organizers = []
        self.__objects = set()
        self.__reference_branch = None
        self.__mapping = {}
        self.holidays = []
        self.history = CallTracker()

        typeerror_if_not_isinstance_or_none(name, str)
        typeerror_if_not_isinstance_or_none(description, dict)

        super().__init__(
            name=name,
            temporal_manager=temporal_manager,
        )

        if project is not None:
            project.add_branches(self)

        if year is None:
            raise ValueError("Cannot create branch: Year must be specified")
        self.year = year  # call setter
        self.weather = weather  # call setter
        self.financing = financing  # call setter

        # assert that description is a shallow dictionary of strings:
        if description is None:
            self.description = {}
        else:
            if not all(isinstance(k, str) for k in description.keys()):
                raise TypeError("Description must be a dictionary of strings as keys.")
            self.description = description.copy()

    def __del__(self):
        if self.project is not None and self.project.file_adapter is not None:
            self.project.file_adapter.close_hdf_file_for_branch(self)

    def __repr__(self):
        if self.name is not None:
            return f"{self.__class__.__name__}(id={self.id}, n_objects={len(self._Branch__objects)}, year={self.year}, name='{self.name}')"
        else:
            return f"{self.__class__.__name__}(id={self.id}, n_objects={len(self._Branch__objects)}, year={self.year})"

    def __eq__(self, other) -> bool:
        return id(self) == id(other)

    def __hash__(self):
        return id(self)

    @property
    def timeindex(self) -> pd.DatetimeIndex | None:
        """
        Return a copy of the Branch's validity timeindex, if present.
        """
        return self.__timeindex.copy()

    @property
    def year(self) -> int | None:
        if self.__timeindex is not None:
            return self.__timeindex[0].year

    @year.setter
    def year(self, year: int | None):
        typeerror_if_not_isinstance(year, int)
        dti = pd.date_range(
            start=pd.Timestamp(year=year, month=1, day=1),
            end=pd.Timestamp(year=year + 1, month=1, day=1),
            inclusive="left",
            freq="h",
        )
        self.__timeindex = dti

    @property
    def validity(self):
        raise Exception("removed. Use `year` or `timeindex`.")

    @validity.setter
    def validity(self, x):
        raise Exception("removed. Use `year` or `timeindex`.")

    @property
    def project(self) -> Project | None:
        """
        returning the corresponding `Project` object to this `Branch`
        """
        return self.__project

    def _set_project(self, project: "Project"):
        """
        This should only ever be called by `Project` when adding a new `Branch`.
        Don't use it in any other case.
        """
        assert isinstance(project, Project) or project is None
        assert (
            self.__project is None or self.__project is project or project is None
        )  # could lead to problems otherwise?
        self.__project = project

    @property
    def mapping(self) -> dict[Object, Object]:
        """
        list of tuples of the complete mapping for the branch.
        First value represents the branch `Object`, second value represents the
        reference `Object`.
        """
        return self.__mapping.copy()

    @mapping.setter
    def mapping(self, mapping: dict[Object, Object]):
        assert isinstance(mapping, dict)
        assert all(o in self.__objects for o in mapping.keys())

        if len(mapping) == 0:
            self.__reference_branch = None

        else:
            reference_branches = [r.branch for r in mapping.values()]
            reference_branches = list(set(reference_branches))
            if len(reference_branches) > 1:
                raise ValueError("All reference objects in mapping must be from the same branch")

            reference_branch = reference_branches[0]
            assert isinstance(reference_branch, Branch)
            assert reference_branch is not self
            self.__reference_branch = reference_branch

        self.__mapping = mapping.copy()

    def _deepcopy_objects(self) -> dict[Object, Object]:
        def _collect_ids():
            seen_ids = set()
            copy_ids = set()
            for o in self.objects:
                copy_ids |= o._collect_ids(down=True, up=True, sideways=True, seen_ids=seen_ids)
            return copy_ids

        copy_ids = _collect_ids()
        memo = {"DEEPCOPY_copy_ids": copy_ids}
        mapping = {}
        for o in tqdm(self.objects, "creating branch"):
            o2 = copy.deepcopy(o, memo)
            mapping[o2] = o
        return mapping

    @property
    def reference_branch(self) -> Branch | None:
        """
        The branch that objects in this branch reference. If this branch was
        created by bifurcation, it's the original branch.
        """
        return self.__reference_branch

    def _children_as_set(self) -> set[Object]:
        return self.__objects

    @property
    def children(self) -> list[Object]:
        """
        list of all `Object`s inside the `Branch` (without reference). Alias for
        `objects`.
        """
        ret = list(self.__objects)
        ret.sort(key=lambda x: x.id)
        return ret

    @property
    def objects(self) -> list[Object]:
        """
        list of all `Object`s inside the `Branch` (without reference).  Alias
        for `children`.
        """
        ret = list(self.__objects)
        ret.sort(key=lambda x: x.id)
        return ret

    def add_children(self, objects: Object | list[Object]):
        """Alias for `add_objects`."""
        self.add_objects(objects)

    def remove_children(self, objects: Object | list[Object]):
        """Alias for `remove_objects`."""
        self.remove_objects(objects)

    def add_objects(self, objects: Object | list[Object]):
        """Add one or multiple objects to the branch.

        Parameters
        ----------
        objects : Object or list[Object]
            Objects whose parent is None or another branch.
        """
        objects = none_object_or_list_to_list(objects)

        for object in objects:
            if not isinstance(object, Object):
                raise TypeError(f"Object to add must be an instance of Object, not {type(object)}")
            assert not isinstance(object, Organizer)
            assert object.parent is None or isinstance(object.parent, Branch)
            if isinstance(object.parent, Branch):
                object.parent.remove_objects(object)
            if object in self.__objects:
                raise ValueError(f"Object already in branch: {object}")
            else:
                self.__objects.add(object)
                object._set_parent(self)

            # apply the swap settings to all temporals contained in the object
            # if we can find a temporal manager:
            temporal_manager = object.branch.temporal_manager
            if temporal_manager is not None:
                temporal_manager.apply_settings_for_object(object)

    def remove_objects(
        self,
        objects: Object | list["Object"],
    ):
        """
        Remove one or multiple objects from the branch and set their parent to
        None. This will work for objects as well as organizers.
        """
        self._remove_objects(
            objects=objects,
            error_if_not_found=True,
            reverse=True,
        )

    def _remove_objects(
        self,
        objects: Object | list[Object],
        error_if_not_found: bool = True,
        reverse: bool = True,
    ):
        """
        Remove one or multiple objects from the branch and set their parent to
        None. This will work for objects as well as organizers.
        """
        objects = none_object_or_list_to_list(objects)

        organizers = [o for o in objects if isinstance(o, Organizer)]
        objects = [o for o in objects if not isinstance(o, Organizer)]

        if error_if_not_found:
            if not set(objects).issubset(self.__objects):
                raise ValueError("Cannot remove objects: Not all objects are in the branch")
            if not set(organizers).issubset(self.__organizers):
                raise ValueError("Cannot remove organizers: Not all organizers are in the branch")

        # resolve reverse link:
        if reverse:
            for object in objects:
                object._set_parent(None)
            for organizer in organizers:
                organizer._set_parent(None)

        # resolve forward link:
        self.__objects -= set(objects)
        self.__organizers = [o for o in self.__organizers if o not in organizers]

        # clear from mapping:
        for object in objects:
            self.__mapping.pop(object, None)

    # Methods for cross-branch referencing
    # --------------------------------------------------------------------------

    @property
    def references(self) -> list[Object]:
        """List of reference target objects (values of mapping)."""
        return list(self.__mapping.values())

    @classmethod
    def get_reference(cls, object: Object) -> Object | None:
        """
        Return the object in another branch that `object` (from this branch)
        refers to. Will return None if no such object exists.
        """
        return object.branch.mapping.get(object, None)

    def get_object_by_reference(self, reference: Object) -> Object | None:
        """
        Return the objects in this branch that refer to `reference` (in
        another branch). Will return None if no such object exists.
        """
        return next((o for o, r in self.__mapping.items() if r is reference), None)

    @classmethod
    def get_chained_reference(cls, object: Object, target_branch: "Branch" = None) -> Object | None:
        """
        Return the object in `target_branch` that `object` (from this branch)
        refers to, possibly by chained reference across multiple branches. Will
        return None if no such object exists.
        """
        obj = object
        while True:
            if obj.branch is target_branch:
                return obj
            obj2 = obj.branch.get_reference(obj)
            if obj2 is None:  # reached base branch, maybe root
                return obj
            obj = obj2

    def get_object_by_chained_reference(self, reference: Object) -> Object | None:
        """
        Return the object in this branch that refers to `reference` (in
        another branch), possibly by chained reference across multpile branches.
        Will return None if no such object exists.
        """
        other_objs_caller_objs = {
            own_obj: own_obj for own_obj, other_obj in self.__mapping.items() if other_obj is not None
        }
        branches = set([self])

        while len(branches):
            branch = branches.pop()
            branches = set()
            for branch_obj, ref_obj in branch.mapping.items():
                # ref_obj.branch might be None. This means that the object has been deleted in
                # the referred (base) branch but still exists in the bifurcated branch:
                if ref_obj is not None and ref_obj.branch is not None:
                    branches.add(ref_obj.branch)
                    if ref_obj is not None:
                        if branch_obj in other_objs_caller_objs:
                            other_objs_caller_objs[ref_obj] = other_objs_caller_objs[branch_obj]
                        if ref_obj is reference:
                            branches = []  # to break outer loop
                            break
            assert len(branches) <= 1

        return other_objs_caller_objs.get(reference, None)

    # Methods for organizers
    # --------------------------------------------------------------------------

    @property
    def organizers(self) -> list[Organizer]:
        """
        list of all `Organizer`s inside the `Branch` (without reference)
        """
        return self.__organizers.copy()

    def add_organizers(self, organizers: Organizer | list[Organizer]):
        if not isinstance(organizers, (list, tuple)):
            organizers = [organizers]

        for organizer in organizers:
            assert isinstance(organizer, Organizer)
            assert organizer.branch is None
            if organizer not in self.__organizers:
                organizer._set_parent(self)
                self.__organizers.append(organizer)

    def remove_organizers(self, organizers: Organizer | list[Organizer]):
        if not isinstance(organizers, (list, tuple)):
            organizers = [organizers]

        for organizer in organizers:
            if organizer in self.__organizers:
                self.__organizers.remove(organizer)
                organizer._set_parent(None)

    def get_organizers_of_type(self, types=Organizer) -> list[Organizer]:
        """Return organizers that are instances of `types`."""
        return [o for o in self.organizers if isinstance(o, types)]

    # Methods for additional branch attributes
    # --------------------------------------------------------------------------

    @property
    def weather(self) -> Weather | None:
        """Branch level `Weather` instance (if any)."""
        return self.__weather

    @weather.setter
    def weather(self, weather: Weather | None):
        typeerror_if_not_isinstance_or_none(weather, om.Weather)
        assert weather is None or weather.parent is None
        self.__weather = weather
        if weather is not None:
            weather._set_parent(self)

    @property
    def financing(self) -> Financing | None:
        """Branch level `Financing` instance (if any)."""
        return self.__financing

    @financing.setter
    def financing(self, financing: Financing | None):
        typeerror_if_not_isinstance_or_none(financing, om.Financing)
        self.__financing = financing


# ==============================================================================
# Project
# ==============================================================================


class Project(ProjectOrBranch):
    """Top-level container aggregating branches and spatial context.

    Provides coordinate projection, optional geographic boundary and
    manages a main branch along with cross-branch operations.
    """

    id_authority: IdAuthority | None = None
    __name: str | None
    __projector: Projector
    __branches: list[Branch]

    # boundary in WGS84, order = latitude, longitude:
    __boundary_wgs84: Polygon

    # boundary in local CRS (order Northings, Easting):
    __boundary_local: Polygon

    # the main branch of the project that is also contained in `__branches`:
    __main_branch: Branch | None = None

    # the file adapter that can be used to store pickles on the hard drive and
    # to swap timeseries:
    _file_adapter: FileAdapter | None = None

    def __init__(
        self,
        name: str | None = None,
        boundary_wgs84: Polygon | None = None,
        boundary_local: Polygon | None = None,
        projector: Projector | None = None,
        order: Literal["lat_lon", "lon_lat"] = "lat_lon",
        branches: Branch | list[Branch] | None = None,
        main_branch: Branch | None = None,
        file_adapter: FileAdapter | None = None,
        temporal_manager: TemporalManager | None = None,
    ):
        """
        Initialize a Project instance with optional spatial boundary, coordinate
        projector, branches, and file adapter.

        Parameters
        ----------
        name : str | None, Optional
            Optional name of the project.
        boundary_wgs84 : Polygon | None, Optional
            The project boundary in EPSG:4326, coordinate order according to
            `order`. The boundary is an optional attribute of a project that can
            be used for plotting, object detection etc.
        boundary_local : Polygon | None, Optional
            The project boundary in local coordinate system, coordinate order is
            (Northing, Easting). The boundary is an optional attribute of a
            project that can be used for plotting, object detection etc.
        projector : Projector | None, Optional
            A Projector instance used for the project. If no projector is
            passed, a Projector will be created based on either the passed WGS84
            boundary, or a dummy origin of (0,0) (corresponding to the equator
            at the 0-meridian) will be used.
        branches : Branch | list[Branch] | None, Optional
            List of branches that will be added to the project. If the parameter
            `main_branch` is None, the first of these branches will become the
            main branch.
        main_branch : Branch | None, Optional
            Branch that will be set as the main branch of the project. May be
            part of `branches`, or not.
        file_adapter : FileAdapter | None, Optional
            file adapter that manages the connection to the hard disk that will
            be used for swapping timeseries. This file adapter can also be used
            by the user to export the project to file
        temporal_manager : TemporalManager | None, Optional
            TemporalManager instance that allows the swapping and loading of
            this project's temporals. This temporal manager will be used as fall
            back if a branch of the project doesn't have an own temporal
            manager.
        """
        self.__name = name
        self.__branches = []

        super().__init__(temporal_manager=temporal_manager)

        if order == "lon_lat":
            self.__boundary_wgs84 = switch_xy(boundary_wgs84)
        elif order == "lat_lon":
            self.__boundary_wgs84 = boundary_wgs84
        else:
            raise ValueError()

        self.__boundary_local = boundary_local
        if projector is None:
            self.__projector = Projector(origin=self.__boundary_wgs84 or (0, 0), order="lat_lon")
        else:
            self.__projector = projector

        # set branches and main branch:
        branches = none_object_or_list_to_list(branches)
        if len(branches) == 0 and main_branch is not None:
            branches = [main_branch]
        if branches:
            self.add_branches(branches)
        if main_branch is not None:
            assert main_branch in branches
            self.__main_branch = branches[0]
        else:
            self.__main_branch = None

        # set the file adapter:
        self.file_adapter = file_adapter  # call setter

    def __repr__(self) -> str:
        if self.__name is not None:
            return f"{self.__class__.__name__}(name='{self.__name}')"
        else:
            return f"{self.__class__.__name__}"

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, name: str):
        assert isinstance(name, str) or name is None
        self.__name = name

    @property
    def boundary_wgs84(self):
        """
        The project boundary in EPSG:4326 (WGS84), (latitude, longitude)
        """
        if self.__boundary_wgs84 is None and self.__boundary_local is not None:
            self.__boundary_wgs84 = self.projector.to_wgs84(self.__boundary_local, order="lat_lon")
        return self.__boundary_wgs84

    @property
    def boundary_local(self):
        """
        The project boundary in local coordinate system (requires
        `<Project>.projector` to be set)
        """
        if self.__boundary_local is None and self.__boundary_wgs84 is not None:
            self.__boundary_local = self.projector.from_wgs84(self.__boundary_wgs84, order="lat_lon")
        return self.__boundary_local

    @property
    def projector(self) -> Projector:
        return self.__projector

    @property
    def file_adapter(self) -> "FileAdapter":
        return self._file_adapter

    @file_adapter.setter
    def file_adapter(self, file_adapter: "FileAdapter"):
        typeerror_if_not_isinstance_or_none(file_adapter, oio.FileAdapter)
        if self._file_adapter is not None:
            self._file_adapter._set_project(None)
        self._file_adapter = file_adapter
        if file_adapter is not None:
            file_adapter._set_project(self)

    @property
    def main_branch(self) -> Branch | None:
        """
        The main `Branch` which in most cases should represent the status quo.

        If no main branch has been set, None will be returned.
        """
        return self.__main_branch

    @main_branch.setter
    def main_branch(self, branch: Branch | None):
        """
        Setting a branch as main branch will also add it to the project if not
        contained yet.
        """
        typeerror_if_not_isinstance_or_none(branch, Branch)
        if branch is not None:
            branch._set_project(self)
            if branch not in self.branches:
                self.branches.append(branch)
        self.__main_branch = branch

    @property
    def root(self):
        raise Exception("Has been renamed to main_branch")

    @root.setter
    def root(self, branch: Branch):
        raise Exception("Has been renamed to main_branch")

    @property
    def branches(self) -> list[Branch]:
        """
        List of all `Branch`es inside the project, including the main branch.
        """
        ret = self.__branches
        ret.sort(key=lambda x: x.id)
        return ret

    def add_branches(self, branches: Branch | list[Branch]):
        """Add one or more branches to the project."""
        branches = none_object_or_list_to_list(branches)
        for branch in branches:
            assert branch not in self.__branches
            branch._set_project(self)
            self.__branches.append(branch)

    def remove_branches(self, branches: Branch | list[Branch]):
        """
        Remove one or more branches from the project. This will also remove
        all objects in these branches from the mappings of all remaining
        branches. If the project's main branch is among the removed branches,
        the project won't have a main branch afterwards.
        """
        branches = none_object_or_list_to_list(branches)
        removed_objects = []
        for branch in branches:
            assert branch in self.__branches
            removed_objects += branch.offspring
            branch._set_project(None)
            self.__branches.remove(branch)
            if self.__main_branch is branch:
                self.__main_branch = None

        removed_objects = set(removed_objects)

        # clear mappings:
        for branch in self.branches:
            new_mapping = {}
            n_removed = 0
            for branch_obj, ref_obj in branch.mapping.items():
                if ref_obj in removed_objects:
                    new_mapping.pop(branch_obj)
                    n_removed += 1
                else:
                    new_mapping[branch_obj] = ref_obj
            if n_removed:
                logger.info(f"Removed {n_removed} references in Branch {branch}")
            branch.mapping = new_mapping

    def reorder_branches(self, branches_in_new_order: list[Branch]):
        """Reorder current branches (main branch unaffected)."""
        assert all(b in self.__branches for b in branches_in_new_order)
        assert all(b in branches_in_new_order for b in self.__branches)
        self.__branches = branches_in_new_order.copy()

    def bifurcate_from_branch(
        self,
        source_branch: Branch,
        name: str | None = None,
        year: int | None = None,
        description: dict | None = None,
    ) -> Branch:
        """
        Create a new branch from the given source branch containing references
        to the objects in the source branch. The branch will be returned and
        also added to the project.

        Parameters
        ----------
        source_branch : Branch
            The branch from which to create the new branch.
        name : str or None, optional
            The name of the new branch.
        year : int or None, optional
            The year of the new branch. If None, the year of the source branch
            is used.
        description : dict or None, optional
            A description for the new branch. If None, the description of the
            source branch is copied.
        """
        typeerror_if_not_isinstance(source_branch, Branch)

        new_mapping = source_branch._deepcopy_objects()
        new_branch = Branch(
            year=year if year is not None else source_branch.year,
            name=name,
            description=description if description is not None else source_branch.description.copy(),
            weather=source_branch.weather.copy() if source_branch.weather is not None else None,
            financing=source_branch.financing.copy() if source_branch.financing is not None else None,
        )
        new_objects = list(new_mapping.keys())
        for o in new_objects:
            assert isinstance(o, Object)
            assert o.parent is None  # has been set to None in deepcopy
            new_branch.add_objects(o)
        new_branch.mapping = new_mapping
        new_branch.history = copy.deepcopy(source_branch.history)

        self.add_branches(new_branch)
        return new_branch

    def bifurcate_from_main(
        self,
        name: str | None = None,
        year: int | None = None,
        description: dict | None = None,
    ):
        """
        Shortcut for `bifurcate_from_branch` using the main branch as source.
        """
        return self.bifurcate_from_branch(
            source_branch=self.main_branch,
            name=name,
            year=year,
            description=description,
        )

    def find_branches(
        self,
        name: str = None,
        id: int | list[int] = None,
        years: int | list[int] = None,
        description: dict | None = None,
        description_match_mode: Literal["if_present", "keys", "exact"] = "if_present",
        **kwargs,
    ) -> list[Branch]:
        """
        Get Branches by filtering on name, id, description or year.

        Parameters
        ----------
        name : str = None
            If given, the branches returned must have that name. Note that None
            doesn't count as a criterion.
        id : int | list[int] = None
            If given, the branches returned must have that id or one of the ids
            in the list.
        years : int | list[int] = None
            If given, the branches returned must have the given year(s) in their
            validity. If an int is given, it will be converted to a list.
        description : dict | None = None
            description dictionary that thte returned branches must match.
        description_match_mode : Literal["if_present", "keys", "exact"] = \
            "if_present"
            How to match the description:
            - "if_present": If the key is present in the branch's description,
              the value must match. If the key is not present, it doesn't 
              count as a criterion.
            - "keys": All keys must be present in the branch's description, and
              the values must match.
            - "exact": The branch's description must exactly match the given
              dictionary.
        kwargs : dict
            A dict that will be added to the dictionary used for filtering the
            description (convenience parameter).
        """

        candidates = self.branches

        if name is not None:
            candidates = [b for b in candidates if b.name == name]

        if id is not None:
            if isinstance(id, int):
                id = [id]
            candidates = [b for b in candidates if b.id in id]

        if years is not None:
            if isinstance(years, int):
                years = [years]
            candidates = [b for b in candidates if b.year in years]

        ret = []

        if description is None:
            description = {}
        if kwargs:
            description |= kwargs

        if description:
            if description_match_mode == "if_present":
                for b in candidates:
                    match = True
                    for k, v in description.items():
                        if k in b.description:
                            if v != b.description[k]:
                                match = False
                                break
                    if match:
                        ret.append(b)

            elif description_match_mode == "keys":
                for b in candidates:
                    match = True
                    for k, v in description.items():
                        if k not in b.description or v != b.description[k]:
                            match = False
                            break
                    if match:
                        ret.append(b)

            elif description_match_mode == "exact":
                for b in candidates:
                    if b.description == description:
                        ret.append(b)

        else:
            ret = candidates

        return ret

    def find_branch(
        self,
        name: str = None,
        id: int | list[int] = None,
        years: int | list[int] = None,
        description: dict | None = None,
        description_match_mode: Literal["if_present", "keys", "exact"] = "if_present",
        not_found: Literal["exception", "none"] = "exception",
        **kwargs,
    ) -> Branch | None:
        """
        Shortcut for `find_branches` expecting only one result. If multiple
        branches match the criteria, an Exception is raised. If no branch
        matches the criteria, either an Exception is raised or None is returned,
        depending on the `not_found` parameter.

        Parameters
        ----------
        name : str = None
            If given, the branch returned must have that name. Note that None
            doesn't count as a criterion.
        id : int | list[int] = None
            If given, the branch returned must have that id or one of the ids
            in the list.
        years : int | list[int] = None
            If given, the branch returned must have the given year(s) in its
            validity. If an int is given, it will be converted to a list.
        description : dict | None = None
            description dictionary that thte returned branches must match.
        description_match_mode : Literal["if_present", "keys", "exact"] = \
            "if_present"
            How to match the description:
            - "if_present": If the key is present in the branch's description,
              the value must match. If the key is not present, it doesn't 
              count as a criterion.
            - "keys": All keys must be present in the branch's description, and
              the values must match.
            - "exact": The branch's description must exactly match the given
              dictionary.
        not_found : Literal["exception", "none"] = "exception"
            If no branch matches the criteria, either raise an Exception or
            return None.
        kwargs : dict
            A dict that will be added to the dictionary used for filtering the
            description (convenience parameter).
        """
        matches = self.find_branches(
            name=name,
            id=id,
            years=years,
            description=description,
            description_match_mode=description_match_mode,
            **kwargs,
        )

        if len(matches) > 1:
            raise Exception("Multiple branches match the criteria")
        elif len(matches) == 0:
            if not_found == "exception":
                raise Exception("No branch found matching the criteria")
            else:
                return None
        return matches[0]

    def find_objects(
        self,
        type: TypeDescriptor = None,
        name: str | list[str] = None,
        id: int | list[int] = None,
    ) -> list["Object"]:
        """
        Find `Object`s in the project by type, name or id. The search is
        performed in all branches of the project. Returns a list of all found
        objects, sorted by id.

        Parameters
        ----------
        type : TypeDescriptor = None
            If given, the object returned must be of that type.
        name : str | list[str] = None
            If given, the object returned must have that name or one of the
            names in the list. Note that a name of None doesn't count as a
            criterion.
        id : int | list[int] = None
            If given, the object returned must have that id or one of the ids
            in the list.
        """
        ret = []

        for branch in self.branches:
            ret += branch.find_objects(type=type, name=name, id=id)

        ret.sort(key=lambda x: x.id)

        return ret

    def find_object(
        self,
        type: TypeDescriptor = None,
        name: str | list[str] = None,
        id: int | list[int] = None,
        not_found: Literal["exception", "none"] = "exception",
    ) -> Object | None:
        """
        Find an `Object` in the project by type, name or id. The search is
        performed in all branches of the project. Returns the first found
        object. If multiple objects match the criteria, an Exception is raised.
        If no object matches the criteria, either an Exception is raised or
        None is returned, depending on the `not_found` parameter.

        Parameters
        ----------
        type : TypeDescriptor = None
            If given, the object returned must be of that type.
        name : str | list[str] = None
            If given, the object returned must have that name or one of the
            names in the list. Note that a name of None doesn't count as a
            criterion.
        id : int | list[int] = None
            If given, the object returned must have that id or one of the ids
            in the list.
        not_found : Literal["exception", "none"] = "exception"
            If no object matches the criteria, either raise an Exception or
            return None.
        """
        objects = self.find_objects(type=type, name=name, id=id)

        if len(objects) > 1:
            raise Exception("Multiple objects match the criteria")

        elif len(objects) == 0:
            if not_found == "exception":
                raise Exception("No object found matching the criteria")
            else:
                return None

        return objects[0]

    def get_object_slice(self, object: Object) -> dict[Branch, Object]:
        """
        Get all objects from other branches that are connected to the passed
        object by a reference (of any direction).

        If, for example, there are branches A, B, C and D each having an object
        a, b, c or d with references
        ```
        a, b -> c
        c -> d
        ```
        then calling `get_object_slice(a)` will return
        ```
        {
            A: a,
            B: b,
            C: c,
            D: d
        }
        ```
        """
        assert isinstance(object, Object)
        assert object.branch is not None

        ret = {object.branch: object}

        # get all branches that have a reference to the object
        for branch in self.branches:
            if branch is object.branch:
                continue
            ref_obj = branch.get_object_by_reference(object)
            if ref_obj is not None:
                ret[branch] = ref_obj

        return ret

    def renew_ids(self):
        """
        Renew all IDs of all objects in all branches. This will not change any
        references, but will make sure that all objects have a unique ID.
        """
        id_authority.set_last_value(-1)  # reset id authority
        self.id_authority = id_authority  # assign global id authority to project

        for branch in self.root_and_branches:
            for obj in branch.offspring:
                obj._Identified__id = self.id_authority()
