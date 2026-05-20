from numbers import Number
from typing import Literal
import pandas as pd
import geopandas as gpd
from copy import copy, deepcopy

from .decision import DecisionState
from .temporal import Temporal
from .device import (
    ElectricityGridConnection,
    ElectricTransformer,
    ElectricityStorage,
    PhotovoltaicDevice,
    WindpowerDevice,
    ElectricityDemand,
    TransformerStation,
    Medium,
    Heatpump,
    ElectrodeHeater,
    ElectrodeBooster,
    ElectricityGridSource,
    Bus,
    Device,
)
from .energy_network import EnergyNetworkObject, EnergyNode, EnergyEdge, EnergyNetwork
from ..processing.utils.utils import (
    typeerror_if_not_isinstance,
    typeerror_if_not_isinstance_or_none,
    typeerror_if_not_list_isinstance,
    typeerror_if_not_list_isinstance_or_none,
)


class DegObject(EnergyNetworkObject):  # TODO necessary?
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class DegNode(EnergyNode, DegObject):
    """
    Deg Node Object is based on the Network node object. Additionaly it offers
    a voltage timeseries as well as properties to collect connected devices.
    Allowed attachments are Transformer Station and Electricity Grid
    Connection. Transformers are connected via Transformer Station. Demands,
    PV, Wind and E-mobility is connected via Electricity Grid Connection.
    Stores can be connected via GridCon and Transformer Station.
    """

    _TEMPORAL_ATTRIBUTES = ["_voltage"]
    _voltage: Temporal = None  # [V]
    # nominal voltage of the node [kV]

    def __init__(self, vn_kv: float = 0.4, **kwargs):
        typeerror_if_not_isinstance(x=vn_kv, types_=(int, float))
        self._voltage = None
        self.vn_kv = vn_kv
        super().__init__(**kwargs)

    def connected_devices_of_type(self, type_: type) -> list[Device]:
        """
        collects all devices of the passed type connected to the node and
        returns them as a List. Only devices with a
        `DecisionState != Decided_Against` are considered.

        Returns
        -------
        list[Device]
        """
        typeerror_if_not_isinstance(x=type_, types_=type)

        if self.attachment is None:
            return []
        devices = [
            c
            for c in self.attachment.linked_components
            if isinstance(c, type_) and c.existence != DecisionState.DECIDED_AGAINST
        ]
        return devices

    @property
    def demand(self) -> Temporal | None:
        """Collects and sums up all electricity demands, connected to the node.
        If no device connected, returns None. Demands of type [Heatpump,
        ElectrodeHeater, ElectrodeBooster, ElectricityDemand] are considered.
        Demands are connected via Electricity Grid Connection.

        Returns
        -------
        Temporal | None
            electricity_demand
        """
        if not isinstance(self.attachment, ElectricityGridConnection):
            return None

        demands = [
            c.get_input_flow(at=Medium.ELECTRIC_ENERGY)
            for c in self.attachment.following_components
            if isinstance(c, (Heatpump, ElectrodeHeater, ElectrodeBooster, ElectricityDemand))
        ]
        if len(demands) > 1:
            return Temporal.sum(demands)
        elif len(demands) == 1:
            return demands[0]
        else:
            return None

    @property
    def storage(self) -> Temporal | None:
        """
        Collects and sums up all storage profiles, connected to the node.
        Returns None if no device is connected. Stores can be connected via
        `ElectricityGridConnection` or `TransformerStation`.

        Returns
        -------
        Temporal | None
            storage_profile
        """
        if self.attachment is None:
            return None
        elif isinstance(self.attachment, ElectricityGridConnection):
            s = [
                c.get_input_flow(at=Medium.ELECTRIC_ENERGY) - c.get_output_flow(at=Medium.ELECTRIC_ENERGY)
                for c in self.attachment.following_components
                if isinstance(c, ElectricityStorage)
            ]
        elif isinstance(self.attachment, TransformerStation):
            s = [
                c.get_input_flow(at=Medium.ELECTRIC_ENERGY) - c.get_output_flow(at=Medium.ELECTRIC_ENERGY)
                for c in self.attachment.previous_components
                if isinstance(c, ElectricityStorage)
            ]
        if len(s) > 1:
            return Temporal.sum(s)
        elif len(s) == 1:
            return s[0]
        else:
            return None

    @property
    def gen(self) -> Temporal | None:
        """
        Collects and sums up all generation profiles, connected to the node.
        Returns None if no device is connected. Generators of type
        [PhotovoltaicDevice, WindpowerDevice] are considered. Only considers
        Generator `if not DecisionState.DECIDED_AGAINST`. Generators are
        connected via `ElectricityGridConnection`.

        Returns
        -------
        Temporal | None
            gen_profile
        """
        if not isinstance(self.attachment, ElectricityGridConnection):
            return None
        components = [
            c
            for c in self.attachment.previous_components
            if isinstance(c, (PhotovoltaicDevice, WindpowerDevice)) and c.existence != DecisionState.DECIDED_AGAINST
        ]
        gen = [c.get_output_flow(at=Medium.ELECTRIC_ENERGY) for c in components]
        if len(gen) > 1:
            return Temporal.sum(gen)
        elif len(gen) == 1:
            return gen[0]
        else:
            return None

    @property
    def voltage(self) -> Temporal | None:
        """Temporal of voltage level at the bus.

        Returns
        -------
        Temporal | None
            voltage profile
        """
        return self._voltage

    @voltage.setter
    def voltage(self, volt_series: Temporal):
        self._voltage = volt_series

    def get_trafos_in_node(self) -> list[ElectricTransformer]:
        """
        collects all `ElectricTransformer`s connected to the node and returns
        them as a list. Transformers need to be connected via
        `TransformerStation`. Only Transformers with a
        `DecisionState != Decided_Against` are considered

        Returns
        -------
        list[ElectricTransformer]
            List of transformers connected to the node
        """
        trafos = self.connected_devices_of_type(ElectricTransformer)
        return trafos

    def get_flows_by_attached_component(
        self,
        type_: Literal["load", "gen", "storage"],
    ) -> dict[ElectricityGridConnection | TransformerStation, Temporal | None]:
        """
        Collects the flows of connected devices of a certain type (load, gen,
        storage) and returns them in a dict with the attached component as key.
        Only considers devices with `DecisionState != Decided_Against`.

        Parameters
        ----------
        type_ : Literal[&quot;load&quot;, &quot;gen&quot;, &quot;storage&quot;]
            type of flow to be collected, either load, gen or storage

        Returns
        -------
        dict[ElectricityGridConnection | TransformerStation, Temporal | None]
            dict with attached component as key and flow as value
        """
        typeerror_if_not_isinstance(x=type_, types_=str)
        if type_ not in ["load", "gen", "storage"]:
            raise ValueError('Passed type needs to be either "load", "gen" or "storage"')

        flows = {}
        if type_ == "load":
            flows = {self.attachment: self.demand}
        elif type_ == "gen":
            flows = {self.attachment: self.gen}
        elif type_ == "storage":
            flows = {self.attachment: self.storage}
        return flows

    def get_el_bus_from_attachment(self) -> Bus | None:
        """Collect the electricity bus, connected to the Nodes' attachment.

        Returns
        -------
        Bus | None
            Bus if there is an electricity bus connected to the attachment, else None
        """
        if self.attachment is None:
            return None
        bus = next(
            (c for c in self.attachment.linked_components if isinstance(c, Bus) and c.medium == Medium.ELECTRIC_ENERGY),
            None,
        )
        return bus

    def copy(self, deep_custom_data: bool = True) -> "DegNode":
        """
        Return a copy.

        Returns
        -------
        DegNode
            A Node that references the same object as `attachment`, copied
            `partitions`, copied Geometry, and copied `custom_data` (deep or
            shallow, depending on `deep_custom_data`). The set Network will be
            None.
        """

        node = DegNode(
            name=self.name,
            custom_data=deepcopy(self.custom_data) if deep_custom_data else copy(self.custom_data),
            elevation=self.elevation,
            attachment=self.attachment,
            geometry=copy(self.geometry),
            partitions=copy(self.partitions),
            vn_kv=copy(self.vn_kv),
        )
        return node


