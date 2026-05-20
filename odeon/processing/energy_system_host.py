from typing import Literal
import pandas as pd
from numbers import Number

from ..model.energy_system import EnergySystemHost
from ..model.device import (
    ElectricityDemand,
    HeatingDemand,
    DhwDemand,
    CoolingDemand,
    Heatpump,
    ElectrodeBooster,
    CompressionChiller,
    WallBox,
    FuelOilBoiler,
    MethaneBoiler,
    MethaneChp,
    BiomassBoiler,
    BiomassChp,
    BuildingDhnConnection,
)
from ..model.temporal import Temporal
from ..model.energy import Medium

def get_demand_temporal(
    structure: EnergySystemHost,
    level: Literal["useful", "final"],
    finals: list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None = None,
    final_el_purpose: list[Literal["electricity", "heat", "cooling", "mobility"]] | None = None,
    usefuls: list[Literal["electricity", "heating", "dhw", "cooling"]] | None = None,
    include_sub_structures: bool = True,
) -> Temporal:
    """
    Get the energy demand for a given structure at a specific level (useful or final).

    Parameters
    ----------
    structure : EnergySystemHost
        The structure for which to calculate the energy demand. May contain
        sub-structures.
    level : Literal["useful", "final"]
        The level of demand to calculate. "useful" for useful energy demand,
        "final" for final energy demand.
    finals : list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None, optional
        List of final energy types to include when level is "final". If None,
        all types are included.
    final_el_purpose : list[Literal["electricity", "heat", "cooling", "mobility"]] | None, optional
        List of purposes for final electricity demand when level is "final" and
        "electricity" is included in finals. If None, all purposes are included.
    usefuls : list[Literal["electricity", "heating", "dhw", "cooling"]] | None, optional
        List of useful energy types to include when level is "useful". If None,
        all types are included.
    include_sub_structures : bool, optional
        Whether to sum the demands of possible sub-structures of the given
        structure. If True, demands of sub-structures are included. If False,
        only direct demands of the given structure are considered.
    """
    return _get_demand(
        structure,
        level,
        finals=finals,
        final_el_purpose=final_el_purpose,
        usefuls=usefuls,
        return_type="temporal",
        include_sub_structures=include_sub_structures,
    )


def get_demand_total(
    structure: EnergySystemHost,
    level: Literal["useful", "final"],
    finals: list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None = None,
    final_el_purpose: list[Literal["electricity", "heat", "cooling", "mobility"]] | None = None,
    usefuls: list[Literal["electricity", "heating", "dhw", "cooling"]] | None = None,
    include_sub_structures: bool = True,
) -> float:
    """
    Get the energy demand for a given structure at a specific level (useful or final).

    Parameters
    ----------
    structure : EnergySystemHost
        The structure for which to calculate the energy demand. May contain
        sub-structures.
    level : Literal["useful", "final"]
        The level of demand to calculate. "useful" for useful energy demand,
        "final" for final energy demand.
    finals : list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None, optional
        List of final energy types to include when level is "final". If None,
        all types are included.
    final_el_purpose : list[Literal["electricity", "heat", "cooling", "mobility"]] | None, optional
        List of purposes for final electricity demand when level is "final" and
        "electricity" is included in finals. If None, all purposes are included.
    usefuls : list[Literal["electricity", "heating", "dhw", "cooling"]] | None, optional
        List of useful energy types to include when level is "useful". If None,
        all types are included.
    include_sub_structures : bool, optional
        Whether to sum the demands of possible sub-structures of the given
        structure. If True, demands of sub-structures are included. If False,
        only direct demands of the given structure are considered.
    """
    return _get_demand(
        structure,
        level,
        finals=finals,
        final_el_purpose=final_el_purpose,
        usefuls=usefuls,
        return_type="total",
        include_sub_structures=include_sub_structures,
    )


