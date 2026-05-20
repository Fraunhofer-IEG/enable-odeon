from __future__ import annotations
import networkx as nx

from .base import UniqueEnum


class DagNode:
    """
    A container for stuff structured in a DAG (directed acyclic graph).
    """

    name: str = None
    _parents: list[DagNode] = None
    _children: list[DagNode] = None

    def __init__(self, parents: DagNode | list[DagNode] | None = None, name: str = None) -> None:
        if isinstance(parents, DagNode):
            parents = [parents]
        elif isinstance(parents, (list, tuple)) and all(isinstance(p, DagNode) for p in parents):
            parents = [*parents]
        elif parents is None:
            parents = []
        else:
            raise TypeError()
        self.name = name
        self._parents = []
        self._children = []
        for p in parents:
            p.add_child(self)

    def add_child(self, children: DagNode | list[DagNode]):
        if isinstance(children, DagNode):
            children = [children]
        if not all(isinstance(c, DagNode) for c in children):
            raise TypeError()
        for c in children:
            c._add_parent(self)
            self._children.append(c)

    def _add_parent(self, parent: DagNode):
        if not isinstance(parent, DagNode):
            raise TypeError()
        if parent is self:
            raise TypeError()
        if parent in self.subs:
            raise Exception(f"Circular dependency")
        if parent not in self._parents:
            self._parents.append(parent)

    @property
    def roots(self) -> list[DagNode]:
        """Supers without a parent"""
        ret = []
        if len(self._parents):
            for p in self._parents:
                ret += p.roots
        else:
            ret.append(self)
        return ret

    @property
    def parents(self) -> list[DagNode]:
        return [*self._parents]

    @property
    def children(self) -> list[DagNode]:
        return [*self._children]

    @property
    def supers(self) -> list[DagNode]:
        """Parents and their parents and so on, not including self"""
        ret = []
        for p in self._parents:
            ret.append(p)
            ret += p.supers
        return ret

    @property
    def subs(self) -> list[DagNode]:
        """Children and their children and so on, not including self"""
        ret = []
        for p in self._children:
            ret.append(p)
            ret += p.subs
        return ret

    @property
    def digraph(self) -> nx.DiGraph:
        """
        Return a DiGraph including all subs of all roots of this DagNode
        with Edge direction from parent to children and
        """
        roots = self.roots
        edge_tuples = set()
        for r in roots:
            edge_tuples |= r.edge_tuples(recursive=True)
        digraph = nx.DiGraph()
        digraph.add_edges_from(edge_tuples)
        return digraph

    def edge_tuples(self, recursive: bool = True) -> set[tuple[DagNode, DagNode]]:
        ret = set()
        for c in self.children:
            ret.update([tuple([self, c])])
            if recursive:
                ret |= c.edge_tuples(recursive=recursive)
        return ret

    # TODO multiple supers might exist, nx can apparently only return one?
    def closest_common_super(self, other: DagNode) -> DagNode | None:
        lca = nx.lowest_common_ancestor(self.digraph, node1=self, node2=other)
        return lca

    # TODO probably won't work if it's a DAG rather than a tree.
    def closest_common_super_multi(self, nodes: list[DagNode]) -> DagNode | None:
        nodes = list(set(nodes))
        if len(nodes) == 0:
            return
        elif len(nodes) == 1:
            return nodes[0]
        pairs = []
        while len(nodes) > 1:
            pairs.append((nodes.pop(), nodes.pop()))
        lcas = nx.algorithms.lowest_common_ancestors.all_pairs_lowest_common_ancestor(G=self.digraph, pairs=pairs)
        nodes += dict(lcas).values()
        return self.closest_common_super_multi(nodes=nodes)

    def superiority(self, other: DagNode) -> int | None:
        """
        Return superiority of this DagNode over `other`. The superiority is the
        number of parent-child relationships between his DagNode and `other`, if
        they are in a linear relation.
        If `other` is a child of this DagNode, superiority is 1. If `other` is
        a parent of this DagNode, superiority will be -1. If they are the same,
        superiority will be 0.

        Returns
        -------
        Superiority of this DagNode over `other`, if they are connected and in
        linear relation. None otherwise.
        """
        digraph = self.digraph
        if self is other:
            return 0
        elif self in other.supers:
            return nx.shortest_path_length(G=digraph, source=self, target=other)
        elif other in self.supers:
            return -nx.shortest_path_length(G=digraph, source=other, target=self)
        else:
            return None

    def inferiority(self, other: DagNode) -> int | None:
        """The inverse of `self.superiority(other)`"""
        s = self.superiority(other=other)
        if isinstance(s, int):
            return -s

    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, DagNode) and self.name == __value.name

    def __hash__(self) -> int:
        return id(self)