class DegCable(EnergyEdge, DegObject):
    """
    DegCable Object is based on the Network Edge object. Additionally it offers
    a lineload timeseries as well as a number of parallel lines. Cable Type is
    determined via Edge partition.

    TODO That cable type is set via partition came from the open source
    approach and was a quick hack. in the future use the partitions in Base
    Network but in the conversion function to DEG transform them into a
    property "cable_type" or "type". Atm cable data is not included, maybe add
    it to odeon?
    """

    # temporal attributes:
    _TEMPORAL_ATTRIBUTES = ["_lineload_percent"]
    _lineload_percent: Temporal = None

    # additional attributes:

    parallel: int = 1
    type_: str = None
    max_current: float = None
    r_ohm_per_km: float = None  # net.line.r_ohm_per_km.values
    x_ohm_per_km: float = None  # net.line.x_ohm_per_km.values #f =50hz
    c_nf_per_km: float = None  # net.line.c_nf_per_km.values
    max_i_ka: float = None  # net.line.max_i_ka.values

    def __init__(
        self,
        type_: str = None,
        parallel: int = 1,
        max_current: float = None,
        **kwargs,
    ):
        typeerror_if_not_isinstance_or_none(x=type_, types_=str)
        typeerror_if_not_isinstance_or_none(x=parallel, types_=int)
        typeerror_if_not_isinstance_or_none(x=max_current, types_=(int, float))
        self.type_ = type_
        self.parallel = parallel
        self.max_current = max_current
        super().__init__(**kwargs)

    # properties for temporals:

    @property
    def lineload_percent(self) -> Temporal:
        return self._lineload_percent

    @lineload_percent.setter
    def lineload_percent(self, lineload_percent: Temporal | Number | pd.Series | None):
        typeerror_if_not_isinstance_or_none(x=lineload_percent, types_=(Temporal, Number, pd.Series))
        self.set_temporal("_lineload_percent", lineload_percent)


