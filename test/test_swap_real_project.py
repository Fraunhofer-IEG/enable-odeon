from pathlib import Path

import numpy as np
import pandas as pd

from odeon.io import FileAdapter, TemporalManager
from odeon.model import Project, Branch, Building, HeatDemand, Object


def test_swap_real_project_1():

    TEST_DIR = Path("out/test_swap_real_project_1")

    project = Project(
        name="Test Project",
        file_adapter=FileAdapter(dir=TEST_DIR),
        temporal_manager=TemporalManager(settings="loaded"),
    )
    project.main_branch = Branch(name="Main Branch", year=2025)

    # create some buildings with heat demand timeseries:
    N_BUILDINGS = 100
    for i in range(N_BUILDINGS):
        building = Building(name=f"Building {i}")
        building.heat_demand = pd.Series(np.random.rand(8760) * 1000)
        project.main_branch.add_objects(building)

    project.temporal_manager.swap_temporals()
    project.temporal_manager.load_temporals()


# def test_swap_real_project_2():

#     TEST_DIR = Path("out/test_swap_real_project_2")

#     file_adapter = FileAdapter(TEST_DIR)
#     project = file_adapter.from_dir(TEST_DIR)
#     file_adapter.swap_timeseries()

#     file_adapter.load_timeseries()


if __name__ == "__main__":
    test_swap_real_project_1()
    # test_swap_real_project_2()