class TypeDagNode(DagNode):

    def generalizes(self, other: TypeDagNode, include_same: bool = True) -> bool:
        """Return whether this object is a generalization of `other`"""
        ret = other in self.subs
        if include_same:
            ret |= other is self
        return ret

    def specifies(self, other: TypeDagNode, include_same: bool = True) -> bool:
        """Return whether this object is a specification of `other`"""
        ret = other in self.supers
        if include_same:
            ret |= other is self
        return ret

    def is_linear(self, other: TypeDagNode, include_same: bool = True) -> bool:
        return self.generalizes(other=other, include_same=include_same) or self.specifies(
            other=other, include_same=include_same
        )

    def __repr__(self) -> str:
        return f"<TypeDagNode '{self.name}'>"


# @unique
class Medium(UniqueEnum):

    ENERGY = ("energy", [])

    ELECTRIC_ENERGY = ("electric energy", ["ENERGY"])
    THERMAL_ENERGY = ("thermal energy", ["ENERGY"])
    CHEMICAL_ENERGY = ("chemical energy", ["ENERGY"])
    EM_RADIATION_ENERGY = ("EM radiation energy", ["ENERGY"])

    AIR_THERMAL_ENERGY = ("air thermal energy", ["THERMAL_ENERGY"])
    WATER_THERMAL_ENERGY = ("water thermal energy", ["THERMAL_ENERGY"])
    BRINE_THERMAL_ENERGY = ("brine thermal energy", ["THERMAL_ENERGY"])

    WATER_THERMAL_ENERGY_LO = ("water thermal energy, LT", ["WATER_THERMAL_ENERGY"])
    WATER_THERMAL_ENERGY_MED = ("water thermal energy, MT", ["WATER_THERMAL_ENERGY"])
    WATER_THERMAL_ENERGY_HI = ("water thermal energy, HT", ["WATER_THERMAL_ENERGY"])

    LIQUID_CHEMICAL_ENERGY = ("liquid chemical energy", ["CHEMICAL_ENERGY"])
    GASEOUS_CHEMICAL_ENERGY = ("gaseous chemical energy", ["CHEMICAL_ENERGY"])
    SOLID_CHEMICAL_ENERGY = ("solid chemical energy", ["CHEMICAL_ENERGY"])

    SOLAR_ENERGY = ("solar energy", ["EM_RADIATION_ENERGY"])

    FUEL_OIL = ("fuel oil", ["LIQUID_CHEMICAL_ENERGY"])

    NATURAL_GAS = ("natural gas", ["GASEOUS_CHEMICAL_ENERGY"])
    SYNGAS = ("syngas", ["GASEOUS_CHEMICAL_ENERGY"])
    BIOGAS = ("biogas", ["GASEOUS_CHEMICAL_ENERGY"])
    HYDROGEN = ("hydrogen", ["GASEOUS_CHEMICAL_ENERGY"])

    BIOMASS = ("biomass", ["SOLID_CHEMICAL_ENERGY"])

    BIOMASS_WOODCHIPS = ("biomass: woodchips", ["BIOMASS"])
    BIOMASS_PELLETS = ("biomass: pellets", ["BIOMASS"])
    BIOMASS_WOODLOGS = ("biomass: woodlogs", ["BIOMASS"])

    def __init__(self, label, parent_names):
        self.label = label
        self.parent_names = parent_names

    def __repr__(self) -> str:
        return f"<Medium '{self.name}'>"

    @classmethod
    def get_by_label(cls, label: str) -> Medium | None:
        return next((Medium[m] for m in cls.__members__ if Medium[m].label == label), None)

    # def __json__(self):
    #     return self.name


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class MediumManager(metaclass=Singleton):
    """
    A class for checking relations between Mediums. As Mediums are Enums, they
    don't contain their relationships as direct implementations. Rather, it's
    necessary to interpret the additional data they come with and build a graph
    from it dynamically.
    """

    def __init__(self):
        self._build_dag()

    def _build_dag(self):
        self.nodes = {}
        for m in [*Medium.__members__]:
            parents = [self.nodes[p] for p in Medium[m].parent_names]
            node = TypeDagNode(name=m, parents=parents)
            self.nodes[m] = node

    def __getitem__(self, medium: Medium) -> TypeDagNode | None:
        return self.nodes.get(medium.name, None)

    def closest_common_super(self, medium1: Medium, medium2: Medium) -> Medium | None:
        """
        Return the closest common super Medium of `medium1` and `medium2`, if it
        exists.
        """
        assert medium1 is not None and medium2 is not None
        ret = self[medium1].closest_common_super(other=self[medium2])
        if ret is not None:
            return Medium[ret.name]

    def closest_common_super_multi(self, mediums: list[Medium]) -> Medium | None:
        """
        Return the closest common super Medium of `mediums`, if it exists.
        """
        ret = self[mediums[0]].closest_common_super_multi(nodes=[self[m] for m in mediums])
        if ret is not None:
            return Medium[ret.name]

    def supers(self, medium: Medium) -> list[Medium]:
        """
        Return all supers of `medium`, sorted by distance to `medium` (closest
        first).
        """
        assert medium is not None
        return [Medium[s.name] for s in self[medium].supers]

    def subs(self, medium: Medium) -> list[Medium]:
        """
        Return all subs of `medium`, sorted by distance to `medium`
        (closest first).
        """
        assert medium is not None
        return [Medium[s.name] for s in self[medium].subs]

    def specifies(self, medium1: Medium, medium2: Medium, include_same: bool = True) -> bool:
        """
        Check if `medium1` specifies `medium2`.

        Parameters
        ----------
        medium1 : Medium
            The first medium to check.
        medium2 : Medium
            The second medium to check.
        include_same : bool, optional
            If True, consider mediums that are the same as specifying each other.

        Returns
        -------
        bool
            True if `medium1` specifies `medium2`, False otherwise.
        """
        assert medium1 is not None and medium2 is not None
        return self[medium1].specifies(other=self[medium2], include_same=include_same)

    def generalizes(self, medium1: Medium, medium2: Medium, include_same: bool = True) -> bool:
        """
        Check if `medium1` generalizes `medium2`.

        Parameters
        ----------
        medium1 : Medium
            The first medium to check.
        medium2 : Medium
            The second medium to check.
        include_same : bool, optional
            If True, consider mediums that are the same as generalizing each other.

        Returns
        -------
        bool
            True if `medium1` generalizes `medium2`, False otherwise.
        """
        assert medium1 is not None and medium2 is not None
        return self[medium1].generalizes(other=self[medium2], include_same=include_same)

    def is_linear(self, medium1: Medium, medium2: Medium, include_same: bool = True) -> bool:
        """
        Check if `medium1` is linear with `medium2`. Linear means that one of
        the mediums generalizes the other, or they are the same (if
        `include_same` is True). If they are not linear, they are in

        Parameters
        ----------
        medium1 : Medium
            The first medium to check.
        medium2 : Medium
            The second medium to check.
        include_same : bool, optional
            If True, consider mediums that are the same as linear with each
            other.

        Returns
        -------
        bool
            True if `medium1` is linear with `medium2`, False otherwise.
        """
        assert medium1 is not None and medium2 is not None
        return self[medium1].is_linear(other=self[medium2], include_same=include_same)

    def superiority(self, medium1: Medium, medium2: Medium) -> int | None:
        """
        Determine the superiority between two mediums. Superiority is defined as
        the number of parent-child relationships between `medium1` and `medium2`
        in the DAG, if they are in a linear relation. If `medium1` is a child of
        `medium2`, superiority is 1. If `medium1` is a parent of `medium2`,
        superiority will be -1. If they are the same, superiority will be 0. If
        they are not in a linear relation, None is returned.

        Parameters
        ----------
        medium1 : Medium
            The first medium to check.
        medium2 : Medium
            The second medium to check.

        Returns
        -------
        int | None
            An integer representing the superiority of `medium1` over `medium2`,
            or None if they are incomparable.
        """
        assert medium1 is not None and medium2 is not None
        return self[medium1].superiority(other=self[medium2])
