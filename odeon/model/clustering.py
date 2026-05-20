from numbers import Real

from .base import Base, Branch, Object, Organizer
from .region import Segregation, Region


class Group(Organizer):
    _MEMBER_ATTRIBUTES = ["_members"]
    _members: list[Object] = None

    def __init__(self, members: list[Object] = None, **kwargs):
        super().__init__(**kwargs)
        self._members = []
        if members:
            self.add_members(members)

    def add_members(self, members: Object | list[Object]):
        if isinstance(members, Object):
            members = [members]
        for member in members:
            assert member not in self._members
            assert member.branch is self.branch or member.branch is None or self.branch is None
            self._members.append(member)
            if self not in member.affiliations:
                member.affiliations.append(self)

    def _add_assert_type(self, members: Object | list[Object], type_: type | tuple[type]):
        if isinstance(members, Object):
            members = [members]
        if isinstance(type_, list):
            type_ = tuple(type_)
        for m in members:
            if isinstance(m, type_):
                self.add_members(m)
            else:
                raise TypeError()

    def remove_members(self, members: Object | list[Object]):
        raise NotImplementedError()

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id}, n={len(self._members)})"


class SubstituteGroup(Group):
    """
    A Group that can additionally store Objects in a parent-child (1:N)
    relationship (contrasting its members which are in an affiliation-member
    (M:N) relationship). Note that objects added to an ObjectGroup will not
    appear in the objects of any Branch. However, querying an object's branch
    via `<Object>.branch` will still return the branch this ObjectGroup is
    assigned to.
    """

    _CHILDREN_ATTRIBUTES = {"_objects": "Object[]"}
    _objects: list[Object] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._objects = []

    @property
    def objects(self) -> list[Object]:
        return [*self._objects]

    def add_objects(self, objects: Object | list[Object]):
        """
        add a new `Object` or a list of new `Object`(s) to the Group. The
        new objects' parents must be None, or instances of `Branch` or
        `ObjectGroup`.
        """
        if not isinstance(objects, (list, tuple)):
            objects = [objects]

        for object in objects:
            assert isinstance(object, Object)
            assert not isinstance(object, Organizer)
            assert object.parent is None or isinstance(object.parent, (Branch, SubstituteGroup))
            if object not in self._objects:
                self._objects.append(object)
                object._set_parent(self)

    def remove_objects(self, objects: Object | list[Object]):
        if not isinstance(objects, (list, tuple)):
            objects = [objects]

        for object in objects:
            if object in self._objects:
                self._objects.remove(object)
                object._set_parent(None)


class Clustering(Organizer):
    """
    An Organizer that stores several (typically exclusive) Groups and an
    additional Group of unclustered objects as children.
    """

    _CHILDREN_ATTRIBUTES = {
        "_groups": "Group[]",
        "_unclustered": "Group",
    }
    _groups: list[Group] = None
    _unclustered: Group = None  # objects that were considered but don't fit in any cluster

    def __init__(self, groups: list[Group] = None, unclustered: Group = None, **kwargs):
        super().__init__(**kwargs)

        # init list:
        self._groups = []

        if unclustered is None:
            unclustered = Group()
        if groups is None:
            groups = []

        # set parents in children:
        for g in groups:
            g._set_parent(self)
        unclustered._set_parent(self)

        # set children in parent (i.e. self):
        self._groups = groups
        self._unclustered = unclustered

    @property
    def clustered_objects(self) -> list[Base]:
        """return all Objects contained in `self.groups`"""
        objs = []
        for g in self._groups:
            objs.extend(g.members)
        return objs

    @property
    def groups(self) -> list[Group]:
        return self._groups.copy()

    @property
    def unclustered(self) -> Group:
        return self._unclustered


class FactorizedClustering(Clustering):
    """
    A Clustering with a factor per Object per Group indicating the grade of
    affinity of an Object to that Group. The same Object can be present in
    multiple Groups.
    """

    factors: dict[Group, dict[Object, Real]] = None

    def __init__(
        self,
        groups: list[Group] = None,
        factors: dict[Group, dict[Object, Real]] = None,
        unclustered: Group = None,
        **kwargs,
    ):
        super().__init__(groups=groups, unclustered=unclustered, **kwargs)
        self.factors = factors or {}

    def get_factor(self, group: Group, object: Object) -> Real:
        if group is not None:
            return self.factors.get(group, {}).get(object, 1.0)
        else:
            return self.unique_objects_summed_factors.get(object, None)

    @property
    def unique_objects(self) -> list[Object]:
        """
        collect unique objects from all groups (using python's identity rather
        than any `__eq__` implementations)
        """
        return list(self.unique_objects_summed_factors.keys())

    @property
    def unique_objects_summed_factors(self) -> dict[Object, Real]:
        ret = {}
        for group, objects_factors in self.factors.items():
            for object, factor in objects_factors.items():
                ret[object] = ret.get(object, 0) + factor
        return ret

    @property
    def has_valid_factors(self) -> bool:
        ret = True
        ret &= all(g in self.factors for g in self._groups)
        for group, objects_factors in self.factors.items():
            for object, factor in objects_factors.item():
                ret &= object in group.objects
                ret &= isinstance(factor, Real)
                if not ret:
                    return ret
        return ret

    @property
    def is_normalized(self) -> bool:
        """
        check if per object in any group, factors across all groups sum up to 1
        """
        ret = self.has_valid_factors
        ret &= all(round(f, 6) == 1 for f in self.unique_objects_summed_factors.keys())
        return ret


class SpatialClustering(FactorizedClustering):
    """
    A `FactorizedClustering` based on a `Segregation`

    Attributes
    ----------
    - `segregation`: The Segregation
    - `groups`: A list of Groups of same length and order as the number of
    Regions in `segregation`. If for a Region no Objects are clustered, the
    corresponding Group will be empty
    """

    _CHILDREN_ATTRIBUTES = {"_segregation": "Segregation"}
    _segregation: Segregation = None

    def __init__(
        self,
        segregation: Segregation = None,
        groups: list[Group] = None,
        factors: dict[Group, dict[Object, Real]] = None,
        unclustered: Group = None,
        **kwargs,
    ):
        super().__init__(groups=groups, unclustered=unclustered, factors=factors, **kwargs)
        assert isinstance(segregation, Segregation) or segregation is None
        assert len(segregation.regions) == len(groups) or segregation is None
        self._segregation = segregation
        self._segregation._set_parent(self)

    def get_group_by_region(self, region: Region) -> Group:
        return next((g for r, g in zip(self._segregation.regions, self._groups) if r is region), None)

    @property
    def segregation(self):
        return self._segregation


class BinClustering(Clustering): ...
