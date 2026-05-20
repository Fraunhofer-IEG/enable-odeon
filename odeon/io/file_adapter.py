from pathlib import Path
import pickle
import json
import time
import os
import logging
from typing import Literal, Tuple, List, Union, Dict, TYPE_CHECKING
import warnings
import h5py

from ..processing.utils.utils import file_size_as_str, typeerror_if_not_isinstance, typeerror_if_not_isinstance_or_none

import odeon.model as om

if TYPE_CHECKING:
    from ..model.base import Project, Branch

logger = logging.getLogger(name=f"enable.{__name__}")


class FileAdapter:
    """
    A class that links a project with a directory on the filesystem. Additionally, it
    provides methods to load and store projects from/to pickle files, and to manage
    HDF files for temporals.
    """

    _dir: Union[Path, None] = None
    _project: Union["Project", None] = None
    _branches_hdffilenames: Dict["Branch", str] = None
    _branches_hdffiles: Dict["Branch", h5py.File] = None

    def __init__(
        self,
        dir: Union[Path, None] = None,
        project: Union["Project", None] = None,
    ):
        self.dir = dir  # call setter
        self._project = None
        self._branches_hdffilenames = {}
        self._branches_hdffiles = {}
        self._set_project(project)  # might set file_adapter of project

    def _clear_branches(self):
        """
        Clear the stored HDF filenames and close any open HDF files.
        """
        for branch in self._branches_hdffiles:
            self._branches_hdffiles[branch].close()
        self._branches_hdffilenames.clear()
        self._branches_hdffiles.clear()

    @classmethod
    def from_dir(cls, dir: Path) -> "FileAdapter":
        """
        Load a project from a pickle file stored in the given directory. The
        directory must contain exactly one pickle file. This will create a new
        FileAdapter instance with the given directory and set it to the loaded
        project. The FileAdapter will have its directory assigned to the given
        directory.
        """
        assert isinstance(dir, Path)
        pk_files = [f for f in os.listdir(dir) if f.endswith(".pk")]
        assert len(pk_files) == 1, f"Directory {dir} must contain exactly one .pk file"
        file_adapter = cls.from_pickle(dir / pk_files[0])
        file_adapter.dir = dir

        return file_adapter

    @classmethod
    def from_pickle(cls, filename: str) -> "FileAdapter":
        """
        Load a project from a pickle file stored anywhere in the file system.
        This will create a new FileAdapter instance and set it to the loaded
        project. The FileAdapter will not have a directory assigned.
        """
        tic = time.time()
        with open(filename, "rb") as file:
            project = pickle.load(file)
        assert isinstance(project, om.Project)

        # set the gloabl ID authority's value to the one stored in the project:
        # DISCUSSION shoudn't the whole id_authority be replaced instead?
        if isinstance(project.id_authority, om.IdAuthority):
            om.base.id_authority.set_last_value(project.id_authority.last_value)

        toc = time.time()
        s = file_size_as_str(filename)
        t = round(abs(tic - toc), 1)
        n = len(project.branches)

        logger.info(f"loaded pickle from {filename} ({s}, {t} s, {n} branches)")

        # create a new file adapter for the loaded project:
        file_adapter = cls(dir=None, project=project)

        return file_adapter

    @property
    def project(self) -> Union["Project", None]:
        """
        The project currently loaded in the file adapter, or None if no
        project is loaded.
        """
        return self._project

    def _set_project(self, project: Union["Project", None]):
        """
        Set the project currently loaded in the file adapter. This will set
        the file_adapter attribute of the project to this file adapter if it
        is not already set to a different file adapter. Should not be
        called directly. Use the property setter in the Project class instead.
        """
        typeerror_if_not_isinstance_or_none(project, om.Project)

        # remove the file adapter from the previous project, if any:
        if self._project is not None:
            self._project._file_adapter = None  # don't use setter to avoid recursion

        # set the new project, if any:
        if project is not None:
            if project.file_adapter is not None and project.file_adapter is not self:
                raise ValueError("The provided project already has a different file adapter assigned")
            self._project = project
            project._file_adapter = self  # don't use setter to avoid recursion
        else:
            self._project = None

        # clear any stored branch HDF filenames and close open HDF files:
        self._clear_branches()

    @property
    def dir(self) -> Union[Path, None]:
        """
        The directory where project files will be stored.
        """
        return self._dir

    @dir.setter
    def dir(self, dir: Path):
        """
        Sets the directory for the project.
        """
        typeerror_if_not_isinstance_or_none(dir, (Path, str))
        if isinstance(dir, str):
            dir = Path(dir)
        if dir != self._dir and self._dir is not None:
            msg = (
                "You are changing the directory of a file manager that already",
                "has a directory assigned. If timeseries files have been swapped",
                "to this directory, they won't be available any more unless",
                "you move them manually.",
            )
            warnings.warn(" ".join(msg))
        if dir is not None:
            dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Set file manager directory to {dir}")
        self._dir = dir

    def write_to_dir(
        self,
        filename: str = "project.pk",
        overwrite: bool = True,
    ) -> Path:
        """
        Export the project to the file manager's directory with the given
        filename. Returns the Path of the created pickle.

        This will only write the pickle. Swap files for the temporals might
        have been created before, or not, in the same directory.
        """
        project = self.project
        if not isinstance(project, om.Project):
            raise ValueError("No project provided and no project loaded in file adapter")
        if self.dir is None:
            raise ValueError("File manager directory is not set")
        path = self.dir / filename
        self.write_to_pickle(filename=path, overwrite=overwrite, error_if_swapped_temporals=False)
        return path

    def write_to_pickle(
        self,
        filename: str,
        overwrite: bool = True,
        error_if_swapped_temporals: bool = True,
    ):
        """
        Store the file adapter's project to a pickle file with the given
        filename relative to the working dir (may contain path-elements).  The file adapter's directory is not used. Note that the
        stored pickle might not contain all temporal data if some timeseries
        are swapped to HDF files. In that case, the HDF files must be kept
        alongside the pickle file to be able to load the project again.
        """
        project = self.project

        # assert that no temporals with swap_mode "swapped" exist:
        if error_if_swapped_temporals:
            swapped_temporals = []
            for branch in project.branches:
                swapped_temporals += [t for t in branch.temporals_recursive() if t._swapped or t.swap_mode != "loaded"]
            if len(swapped_temporals) > 0:
                raise ValueError(
                    f"Cannot store project to pickle because it contains {len(swapped_temporals)} "
                    "temporals that are swapped or in swap_mode 'swapped'. Please load them first or set "
                    "error_if_swapped_temporals to False."
                )

        # store the global ID authority so that it can be restored when loading:
        project.id_authority = om.base.id_authority

        path = Path(filename)
        if path.exists() and not overwrite:
            raise FileExistsError(f"File {filename} already exists and overwrite is False")

        # temporarily disconnect the file adapter to avoid recursive references:
        file_adapter = project.file_adapter
        project.file_adapter = None

        tic = time.time()
        with open(filename, "wb") as file:
            pickle.dump(project, file)
        toc = time.time()

        # reconnect the file adapter:
        project.file_adapter = file_adapter

        logger.info(f"stored pickle to {filename} ({file_size_as_str(filename)}, {round(abs(tic-toc), 1)} s)")

    def get_hdf_path_for_branch(self, branch: "Branch") -> Path:
        """
        Get the HDF path for the given branch. If no path has been assigned yet,
        a new filename will be generated from the branch ID.
        """
        typeerror_if_not_isinstance(branch, om.Branch)
        if self.dir is None:
            raise ValueError("File manager directory is not set")
        if self._project is None:
            raise ValueError("File manager has no project assigned")
        if branch not in self._project.branches:
            raise ValueError("Branch is not part of the project associated with this file adapter")
        filename = self._branches_hdffilenames.get(branch, None)
        if filename is None:
            filename = f"branch_{branch.id}.hdf"
            self._branches_hdffilenames[branch] = filename
        return self.dir / filename

    def get_hdf_file_for_branch(self, branch: "Branch") -> h5py.File:
        """
        Get the HDF file for the given branch. If no file has been opened yet,
        it will be opened in "r+" mode.
        """
        typeerror_if_not_isinstance(branch, om.Branch)
        if self.dir is None:
            raise ValueError("File manager directory is not set")
        path = self.get_hdf_path_for_branch(branch)
        hdf_file = self._branches_hdffiles.get(branch, None)
        if hdf_file is None:
            if not os.path.isfile(path):
                with h5py.File(path, "w") as f:  # create empty hdf file
                    pass
            hdf_file = h5py.File(path, "r+")
            self._branches_hdffiles[branch] = hdf_file
        return hdf_file

    def flush_hdf_files(self):
        """
        Flush all open HDF files to ensure that all data is written to disk.
        """
        for hdf_file in self._branches_hdffiles.values():
            hdf_file.flush()

    def close_hdf_files(self, only_orphans: bool = False):
        """
        Close all open HDF files. If only_orphans is True, only close HDF files
        of branches that don't exist in the project anymore.
        """

        if self.dir is None or self.project is None:
            return

        existing_branch_ids = {branch.id for branch in self.project.branches}
        for branch in list(self._branches_hdffiles.keys()):
            if not only_orphans or (branch.id not in existing_branch_ids):
                self.close_hdf_file_for_branch(branch)

    def close_hdf_file_for_branch(self, branch: "Branch"):
        """
        Close the HDF file for the given branch, if it is open.
        """
        typeerror_if_not_isinstance(branch, om.Branch)
        hdf_file = self._branches_hdffiles.get(branch, None)
        if hdf_file is not None:
            hdf_file.close()
            del self._branches_hdffiles[branch]

    def clean(self, delete_files: bool = False):
        """
        Delete all temporals stored in HDF files that don't exist in the project
        anymore. Temporals that still exist but are currently loaded (i.e. not
        swapped) won't be deleted.

        HDF files of branches that don't exist anymore will be closed. If
        delete_files is True, HDF files of non-existing branches will be
        deleted as well.

        If the file adapter has no directory or no project assigned, this method
        does nothing.
        """
        if self.dir is None or self.project is None:
            return

        # remove keys in HDF files that don't exist anymore:
        self._remove_unused_temporal_keys()

        # close HDF files of branches that aren't part of the project anymore:
        self.close_hdf_files(only_orphans=True)

        # delete HDF files of branches that don't exist anymore:
        if delete_files:
            self._delete_unused_hdf_files()

    def _remove_unused_temporal_keys(self):
        """
        Remove keys in HDF files that don't correspond to temporals that exist
        anymore.
        """
        for branch in self.project.branches:
            # get all keys in HDF file:
            hdf_file = self.get_hdf_file_for_branch(branch)
            keys = list(hdf_file.keys())
            # delete keys that don't exist anymore:
            existing_temporals = branch.temporals_recursive()
            existing_keys = {om.temporal.hdf_key_from_temporal(temporal) for temporal in existing_temporals}
            for key in keys:
                if key not in existing_keys:
                    del hdf_file[key]
            hdf_file.flush()

    def _delete_unused_hdf_files(self):
        """
        Delete HDF files of branches that don't exist in the project anymore.
        """
        if self.dir is None or self.project is None:
            return
        existing_branch_ids = {branch.id for branch in self.project.branches}
        for filename in os.listdir(self.dir):
            if filename.startswith("branch_") and filename.endswith(".hdf"):
                branch_id = int(filename[len("branch_") : -len(".hdf")])
                if branch_id not in existing_branch_ids:
                    path = self.dir / filename
                    os.remove(path)
                    logger.info(f"deleted HDF file {path} of non-existing branch")

    def __del__(self):
        self.close_hdf_files()
