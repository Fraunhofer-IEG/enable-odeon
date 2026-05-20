import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import json

from odeon.io import SQLiteAdapter, utils
from odeon.model import Project, Branch, HeatDemand


def _create_sample_project(n_branches=2):
    project = Project(name="sample")
    for i in range(n_branches):
        b = Branch(year=2020 + i, project=project, description={"scenario": f"s{i}"})
        hd = HeatDemand()
        # give the heat demand a series so we have temporal payload ~ small
        series = pd.Series(np.random.uniform(0, 5, size=len(b.timeindex)))
        hd.input_flow = series
        b.add_objects(hd)
    return project


class TestSQLiteAdapter(unittest.TestCase):

    def test_serialize_objects(self):
        dir = Path(__file__).parent
        # with tempfile.TemporaryDirectory() as tmp:
        project = _create_sample_project(n_branches=1)

        objects_dicts = {}
        for o in project.branches[0].find_objects():
            d = utils.object_to_json_dict(o)
            objects_dicts[o.id] = d

        # write to json file:
        json_path = dir / "test_sqlite_adapter_objects.json"
        with open(json_path, "w") as f:
            json_dict = {
                "branch_id": project.branches[0].id,
                "objects": objects_dicts,
            }
            json.dump(json_dict, f, indent=2)

        pass


if __name__ == "__main__":
    TestSQLiteAdapter().test_serialize_objects()
