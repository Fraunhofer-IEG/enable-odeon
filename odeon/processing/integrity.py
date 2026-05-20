from __future__ import annotations

from ..model import (
    Branch,
    Object,
    DistrictHeatingNetwork,
    BuildingDhnConnection,
    TransferStation,
    Building,
    BuildingUnit,
    Device,
    Demand,
    Component,
    Site,
    ThermalComponent,
    Structure,
    Socket,
    MediumManager,
    Medium,
    Temporal,
    Project,
    DhnEdge,
    DhnPipe,
    Heatpump,
    Storage,
    Network,
)
from typing import Literal, Any

from dataclasses import dataclass, field

# ------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------


INDENT_PER_LEVEL = "    "
OK = "ok"
WARN = "warn"
BAD = "bad"


def _chapter_header(title: str, print_: bool = False) -> list[str]:
    strs = [
        "",
        "=" * 80,
        title,
        "=" * 80,
    ]
    if print_:
        for s in strs:
            print(s)
    return strs


def _section_header(title: str, print_: bool = False) -> list[str]:
    strs = [
        "",
        title,
        "=" * 80,
    ]
    if print_:
        for s in strs:
            print(s)
    return strs


def _subsection_header(title: str, print_: bool = False) -> list[str]:
    strs = [
        "",
        title,
        "-" * 80,
    ]
    if print_:
        for s in strs:
            print(s)
    return strs


def _record_header(title: str, print_: bool = False) -> list[str]:
    strs = [
        "",
        title,
        "-" * len(title),
    ]
    if print_:
        for s in strs:
            print(s)
    return strs


def _bool_to_str(value: bool) -> str:
    # return "✔" if value else "✘"
    return "Yes" if value else "No"


