import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import sqlite3
from enum import Enum

from odeon.io import SQLiteAdapter
from odeon.model import Project, Branch, Temporal
from odeon.model.device import HeatDemand
from odeon.samples.base import sample_project


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


def _compare_sqlite_files(file1: Path, file2: Path) -> bool:
    """Utility function to compare two SQLite database files for equality."""

    def fetch_all_data(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        data = {}
        for table_name in tables:
            table_name = table_name[0]
            cursor.execute(f"SELECT * FROM {table_name};")
            data[table_name] = cursor.fetchall()
        conn.close()
        return data

    data1 = fetch_all_data(file1)
    data2 = fetch_all_data(file2)

    return data1 == data2


def _compare_projects(proj1: Project, proj2: Project) -> bool:
    """Utility function to compare two Project instances for equality."""

    def _comopare_objects(obj1, obj2) -> bool:
        """Compare two objects' attributes for equality."""

        def _is_scalar_type(val) -> bool:
            """Check if the value is a scalar type (str, bool, int, float, pd.Series)."""
            return val is None or isinstance(val, (str, bool, int, float, pd.Series))

        def _is_container_type(val) -> bool:
            """Check if the value is a container type (list, tuple, dict, set, Enum)."""
            return isinstance(val, (list, tuple, dict, set, Enum))

        def _compare_scalar_values(val1, val2) -> bool:
            """Compare two values for equality, handling simple, scalar types."""

            if (
                (val1 is None and val2 is not None)
                or (type(val1) != type(val2))
                or (isinstance(val1, (str, bool, int)) and val1 != val2)
                or (isinstance(val1, float) and not np.isclose(val1, val2))
                or (isinstance(val1, pd.Series) and not val1.equals(val2))
            ):
                return False

            return True

        def _compare_container_values(val1, val2) -> bool:
            """Compare two container values for equality."""

            if isinstance(val1, (list, tuple)):
                if len(val1) != len(val2):
                    return False
                for item1, item2 in zip(val1, val2):
                    if _is_scalar_type(item1):
                        if not _compare_scalar_values(item1, item2):
                            return False
                    elif _is_container_type(item1):
                        if not _compare_container_values(item1, item2):
                            return False
                    else:
                        if not _comopare_objects(item1, item2):
                            return False

            elif isinstance(val1, dict):
                if val1.keys() != val2.keys():
                    return False
                for key in val1.keys():
                    if _is_scalar_type(val1[key]):
                        if not _compare_scalar_values(val1[key], val2[key]):
                            return False
                    elif _is_container_type(val1[key]):
                        if not _compare_container_values(val1[key], val2[key]):
                            return False
                    else:
                        if not _comopare_objects(val1[key], val2[key]):
                            return False

            elif isinstance(val1, (set, Enum)):
                if val1 != val2:
                    return False

            return True

        if type(obj1) != type(obj2):
            return False

        for attr in obj1.__dict__.keys():
            if (
                attr.startswith("__")
                or "__parent" in attr
                or getattr(obj1, attr) is obj1.parent
                or "_CHILDREN_ATTRIBUTES" in attr
                or "_children_attributes" in attr
                or "_ASSOCIATED_ATTRIBUTES" in attr
                or "_associated_attributes" in attr
                or attr == "_n_accesses"
                or (isinstance(obj1, Temporal) and attr in ["_min", "_max", "_mean"])
            ):
                continue  # attributes to skip

            if not hasattr(obj2, attr):
                return False

            val1 = getattr(obj1, attr)
            val2 = getattr(obj2, attr)
            if type(val1) != type(val2):
                return False

            if _is_scalar_type(val1):
                if not _compare_scalar_values(val1, val2):
                    return False

            elif _is_container_type(val1):
                if not _compare_container_values(val1, val2):
                    return False

            else:
                if not _comopare_objects(val1, val2):
                    return False

        return True

    # Compare project attributes
    if (
        (proj1.name != proj2.name)
        or (proj1.boundary_wgs84 != proj2.boundary_wgs84)
        or (proj1.boundary_local != proj2.boundary_local)
        or (proj1.projector._origin != proj2.projector._origin)
        or (proj1.projector.proj_str != proj2.projector.proj_str)
        or (len(proj1.branches) != len(proj2.branches))
        or (proj1.main_branch.id != proj2.main_branch.id)
        or (proj1.file_adapter.dir != proj2.file_adapter.dir if proj1.file_adapter else False)
        or (proj1.temporal_manager.settings != proj2.temporal_manager.settings if proj1.temporal_manager else False)
        or (proj1.temporal_manager.target != proj2.temporal_manager.target if proj1.temporal_manager else False)
    ):
        return False

    # Compare each branch in the project
    for branch1, branch2 in zip(proj1.branches, proj2.branches):
        # Compare branch attributes
        if branch1.id != branch2.id:
            return False
        if branch1.name != branch2.name:
            return False
        if branch1.year != branch2.year:
            return False
        if branch1.timeindex.equals(branch2.timeindex) is False:
            return False
        if branch1.description != branch2.description:
            return False

        # Compare number of objects in each branch
        if len(branch1.objects) != len(branch2.objects):
            return False

        # Compare each object in the branch
        for obj1, obj2 in zip(branch1.objects, branch2.objects):
            if not _comopare_objects(obj1, obj2):
                return False

    return True


class TestSQLiteAdapter(unittest.TestCase):

    def test_write_and_reload_project(self):

        # project = _create_sample_project(n_branches=3)  # create sample project with 3 branches
        project = sample_project(
            n_branches=2,
            n_buildings=10,
            random_sample=True,
            create_geometry=False,
            create_physics=False,
            add_devices=["heatpump", "boiler", "pv", "solar_thermal", "chp", "heating_storage"],
            add_demands=["heating_demand", "dhw_demand", "electricity_demand", "cooling_demand"],
            root_year=2022,
        )

        with tempfile.TemporaryDirectory() as tmp:
            # Write project to SQLite
            adapter = SQLiteAdapter(tmp)
            adapter.write_project(project)

            # verify metadata listing
            meta = adapter.list_branches()
            assert len(meta) == 3
            ids = {m["id"] for m in meta}
            assert ids == {b.id for b in project.branches}

            # read back into a fresh project
            project_reload = adapter.read_project()

            # Compare original and reloaded projects
            assert _compare_projects(project, project_reload), "Projects do not match after reload."

            with tempfile.TemporaryDirectory() as tmp_2:
                # Write the reloaded project to a new SQLite file
                adapter_2 = SQLiteAdapter(tmp_2)
                adapter_2.write_project(project_reload)

                # Compare the SQLite files directly
                assert len(list(Path(tmp).glob("*.sqlite"))) == len(
                    list(Path(tmp_2).glob("*.sqlite"))
                ), "Number of SQLite files do not match after reload."
                for original_db_path in Path(tmp).glob("*.sqlite"):
                    reloaded_db_path = Path(tmp_2) / original_db_path.name

                    assert _compare_sqlite_files(
                        original_db_path, reloaded_db_path
                    ), f"SQLite files do not match after reload for {original_db_path.name}."

    @unittest.skip("SQLite adapter not fully implemented yet")
    def test_selective_load_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_full = _create_sample_project(n_branches=2)
            adapter = SQLiteAdapter(tmp)
            adapter.write_project(project_full)
            # load only first branch into a fresh project
            target = Project(name="target")
            adapter.read_project(target, branch_ids=[project_full.branches[0].id])
            assert len(target.branches) == 1
            assert target.branches[0].id == project_full.branches[0].id

    @unittest.skip("SQLite adapter not fully implemented yet")
    def test_selective_load_by_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_full = _create_sample_project(n_branches=2)
            adapter = SQLiteAdapter(tmp)
            adapter.write_project(project_full)
            target = Project(name="target")
            adapter.read_project(target, description_contains={"scenario": "s1"})
            assert len(target.branches) == 1
            assert target.branches[0].description["scenario"] == "s1"


if __name__ == "__main__":
    adapter = TestSQLiteAdapter()
    adapter.test_write_and_reload_project()
    # adapter.test_selective_load_by_id()
    # adapter.test_selective_load_by_description()
