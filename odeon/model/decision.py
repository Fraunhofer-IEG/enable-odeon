from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING

# NOTE: Introduced the following import because "from .devices import Device" led to a circular import error
# This import is just a quick workaround, probably needs to be reconsidered in the future
import odeon.model as om

if TYPE_CHECKING:
    from .building import Building
    from .asset import Asset
    from .base import Object


class DecisionState(str, Enum):
    FIXED = "fixed"  # a device that cannot be changed in a decision process
    UNDECIDED_EXISTING = "undecided_existing"  # an existing device that could be replaced
    UNDECIDED_OPTION = "undecided_option"  # an unexisting device that could be decided for
    UNDECIDED_SCALING = "undecided_scaling"  # a device with scaling decision not yet taken
    DECIDED_FOR = "decided_for"  # a (now existing) device that was once for decision
    DECIDED_AGAINST = "decided_against"  # an unexisting device that was once for decision
    DECIDED_SCALING = "decided_scaling"  # a device with scaling decision already taken
    UNKNOWN = "unknown"


class DecisionType(str, Enum):
    INDEPENDENT = "independent"  # deciding for or against a device without constraints
    INDEPENDENT_SCALING = (
        "independent_scaling"  # deciding on the dimension of a device while existence is fixed (=true)
    )
    ONLY_ONE = "only_one"  # including replacing one device with another
    LINEAR_COMPETITION = "linear_competition"  # non-existing devices compete linearly for their maximum dimension


class Decision(om.Object):
    _ASSOCIATED_ATTRIBUTES = ["_objects"]
    _objects: list[Object] = None
    # additional attributes:
    _type: DecisionType = None
    decided: bool = False

    def __init__(self, type_: DecisionType, objects: list, **kwargs):
        self._type = type_
        self._objects = []
        self.decided = False
        for o in objects:
            self._add_object(o)
        super().__init__(**kwargs)

    @property
    def type_(self):
        return self._type

    @property
    def existing(self):
        return next((o for o in self._objects if o._exists), None)

    def _add_object(self, object: Object):
        if self._type is DecisionType.INDEPENDENT:
            assert not self._objects
        if self._type is DecisionType.ONLY_ONE and self.existing is not None:
            assert not object._exists
        assert not any(object is o for o in self._objects)
        assert object._decision is None
        object._decision = self  # kg, mj: Was war hier die Idee dahinter?
        self._objects.append(object)

    def set_existing(self, object: Object, value: bool):
        if self._type is DecisionType.ONLY_ONE:
            if value:
                for o in self._objects:
                    o._exists = False
                    object._exists = True
        else:
            object._exists = value


class AssetDecision(Decision):
    def __init__(self, type_: DecisionType, devices: list["Asset"], **kwargs):
        super().__init__(type_=type_, objects=devices, **kwargs)

    @property
    def devices(self):
        return self._objects

    def add_device(self, device: "Asset"):
        assert isinstance(device, om.Asset)
        self._add_object(device)


class BuildingDecision(Decision):
    def __init__(self, type_: DecisionType, buildings: list["Building"], **kwargs):
        super().__init__(type_=type_, objects=buildings, **kwargs)

    @property
    def buildings(self):
        return self._objects

    def add_building(self, building: "Building"):
        assert isinstance(building, om.Building)
        self._add_object(building)