def _float_to_str(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _share_to_str(value: int, total: int, decimals: int = 1) -> str:
    if total == 0:
        return "n=0 (0.0%)"
    else:
        share = value / total * 100
        return f"n={value} ({share:.{decimals}f}%)"


def _value_to_str(value) -> str:
    if isinstance(value, bool):
        return _bool_to_str(value)
    elif isinstance(value, float):
        return _float_to_str(value)
    else:
        return str(value)


def _print_strs(strs: list[str]) -> None:
    for s in strs:
        print(s)


# ------------------------------------------------------------------------------
# Classes for checks and check records
# ------------------------------------------------------------------------------


@dataclass
class Check:
    label: str
    value: Any = None

    verdict: Literal[OK, WARN, BAD] | None = None

    # if the value is in else_check, it's interpreted as ok. Otherwise it will
    # be interpreted as check:
    else_check: Any | list[Any] | None = None

    # if the value is in else_bad, it's interpreted as ok. Otherwise it will
    # be interpreted as bad:
    else_bad: Any | list[Any] | None = None

    # if the value is in check, it's interpreted as check. Otherwise it will be
    check: Any | list[Any] | None = None

    # if the value is in bad, it's interpreted as bad. Otherwise it will be
    # interpreted as ok:
    bad: Any | list[Any] | None = None

    subs: list["Check"] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.else_check, list):
            if self.else_check is not None:
                self.else_check = [self.else_check]
            else:
                self.else_check = []
        if not isinstance(self.else_bad, list):
            if self.else_bad is not None:
                self.else_bad = [self.else_bad]
            else:
                self.else_bad = []
        if not isinstance(self.check, list):
            if self.check is not None:
                self.check = [self.check]
            else:
                self.check = []
        if not isinstance(self.bad, list):
            if self.bad is not None:
                self.bad = [self.bad]
            else:
                self.bad = []

    def get_status(self) -> str | None:
        if self.verdict is not None:
            return self.verdict
        if self.else_check:
            if self.value in self.else_check:
                return OK
            else:
                return WARN
        if self.else_bad:
            if self.value in self.else_bad:
                return OK
            else:
                return BAD
        if self.check:
            if self.value in self.check:
                return WARN
            else:
                return OK
        if self.bad:
            if self.value in self.bad:
                return BAD
            else:
                return OK

    def status_to_symbol(self, else_="  ") -> str:
        status = self.get_status()
        if status == OK:
            return "🟢"
        elif status == WARN:
            return "🟡"
        elif status == BAD:
            return "🔴"
        else:
            return else_  # emojis take two spaces

    def to_key_value_str(self) -> str:
        if self.value is not None:
            return f"{self.label}: {_value_to_str(self.value)}"
        else:
            return self.label

    def to_line_str(self, indent: int = 0) -> str:
        symbol_str = self.status_to_symbol(else_="- ")
        key_value_str = self.to_key_value_str()
        indent_str = INDENT_PER_LEVEL * indent
        return f"{indent_str}{symbol_str} {key_value_str}"

    def to_strs(self, indent: int = 0) -> list[str]:
        lines = [self.to_line_str(indent=indent)]
        for sub in self.subs:
            lines.extend(sub.to_strs(indent=indent + 1))
        return lines

    def to_series_value(self) -> Any:
        key_value_str = self.to_key_value_str()
        prefix = f"{self.label}: "
        if key_value_str.startswith(prefix):
            return key_value_str[len(prefix) :]
        return key_value_str

    def _to_series_items(self, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
        current_key = prefix + (self.label,)
        items: list[tuple[tuple[str, ...], Any]] = [(current_key, self.to_series_value())]
        for sub in self.subs:
            items.extend(sub._to_series_items(prefix=current_key))
        return items


@dataclass
class ShareCheck(Check):
    total: int = 0

    def to_key_value_str(self) -> str:
        share_str = _share_to_str(self.value, self.total)
        return f"{self.label}: {share_str}"


@dataclass
class NCheck(Check):
    def to_key_value_str(self) -> str:
        return f"{self.label}: n={self.value}"


@dataclass
class BoolCheck(Check):
    def to_key_value_str(self) -> str:
        return f"{self.label}: {_bool_to_str(self.value)}"


@dataclass
class TemporalCheck(Check):
    empty: str = WARN
    no_series: str = WARN
    total_zero: str = WARN
    any_zero: str = OK
    negative: str = BAD
    nan: str = BAD
    above_threshold: dict[float, str] | None = None
    below_threshold: dict[float, str] | None = None

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.value, Temporal):
            raise ValueError(f"Value must be a Temporal, got {type(self.value)}")

    def get_not_ok_properties(self) -> list[str]:
        properties = []
        if self.value.is_empty:
            properties.append("empty")
        else:
            if self.total_zero != OK:
                if self.value.total == 0:
                    properties.append("total=0")
            if self.no_series != OK:
                if not self.value.has_series:
                    properties.append("no series")

            min_ = self.value.min()
            max_ = self.value.max()
            if self.any_zero != OK:
                if min_ <= 0:
                    properties.append("contains zero")
            if self.negative != OK:
                if min_ < 0:
                    properties.append("contains negative")
            if self.value.has_series:
                if self.nan != OK:
                    if self.value.series.isna().any():
                        properties.append("contains nan")
            if self.above_threshold is not None:
                for threshold in self.above_threshold:
                    if max_ > threshold:
                        properties.append(f"above {threshold}")
            if self.below_threshold is not None:
                for threshold in self.below_threshold:
                    if min_ < threshold:
                        properties.append(f"below {threshold}")
        return properties

    def get_status(self):
        def worsen(status: str, new_status: str) -> str:
            if status == BAD or new_status == BAD:
                return BAD
            elif status == WARN or new_status == WARN:
                return WARN
            else:
                return OK

        status = OK
        if self.value.is_empty:
            status = worsen(status, self.empty)
        else:
            if self.value.total == 0:
                status = worsen(status, self.total_zero)
            if not self.value.has_series:
                status = worsen(status, self.no_series)
            elif self.value.series.isna().any():
                status = worsen(status, self.nan)

            min_ = self.value.min()
            max_ = self.value.max()

            if min_ <= 0:
                status = worsen(status, self.any_zero)
            if min_ < 0:
                status = worsen(status, self.negative)
            if max_ is not None and self.above_threshold is not None:
                for threshold, threshold_status in self.above_threshold.items():
                    if max_ > threshold:
                        status = worsen(status, threshold_status)
            if self.below_threshold is not None:
                for threshold, threshold_status in self.below_threshold.items():
                    if min_ < threshold:
                        status = worsen(status, threshold_status)
        return status

    def to_key_value_str(self) -> str:
        not_ok_properties = self.get_not_ok_properties()
        if not_ok_properties:
            properties_str = ", ".join(not_ok_properties)
            return f"{self.label}: {properties_str}"
        else:
            return f"{self.label}: ok"