def _get_demand(
    structure: EnergySystemHost,
    level: Literal["useful", "final"],
    finals: list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None = None,
    final_el_purpose: list[Literal["electricity", "heat", "cooling", "mobility"]] | None = None,
    usefuls: list[Literal["electricity", "heating", "dhw", "cooling"]] | None = None,
    return_type: Literal["temporal", "total"] = "temporal",
    include_sub_structures: bool = True,
) -> Temporal | float:
    """
    Get the energy demand for a given structure at a specific level (useful or final).

    Parameters
    ----------
    structure : EnergySystemHost
        The structure for which to calculate the energy demand. May contain
        sub-structures.
    level : Literal["useful", "final"]
        The level of demand to calculate. "useful" for useful energy demand,
        "final" for final energy demand.
    finals : list[Literal["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]] | None, optional
        List of final energy types to include when level is "final". If None,
        all types are included.
    final_el_purpose : list[Literal["electricity", "heat", "cooling", "mobility"]] | None, optional
        List of purposes for final electricity demand when level is "final" and
        "electricity" is included in finals. If None, all purposes are included.
    usefuls : list[Literal["electricity", "heating", "dhw", "cooling"]] | None, optional
        List of useful energy types to include when level is "useful". If None,
        all types are included.
    return_type : Literal["temporal", "total"], optional
        The type of result to return. "temporal" for a Temporal, "total" for a
        total value.
    include_sub_structures : bool, optional
        Whether to sum the demands of possible sub-structures of the given
        structure. If True, demands of sub-structures are included. If False,
        only direct demands of the given structure are considered.
    """
    # TODO this is all very dirty and incomplete. should "solve" the energy system first by wiring everything
    # together, placing supply devices like ElectricityGridConnection, FuelOilSupply and so on and just taking
    # their summed output flow
    # TODO consider energy production and storage

    structures = [structure]
    if include_sub_structures:
        structures += structure.find_objects(EnergySystemHost)

    srs_list = []
    demands = []

    for s in structures:
        s: EnergySystemHost

        if level == "useful":
            usefuls = usefuls or ["electricity", "heating", "dhw", "cooling"]
            if "electricity" in usefuls:
                demands += s.find_objects(ElectricityDemand)
            if "heating" in usefuls:
                demands += s.find_objects(HeatingDemand)
            if "dhw" in usefuls:
                demands += s.find_objects(DhwDemand)
            if "cooling" in usefuls:
                demands += s.find_objects(CoolingDemand)

        elif level == "final":
            finals = finals or ["electricity", "fuel_oil", "natural_gas", "biomass", "heat"]
            if "electricity" in finals:
                final_el_purpose = final_el_purpose or ["electricity", "heat", "cooling", "mobility"]
                if "electricity" in final_el_purpose:
                    demands += s.find_objects(ElectricityDemand)
                if "heat" in final_el_purpose:
                    srs_list += [
                        d.get_input_flow(at=Medium.THERMAL_ENERGY, medium_relation="socket_specifies")
                        for d in s.find_objects((Heatpump, ElectrodeBooster))
                    ]
                if "cooling" in final_el_purpose:
                    srs_list += [d.input_flow for d in s.find_objects(CompressionChiller)]
                if "mobility" in final_el_purpose:
                    srs_list += [d.input_flow for d in s.find_objects(WallBox)]

            if "fuel_oil" in finals:
                srs_list += [d.input_flow for d in s.find_objects(FuelOilBoiler)]
            if "natural_gas" in finals:
                srs_list += [d.input_flow for d in s.find_objects((MethaneBoiler, MethaneChp))]
            if "biomass" in finals:
                srs_list += [d.input_flow for d in s.find_objects((BiomassBoiler, BiomassChp))]
            if "heat" in finals:
                srs_list += [d.input_flow for d in s.find_objects(BuildingDhnConnection)]
        else:
            raise ValueError()

    rets = []
    for i, srs in enumerate(srs_list):
        if isinstance(srs, pd.Series):
            rets.append(Temporal(series=srs, timeindex=structure.branch.timeindex))
        elif isinstance(srs, Temporal):
            rets.append(srs)
        elif isinstance(srs, Number):
            rets.append(Temporal(total=srs, timeindex=structure.branch.timeindex))
        elif srs is None:
            ...
        else:
            raise ValueError()  # what might it be?

    demands = list(set(demands))
    for d in demands:
        rets.append(d.input_flow)

    if return_type == "temporal":
        return Temporal.sum(rets)
    elif return_type == "total":
        return sum(r.total or 0 for r in rets)
