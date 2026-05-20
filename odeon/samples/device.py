from typing import Literal, List
import random
from odeon.model import (
    EnergySystem,
    AirWaterHeatpump,
    HeatingStorage,
    MethaneBoiler,
    Chp,
    PhotovoltaicDevice,
    SolarThermalDevice,
    SolarSurface,
    MethaneChp,
)


def sample_device_host(
    randoms: bool = True,
    add_devices: List[Literal["heatpump", "boiler", "chp", "heating_storage", "pv", "solar_thermal"]] = None,
) -> EnergySystem:
    if add_devices is None:
        add_devices = ["heatpump", "boiler", "pv"]
    device_host = EnergySystem()
    surface = None
    if randoms:
        n_devices = random.choice(range(1, 5))
        add_devices = random.sample(
            ["heatpump", "boiler", "chp", "heating_storage"],
            n_devices,
        )
    if "heatpump" in add_devices:
        device_host.add_components(AirWaterHeatpump())
    if "boiler" in add_devices:
        device_host.add_components(MethaneBoiler())
    if "chp" in add_devices:
        device_host.add_components(MethaneChp())
    if "heating_storage" in add_devices:
        device_host.add_components(HeatingStorage())
    if "pv" in add_devices:
        surface = SolarSurface()
        pv = PhotovoltaicDevice()
        device_host.add_components(pv)
        pv._solar_surface = surface  # TODO this is a dirty hack reuqired because the surface doesn't yet have a parent
    if "solar_thermal" in add_devices:
        surface = surface or SolarSurface()
        st = SolarThermalDevice()
        st._solar_surface = surface  # TODO this is a dirty hack reuqired because the surface doesn't yet have a parent
        device_host.add_components(st)
    return device_host, surface