@dataclass
class MultiTemporalCheck(Check):
    empty: str = WARN
    no_series: str = WARN
    total_zero: str = WARN
    any_zero: str = OK
    negative: str = BAD
    nan: str = BAD
    above_threshold: dict[float, str] | None = None
    below_threshold: dict[float, str] | None = None

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.value, list):
            raise ValueError(f"Value must be a list[Temporal], got {type(self.value)}")
        if not all(isinstance(v, Temporal) for v in self.value):
            types = {type(v).__name__ for v in self.value}
            raise ValueError(f"All values must be Temporal, got: {types}")

    def _worsen(self, status: str, new_status: str) -> str:
        if status == BAD or new_status == BAD:
            return BAD
        elif status == WARN or new_status == WARN:
            return WARN
        else:
            return OK

    def _temporal_not_ok_properties(self, temporal: Temporal) -> list[str]:
        properties = []
        if temporal.is_empty:
            if self.empty != OK:
                properties.append("empty")
            return properties

        if self.total_zero != OK and temporal.total == 0:
            properties.append("total=0")
        if self.no_series != OK and not temporal.has_series:
            properties.append("no series")

        min_ = temporal.min()
        max_ = temporal.max()
        if self.any_zero != OK and min_ is not None and min_ <= 0:
            properties.append("contains zero")
        if self.negative != OK and min_ is not None and min_ < 0:
            properties.append("contains negative")
        if temporal.has_series:
            if self.nan != OK and temporal.series.isna().any():
                properties.append("contains nan")
        if max_ is not None and self.above_threshold is not None:
            for threshold in self.above_threshold:
                if max_ > threshold:
                    properties.append(f"above {threshold}")
        if min_ is not None and self.below_threshold is not None:
            for threshold in self.below_threshold:
                if min_ < threshold:
                    properties.append(f"below {threshold}")

        return properties

    def get_not_ok_properties_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for temporal in self.value:
            for prop in self._temporal_not_ok_properties(temporal):
                counts[prop] = counts.get(prop, 0) + 1
        return counts

    def get_status(self):
        status = OK
        for temporal in self.value:
            if temporal.is_empty:
                status = self._worsen(status, self.empty)
                continue

            if temporal.total == 0:
                status = self._worsen(status, self.total_zero)
            if not temporal.has_series:
                status = self._worsen(status, self.no_series)
            elif temporal.series.isna().any():
                status = self._worsen(status, self.nan)

            min_ = temporal.min()
            max_ = temporal.max()
            if min_ is not None:
                if min_ is not None and min_ <= 0:
                    status = self._worsen(status, self.any_zero)
                if min_ is not None and min_ < 0:
                    status = self._worsen(status, self.negative)
                if self.below_threshold is not None:
                    for threshold, threshold_status in self.below_threshold.items():
                        if min_ < threshold:
                            status = self._worsen(status, threshold_status)
            if max_ is not None:
                if self.above_threshold is not None:
                    for threshold, threshold_status in self.above_threshold.items():
                        if max_ > threshold:
                            status = self._worsen(status, threshold_status)

        return status

    def to_key_value_str(self) -> str:
        counts = self.get_not_ok_properties_counts()
        if not counts:
            return f"{self.label}: {len(self.value)}× ok"

        details = ", ".join(f"{n}× {prop}" for prop, n in counts.items())
        return f"{self.label}: {details}"


@dataclass
class CheckGroup:
    label: str
    subs: list[Check | "CheckGroup"]
    mode: Literal["section", "record"] = "section"

    INDENT_PER_LEVEL = "    "
    LEVEL_RECORD = -1

    @classmethod
    def record(cls, label: str, subs: list[Check | "CheckGroup"]) -> "CheckGroup":
        return cls(label=label, subs=subs, mode="record")

    @classmethod
    def section(cls, label: str, subs: list[Check | "CheckGroup"]) -> "CheckGroup":
        return cls(label=label, subs=subs, mode="section")

    def print(self) -> None:
        for line in self._to_strs():
            print(line)

    def _record_to_strs(self, indent_level: int = 0) -> list[str]:
        indent = self.INDENT_PER_LEVEL * indent_level
        lines: list[str] = []

        for sub in self.subs:
            if isinstance(sub, Check):
                lines.extend(sub.to_strs(indent=indent_level))
            elif isinstance(sub, CheckGroup):
                if sub.mode == "record":
                    lines.append(f"{indent}-  {sub.label}")
                    lines.extend(sub._record_to_strs(indent_level + 1))
                else:
                    lines.extend(sub._to_strs(level=indent_level + 1))
            else:
                raise ValueError(f"Invalid sub type: {type(sub)}")

        return lines

    def _to_strs(self, level: int = 0) -> list[str]:
        if self.mode == "record":
            return self._record_to_strs(indent_level=0)

        lines = self._header(title=self.label, level=level)

        for sub in self.subs:
            if isinstance(sub, Check):
                lines.extend(sub.to_strs(indent=0))
            elif isinstance(sub, CheckGroup):
                if sub.mode == "section":
                    lines.extend(sub._to_strs(level=level + 1))
                else:
                    lines.extend(self._header(title=sub.label, level=self.LEVEL_RECORD))
                    lines.extend(sub._record_to_strs(indent_level=0))
            else:
                raise ValueError(f"Invalid sub type: {type(sub)}")

        return lines

    def _header(self, title: str, level: int) -> list[str]:
        if level == 0:
            return _chapter_header(title)
        elif level == 1:
            return _section_header(title)
        elif level == 2:
            return _subsection_header(title)
        elif level == self.LEVEL_RECORD:
            return _record_header(title)
        else:
            return _subsection_header(title)

    def _to_series_items(
        self,
        prefix: tuple[str, ...] = (),
        include_self_label: bool = False,
    ) -> list[tuple[tuple[str, ...], Any]]:
        current_prefix = prefix + (self.label,) if include_self_label else prefix
        items: list[tuple[tuple[str, ...], Any]] = []

        for sub in self.subs:
            if isinstance(sub, Check):
                items.extend(sub._to_series_items(prefix=current_prefix))
            elif isinstance(sub, CheckGroup):
                items.extend(sub._to_series_items(prefix=current_prefix, include_self_label=True))
            else:
                raise ValueError(f"Invalid sub type: {type(sub)}")

        return items

    def to_series(self):
        import pandas as pd

        items = self._to_series_items()
        if not items:
            return pd.Series(dtype=object, name=self.label)

        keys = [k for k, _ in items]
        values = [v for _, v in items]

        if all(len(k) == 1 for k in keys):
            index = pd.Index([k[0] for k in keys], name="label")
        else:
            index = pd.MultiIndex.from_tuples(keys)
            if index.nlevels > 1:
                index = index.droplevel(0)

        return pd.Series(values, index=index, name=self.label)


