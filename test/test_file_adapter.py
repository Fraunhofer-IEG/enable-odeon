import os
import unittest
import tempfile
import warnings
from pathlib import Path
import h5py
import pandas as pd

from odeon.io import FileAdapter, TemporalManager
from odeon.model import Project, Branch, Building, HeatingDemand, Temporal
from odeon.model.base import id_authority
from odeon.model.temporal import hdf_key_from_temporal


class TestFileAdapterBasic(unittest.TestCase):

    def test_to_pickle_roundtrip(self):
        """
        Test saving a Project to pickle and loading it back, checking that
        the FileAdapter and Project properties are correctly set.
        """
        project1 = Project(name="TestProject")

        with tempfile.TemporaryDirectory() as td:
            file_adapter1 = FileAdapter(Path(td), project=project1)  # will set the file_adapter of project
            pk_path = file_adapter1.write_to_dir(filename="proj.pk", overwrite=True)

            assert pk_path.exists()
            assert pk_path.absolute() == Path(td).joinpath("proj.pk").absolute()
            assert file_adapter1.project is project1
            assert project1.file_adapter is file_adapter1
            assert file_adapter1.dir == Path(td)

            # loading from pickle will
            # - return the project
            # - set the project to the file_adapter and vice versa
            # - not set the dir of the file_adapter
            # - keep properties of the project except file_adapter:

            file_adapter2 = FileAdapter.from_pickle(str(pk_path))
            project2 = file_adapter2.project

            assert file_adapter1 is not file_adapter2
            assert isinstance(project2, Project)
            assert project2 is not project1
            assert file_adapter2.dir is None

            # loading the dir will additionally set the dir:

            file_adapter3 = FileAdapter.from_dir(dir=Path(td))
            project3 = file_adapter3.project

            assert file_adapter3.dir == Path(td)
            assert file_adapter3 is not file_adapter1
            assert file_adapter3 is not file_adapter2
            assert isinstance(project3, Project)
            assert project3 is not project1
            assert project3 is not project2

    def test_dir_setter_creates_directory(self):
        """
        Check that setting the dir property creates the directory if it does
        not exist, and that changing the dir emits a warning if the directory
        is changed after initialization.
        """
        with tempfile.TemporaryDirectory() as td:
            base_path = Path(td)
            target = base_path / "nested" / "data"
            self.assertFalse(target.exists())

            # Setting dir creates the directory:
            file_adapter = FileAdapter(target)
            self.assertTrue(target.exists())

            # Changing dir emits warning:
            new_dir = base_path / "other"
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                file_adapter.dir = new_dir
                self.assertTrue(any("You are changing the directory" in str(x.message) for x in w))

            self.assertEqual(file_adapter.dir, new_dir)

    def test_updating_project_file_adapter(self):
        """
        Check that setting a new project to the FileAdapter updates both sides
        of the relationship correctly.
        """
        project1 = Project(name="Project1")
        project2 = Project(name="Project2")

        with tempfile.TemporaryDirectory() as td:
            file_adapter = FileAdapter(Path(td), project=project1)

            assert file_adapter.project is project1
            assert project1.file_adapter is file_adapter
            assert project2.file_adapter is None

            # adding the file adapter to another project will remove it from the first:
            project2.file_adapter = file_adapter

            assert project1.file_adapter is None
            assert file_adapter.project is project2
            assert project2.file_adapter is file_adapter


