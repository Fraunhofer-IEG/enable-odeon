import logging
import unittest
import os
import time
import pandas as pd
from pathlib import Path
import numpy as np
import h5py
from pympler import asizeof
import tempfile

from odeon.model import Branch, Project, HeatDemand, Object
from odeon.io import FileAdapter, TemporalManager
from odeon.model.building import Building
from odeon.model.device import ElectricityDemand
from odeon.processing.utils.utils import file_size_as_str, bytes_as_str


class TestTemporalManager(unittest.TestCase):

    def test_set_temporal_manager(self):
        """
        Test whether a target can be set to a project or a branch.
        """
        project = Project()
        branch1 = Branch(year=2025, project=project)
        branch2 = Branch(year=2030, project=project)

        tp = TemporalManager()
        t1 = TemporalManager()
        project.temporal_manager = tp
        branch1.temporal_manager = t1

        assert branch1.temporal_manager is t1
        assert project.temporal_manager is tp
        assert t1.target is branch1
        assert tp.target is project

        # if a branch has no direct temporal manager, project's one will be used:
        assert branch2.temporal_manager is tp

        # temporal managers can be replaced:
        t2 = TemporalManager()
        branch1.temporal_manager = t2
        assert branch1.temporal_manager is t2
        assert t2.target is branch1

    def test_settings(self):
        """
        Test whether the settings can be set and retrieved correctly.
        """

        # no settings will lead to default settings:
        tp = TemporalManager()
        assert tp.settings == {Object: "loaded"}

        settings = {HeatDemand: "lazy"}
        tp.settings = settings
        assert tp.settings == settings

        # setting to a single mode will apply this to type Object again:
        tp.settings = "swapped"
        assert tp.settings == {Object: "swapped"}

    def test_set_swap_mode(self):
        """
        Check that setting the swap mode of a project or branch will affect
        all included temporals.
        """
        project = Project()
        branch1 = Branch(year=2023, temporal_manager=TemporalManager())
        branch2 = Branch(year=2030, temporal_manager=TemporalManager())
        project.add_branches([branch1, branch2])

        # add a building per branch with a heat demand (will contain 2 temporals:)
        building1 = Building()
        building1.heat_demand = pd.Series(np.random.uniform(low=0.0, high=10.0, size=8760))
        branch1.add_objects(building1)

        building2 = Building()
        building2.heat_demand = pd.Series(np.random.uniform(low=0.0, high=10.0, size=8760))
        branch2.add_objects(building2)

        # check that the default swap_mode is "loaded":
        for branch in [branch1, branch2]:
            for temporal in branch.temporals_recursive():
                assert temporal.swap_mode == "loaded"

        # setting swap mode is not possible if file adapter is missing:
        self.assertRaises(
            Exception,
            lambda: branch1.temporal_manager.set_swap_mode("swapped"),
        )

        # create a temporary directory and set it to the project's file adapter:
        with tempfile.TemporaryDirectory() as tmpdirname:
            file_adapter = FileAdapter(dir=Path(tmpdirname))
            project.file_adapter = file_adapter

            # now setting the swap mode should work:
            branch1.temporal_manager.set_swap_mode("swapped")

            # setting swap mode of a branch to "swapped" will affect all temporals:
            branch1.temporal_manager.set_swap_mode("swapped")
            for temporal in branch1.temporals_recursive():
                assert temporal.swap_mode == "swapped"

            # settings will be unaffected:
            assert branch1.temporal_manager.settings == {Object: "loaded"}

            # branch2 will be unaffected:
            for temporal in branch2.temporals_recursive():
                assert temporal.swap_mode == "loaded"

            # need to release the files:
            file_adapter.close_hdf_files()

    def test_apply_settings_to_new_objects(self):
        """
        Check that the settings are applied correctly when adding objects to
        a branch or project.
        """
        project = Project()
        branch = Branch(
            year=2025,
            project=project,
            temporal_manager=TemporalManager(
                settings={HeatDemand: "lazy", Object: "loaded"},
            ),
        )

        # new HeatDemand will get swap_mode "lazy":
        heat_demand = HeatDemand()
        branch.add_objects(heat_demand)
        assert heat_demand.get_factor().swap_mode == "lazy"

        # new ElectricityDemand will get swap_mode "loaded" as defined for Object:
        electricity_demand = ElectricityDemand()
        branch.add_objects(electricity_demand)
        assert electricity_demand.get_factor().swap_mode == "loaded"

    def test_apply_settings_to_existing_objects(self):
        """
        Check that the settings are applied correctly when changing the
        settings of a TemporalManager after objects have been added to a
        branch or project.
        """

        project = Project()
        branch = Branch(
            year=2025,
            project=project,
            temporal_manager=TemporalManager(),  # default settings = {"Object": "loaded"}
        )

        # new HeatDemand will get swap_mode "loaded":
        heat_demand = HeatDemand()
        branch.add_objects(heat_demand)
        assert heat_demand.get_factor().swap_mode == "loaded"

        # electricity demand too:
        electricity_demand = ElectricityDemand()
        branch.add_objects(electricity_demand)
        assert electricity_demand.get_factor().swap_mode == "loaded"

        # change settings to lazy for HeatDemand:
        branch.temporal_manager.settings = {HeatDemand: "lazy", Object: "loaded"}
        branch.temporal_manager.apply_settings_for_object(heat_demand)
        assert heat_demand.get_factor().swap_mode == "lazy"

        # electricity demand will be unaffected:
        assert electricity_demand.get_factor().swap_mode == "loaded"

    def test_reset_swap_mode(self):
        """
        Check that the swap mode can be reset to the settings after manual
        override.
        """

        project = Project()
        branch = Branch(
            year=2025,
            project=project,
            temporal_manager=TemporalManager(
                settings={HeatDemand: "lazy", Object: "loaded"},
            ),
        )

        # new HeatDemand will get swap_mode "lazy":
        heat_demand = HeatDemand()
        branch.add_objects(heat_demand)
        assert heat_demand.get_factor().swap_mode == "lazy"

        # new ElectricityDemand will get swap_mode "loaded" as defined for Object:
        electricity_demand = ElectricityDemand()
        branch.add_objects(electricity_demand)
        assert electricity_demand.get_factor().swap_mode == "loaded"

        # manually change swap mode of all temporals:
        branch.temporal_manager.set_swap_mode("loaded")
        assert heat_demand.get_factor().swap_mode == "loaded"

        # reset swap mode will apply the settings again:
        branch.temporal_manager.reset_swap_mode()
        assert heat_demand.get_factor().swap_mode == "lazy"
        assert electricity_demand.get_factor().swap_mode == "loaded"


if __name__ == "__main__":
    TestTemporalManager().test_set_temporal_manager()
    TestTemporalManager().test_settings()
    TestTemporalManager().test_set_swap_mode()
    TestTemporalManager().test_apply_settings_to_new_objects()
    TestTemporalManager().test_apply_settings_to_existing_objects()
    TestTemporalManager().test_reset_swap_mode()