# ------------------------------------------------------------------------------
# Helper checks
# ------------------------------------------------------------------------------


def temporal_flow_check(
    label: str,
    temporal: Temporal,
) -> TemporalCheck:
    return TemporalCheck(
        label=label,
        value=temporal,
        empty=WARN,
        total_zero=WARN,
        any_zero=OK,
        negative=BAD,
        nan=BAD,
    )


def multi_temporal_flow_check(
    label: str,
    temporals: list[Temporal],
) -> MultiTemporalCheck:
    return MultiTemporalCheck(
        label=label,
        value=temporals,
        empty=WARN,
        total_zero=WARN,
        any_zero=OK,
        negative=BAD,
        nan=BAD,
    )


def temporal_temperature_check(
    label: str,
    temporal: Temporal,
) -> TemporalCheck:
    return TemporalCheck(
        label=label,
        value=temporal,
        empty=WARN,
        total_zero=WARN,
        any_zero=OK,
        negative=OK,
        nan=BAD,
        above_threshold={150: BAD},  # catch K instead of °C
        below_threshold={-50: BAD},  # catch incorrect conversion from K to °C
    )


def multi_temporal_temperature_check(
    label: str,
    temporals: list[Temporal],
) -> MultiTemporalCheck:
    return MultiTemporalCheck(
        label=label,
        value=temporals,
        empty=WARN,
        total_zero=WARN,
        any_zero=OK,
        negative=OK,
        nan=BAD,
        above_threshold={150: BAD},  # catch K instead of °C
        below_threshold={-50: BAD},  # catch incorrect conversion from K to °C
    )


def _temporals_to_checks(temporals: list[Object]) -> list[Check]:
    # empties = [x for x in temporals if x.is_empty]
    # not_empties = [x for x in temporals if not x.is_empty]
    # fixes = [x for x in not_empties if x.fix is not None]
    # total_zero = [x for x in not_empties if x.total == 0]
    with_masters = [x for x in temporals if x.master is not None]
    with_clients = [x for x in temporals if x.clients]

    n = len(temporals)
    checks = [
        ShareCheck("with master", len(with_masters), total=n),
        ShareCheck("with clients", len(with_clients), total=n),
    ]
    return checks


# ------------------------------------------------------------------------------
# Network
# ------------------------------------------------------------------------------


def check_network(
    network: Network,
) -> CheckGroup:

    attachments = network.attachments()
    attachment_types = set(type(attachment) for attachment in attachments)
    attachment_type_counts = {at: sum(1 for a in attachments if isinstance(a, at)) for at in attachment_types}

    doublets_directed = network.doublets(respect_direction=True)
    doublets_undirected = network.doublets(respect_direction=False)
    is_doublet_free = len(doublets_undirected) == 0
    is_valid = network.is_valid()
    is_edgecomplete = network.is_edgecomplete()
    is_geometric = network.is_geometric()

    checks = [
        NCheck("no. of nodes", len(network.nodes)),
        NCheck("no. of edges", len(network.edges)),
        NCheck("no. of loops", len(network.loops()), else_check=0),
        NCheck("no. of undirected doublets", len(doublets_undirected), else_bad=0),
        NCheck("no. of directed doublets", len(doublets_directed), else_bad=0),
    ]

    if is_doublet_free and is_valid and is_edgecomplete:
        n_cycles = network.n_cycles()
        n_components = network.n_components()
        checks += [
            NCheck("no. of components", n_components),
            NCheck("no. of cycles", n_cycles),
        ]

    if is_doublet_free and is_valid and is_edgecomplete:
        nodes_0 = network.get_nodes_with_degree(degree=0, directed=False)
        nodes_1 = network.get_nodes_with_degree(degree=1, directed=False)
        nodes_2 = network.get_nodes_with_degree(degree=2, directed=False)
        checks += [
            ShareCheck("no. of nodes with degree 0", len(nodes_0), total=len(network.nodes), else_bad=0),
            ShareCheck("no. of nodes with degree 1", len(nodes_1), total=len(network.nodes), else_check=0),
            ShareCheck("no. of nodes with degree 2", len(nodes_2), total=len(network.nodes), else_check=0),
        ]

    checks += [
        BoolCheck("doublet-free", is_doublet_free, bad=False),
        BoolCheck("valid", is_valid, bad=False),
        BoolCheck("edge-complete", is_edgecomplete, bad=False),
        BoolCheck("geometric", is_geometric, bad=False),
    ]

    if is_doublet_free and is_valid and is_edgecomplete:
        is_linked = network.is_linked()
        checks.append(BoolCheck("linked", is_linked, bad=False))
        if is_linked and is_geometric:
            is_continuous = network.is_continuous()
            checks.append(BoolCheck("continuous", is_continuous, bad=False))
            if is_continuous:
                # planar = network.is_planar()
                # checks.append(BoolCheck("planar", planar, bad=False))
                pass

    return CheckGroup.record(label=f"Network topology & geometry, id={network.id:_}", subs=checks)