class TestFileAdapterHdf(unittest.TestCase):

    def test_hdf_file_creation_and_reuse(self):
        """
        Check that requesting the HDF file for a branch creates the file if it
        does not exist, and reuses the open file if it does.
        """
        # get a temporary directory for the HDF files:
        tempdir = tempfile.TemporaryDirectory()

        # create a project with one branch, a file adapter and a temporal manager:
        project = Project(temporal_manager=TemporalManager())
        branch = Branch(2023)
        project.main_branch = branch
        file_adapter = FileAdapter(Path(tempdir.name), project=project)

        hdf_file1: h5py.File = file_adapter.get_hdf_file_for_branch(branch)
        assert isinstance(hdf_file1, h5py.File)
        assert hdf_file1.id.valid == 1  # = file is opened

        # Requesting again should return the same open file:
        hdf_file2 = file_adapter.get_hdf_file_for_branch(branch)
        assert hdf_file1 is hdf_file2
        assert hdf_file2.id.valid == 1  # = file is still opened

        # Closing the file in the FileAdapter should close it:
        file_adapter.close_hdf_files()
        assert hdf_file1.id.valid == 0  # = file is closed

        # Requesting again should open a new file:
        hdf_file3 = file_adapter.get_hdf_file_for_branch(branch)
        assert isinstance(hdf_file3, h5py.File)
        assert hdf_file3.id.valid == 1  # = file is opened
        assert hdf_file1 is not hdf_file3

        file_adapter.close_hdf_files()
        tempdir.cleanup()

    def test_clean_hdf_files_removes_orphan_temporals(self):
        """
        Check that calling clean_hdf_files removes unused temporals in HDF files.
        """
        # get a temporary directory for the HDF files:
        tempdir = tempfile.TemporaryDirectory()

        # create a project with one branch, a file adapter and a temporal manager:
        project = Project(temporal_manager=TemporalManager())
        branch = Branch(2023)
        project.main_branch = branch
        file_adapter = FileAdapter(Path(tempdir.name), project=project)

        hdf_file1 = file_adapter.get_hdf_file_for_branch(branch)
        assert isinstance(hdf_file1, h5py.File)
        assert hdf_file1.id.valid == 1  # = file is opened

        # create two buildings with a heating demand temporal:
        building1 = Building()
        building1.heating_demand = pd.Series(range(8760)) / 20
        branch.add_objects(building1)
        assert len(building1.temporals_recursive()) == 2  # 1x flow, 1x factor
        # only keep the temporals without fix because fixed temporals are not swapped to HDF:
        temporals1 = [t for t in building1.temporals_recursive() if t.fix is None]

        building2 = Building()
        building2.heating_demand = pd.Series(range(8760)) / 10
        branch.add_objects(building2)
        assert len(building2.temporals_recursive()) == 2
        temporals2 = [t for t in building2.temporals_recursive() if t.fix is None]

        # Swap the temporals to HDF:
        project.temporal_manager.swap_temporals()

        # assert that the hdf file contains both temporals:
        assert hdf_key_from_temporal(temporals1[0]) in hdf_file1
        assert hdf_key_from_temporal(temporals2[0]) in hdf_file1

        # remove one building, which will disconnect the temporal from the branch:
        branch.remove_objects(building1)

        # Call clean_hdf_files, which should remove the disconnected temporal:
        file_adapter.clean(delete_files=False)
        assert hdf_key_from_temporal(temporals1[0]) not in hdf_file1
        assert hdf_key_from_temporal(temporals2[0]) in hdf_file1

        # The HDF file should still be open and accessible:
        assert hdf_file1.id.valid == 1  # = file is opened
        hdf_file2 = file_adapter.get_hdf_file_for_branch(branch)
        assert hdf_file1 is hdf_file2

        file_adapter.close_hdf_files()
        tempdir.cleanup()

    def test_clean_hdf_files_deletes_removed_branch_file(self):
        """
        Check that removing a branch from the project and calling clean_hdf_files
        closes and deletes the corresponding HDF file.
        """

        # get a temporary directory for the HDF files:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        # create a project with two branches, a file adapter and a temporal manager:
        project = Project(temporal_manager=TemporalManager())
        branch1 = Branch(2023)
        branch2 = Branch(2025)
        project.main_branch = branch1
        project.add_branches(branch2)
        file_adapter = FileAdapter(Path(tempdir.name), project=project)

        # create a building with a heating demand temporal in each branch:
        building1 = Building()
        building1.heating_demand = pd.Series(range(8760)) / 20
        branch1.add_objects(building1)
        building2 = Building()
        building2.heating_demand = pd.Series(range(8760)) / 10
        branch2.add_objects(building2)

        # Get the HDF files for both branches to trigger their creation:
        hdf_file1 = file_adapter.get_hdf_file_for_branch(branch1)  # trigger file creation
        hdf_filename1 = file_adapter.get_hdf_path_for_branch(branch1)
        hdf_file2 = file_adapter.get_hdf_file_for_branch(branch2)  # trigger file creation
        hdf_filename2 = file_adapter.get_hdf_path_for_branch(branch2)
        assert os.path.exists(hdf_filename1)

        # swap the temporals to HDF:
        project.temporal_manager.swap_temporals()

        # Remove the branch from the project:
        project.remove_branches(branch1)

        # Call clean_hdf_files, which should close and delete the HDF file:
        file_adapter.clean(delete_files=True)

        assert not os.path.exists(hdf_filename1)
        assert os.path.exists(hdf_filename2)

        file_adapter.close_hdf_files()
        tempdir.cleanup()


if __name__ == "__main__":
    # TestFileAdapterBasic().test_dir_setter_creates_directory()
    # TestFileAdapterBasic().test_to_pickle_roundtrip()
    # TestFileAdapterBasic().test_updating_project_file_adapter()
    tfah = TestFileAdapterHdf()
    # tfah.test_hdf_file_creation_and_reuse()
    tfah.test_clean_hdf_files_removes_orphan_temporals()
    tfah.test_clean_hdf_files_deletes_removed_branch_file()
