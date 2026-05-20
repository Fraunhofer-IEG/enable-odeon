from __future__ import annotations
import math
from numbers import Number
from typing import Any, Literal, TYPE_CHECKING, Type

import pandas as pd

from .base import Object
from .temporal import Temporal
from .energy import Medium, MediumManager

from ..processing.utils.utils import typeerror_if_not_isinstance_or_none

import odeon.model as om

if TYPE_CHECKING:
    from .energy_system import EnergySystem


MediumRelation = Literal["exact", "linear", "socket_specifies", "socket_generalizes"]
MediumLocation = Literal["socket", "link", "socket_else_link"]


def _is_valid_activity(activity: Any, validity_index: pd.DatetimeIndex = None) -> bool:
    ret = isinstance(activity, bool)
    ret = ret or (
        isinstance(activity, pd.Series) and activity.dtype == "bool" and activity.index.equals(validity_index)
    )
    return ret


class Link(Object):
    """
    An object to analyze the link of two `Component`s. The object isn't designed
    to store any data except to receive an id so that it can be identified and
    is part of the hierarchy.

    If only one component is given, the Link is called "abstract".
    """

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_flow_location"]
    _flow_location: Socket | None = None

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_flow"]
    _flow: Temporal = None

    def __init__(self, parent: "Socket" = None, other: Socket | None = None, **kwargs):
        typeerror_if_not_isinstance_or_none(parent, Socket)
        typeerror_if_not_isinstance_or_none(other, Socket)
        self._flow_location = None
        super().__init__(**kwargs)
        self._set_parent(parent)

    @property
    def sockets(self) -> list["Socket"]:
        """
        The parent and the other socket, if present. List of 0, 1 or 2 elements.
        """
        sockets = []
        if self.parent is not None:
            sockets.append(self.parent)
            if self.parent.other is not None:
                sockets.append(self.parent.other)
        return sockets

    @property
    def is_abstract(self) -> bool:
        """
        The Link is abstract if only one Socket/Component is given.
        """
        return self.parent is not None and self.parent.other is not None

    @property
    def components(self) -> list["Component"]:
        """
        The involved components (0, 1, or 2)
        """
        return [s.parent for s in self.sockets]

    @property
    def from_(self) -> Component | None:
        return next((c for c in self.components if any(s in c.output_sockets for s in self.sockets)), None)

    @property
    def to_(self) -> Component | None:
        return next((c for c in self.components if any(s in c.input_sockets for s in self.sockets)), None)

    @property
    def from_socket(self) -> Socket | None:
        return next((s for s in self.sockets if s is not None and s.parent is self.from_), None)

    @property
    def to_socket(self) -> Socket | None:
        return next((s for s in self.sockets if s is not None and s.parent is self.to_), None)

    @property
    def activity(self):
        self._error_if_not_valid()
        ret = self.sockets[0].activity
        if len(self.sockets) == 2:
            ret &= self.sockets[1].activity
        return ret

    @property
    def flow(self) -> Temporal:
        return self._flow

    def _set_flow(self, flow: Temporal | Number | pd.Series | None, socket: Socket | None):
        if socket in [*self.sockets, None]:
            self._flow_location = socket
        else:
            raise ValueError()
        self.set_temporal("_flow", flow, error_if_values_below=-0.0001)

    @flow.setter
    def flow(self, flow: Temporal | Number | pd.Series | None):
        self._set_flow(flow=flow, socket=None)

    @property
    def medium(self) -> Medium | None:
        """
        Return the closest super medium of the link. If only one Socket is given
        or only one has a Medium set, this will be returned. If no Socket has a
        Medium set, None will be returned.
        """
        sockets = self.sockets
        medium = sockets[0].medium
        if len(sockets) == 2:
            if sockets[1].medium is not None:
                if medium is None:
                    medium = sockets[1].medium
                elif sockets[1].medium is not medium:
                    mm = MediumManager()
                    medium = mm.closest_common_super(medium, sockets[1].medium)
        return medium

    def other_component(self, this: Component) -> Component | None:
        sockets = self.sockets
        socket = next(s for s in sockets if s.parent is this)
        if len(sockets) == 2:
            return sockets[1 - sockets.index(socket)].parent

    def other_socket(self, this: Socket) -> Socket | None:
        sockets = self.sockets
        return next((s for s in sockets if s is not this), None)

    def __repr__(self):
        from_ = self.from_
        to_ = self.to_

        if from_ is not None:
            from_name = f", '{from_.name}'" if from_.name is not None else ""
            from_str = f"{from_.__class__.__name__}({from_.id}{from_name})"
        else:
            from_str = "?"

        if to_ is not None:
            to_name = f", '{to_.name}'" if to_.name is not None else ""
            to_str = f"{to_.__class__.__name__}({to_.id}{to_name})"
        else:
            to_str = "?"

        return f"{self.__class__.__name__}(id={self.id}, {from_str}->{to_str})"