# ------------------------------------------------------------------------------
# DHN
# ------------------------------------------------------------------------------


def check_dhn_attachments(
    dhn: DistrictHeatingNetwork,
) -> CheckGroup:

    attachments = dhn.attachments()
    attachment_types = set(type(attachment) for attachment in attachments)
    attachment_type_counts = {at: sum(1 for a in attachments if isinstance(a, at)) for at in attachment_types}

    n_buildings = attachment_type_counts.pop(BuildingDhnConnection, 0)
    n_sites = attachment_type_counts.pop(Site, 0)
    n_substations = attachment_type_counts.pop(BuildingDhnConnection, 0)
    n_transfer_stations = attachment_type_counts.pop(TransferStation, 0)

    mixed_consumer = n_buildings > 0 and n_substations > 0
    mixed_producer = n_sites > 0 and n_transfer_stations > 0
    mixed_cross = (n_buildings > 0 and n_transfer_stations > 0) or (n_sites > 0 and n_substations > 0)

    checks = [
        NCheck("total attachments", len(attachments), OK if len(attachments) > 0 else BAD),
        NCheck("Sites", n_sites, OK if n_sites == 0 else WARN),
        NCheck("Buildings", n_buildings, OK if n_buildings == 0 else WARN),
        NCheck("Transfer Stations", n_transfer_stations, OK if n_transfer_stations > 0 else WARN),
        NCheck("Substations", n_substations, OK if n_substations > 0 else WARN),
        BoolCheck("Mixed consumer types", mixed_consumer, OK if not mixed_consumer else BAD),
        BoolCheck("Mixed producer types", mixed_producer, OK if not mixed_producer else BAD),
        BoolCheck("Mixed cross types", mixed_cross, OK if not mixed_cross else BAD),
    ]
    checks += [
        NCheck(f"{at.__name__}", count, OK if count == 0 else BAD) for at, count in attachment_type_counts.items()
    ]
    return CheckGroup.record(label=f"Attachments of DHN id={dhn.id:_}", subs=checks)


def check_dhn_substations(
    substations: list[BuildingDhnConnection],
) -> CheckGroup:

    with_input = []
    with_output = []

    for substation in substations:

        if substation.input is not None:
            with_input.append(substation)
        if substation.output is not None:
            with_output.append(substation)

    n = len(substations)
    checks = [
        NCheck("total", n),
        ShareCheck("input connected", len(with_input), total=n, else_check=n),
        ShareCheck("output connected", len(with_output), total=n, else_check=n),
        multi_temporal_flow_check("input flow", [s.input_flow for s in substations if s.input_flow is not None]),
        multi_temporal_flow_check("output flow", [s.output_flow for s in substations if s.output_flow is not None]),
        multi_temporal_temperature_check(
            "input forward temperature",
            [s.input_forward_temperature for s in substations if not s.input_forward_temperature.is_empty],
        ),
        multi_temporal_temperature_check(
            "input return temperature",
            [s.input_return_temperature for s in substations if not s.input_return_temperature.is_empty],
        ),
        multi_temporal_temperature_check(
            "output forward temperature",
            [s.output_forward_temperature for s in substations if not s.output_forward_temperature.is_empty],
        ),
        multi_temporal_temperature_check(
            "output return temperature",
            [s.output_return_temperature for s in substations if not s.output_return_temperature.is_empty],
        ),
    ]

    return CheckGroup.record(label="Substations", subs=checks)