class DistrictElectricityGrid(EnergyNetwork):
    """DistrictElectricityGrid Object is based on the Network object. Instead
    of `Nodes` and `Edges` it Uses `DegNodes` and `DegCables`. Additionally to
    the base network functions, it offers different useful functions for
    advanced electricity grid analysis like a search of nodes based on
    connected devices or the creation of GeoDFs with insights into the DEG.
    """

    def __init__(self, nodes: list[DegNode] = None, cables: list[DegCable] = None, **kwargs):
        typeerror_if_not_list_isinstance_or_none(x=nodes, types_=DegNode)
        typeerror_if_not_list_isinstance_or_none(nodes, types_=DegCable)
        super().__init__(nodes=nodes, edges=cables, **kwargs)

    @property
    def cables(self) -> list[DegCable]:
        return self.edges

    def add_nodes(self, nodes: list[DegNode], existing_mode: Literal["skip", "exception"] = "exception"):
        """
        Adds nodes to the network.
        If existing_mode is "skip", existing nodes will be skipped, if it is
        "exception", an exception will be raised.

        Parameters
        ----------
        nodes : list[DegNode]
            List of nodes to be added
        existing_mode : Literal[&quot;skip&quot;, &quot;exception&quot;], optional
            existing_mode determines how to handle existing nodes, by default "exception"

        Raises
        ------
        ValueError
            If existing_mode is not "skip" or "exception"
        """
        typeerror_if_not_list_isinstance(x=nodes, types_=DegNode)
        typeerror_if_not_isinstance(existing_mode, str)
        if existing_mode not in ["skip", "exception"]:
            raise ValueError('existing_mode needs to be either "skip" or "exception"')

        super().add_nodes(nodes=nodes, existing_mode=existing_mode)

    def remove_nodes(self, nodes: list[DegNode], edge_mode: Literal["remove", "set_none"] = "remove"):
        """
        Removes nodes from the network. If edge_mode is "remove", connected
        edges will be removed, if it is "set_none", the start and end node of
        connected edges will be set to None.

        Parameters
        ----------
        nodes : list[DegNode]
            List of nodes to be removed
        edge_mode : Literal[&quot;remove&quot;, &quot;set_none&quot;], optional
            edge_mode determines how to handle connected edges, by default "remove"

        Raises
        ------
        ValueError
            If edge_mode is not "remove" or "set_none"
        """
        typeerror_if_not_list_isinstance(x=nodes, types_=DegNode)
        typeerror_if_not_isinstance(edge_mode, str)
        if edge_mode not in ["remove", "set_none"]:
            raise ValueError('edge_mode needs to be either "remove" or "set_none"')

        super().remove_nodes(nodes=nodes, edge_mode=edge_mode)

    def add_cables(self, cables: list["DegCable"]):
        """
        Adds cables to the network.

        Parameters
        ----------
        cables : list[&quot;DegCable&quot;]
            List of cables to be added
        """
        typeerror_if_not_list_isinstance(x=cables, types_=DegCable)
        super().add_edges(edges=cables)

    def remove_cables(
        self,
        cables: list[DegCable | int],
        node_mode: Literal["keep_all", "keep_connected", "remove"] = "keep_all",
    ):
        """
        Removes cables from the network. If node_mode is "keep_all", all nodes
        will be kept, if node_mode is "keep_connected", only nodes that are not
        connected to other edges will be removed, if node_mode is "remove", all
        connected nodes will be removed.

        Parameters
        ----------
        cables : list[DegCable | int]
            List of cables to be removed, can be either list of cable objects or list of cable ids
        node_mode : Literal[&quot;keep_all&quot;, &quot;keep_connected&quot;, &quot;remove&quot;], optional
            node_mode determines how to handle connected nodes, by default "keep_all"

        Raises
        ------
        ValueError
            If node_mode is not "keep_all", "keep_connected" or "remove"
        """
        typeerror_if_not_list_isinstance(x=cables, types_=(DegCable, int))
        typeerror_if_not_isinstance(node_mode, str)
        if node_mode not in ["keep_all", "keep_connected", "remove"]:
            raise ValueError('node_mode needs to be either "keep_all", "keep_connected" or "remove"')

        super().remove_edges(edges=cables, node_mode=node_mode)

    def get_lgs_nodes(self) -> tuple[list[DegNode], list[DegNode], list[DegNode]]:
        """
        Searches deg for nodes with connected devices and sorts them by load
        nodes, generator nodes and storage nodes. Double occurrence of nodes
        are possible, as they can parallelly host loads, as well as generation
        units and electricity storages.

        Returns
        -------
        tuple[list[DegNode], list[DegNode], list[DegNode]]
            Load nodes, generator nodes and storage nodes as tuple in the
            format ([Load Nodes], [Generator Nodes], [Storage Nodes])
        """
        load_nodes = self.get_nodes_by_connection_types(
            [Heatpump, ElectrodeHeater, ElectrodeBooster, ElectricityDemand]
        )
        gen_nodes = self.get_nodes_by_connection_types([PhotovoltaicDevice, WindpowerDevice])
        storage_nodes = self.get_nodes_by_connection_types([ElectricityStorage])

        return load_nodes, gen_nodes, storage_nodes

    def to_node_gdf(self) -> gpd.GeoDataFrame:
        """Creates GeoDataFrame with all DegNode information.

        Returns
        -------
        gpd.GeoDataFrame
            GeoDataFrame with all DegNode information, including voltage
            deviation and voltage at maximum deviation
        """
        gdf = super().to_node_gdf()

        for node in self.nodes:
            node_factor = 1 / (node.vn_kv * 1000) * 100
            if not node.voltage.is_empty:
                dev_pos = node.vn_kv * 1000 - node.voltage.series.min()
                dev_neg = node.voltage.series.max() - node.vn_kv * 1000
                delta_max = max([dev_pos, dev_neg])

                if node.voltage.series.min() == 0:
                    delta_max = 0
                else:
                    delta_max = delta_max * node_factor  # in %
                gdf.loc[gdf["id"] == node.id, "max_voltage_deviation[%]"] = delta_max
                if delta_max == dev_neg:
                    gdf.loc[gdf["id"] == node.id, "voltage_at_max_voltage_deviation[%]"] = (
                        node.voltage.series.min() * node_factor
                    )
                else:
                    gdf.loc[gdf["id"] == node.id, "voltage_at_max_voltage_deviation[%]"] = (
                        node.voltage.series.max() * node_factor
                    )

            else:
                gdf.loc[gdf["id"] == node.id, "max_voltage_deviation[%]"] = 0
                gdf.loc[gdf["id"] == node.id, "voltage_at_max_voltage_deviation[%]"] = 0

        gdf = gdf.fillna(0)

        return gdf

    def to_transformer_gdf(self) -> gpd.GeoDataFrame:
        """Creates GeoDataFrame with all Transformer information.

        Returns
        -------
        gpd.GeoDataFrame
            GeoDataFrame with all Transformer information, including
            transformer load, transformer station, connected node and
            transformer type. Each transformer gets its own row in the
            GeoDataFrame, so if there are multiple transformers connected to
            the same node, they will be listed in separate rows
        """
        gdf = super().to_node_gdf()
        transformer_nodes = self.get_transformer_nodes()
        ids = [n.id for n in transformer_nodes]
        gdf = gdf.loc[gdf.id.isin(ids), :]
        for node in transformer_nodes:
            transformers = node.get_trafos_in_node()
            for transformer in transformers:
                gdf.loc[transformer.id, :] = gdf.loc[gdf["id"] == node.id, :].iloc[0, :]
                if not transformer.transformer_load.is_empty:
                    gdf.loc[transformer.id, "transformer_load [%]"] = transformer.transformer_load.series.max()

                else:
                    gdf.loc[transformer.id, "transformer_load [%]"] = 0
                gdf.loc[transformer.id, "sn_mva"] = transformer.sn_mva
                gdf.loc[transformer.id, "name"] = transformer.name
                gdf.loc[transformer.id, "vn_lv_kv"] = transformer.vn_lv_kv
                gdf.loc[transformer.id, "vn_hv_kv"] = transformer.vn_hv_kv
                gdf.loc[transformer.id, "type"] = (
                    f"{transformer.sn_mva}MVA/{transformer.vn_lv_kv}KV_lv/{transformer.vn_hv_kv}KV_hv"
                )
                gdf.loc[transformer.id, "id"] = transformer.id
                gdf.loc[transformer.id, "node_id"] = node.id
                gdf.loc[transformer.id, "trafo_station"] = node.attachment.id
                gdf.loc[transformer.id, "count"] = 1

        gdf = gdf.drop(index=gdf.loc[gdf.id.isin(ids), :].index)
        gdf = gdf.fillna(0)

        return gdf

    def to_transformer_station_gdf(self) -> gpd.GeoDataFrame:
        """
        Creates GeoDataFrame with all Transformer information and merge them by
        TransformerStation. Shows maximum loaded transformer in
        TransformerStation.

        Returns
        -------
        gpd.GeoDataFrame
            GeoDataFrame with all Transformer information, including
            transformer load, transformer station, connected node and
            transformer type. Each transformer station gets its own row in the
            GeoDataFrame, so if there are multiple transformers connected to
            the same transformer station, only the transformer with the highest
            load will be listed in the GeoDataFrame.
        """
        trafo_gdf = self.to_transformer_gdf()
        stations = trafo_gdf["trafo_station"].unique()
        for station in stations:
            trafo_gdf.loc[trafo_gdf["trafo_station"] == station, "count"] = trafo_gdf.loc[
                trafo_gdf["trafo_station"] == station, "count"
            ].sum()
        gdf = trafo_gdf.loc[trafo_gdf.groupby("trafo_station")["transformer_load [%]"].idxmax()]

        return gdf

    def to_edge_gdf(self) -> gpd.GeoDataFrame:
        """Creates GeoDataFrame with all Cable information.

        Returns
        -------
        gpd.GeoDataFrame
            GeoDataFrame with all Cable information, including line load,
            number of parallel lines, connected nodes and cable type. Each
            cable gets its own row in the GeoDataFrame, so if there are
            multiple cables connected to the same nodes, they will be listed in
            separate rows.
        """
        gdf = super().to_edge_gdf()
        for edge in self.edges:
            gdf.loc[gdf["id"] == edge.id, "line_count"] = edge.parallel
            if not edge.lineload_percent.is_empty:

                gdf.loc[gdf["id"] == edge.id, "lineload [%]"] = edge.lineload_percent.series.max()
                gdf.loc[gdf["id"] == edge.id, "lineload_max[%]"] = edge.lineload_percent.series.max()
            else:
                gdf.loc[gdf["id"] == edge.id, "lineload [%]"] = 0
                gdf.loc[gdf["id"] == edge.id, "lineload_max[%]"] = 0

        gdf = gdf.fillna(0)

        return gdf

    def get_transformer_nodes(self) -> list[DegNode]:
        """Get list of all nodes with connected transformers

        Returns
        -------
        list[DegNode]
            List of nodes with connected transformers
        """
        return_list = []
        for n in self.nodes:
            if isinstance(n.attachment, TransformerStation):
                trafos = n.get_trafos_in_node()
                if len(trafos) > 0:
                    return_list.append(n)
        return return_list

    def get_source_nodes(self) -> list[DegNode]:
        """Get list of all nodes with connected ElectricityGridSources

        Returns
        -------
        list[DegNode]
            List of nodes with connected ElectricityGridSources
        """
        return_list = []
        for n in self.nodes:
            if isinstance(n.attachment, ElectricityGridSource):
                return_list.append(n)
        return return_list

    def get_all_trafos_in_deg(self) -> list[ElectricTransformer]:
        """Collect all Transformers in DEG

        Returns
        -------
        list[ElectricTransformer]
            List of all transformers in the DEG
        """
        trafos = []
        trafo_nodes = self.get_transformer_nodes()
        for n in trafo_nodes:
            trafos += n.get_trafos_in_node()
        return trafos

    def get_objects_of_type_by_voltage_lvl(
        self,
        voltage_lvl: float = 0.4,
        object_type: Literal["nodes", "cables"] = "nodes",
    ) -> list[DegNode] | list[DegCable]:
        """Collect nodes or cables by voltage level

        Parameters
        ----------
        voltage_lvl : float, optional
            voltage level in kV, by default 0.4
        objects : Literal[&quot;nodes&quot;, &quot;cables&quot;], optional
            choose if nodes or cables should be collected, by default &quot;nodes&quot;

        Returns
        -------
        list[DegNode] | list[DegCable]
            List of nodes or cables with the specified voltage level. If
            object_type is "nodes", returns list of nodes with vn_kv equal to
            voltage_lvl. If object_type is "cables", returns list of cables
            that are connected to nodes with vn_kv equal to voltage_lvl.
        """
        typeerror_if_not_isinstance(voltage_lvl, (int, float))
        typeerror_if_not_isinstance(object_type, str)
        if object_type not in ["nodes", "cables"]:
            raise ValueError('object_type needs to be either "nodes" or "cables"')

        if object_type == "nodes":
            return [n for n in self.nodes if n.vn_kv == voltage_lvl]
        elif object_type == "cables":
            nodes = [n for n in self.nodes if n.vn_kv == voltage_lvl]
            node_ids = [n.id for n in nodes]
            cables = [e for e in self.edges if e.start_node.id in node_ids and e.end_node.id in node_ids]
            return cables
        else:
            raise Exception('objects needs to be either "nodes" or "cables"')

    def get_nodes_by_connection_types(self, attachment_types: type | list[type] | tuple[type]) -> list[DegNode]:
        """
        Collect nodes with linked_components of type "attachment_types". Only
        nodes with linked components of the specified type(s) and
        `DecisionState != Decided_Against` will be returned.

        Parameters
        ----------
        attachment_types : type | list[type] | tuple[type]
            type, list or tuple of types of linked components that are
            connected to the node via the attachment

        Returns
        -------
        list[DegNode]
            List of nodes with linked components of type "attachment_types"
        """
        typeerror_if_not_isinstance(attachment_types, (type, list, tuple))
        if not isinstance(attachment_types, (list, tuple)):
            attachment_types = [attachment_types]
        if not isinstance(attachment_types, tuple):
            attachment_types = tuple(attachment_types)

        return_list = []
        for n in self.nodes:
            if n.attachment is None:
                continue
            if any(
                isinstance(c, attachment_types)
                and (not hasattr(c, "existence") or c.existence != DecisionState.DECIDED_AGAINST)
                for c in n.attachment.linked_components
            ):
                return_list.append(n)
        return return_list

    def create_component_df(self) -> pd.DataFrame:
        """
        Create DataFrame with component data in DEG. Includes Transformer and
        Cable information. Cable data is compressed by cable type with summed
        cable length and digging length

        Returns
        -------
        pd.DataFrame
            DataFrame with component data, including type, count, total length
            of all lines [m], digging length [m] for cables and count for
            transformers. Additionally, a column "component" is added to
            distinguish between cables and transformers.
        """
        cables = self.to_edge_gdf()
        transformers_df = self.to_transformer_gdf()
        # print(transformers_df)
        cables = cables.loc[cables["partitions"] != None]
        if len(cables) <= 0:
            Warning("no cables with specific type found, add base cable type")
        cables_index = cables["partitions"].apply(lambda x: len(x) > 0)
        cables.loc[cables_index, "type"] = cables.loc[cables_index, "partitions"].apply(lambda x: x[0])
        cables["linelength[m]"] = cables["geometry"].apply(lambda x: x.length)

        unique_cable_df = cables.loc[:, ["type", "line_count", "linelength[m]"]]
        unique_cable_df = unique_cable_df.drop_duplicates(subset=["type"])
        for i in unique_cable_df.index:
            unique_cable_df.loc[i, "linelength[m]"] = (
                cables.loc[cables["type"] == unique_cable_df.loc[i, "type"], "linelength[m]"]
                * cables.loc[cables["type"] == unique_cable_df.loc[i, "type"], "line_count"]
            ).sum()
            unique_cable_df.loc[i, "digging_length[m]"] = cables.loc[
                cables["type"] == unique_cable_df.loc[i, "type"], "linelength[m]"
            ].sum()
            unique_cable_df.loc[i, "line_count"] = cables.loc[
                cables["type"] == unique_cable_df.loc[i, "type"], "line_count"
            ].sum()
        unique_cable_df = unique_cable_df.rename(
            columns={"linelength[m]": "total length of all lines [m]", "line_count": "count"}, inplace=False
        )
        unique_transformers_df = transformers_df.loc[:, ["type", "count"]]
        unique_transformers_df = unique_transformers_df.drop_duplicates(subset=["type"])
        for i in unique_transformers_df.index:
            unique_transformers_df.loc[i, "count"] = transformers_df.loc[
                transformers_df["type"] == unique_transformers_df.loc[i, "type"], "count"
            ].sum()

        unique_transformers_df["component"] = "transformer"
        unique_cable_df["component"] = "cable"

        combined_df = pd.concat([unique_cable_df, unique_transformers_df], ignore_index=True)

        return combined_df