class Socket(Object):
    """
    Parent: Component (via `<Component>.input_sockets` or
    `<Component>.output_sockets`)
    """

    # children attributes:
    _CHILDREN_ATTRIBUTES = {"_link": "Link"}
    _link: Link | None = None

    # associated attributes:
    _ASSOCIATED_ATTRIBUTES = ["_other"]
    _other: Socket | None = None

    # additional attributes:
    _medium: Medium | None = None
    _activity: pd.Series | bool = True  # TODO make it a "BoolTemporal"?

    def __init__(self, medium: Medium = None, other: "Socket" = None, flow: Temporal = None, **kwargs):
        self.medium = medium  # call setter
        self.other = None  # call seter, will create link
        self.flow = flow
        super().__init__(**kwargs)
        if other is not None:
            self.other = other  # call setter

    def _remove_link(self, reciproke: bool = True):
        """
        Remove the child link, if present. Also remove the knowledge of the
        second socket in the child link.

        If this socket hasn't a child link but it is linked to another socket
        (which is parent of the link), remove the parent-child relationship
        over there.
        """
        if self._link is not None:
            self._link._set_parent(None)
            self._link = None
        elif reciproke and self._other is not None:
            self._other._remove_link(reciproke=False)

    @property
    def link(self) -> Link:
        if self._link is not None:
            return self._link
        elif self._other is not None:
            return self._other._link
        else:
            ...  # this may occur during init

    @property
    def other(self) -> Socket | None:
        return self._other

    @other.setter
    def other(self, other: Socket | None):
        typeerror_if_not_isinstance_or_none(other, Socket)

        if other is None:
            if isinstance(self._other, Socket):
                self.remove_other()  # will remove link also, and create a new one
            else:
                self._link = Link(parent=self, other=None)  # should only occur in Socket.__init__

        else:
            # when we link two sockts, 0, 1, or 2 flows could be present (max.
            # one in the link of each socket). In order to find out which flow
            # to set for the new connection, we will discard all flows for which
            # the link has a socket on the opposite connected and the flow is
            # located over there. The remaining number of flows should be 0 or 1
            flows = []
            flow_location = None
            for socket in [self, other]:
                socket: Socket
                if socket.link is not None:  # Should only occur in Socket.__init__
                    if not socket.flow.is_empty:
                        if len(socket.link.sockets) == 2 and socket.link._flow_location is socket:
                            flows.append(socket.link._flow)
                            flow_location = socket
                        elif len(socket.link.sockets) == 1:
                            flows.append(socket.link._flow)
                            flow_location = socket.link._flow_location
                        else:
                            pass  # don't keep any other flows

            flows = list(set(flows))
            if len(flows) > 1:
                raise Exception("Can't link two Sockets with both having a non-empty flow")
            flow = flows[0] if len(flows) == 1 else None

            assert other is not self
            if (self.is_input_socket and other.is_input_socket) or (self.is_output_socket and other.is_output_socket):
                raise Exception("Can't link two input sockets or two output sockets")
            if self._other is other:
                raise Exception("Can't link Sockets: Already linked")

            if self._other is not None:
                self._other.remove_other()  # will remove link also
            else:
                self._remove_link()

            self._other = other

            if self._other._other is not self:
                other.other = self  # call the same method
                if self._other._link is not None:
                    assert self._other._link.other_socket(other) is self
                else:
                    self._link = Link(parent=self, other=other)
                    self._link.flow = flow
                    self._link._flow_location = flow_location
            else:
                pass  # = this method got called from the same method in other already

    @property
    def is_output_socket(self) -> bool:
        """
        Return whether the socket is in its parent's output sockets. If the
        socket doesn't have a parent, False will be returned.
        """
        return self.parent is not None and self in self.parent.output_sockets

    @property
    def is_input_socket(self) -> bool:
        """
        Return whether the socket is in its parent's input sockets. If the
        socket doesn't have a parent, False will be returned.
        """
        return self.parent is not None and self in self.parent.input_sockets

    def get_medium(self, medium_considered: MediumLocation) -> Medium | None:
        if medium_considered == "socket":
            return self.medium
        elif medium_considered == "link":
            return self.link.medium if self.link is not None else None
        elif medium_considered == "socket_else_link":
            if self.medium is not None:
                return self.medium
            elif self.link is not None:
                return self.link.medium
            else:
                return None
        else:
            raise ValueError()

    @property
    def medium(self) -> Medium | None:
        return self._medium

    @medium.setter
    def medium(self, medium: Medium) -> Medium | None:
        # TODO typecheck
        self._medium = medium

    @property
    def flow(self) -> Temporal:
        return self.link.flow

    @flow.setter
    def flow(self, flow: Temporal | Number | pd.Series | None):
        self.link._set_flow(flow=flow, socket=self)

    @property
    def activity(self):
        """
        The boolean activity of the Socket (enabled/disabled, or
        activated/deactivated)
        """
        return self._activity

    @activity.setter
    def activity(self, activity: pd.Series | bool):
        if not self._is_valid_activity(activity=activity):
            msg = (
                "Not a valid activity. A activity has to be either a bool, ",
                "a Series of bools with the same activity as the Branch.",
            )
            raise TypeError("".join(msg))
        self._activity = activity

    @property
    def is_abstract(self) -> bool:
        return self._other is None

    def remove_other(self):
        """
        Remove the connection to other, if present. This makes both involved
        Sockets abstract. This will remove the Link object as well and replace
        it by a new one.

        The flow set in the link will be kept in the socket if it has been set
        there originally. Otherwise, it will be reset to an empty Temporal.
        """
        if isinstance(self._other, Socket):
            if self._other._other is self:
                # = direct/first call
                other = self._other
            else:
                # = second call (called by the same function)
                other = None

            # keep flow only if the flow location is in this socket already:
            flow = None
            if self.link is not None:
                if self.link._flow_location is self:
                    flow = self.flow

            # remove the link if it is set in this socket, don't delete it otherwise:
            self._remove_link(reciproke=False)

            self._other = None
            if other is not None:
                other.remove_other()
            self._link = Link(parent=self, other=None)
            if flow is not None:
                self._link._set_flow(flow, socket=self)
                self._link._flow_location = self

    def _is_valid_activity(self, activity: Any) -> bool:
        return _is_valid_activity(activity=activity, validity_index=self.timeindex)

    def apply_activity(self, reset_activity: bool = False, overlay: bool | pd.Series = None):
        """
        Apply the Socket's activity by setting the flow to 0 (if activity is not
        a series), or by setting all timesteps to 0 where activity is False.

        Parameters
        ----------
        - `reset_activity`: If True, after applying the activity to the flow,
        it will be reset to True.
        - `overlay`: If not None, the given bool (scalar or Series) will be
        applied additionally to the Socket's set activity (acting as 'and')
        """

        activity = self._activity
        if overlay is not None:
            assert self._is_valid_activity(activity=overlay)
            activity = activity * overlay

        if self.link._flow_location is self:
            if isinstance(activity, bool) and not activity:
                self.flow.total = 0
            elif isinstance(activity, pd.Series):
                self.flow.timeseries = self.flow.timeseries * activity.astype(int)  # FIXME still valid for temporals?
        if reset_activity:
            self._activity = True

    def __repr__(self):
        if self.medium is not None:
            return f"{self.__class__.__name__}(id={self.id}, medium='{self.medium}')"
        else:
            return f"{self.__class__.__name__}(id={self.id})"