def check_transfer_station(
    transfer_station: TransferStation,
) -> CheckGroup:

    checks = [
        BoolCheck("input connected", transfer_station.input is not None, else_check=True),
        BoolCheck("output connected", transfer_station.output is not None, else_check=True),
        temporal_flow_check("input flow", transfer_station.input_flow),
        temporal_flow_check("output flow", transfer_station.output_flow),
        temporal_temperature_check("input forward temperature", transfer_station.input_forward_temperature),
        temporal_temperature_check("input return temperature", transfer_station.input_return_temperature),
        temporal_temperature_check("output forward temperature", transfer_station.output_forward_temperature),
        temporal_temperature_check("output return temperature", transfer_station.output_return_temperature),
    ]

    return CheckGroup.record(label=f"Transfer Station, id={transfer_station.id:_}", subs=checks)


def check_dhn_topology(
    dhn: DistrictHeatingNetwork,
) -> CheckGroup: ...


def check_dhn_edges(
    dhn: DistrictHeatingNetwork,
) -> CheckGroup:

    def _check_pipes(
        pipes: list[DhnPipe],
    ) -> list[Check]:

        with_diameter = []

        for pipe in pipes:
            if pipe.diameter is not None:
                with_diameter.append(pipe)

        temperature_losses = [pipe.temperature_loss for pipe in pipes]
        temperature_ins = [pipe.temperature_in for pipe in pipes]
        temperature_outs = [pipe.temperature_out for pipe in pipes]

        n = len(pipes)

        checks = [
            NCheck("total", n),
            ShareCheck("with diameter", len(with_diameter), total=n, else_check=n),
            multi_temporal_temperature_check("temperature in", temperature_ins),
            multi_temporal_temperature_check("temperature out", temperature_outs),
            MultiTemporalCheck("temperature loss", temperature_losses, negative=WARN),
        ]
        return checks

    edges: list[DhnEdge] = dhn.edges
    with_supply_pipe: list[DhnEdge] = []
    with_return_pipe: list[DhnEdge] = []
    supply_pipes: list[DhnPipe] = []
    return_pipes: list[DhnPipe] = []

    for edge in edges:

        if edge.pipe_supply is not None:
            with_supply_pipe.append(edge)
            supply_pipes.append(edge.pipe_supply)

        if edge.pipe_return is not None:
            with_return_pipe.append(edge)
            return_pipes.append(edge.pipe_return)

    n = len(edges)
    checks = [
        NCheck("total", n),
        ShareCheck(
            "with supply pipe",
            len(with_supply_pipe),
            total=n,
            else_check=n,
            subs=_check_pipes(supply_pipes) if with_supply_pipe else [],
        ),
        ShareCheck(
            "with return pipe",
            len(with_return_pipe),
            total=n,
            else_check=n,
            subs=_check_pipes(return_pipes) if with_return_pipe else [],
        ),
    ]

    return CheckGroup.record(
        label="Dhn Edges",
        subs=checks,
    )


def check_dhn(
    dhn: DistrictHeatingNetwork,
) -> CheckGroup:

    substations = dhn.get_attachments_of_type(BuildingDhnConnection)
    transfer_station = dhn.get_attachments_of_type(TransferStation)

    section = CheckGroup.section(
        # underscore formatting of number:
        label=f"District Heating Network, id={dhn.id:_}",
        subs=[
            check_dhn_attachments(dhn),
            check_dhn_substations(substations),
        ]
        + [check_transfer_station(ts) for ts in dhn.get_attachments_of_type(TransferStation)]
        + [check_dhn_edges(dhn)],
    )

    return section


# ------------------------------------------------------------------------------
# Buildings
# ------------------------------------------------------------------------------


def check_buildings_overview(
    buildings: list[Building],
) -> CheckGroup:

    with_dhn_connection = []
    with_building_units = []
    with_households = []
    with_commercials = []
    with_devices = []
    with_demands = []
    with_demands_in_building_units = []
    with_demands_in_building = []

    n = len(buildings)

    component_type_sets: dict[frozenset[Demand], list[Building]] = {}

    for building in buildings:

        devices = building.find_objects(Device)  # doesn't include demands
        demands = building.find_objects(Demand)
        if building.building_units:
            with_building_units.append(building)
            if building.households:
                with_households.append(building)
            if building.commercials:
                with_commercials.append(building)
            if any(bu.find_objects(Demand) for bu in building.building_units):
                with_demands_in_building_units.append(building)

        if devices:
            with_devices.append(building)
            if building.find_objects(BuildingDhnConnection):
                with_dhn_connection.append(building)

        if demands:
            with_demands.append(building)
            demands_in_building = building.find_objects_filtered(type=Demand, omit_reachable_through=BuildingUnit)
            if demands_in_building:
                with_demands_in_building.append(building)

        component_types = set(type(component) for component in building.find_objects(Component))
        component_type_sets.setdefault(frozenset(component_types), []).append(building)

    sub_checks = []
    for set_ in component_type_sets:
        sub_check = ShareCheck(
            label=", ".join(sorted(t.__name__ for t in set_)) if set_ else "empty",
            value=len(component_type_sets[set_]),
            total=n,
        )
        sub_checks.append(sub_check)
    sub_check_record = CheckGroup.record(label="Component type sets", subs=sub_checks)

    checks = [
        NCheck("total", n),
        ShareCheck("with DHN connection", len(with_dhn_connection), total=n),
        ShareCheck("with building units", len(with_building_units), total=n, check=0),
        ShareCheck("with households", len(with_households), total=n),
        ShareCheck("with commercials", len(with_commercials), total=n),
        ShareCheck("with demands", len(with_demands), total=n),
        ShareCheck("with demands in building units", len(with_demands_in_building_units), total=n),
        ShareCheck("with demands in building", len(with_demands_in_building), total=n),
        ShareCheck("with devices", len(with_devices), total=n),
        sub_check_record,
    ]

    record = CheckGroup.record(label="Overview", subs=checks)
    return record