class Component(Object):

    # children attributes:
    _CHILDREN_ATTRIBUTES = {
        "_input_sockets": "Socket[]",
        "_output_sockets": "Socket[]",
    }
    _input_sockets: list[Socket] = None
    _output_sockets: list[Socket] = None

    # temporal attributes:
    _TEMPORAL_DICT_ATTRIBUTES = ["_input_factors", "_output_factors"]
    _input_factors: dict[int, Temporal] = None
    _output_factors: dict[int, Temporal] = None

    # additional attributes:
    _activity: pd.Series | bool = True

    def __init__(
        self,
        inputs: list[Socket | Medium | Component] = None,
        outputs: list[Socket | Medium | Component] = None,
        input_sockets: list[Socket] = None,
        output_sockets: list[Socket] = None,
        **kwargs,
    ):
        """
        Parameters
        ----------
        - `inputs`: List of Mediums, Components, or Sockets that have another
        Component set as parent. Will be added as inputs (creating new sockets)
        - `outputs`: List of Mediums, Components, or Sockets that have another
        Component set as parent. Will be added as outputs (creating new sockets)
        - `input_sockets`: List of Sockets without a parent set that will be
        directly added as input_sockets (i.e. children) to the new Component
        - `output_sockets`: List of Sockets without a parent set that will be
        directly added as output_sockets (i.e. children) to the new Component
        """
        self._input_sockets = []
        self._output_sockets = []
        super().__init__(**kwargs)
        if inputs is not None:
            for input in inputs:
                self.add_input(input)
        if outputs is not None:
            for output in outputs:
                self.add_output(output)
        if input_sockets is not None:
            for input_socket in input_sockets:
                self.add_input_socket(input_socket)
        if output_sockets is not None:
            for output_socket in output_sockets:
                self.add_output_socket(output_socket)

    @property
    def energy_system(self) -> EnergySystem | None:
        return self.get_closest_ancestor_of_type(om.EnergySystem, not_found="none")

    @property
    def acitvity(self) -> bool | pd.Series:
        return self._activity

    @acitvity.setter
    def activity(self, activity: bool | pd.Series):
        if not self._is_valid_activity(activity=activity):
            raise TypeError()
        self._activity = activity

    @property
    def sockets(self) -> list[Socket]:
        return [*self._input_sockets, *self._output_sockets]

    @property
    def input_sockets(self) -> list[Socket]:
        return [*self._input_sockets]

    @property
    def output_sockets(self) -> list[Socket]:
        return [*self._output_sockets]

    @property
    def input_flows(self) -> list[Temporal | None]:
        return [x.flow for x in self._input_sockets]

    @property
    def output_flows(self) -> list[Temporal | None]:
        return [x.flow for x in self._output_sockets]

    @property
    def is_source(self) -> bool:
        return len(self._input_sockets) == 0

    @property
    def is_sink(self) -> bool:
        return len(self._output_sockets) == 0

    @property
    def is_intermediate(self) -> bool:
        return len(self._input_sockets) > 0 and len(self._output_sockets) > 0

    @classmethod
    def _get_sockets(
        cls,
        candidates: list[Socket],
        at: Socket | Medium | Component | None = None,
        medium_considered: MediumLocation = "socket",
        medium_relation: MediumRelation = "exact",
    ):
        """
        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        if len(candidates) == 0:
            return []

        elif isinstance(at, Socket) and at in candidates:
            return [at]

        elif isinstance(at, Medium):
            candidate_mediums = [s.get_medium(medium_considered=medium_considered) for s in candidates]

            if medium_relation == "exact":
                return [s for s, m in zip(candidates, candidate_mediums) if m is at]
            else:
                mm = MediumManager()
                if medium_relation == "socket_specifies":
                    return [s for s, m in zip(candidates, candidate_mediums) if mm.specifies(m, at, True)]
                elif medium_relation == "socket_generalizes":
                    return [s for s, m in zip(candidates, candidate_mediums) if mm.generalizes(m, at, True)]
                elif medium_relation == "linear":
                    return [s for s, m in zip(candidates, candidate_mediums) if mm.is_linear(m, at, True)]
                else:
                    raise ValueError()

        elif isinstance(at, Component):
            return [s for s in candidates if s._other is not None and s._other.parent is at]

        elif at is None:
            return candidates

        else:
            raise TypeError()

    def get_input_sockets(
        self,
        at: Socket | Medium | Component | None = None,
        medium_considered: MediumLocation = "socket",
        medium_relation: MediumRelation = "exact",
    ) -> list[Socket]:
        """
        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        return self._get_sockets(
            candidates=self._input_sockets,
            at=at,
            medium_relation=medium_relation,
            medium_considered=medium_considered,
        )

    def get_output_sockets(
        self,
        at: Socket | Medium | Component | None = None,
        medium_considered: MediumLocation = "socket",
        medium_relation: MediumRelation = "exact",
    ) -> list[Socket]:
        """
        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        return self._get_sockets(
            candidates=self._output_sockets,
            at=at,
            medium_relation=medium_relation,
            medium_considered=medium_considered,
        )

    def get_sockets(
        self,
        at: Socket | Medium | Component | None = None,
        medium_relation: MediumRelation = "exact",
        medium_considered: MediumLocation = "socket",
    ) -> list[Socket]:
        """
        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        return self._get_sockets(
            candidates=self.sockets,
            at=at,
            medium_relation=medium_relation,
            medium_considered=medium_considered,
        )

    def get_input_socket(
        self,
        at: Socket | Medium | Component | None = None,
        medium_relation: MediumRelation = "exact",
        medium_considered: MediumLocation = "socket",
    ) -> Socket | None:
        """
        Will raise an Exception if multiple sockets match the description. Will
        return None if no such socket exists.

        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        ret = self.get_input_sockets(at=at, medium_relation=medium_relation, medium_considered=medium_considered)
        if len(ret) > 1:
            raise Exception("Multiple Sockets found that match the description")
        elif len(ret) == 1:
            return ret[0]

    def get_output_socket(
        self,
        at: Socket | Medium | Component | None = None,
        medium_relation: MediumRelation = "exact",
        medium_considered: MediumLocation = "socket",
    ) -> Socket | None:
        """
        Will raise an Exception if multiple sockets match the description. Will
        return None if no such socket exists.

        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        ret = self.get_output_sockets(
            at=at,
            medium_relation=medium_relation,
            medium_considered=medium_considered,
        )
        if len(ret) > 1:
            raise Exception("Multiple Sockets found that match the description")
        elif len(ret) == 1:
            return ret[0]

    def get_socket(
        self,
        at: Socket | Medium | Component | None = None,
        medium_relation: MediumRelation = "exact",
        medium_considered: MediumLocation = "socket",
    ) -> Socket | None:
        """
        Will raise an Exception if multiple sockets match the description. Will
        return None if no such socket exists.

        Parameters
        ----------
        - `medium_considered`: The Medium used as comparison for filtering the
        candidate sockets. Only effective if `x` is a Medium.
            - "socket": The explicit Medium in the socket will be used.
            - "link": The common super Medium of the socket and it's `other`
            will be used.
        - `medium_relation`: The relation between `x` and the comparison Medium
        of the socket or link.
            - "exact": All candidates with differing Mediums will be discared.
            - "socket_specifies": All candidates with a more general Medium
            will be discarded.
            - "socket_generalizes": All candidates with a more specific Medium
            will be discarded.
            - "linear": All candidates returned that generalize or specify `x`
            (including the same Medium).
        """
        ret = self.get_sockets(
            at=at,
            medium_relation=medium_relation,
            medium_considered=medium_considered,
        )
        if len(ret) > 1:
            raise Exception("Multiple Sockets found that match the description")
        elif len(ret) == 1:
            return ret[0]

    @property
    def input_socket(self) -> Socket | None:
        return self.get_input_socket()

    @property
    def output_socket(self) -> Socket | None:
        return self.get_output_socket()

    def get_input_flow(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal | None:
        s = self.get_input_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        return s.flow

    def get_output_flow(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal | None:
        s = self.get_output_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        return s.flow

    def get_flow(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal | None:
        s = self.get_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        return s.flow

    @property
    def input_flow(self) -> Temporal | None:
        """
        The input flow of the only input socket. Shorthand for `get_input_flow()`
        """
        return self.get_input_flow()

    @property
    def output_flow(self) -> Temporal | None:
        """
        The output flow of the only output socket. Shorthand for `get_output_flow()`
        """
        return self.get_output_flow()

    @property
    def input_flow_electric(self) -> Temporal | None:
        """
        The input flow of the only input socket using electricity.
        """
        return self.get_input_flow(at=Medium.ELECTRIC_ENERGY)

    @property
    def input_flow_thermal(self) -> Temporal | None:
        """
        The input flow of the only input socket using thermal energy
        (Medium.THERMAL_ENERGY or any inheriting medium).
        """
        return self.get_input_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
            medium_considered="link",
        )

    @property
    def output_flow_electric(self) -> Temporal | None:
        """
        The output flow of the only output socket using electricity.
        """
        return self.get_output_flow(at=Medium.ELECTRIC_ENERGY)

    @property
    def output_flow_thermal(self) -> Temporal | None:
        """
        The output flow of the only output socket using thermal energy
        (Medium.THERMAL_ENERGY or any inheriting medium).
        """
        return self.get_output_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
            medium_considered="link",
        )

    def get_input_factor(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal:
        s = self.get_input_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        index = self._input_sockets.index(s)
        return self._input_factors[index]

    def get_output_factor(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal:
        s = self.get_output_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        index = self._output_sockets.index(s)
        return self._output_factors[index]

    def get_factor(
        self,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ) -> Temporal:
        s = self.get_socket(at=at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        if s in self._input_sockets:
            index = self._input_sockets.index(s)
            return self._input_factors[index]
        elif s in self._output_sockets:
            index = self._output_sockets.index(s)
            return self._output_factors[index]

    def get_input_mediums(self, medium_considered: MediumLocation = "socket") -> list[Medium]:
        """
        Get a list of unique input mediums.
        """
        return list(set(s.get_medium(medium_considered=medium_considered) for s in self._input_sockets))

    def get_output_mediums(self, medium_considered: MediumLocation = "socket") -> list[Medium]:
        """
        Get a list of unique output mediums.
        """
        return list(set(s.get_medium(medium_considered=medium_considered) for s in self._output_sockets))

    @property
    def input_components(self) -> list["Component"]:
        """
        Duplicate-free list of input Components.
        """
        return list(set([x.other.parent for x in self._input_sockets if x.other is not None]))

    @property
    def output_components(self) -> list["Component"]:
        """
        Duplicate-free list of input Components.
        """
        return list(set([x.other.parent for x in self._output_sockets if x.other is not None]))

    @property
    def input(self) -> Component | None:
        """
        Return the component, if present, of the only input socket.

        Will raise an Exception if the Component has more than one input sockets.
        """
        if len(self._input_sockets) > 1:
            raise Exception()
        components = self.input_components
        if components:
            return components[0]

    @property
    def output(self) -> Component | None:
        """
        Return the component, if present, of the only output socket.

        Will raise an Exception if the Component has more than one output sockets.
        """
        if len(self._output_sockets) > 1:
            raise Exception()
        components = self.output_components
        if components:
            return components[0]

    @property
    def components(self) -> list["Component"]:
        """
        Duplicate-free list of input and output Components.
        """
        return list(set([x.other.parent for x in self.sockets if x.other is not None]))

    @property
    def following_components(self) -> list["Component"]:
        """
        Duplicate-free list of output Components, their output Components and
        so on.

        Will contain `self` only if it's part of a loop.
        """
        seen = []
        return list(set(self._linked_components(seen=seen, outputs=True, inputs=False)))

    @property
    def previous_components(self) -> list["Component"]:
        """
        Duplicate-free list of input Components, their input Components and
        so on.

        Will contain `self` only if it's part of a loop.
        """
        seen = []
        return list(set(self._linked_components(seen=seen, outputs=False, inputs=True)))

    @property
    def linked_components(self) -> list["Component"]:
        """
        Duplicate-free list of all Components that are linked (via input and
        output Components), recursively.

        Will contain `self`
        """
        seen = []
        return list(set(self._linked_components(seen=seen, outputs=True, inputs=True)) | set([self]))

    def find_following_components(self, type: Type["Component"]) -> list["Component"]:
        """
        Find all following components of a specific type.
        """
        return [c for c in self.following_components if isinstance(c, type)]

    def find_previous_components(self, type: Type["Component"]) -> list["Component"]:
        """
        Find all previous components of a specific type.
        """
        return [c for c in self.previous_components if isinstance(c, type)]

    def find_linked_components(self, type: Type["Component"]) -> list["Component"]:
        """
        Find all linked components of a specific type.
        """
        return [c for c in self.linked_components if isinstance(c, type)]

    def _linked_components(self, inputs: bool, outputs: bool, seen: list["Component"]) -> list["Component"]:
        seen.append(self)
        ret = []
        components = []
        if inputs:
            components += self.input_components
        if outputs:
            components += self.output_components
        for c in components:
            ret.append(c)
            if c not in seen:
                ret += c._linked_components(seen=seen, inputs=inputs, outputs=outputs)
        return ret

    def add_input_socket(self, socket: Socket, factor: pd.Series | Number | None = 1.0):
        """
        Add a (parent-less) Socket to the Component. The socket might already
        have `other`, `flow` or `medium` set.
        """
        assert isinstance(socket, Socket)
        assert socket.parent is None
        if socket.other is not None and socket.other.is_input_socket:
            msg = (
                "When adding an input socket that is already linked to ",
                "another socket, the other socket must be the output socket ",
                "of another component.",
            )
            raise Exception("".join(msg))
        self._input_sockets.append(socket)
        self._set_factor(socket=socket, factor=factor)
        socket._set_parent(self)

    def add_output_socket(self, socket: Socket, factor: pd.Series | Number | None = 1.0):
        """
        Add a (parent-less) Socket to the Component. The socket might already
        have `other`, `flow` or `medium` set.
        """
        assert isinstance(socket, Socket)
        assert socket.parent is None
        if socket.other is not None and socket.other.is_output_socket:
            msg = (
                "When adding an output socket that is already linked to ",
                "another socket, the other socket must be the input socket ",
                "of another component.",
            )
            raise Exception("".join(msg))
        self._output_sockets.append(socket)
        self._set_factor(socket=socket, factor=factor)
        socket._set_parent(self)

    def add_input(
        self,
        new: Socket | Medium | Component | None,
        medium: Medium = None,
        flow: Temporal = None,
        factor: pd.Series | Number | None = 1.0,
    ) -> Socket:
        """
        Add a Component, the Socket of another Component, or a Medium as an
        input

        Parameters
        ----------
        - `new`:
            - Type Socket: A socket that has another Component as parent. On
            this Component (`self`), a new socket will be added that will
            receive `new` as other. The Socket on this Component will receive
            `medium` and `flow`.
            - Type Medium: A new abstract Socket will be created with the
            indicated data.
            - Type Component: On both this component and on `new`, a new Socket
            will be created, which will be linked. The Socket on this Component
            will receive `medium` and `flow`.
        """
        if isinstance(new, Socket):
            assert isinstance(new.parent, Component) and new.parent is not self
            this_socket = Socket(medium=medium, flow=flow)
            self.add_input_socket(socket=this_socket, factor=factor)
            this_socket.other = new

        elif isinstance(new, Medium):
            assert medium is None
            this_socket = Socket(medium=new, flow=flow)
            self.add_input_socket(socket=this_socket, factor=factor)

        elif isinstance(new, Component):
            this_socket = Socket(medium=medium, flow=flow)
            self.add_input_socket(socket=this_socket, factor=factor)
            new.add_output(new=this_socket)

        elif new is None:
            this_socket = Socket()
            self.add_input_socket(socket=this_socket, factor=factor)

        else:
            raise TypeError()

        return this_socket

    def add_output(
        self,
        new: Socket | Medium | Component | None,
        medium: Medium = None,
        flow: Temporal = None,
        factor: pd.Series | Number | None = 1.0,
    ) -> Socket:
        """
        Add a Component, the Socket of another Component, or a Medium as an
        output

        Parameters
        ----------
        - `new`:
            - Type Socket: A socket that has another Component as parent. On
            this Component (`self`), a new socket will be added that will
            receive `new` as other. The Socket on this Component will receive
            `medium` and `flow`.
            - Type Medium: A new abstract Socket will be created with the
            indicated data.
            - Type Component: On both this component and on `new`, a new Socket
            will be created, which will be linked. The Socket on this Component
            will receive `medium` and `flow`.
        """
        if isinstance(new, Socket):
            assert isinstance(new.parent, Component) and new.parent is not self
            this_socket = Socket(medium=medium, flow=flow)
            self.add_output_socket(socket=this_socket, factor=factor)
            this_socket.other = new

        elif isinstance(new, Medium):
            assert medium is None
            this_socket = Socket(medium=new, flow=flow)
            self.add_output_socket(socket=this_socket, factor=factor)

        elif isinstance(new, Component):
            this_socket = Socket(medium=medium, flow=flow)
            self.add_output_socket(socket=this_socket, factor=factor)
            new.add_input(new=this_socket)

        elif new is None:
            this_socket = Socket()
            self.add_output_socket(socket=this_socket, factor=factor)

        else:
            raise TypeError()

        return this_socket

    def remove_input(self, at: Socket | Medium | Component | None = None, **kwargs):
        """
        Remove the Socket indicated by `x`. This will also dissolve the link
        between `x` and `x.other`, if set.
        """
        s = self.get_input_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.remove_other()
        s.remove_from_parent()
        assert s not in self._input_sockets
        # self._input_sockets.remove(s) # kg 9.2.26 -> socket already removed in s.remove_from_parent()

    def remove_output(self, at: Socket | Medium | Component | None = None, **kwargs):
        """
        Remove the Socket indicated by `x`. This will also dissolve the link
        between `x` and `x.other`, if set.
        """
        s = self.get_output_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.remove_other()
        s.remove_from_parent()
        assert s not in self._output_sockets
        # self._output_sockets.remove(s) # kg 9.2.26 -> socket already removed in s.remove_from_parent()

    def set_input(
        self,
        new: Socket | Medium | Component,
        at: Socket | Medium | Component | None = None,
        medium: Medium = None,
        flow: Temporal = None,
        factor: pd.Series | Number = None,
        **kwargs,
    ):
        """
        Replace an existing input at the Socket described by `at` with `new`.

        Parameters
        ----------
        - `new`: The input to connect
            - if it's a Medium, this will create an abstract Socket.
            - if it's a Socket, it has to be the Socket of another Component. On
            this Component (self), the Socket indicated by `at` will be updated
            so that it is linked with `new`.
            - if it's a Component, on `new`, a new Socket will be created that
            will be used for the connection.
        - `at`: The description of the Socket that is to be replaced.
        """
        s = self.get_input_socket(at=at, **kwargs)
        if s is None:
            msg = (
                "No appropriate Socket found. Hints: - Did you mean to call",
                "add_output()? - Did you falsely pass `medium` instead of",
                "`at`?",
            )
            raise ValueError(" ".join(msg))

        if isinstance(new, Socket):
            assert new not in self.sockets
            s.other = new
            if medium is not None:
                s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        elif isinstance(new, Medium):
            assert medium is None
            s.remove_other()
            s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        elif isinstance(new, Component):
            other_socket = Socket()
            new.add_output_socket(other_socket)
            s.other = other_socket
            if medium is not None:
                s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        else:
            raise TypeError()

    def set_output(
        self,
        new: Socket | Medium | Component,
        at: Socket | Medium | Component | None = None,
        medium: Medium = None,
        flow: Temporal = None,
        factor: pd.Series | Number = None,
        **kwargs,
    ):
        """
        Replace an existing output at the Socket described by `at` with `new`.

        Parameters
        ----------
        - `new`: The output to connect
            - if it's a Medium, this will create an abstract Socket.
            - if it's a Socket, it has to be the Socket of another Component. On
            this Component (self), the Socket indicated by `at` will be updated
            so that it is linked with `new`.
            - if it's a Component, on `new`, a new Socket will be created that
            will be used for the connection.
        - `at`: The description of the Socket that is to be replaced.
        """
        s = self.get_output_socket(at=at, **kwargs)
        if s is None:
            msg = (
                "No appropriate Socket found. Hints: - Did you mean to call",
                "add_input()? - Did you falsely pass `medium` instead of",
                "`at`?",
            )
            raise ValueError(" ".join(msg))

        if isinstance(new, Socket):
            assert new not in self.sockets
            s.other = new
            if medium is not None:
                s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        elif isinstance(new, Medium):
            assert medium is None
            s.remove_other()
            s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        elif isinstance(new, Component):
            other_socket = Socket()
            new.add_input_socket(other_socket)
            s.other = other_socket
            if medium is not None:
                s.medium = medium
            if flow is not None:
                s.flow = flow
            if factor is not None:
                self._set_factor(s, factor)

        else:
            raise TypeError()

    def set_input_flow(
        self,
        flow: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ):
        s = self.get_input_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.flow = flow  # will check validity

    def set_output_flow(
        self,
        flow: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ):
        s = self.get_output_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.flow = flow  # will check validity

    @input_flow.setter
    def input_flow(self, flow: Temporal | Number | pd.Series | None):
        """
        The input flow of the only input socket. Shorthand for `set_input_flow()`
        """
        return self.set_input_flow(flow=flow)

    @output_flow.setter
    def output_flow(self, flow: Temporal | Number | pd.Series | None):
        """
        The output flow of the only output socket. Shorthand for `set_output_flow()`
        """
        return self.set_output_flow(flow=flow)

    @input_flow_electric.setter
    def input_flow_electric(self, flow: Temporal | Number | pd.Series | None):
        """
        The input flow of the only input socket using electricity.
        """
        self.set_input_flow(at=Medium.ELECTRIC_ENERGY, flow=flow)

    @input_flow_thermal.setter
    def input_flow_thermal(self, flow: Temporal | Number | pd.Series | None):
        """
        The input flow of the only input socket using thermal energy
        (Medium.THERMAL_ENERGY or any inheriting medium).
        """
        self.set_input_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
            medium_considered="link",
            flow=flow,
        )

    @output_flow_electric.setter
    def output_flow_electric(self, flow: Temporal | Number | pd.Series | None):
        """
        The output flow of the only output socket using electricity.
        """
        self.set_output_flow(at=Medium.ELECTRIC_ENERGY, flow=flow)

    @output_flow_thermal.setter
    def output_flow_thermal(self, flow: Temporal | Number | pd.Series | None):
        """
        The output flow of the only output socket using thermal energy
        (Medium.THERMAL_ENERGY or any inheriting medium).
        """
        self.set_output_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
            medium_considered="link",
            flow=flow,
        )

    def set_input_factor(
        self,
        factor: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ):
        s = self.get_input_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        self._set_factor(s, factor=factor)

    def set_output_factor(
        self,
        factor: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = None,
        **kwargs,
    ):
        s = self.get_output_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        self._set_factor(s, factor=factor)

    def set_factor(self, factor: Temporal | Number | pd.Series | None):
        s = self.get_socket(at=None)
        if s is None:
            raise ValueError("No appropriate Socket found")
        self._set_factor(s, factor=factor)

    def _set_factor(self, socket: Socket, factor: Temporal | Number | pd.Series | None):
        if not self._is_valid_factor(factor):
            raise ValueError("Not a valid factor")
        if socket in self._input_sockets:
            index = self._input_sockets.index(socket)
            self.set_temporal(attr="_input_factors", x=factor, key=index, error_if_values_below=-0.0001)
        elif socket in self._output_sockets:
            index = self._output_sockets.index(socket)
            self.set_temporal(attr="_output_factors", x=factor, key=index, error_if_values_below=-0.0001)
        else:
            raise ValueError("Socket not part of this Component")

    @classmethod
    def _is_valid_factor(cls, factor: Any) -> bool:
        valid = True
        if isinstance(factor, Number):
            if factor < 0:
                valid = False
        elif isinstance(factor, pd.Series):
            pass  # could check length etc.
        elif isinstance(factor, Temporal):
            pass
            # TODO muss hier noch was überprüft werden?
        elif factor is not None:
            valid = False
        return valid

    def _is_valid_activity(self, activity: Any) -> bool:
        return _is_valid_activity(activity=activity, validity_index=self.timeindex)

    def get_common_medium(self) -> Medium | None:
        """
        Calculate the closest common unifying Medium of all inputs and outputs
        that have a Medium specified.
        Will return None if no Socket has a Medium specified, or if there is no
        common super.
        """
        mediums = [s.medium for s in self.sockets]
        mediums = list(set(mediums))
        mm = MediumManager()
        if mediums:
            return mm.closest_common_super_multi(mediums=mediums)

    def get_link(
        self,
        at: Socket | Medium | Component,
        direction: Literal["input", "output", "both"] = "both",
        **kwargs,
    ) -> Link | None:
        if direction == "input":
            s = self.get_input_socket(at, **kwargs)
        elif direction == "output":
            s = self.get_output_socket(at, **kwargs)
        else:
            s = self.get_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        return s.link

    def get_links(self) -> list[Link]:
        ret = []
        for s in self.sockets:
            ret.append(s.link)
        return ret

    def get_input_links(self) -> list[Link]:
        ret = []
        for s in self.input_sockets:
            ret.append(s.link)
        return ret

    def get_output_links(self) -> list[Link]:
        ret = []
        for s in self.output_sockets:
            ret.append(s.link)
        return ret

    def apply_activity(self, reset_activity: bool = False):
        """
        Apply the activity of the Component and its Sockets by setting all flows
        to 0 (if activity is not a series), or by setting all timesteps to 0
        where activity is False.

        If present, use the attributes `self.activity` and `<Socket>.activity`
        per socket to set the flows.

        If `self.activity` is given, for all timesteps with `False`, all input
        and output flows will be set to 0.

        If for a socket, `<Socket>.activity` is given, for all timesteps with
        `False`, the socket's flow will be set to 0.

        Parameters
        ----------
        - `reset_activity`: If True, after applying the activity of Component
        and Sockets, they will be reset to True.
        """
        for s in self.sockets:
            s.apply_activity(overlay=self._activity, reset_activity=reset_activity)

    def get_closest_socket_pair(
        self,
        input: "Component" = None,
        output: "Component" = None,
        medium_considered: MediumLocation = "socket",
        ignore_missing_mediums: bool = False,
        if_multiple: Literal["exception", "first"] = "exception",
    ) -> tuple[Socket, Socket] | None:
        """
        Get the pair of closest sockets either between self and `input`, or
        between self and `output`, by looking at their medium distance.

        Parameters
        ----------
        - `ignore_missing_mediums`: If True, a missing Medium in a Socket will
        make this Socket a perfect match for any other Socket. If False, it will
        be the worst match.
        """

        assert input is None or output is None
        assert isinstance(input, Component) or isinstance(output, Component)

        distances: dict[Tuple[Socket, Socket], int] = {}

        if input is not None:
            sockets_of_other = input.output_sockets
            sockets_of_self = self.input_sockets
            other = input
        else:
            sockets_of_other = output.input_sockets
            sockets_of_self = self.output_sockets
            other = output

        for socket_of_other in sockets_of_other:

            for socket_of_self in sockets_of_self:

                if medium_considered == "link":
                    medium_of_self = self.get_link(socket_of_self)
                    medium_of_other = other.get_link(socket_of_other)
                elif medium_considered == "socket":
                    medium_of_self = socket_of_self.medium
                    medium_of_other = socket_of_other.medium

                if medium_of_self is None or medium_of_other is None:
                    if ignore_missing_mediums:
                        distances[(socket_of_self, socket_of_other)] = math.inf
                    else:
                        distances[(socket_of_self, socket_of_other)] = 0
                else:
                    d = MediumManager().superiority(medium1=medium_of_self, medium2=medium_of_other)
                    distances[(socket_of_self, socket_of_other)] = abs(d) if d is not None else math.inf

        min_distance = min(distances.values())
        min_pairs = [k for k, v in distances.items() if v == min_distance]
        if min_distance < math.inf:
            if len(min_pairs) == 1:
                return min_pairs[0]
            elif len(min_pairs) > 1:
                if if_multiple == "exception":
                    raise Exception()
                elif if_multiple == "first":
                    return min_pairs[0]
                else:
                    raise ValueError()

    def __repr__(self):
        id_str = f"id={self.id}"
        input_str = f", in={len(self.input_components)}/{len(self.input_sockets)}" if len(self.input_sockets) else ""
        output_str = (
            f", out={len(self.output_components)}/{len(self.output_sockets)}" if len(self.output_sockets) else ""
        )
        return f"{self.__class__.__name__}({id_str}{input_str}{output_str}')"


class FixedComponent(Component):

    # additional attributes:
    _INPUT_MEDIUMS: list[Medium] = None
    _OUTPUT_MEDIUMS: list[Medium] = None
    __fixed: bool = False

    def __init__(self, **kwargs):
        super().__init__(inputs=self._INPUT_MEDIUMS, outputs=self._OUTPUT_MEDIUMS, **kwargs)
        self.__fixed = True

    # overrides super method
    def add_input_socket(self, socket: Socket, factor: pd.Series | Number | None = 1.0):
        if self.__fixed:
            raise Exception("Can't add Sockets for a FixedComponent. Did you mean to call set_input()?")
        super().add_input_socket(socket=socket, factor=factor)

    # overrides super method
    def add_output_socket(self, socket: Socket, factor: pd.Series | Number | None = 1.0):
        if self.__fixed:
            raise Exception("Can't add Sockets for a FixedComponent. Did you mean to call set_output()?")
        super().add_output_socket(socket=socket, factor=factor)

    # overrides super method
    def remove_input(self, at: Socket | Medium | Component | None = None, **kwargs):
        """
        If the socket indicated by `at` is not abstract, the Link will be
        dissolved, making both involved Sockets abstract afterwards. The
        number of Sockets of the Component(s) won't change.
        """
        s = self.get_input_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.remove_other()

    # overrides super method
    def remove_output(self, at: Socket | Medium | Component | None = None, **kwargs):
        """
        If the socket indicated by `at` is not abstract, the Link will be
        dissolved, making both involved Sockets abstract afterwards. The
        number of Sockets of the Component(s) won't change.
        """
        s = self.get_output_socket(at, **kwargs)
        if s is None:
            raise ValueError("No appropriate Socket found")
        s.remove_other()


class ThermalComponent(Component):
    """
    A component that can have at least one input or output flow of a thermal
    medium
    """

    # temporal attributes:
    _TEMPORAL_DICT_ATTRIBUTES = ["_flow_temperature_forward", "_flow_temperature_return"]
    _flow_temperature_forward: dict[Socket, Temporal] = None  # [°C]
    _flow_temperature_return: dict[Socket, Temporal] = None  # [°C]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_flow_temperature(
        self,
        direction: Literal["forward", "return"],
        at: Socket | Medium | Component | None = Medium.THERMAL_ENERGY,
        symmetric: bool = False,
    ) -> Temporal:

        socket = self.get_socket(at=at, medium_relation="socket_specifies", medium_considered="link")

        if socket is None:
            raise Exception("No appropriate Socket found")

        elif direction == "forward":
            ret = self.get_dict_temporal(attr="_flow_temperature_forward", key=socket)  # might add empty temporal
            if (
                ret.is_empty
                and symmetric
                and socket.other is not None
                and socket.other.parent is not None
                and isinstance(socket.other.parent, ThermalComponent)
            ):
                ret = socket.other.parent.get_flow_forward_temperature(at=socket.other, symmetric=False)
            return ret

        elif direction == "return":
            ret = self.get_dict_temporal(attr="_flow_temperature_return", key=socket)  # might add empty temporal
            if (
                ret.is_empty
                and symmetric
                and socket.other is not None
                and socket.other.parent is not None
                and isinstance(socket.other.parent, ThermalComponent)
            ):
                ret = socket.other.parent.get_flow_return_temperature(at=socket.other, symmetric=False)
            return ret

        else:
            raise ValueError()

    def get_flow_forward_temperature(
        self,
        at: Socket | Medium | Component | None = Medium.THERMAL_ENERGY,
        symmetric: bool = False,
    ) -> Temporal:
        """
        Get the forward temperature of the flow described by `at`. While this
        would logically require that the corresponding flow is thermal, this
        isn't checked or ensured.

        If `at` describes an input socket, the forward temperature is the
        temperature of the flow *entering* the component. If `at` describes an
        output socket, the forward temperature is the temperature of the flow
        *leaving* the component.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        - `symmetric`: If no flow temperature is stored in this component and
        a component is connected at the other end of the flow, lookup the
        temperature from
        """
        return self._get_flow_temperature(direction="forward", at=at, symmetric=symmetric)

    def get_flow_return_temperature(
        self,
        at: Socket | Medium | Component | None = Medium.THERMAL_ENERGY,
        symmetric: bool = False,
    ) -> Temporal:
        """
        Get the return temperature of the flow described by `at`. While this
        would logically require that the corresponding flow is thermal, this
        isn't checked or ensured.

        If `at` describes an input socket, the return temperature is the
        temperature of the flow *leaving* the component. If `at` describes an
        output socket, the return temperature is the temperature of the flow
        *entering* the component.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        - `symmetric`: If no flow temperature is stored in this component and
        a component is connected at the other end of the flow, lookup the
        temperature from
        """
        return self._get_flow_temperature(direction="return", at=at, symmetric=symmetric)

    def _set_flow_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
        direction: Literal["forward", "return"],
        at: Socket | Medium | Component | None = None,
        symmetric: bool = False,
    ) -> Temporal | None:
        socket = self.get_socket(at=at, medium_relation="socket_specifies", medium_considered="link")

        if socket is None:
            raise Exception("No appropriate Socket found")

        elif direction == "forward":
            self.set_temporal(
                attr="_flow_temperature_forward",
                x=flow_temperature,
                key=socket,
            )
            if (
                symmetric
                and socket.other is not None
                and socket.other.parent is not None
                and isinstance(socket.other.parent, ThermalComponent)
            ):
                socket.other.parent.set_flow_forward_temperature(
                    flow_temperature=None, at=socket.other, symmetric=False
                )
            else:
                return

        elif direction == "return":
            self.set_temporal(
                attr="_flow_temperature_return",
                x=flow_temperature,
                key=socket,
            )
            if (
                symmetric
                and socket.other is not None
                and socket.other.parent is not None
                and isinstance(socket.other.parent, ThermalComponent)
            ):
                socket.other.parent.set_flow_return_temperature(
                    flow_temperature=None,
                    at=socket.other,
                    symmetric=False,
                )
            else:
                return

        else:
            raise ValueError()

    def set_flow_forward_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = Medium.THERMAL_ENERGY,
        symmetric: bool = False,
    ) -> Temporal | None:
        """
        Set the forward temperature of the flow described by `at`. While this
        would logically require that the corresponding flow is thermal, this
        isn't checked or ensured.

        If `at` describes an input socket, the forward temperature is the
        temperature of the flow *entering* the component. If `at` describes an
        output socket, the forward temperature is the temperature of the flow
        *leaving* the component.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        - `symmetric`: If no flow temperature is stored in this component and
        a component is connected at the other end of the flow, lookup the
        temperature from
        """
        self._set_flow_temperature(
            flow_temperature=flow_temperature,
            direction="forward",
            at=at,
            symmetric=symmetric,
        )

    def set_flow_return_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
        at: Socket | Medium | Component | None = Medium.THERMAL_ENERGY,
        symmetric: bool = False,
    ) -> Temporal | None:
        """
        Set the return temperature of the flow described by `at`. While this
        would logically require that the corresponding flow is thermal, this
        isn't checked or ensured.

        If `at` describes an input socket, the return temperature is the
        temperature of the flow *leaving* the component. If `at` describes an
        output socket, the return temperature is the temperature of the flow
        *entering* the component.

        Parameters
        ----------
        - `socket`: If the Device has more than one socket (input + output), the
        socket must be specified, otherwise None can be used
        - `symmetric`: If no flow temperature is stored in this component and
        a component is connected at the other end of the flow, lookup the
        temperature from
        """
        self._set_flow_temperature(
            flow_temperature=flow_temperature,
            direction="return",
            at=at,
            symmetric=symmetric,
        )

    @property
    def input_forward_temperature(self) -> Temporal:
        """
        The forward flow temperature of the only input of Medium.THERMAL_ENERGY.
        """
        return self.get_flow_forward_temperature(
            at=self.get_input_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            )
        )

    @property
    def input_return_temperature(self) -> Temporal:
        """
        The return flow temperature of the only input of Medium.THERMAL_ENERGY.
        """
        return self.get_flow_return_temperature(
            at=self.get_input_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            )
        )

    @property
    def output_forward_temperature(self) -> Temporal:
        """
        The forward flow temperature of the only output of Medium.THERMAL_ENERGY.
        """
        return self.get_flow_forward_temperature(
            at=self.get_output_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            )
        )

    @property
    def output_return_temperature(self) -> Temporal:
        """
        The return flow temperature of the only output of Medium.THERMAL_ENERGY.
        """
        return self.get_flow_return_temperature(
            at=self.get_output_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            )
        )

    @input_forward_temperature.setter
    def input_forward_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
    ):
        """
        The forward flow temperature of the only input of Medium.THERMAL_ENERGY.
        """
        return self.set_flow_forward_temperature(
            flow_temperature=flow_temperature,
            at=self.get_input_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            ),
        )

    @input_return_temperature.setter
    def input_return_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
    ):
        """
        The return flow temperature of the only input of Medium.THERMAL_ENERGY.
        """
        return self.set_flow_return_temperature(
            flow_temperature=flow_temperature,
            at=self.get_input_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            ),
        )

    @output_forward_temperature.setter
    def output_forward_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
    ):
        """
        The forward flow temperature of the only output of Medium.THERMAL_ENERGY.
        """
        return self.set_flow_forward_temperature(
            flow_temperature=flow_temperature,
            at=self.get_output_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            ),
        )

    @output_return_temperature.setter
    def output_return_temperature(
        self,
        flow_temperature: Temporal | Number | pd.Series | None,
    ):
        """
        The return flow temperature of the only output of Medium.THERMAL_ENERGY.
        """
        return self.set_flow_return_temperature(
            flow_temperature=flow_temperature,
            at=self.get_output_socket(
                at=Medium.THERMAL_ENERGY,
                medium_considered="socket_else_link",
                medium_relation="socket_specifies",
            ),
        )

    @property
    def thermal_input_flow(self) -> Temporal | None:
        """
        The input flow of the only thermal input socket.
        """
        return self.get_input_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
        )

    @property
    def thermal_output_flow(self) -> Temporal | None:
        """
        The output flow of the only thermal output socket.
        """
        return self.get_output_flow(
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
        )

    @thermal_input_flow.setter
    def thermal_input_flow(self, flow: Temporal | None):
        """
        The input flow of the only thermal input socket.
        """
        return self.set_input_flow(
            flow=flow,
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
        )

    @thermal_output_flow.setter
    def thermal_output_flow(self, flow: Temporal | None):
        """
        The output flow of the only thermal output socket.
        """
        return self.set_output_flow(
            flow=flow,
            at=Medium.THERMAL_ENERGY,
            medium_relation="socket_specifies",
        )