def check_demands(
    buildings: list[Building],
) -> CheckGroup:

    demands: list[Demand] = [x for b in buildings for x in b.find_objects(Demand)]
    n = len(demands)

    checks = [
        NCheck("total", n),
    ]

    demands_by_type = {}
    for demand in demands:
        demand_type = type(demand)
        demands_by_type.setdefault(demand_type, []).append(demand)

    for demand_type, demands_of_type in demands_by_type.items():

        n = len(demands_of_type)

        connected = [d for d in demands_of_type if d.input is not None]
        sub_checks = [
            ShareCheck("connected", len(connected), total=n, else_check=n),
        ]
        sub_checks += _temporals_to_checks([d.input_flow for d in demands_of_type])

        if issubclass(demand_type, ThermalComponent):

            sub_checks += [
                multi_temporal_temperature_check(
                    "forward temperature",
                    [d.input_forward_temperature for d in demands_of_type],
                ),
                multi_temporal_temperature_check(
                    "return temperature",
                    [d.input_return_temperature for d in demands_of_type],
                ),
            ]

        checks.append(
            ShareCheck(
                label=f"{demand_type.__name__}",
                value=len(demands_of_type),
                total=len(demands),
                subs=sub_checks,
            )
        )

    record = CheckGroup.record(label="Demands in buildings", subs=checks)
    return record


def check_buildings(
    buildings: list[Building],
) -> CheckGroup:

    records = [
        check_buildings_overview(buildings),
        check_demands(buildings),
    ]
    section = CheckGroup.section(label="Buildings", subs=records)
    return section


# ------------------------------------------------------------------------------
# Sites
# ------------------------------------------------------------------------------


def _check_heatpump(heatpump: Heatpump) -> list[Check]:

    return [
        TemporalCheck(
            label="nominal cop",
            value=heatpump.cop,
            empty=WARN,
            no_series=WARN,
            total_zero=BAD,
            any_zero=BAD,
            negative=BAD,
            nan=BAD,
        )
    ]


def _check_storage(storage: Storage) -> list[Check]:

    return [
        Check("has capacity", storage.capacity, check=[None, 0]),
        TemporalCheck(
            label="content",
            value=storage.content,
            empty=WARN,
            no_series=WARN,
            total_zero=BAD,
            any_zero=BAD,
            negative=BAD,
            nan=BAD,
        ),
    ]


def check_component(component: Component) -> CheckGroup:

    def socket_to_checks(socket: Socket) -> list[Check]:
        has_flow = not socket.flow.is_empty
        socket_medium = socket.get_medium(medium_considered="socket")
        link_medium = socket.get_medium(medium_considered="link")
        medium = socket.get_medium(medium_considered="socket_else_link")
        other_component = socket.other.parent if socket.other is not None else None

        component = socket.parent
        is_input = socket in component.input_sockets

        socket_checks = [
            Check(
                "target" if is_input else "source",
                (
                    f"{other_component.__class__.__name__}, id={other_component.id:_}"
                    if other_component is not None
                    else "<none>"
                ),
                check="<none>",
            ),
            temporal_flow_check(
                "flow",
                socket.flow,
            ),
        ]

        is_thermal = MediumManager().specifies(medium, Medium.THERMAL_ENERGY, include_same=True)

        if isinstance(component, ThermalComponent) and is_thermal:
            forward_temperature = component.get_flow_forward_temperature(at=socket)
            return_temperature = component.get_flow_return_temperature(at=socket)
            socket_checks += [
                temporal_temperature_check(
                    "forward temperature",
                    forward_temperature,
                ),
                temporal_temperature_check(
                    "return temperature",
                    return_temperature,
                ),
            ]

        return socket_checks

    # check input and output sockets:

    checks = []
    for i, socket in enumerate(component.input_sockets):
        checks.append(
            Check(
                label=f"Input #{i+1} ({socket.get_medium(medium_considered='socket_else_link').name})",
                subs=socket_to_checks(socket),
            )
        )
    for i, socket in enumerate(component.output_sockets):
        checks.append(
            Check(
                label=f"Output #{i+1} ({socket.get_medium(medium_considered='socket_else_link').name})",
                subs=socket_to_checks(socket),
            )
        )

    # check special component types:

    if isinstance(component, Heatpump):
        checks += _check_heatpump(component)
    if isinstance(component, Storage):
        checks += _check_storage(component)

    record = CheckGroup.record(
        label=f"{type(component).__name__}, id={component.id:_}",
        subs=checks,
    )

    return record


def check_site_overview(
    site: Site,
) -> CheckGroup:

    has_geometry = site.geometry is not None
    has_polygon = site.geometry is not None and site.geometry.polygon is not None

    components_by_type = {}
    n = len(site.find_objects(Component))
    for component in site.find_objects(Component):
        component_type = type(component)
        components_by_type.setdefault(component_type, []).append(component)

    sub_check = NCheck(
        label="components",
        value=n,
        subs=[
            NCheck(
                label=f"{component_type.__name__}",
                value=len(components_of_type),
            )
            for component_type, components_of_type in components_by_type.items()
        ],
    )

    checks = [
        BoolCheck("has geometry", has_geometry, else_check=True),
        BoolCheck("has polygon", has_polygon, else_check=True),
        sub_check,
    ]
    record = CheckGroup.record(label=f"Overview", subs=checks)
    return record


def check_site(
    site: Site,
) -> CheckGroup:

    overview_section = check_site_overview(site)
    devices_records = [check_component(component) for component in site.find_objects(Component)]

    section = CheckGroup.section(
        label=f"Site, id={site.id:_}",
        subs=[
            overview_section,
            *devices_records,
        ],
    )
    return section


# ------------------------------------------------------------------------------
# Branch & Project
# ------------------------------------------------------------------------------


def check_branch(
    branch: Branch,
) -> CheckGroup:

    dhns: list[DistrictHeatingNetwork] = branch.find_objects(DistrictHeatingNetwork)

    structures = branch.find_objects(Structure)
    sites = branch.find_objects(Site)
    sites_at_structures = [s.site for s in structures if s.site is not None]
    sites_not_at_structures = [s for s in sites if s not in sites_at_structures]

    sections = [check_dhn(dhn) for dhn in dhns]
    sections += [check_buildings(branch.find_objects(Building))]
    sections += [check_site(site) for site in sites_not_at_structures]

    return CheckGroup.section(label=f"Branch, id={branch.id:_}", subs=sections)


def check_project(
    project: Project,
) -> CheckGroup:

    sections = [check_branch(branch) for branch in project.branches]

    return CheckGroup.section(label=f"Project, id={project.name}", subs=sections)


def check_object(
    obj: Object,
) -> CheckGroup:

    if isinstance(obj, Network):
        return check_network(obj)
    elif isinstance(obj, DistrictHeatingNetwork):
        return check_dhn(obj)
    elif isinstance(obj, Building):
        return check_buildings([obj])
    elif isinstance(obj, Site):
        return check_site(obj)
    elif isinstance(obj, Component):
        return CheckGroup.section(label=f"Component, id={obj.id:_}", subs=[check_component(obj)])
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")


# ------------------------------------------------------------------------------
# Main check function
# ------------------------------------------------------------------------------


def check(objects: Object | Branch | Project | list[Object] | list[Branch]) -> CheckGroup:
    """
    Check the integrity of the given objects and return a CheckGroup
    containing the results.

    Notes
    -----

    Supported types are:

    - Branch(es)
    - DistrictHeatingNetwork(s)
    - Building(s)
    - Site(s)
    - Component(s)
    - Project(s)

    Mixed lists of objects are not supported, i.e. if a list is given, all items
    must be of the same type (Object or Branch). If a single Object or Branch is
    given, it will be converted to a list with one item.

    The check result can be printed using the print() method of the returned
    CheckGroup, or the to_strs() method can be used to get the lines as a list
    of strings.

    Example usage:

        check_result = check(my_branch)
        check_result.print()
    """

    if isinstance(objects, Object):
        objects = [objects]
    elif isinstance(objects, Branch):
        objects = [objects]
    elif isinstance(objects, Project):
        objects = [objects]
    elif isinstance(objects, list):
        if all(isinstance(o, Object) for o in objects):
            pass
        elif all(isinstance(o, Branch) for o in objects):
            pass
        else:
            raise ValueError("If objects is a list, all items must be of the same type (Object or Branch)")
    else:
        raise ValueError("objects must be an Object, a Branch, a Project, a list of Objects or a list of Branches")

    sections = []

    if all(isinstance(o, Building) for o in objects):
        sections.append(check_buildings(objects))  # type: ignore

    else:

        for obj in objects:
            if isinstance(obj, Branch):
                sections.append(check_branch(obj))
            elif isinstance(obj, Project):
                sections.append(check_project(obj))
            else:
                sections.append(check_object(obj))

    return CheckGroup.section(label="Integrity Check", subs=sections)
