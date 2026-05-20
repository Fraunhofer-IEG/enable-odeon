"""Light‑weight SQLite persistence for Odeon projects.

This module provides :class:`SQLiteAdapter`, an alternative to the HDF based
swapping implemented in :class:`~odeon.io.file_adapter.FileAdapter`. Whereas
``FileAdapter`` focuses on serialising full projects to a single pickle plus
branch‑scoped HDF5 files for temporal swapping, the SQLite adapter targets
incremental access patterns:

Use cases
---------
* Loading only a *subset* of branches into a process (e.g. exploratory work
    on one scenario out of hundreds without incurring the startup cost of the
    full project graph).
* Archiving large temporal payloads (per branch up to ~1 GB) in a compact,
    single‑file format with optional compression.
* Exchanging branch snapshots between environments without requiring the full
    pickle (schema is intentionally flat & explicit).

Design overview
---------------
* One SQLite database file per branch: ``branch_<branch_id>.sqlite``. This
    keeps file sizes bounded and allows OS level parallel IO.
* Two main tables inside each DB:

    ``branch_meta``
            Single row with basic metadata (id, name, year, description JSON).

    ``temporals``
            One row per :class:`~odeon.model.temporal.Temporal`. The constraining
            representation (series *or* shape) is stored as a binary blob (NumPy
            contiguous bytes, optionally zlib compressed). Scalar fields (total, fix)
            are persisted directly. Master/client relationships are recreated via
            stored ``master_id``.

    ``objects``
            One row per :class:`~odeon.model.base.Object` (including organizers).
            The attribute payload is a JSON object where references to other
            Odeon objects or temporals are replaced by id dictionaries, e.g.::

                    {"heat_demand": {"temporal_id": 42}, "parent": {"object_id": 7}}

            Only public attributes (no leading underscore) are considered. Values
            that fail JSON serialisation are replaced by a sentinel string.

Scope & limitations
-------------------
* Detached temporals with explicit timeindices are currently stored *without*
    their index (branch‑attached temporals infer the index from the branch).
* Complex 3rd‑party objects (e.g. shapely geometries) are not yet encoded
    specially; they will appear as ``"<unserialisable:TypeName>"`` in JSON.
* Object attribute reconstruction is best‑effort and based on simple type
    heuristics; custom subclasses with dynamic attributes may need adapters.

Selective loading
-----------------
``read_project`` accepts optional filters for branch ids and description
sub‑dictionary matching so callers can lazily bring branches into memory.
The helper ``list_branches`` inspects the adapter directory without loading
any branches.

Example
-------
>>> adapter = SQLiteAdapter('out/sqlite_store')
>>> adapter.write_project(project)  # persist all branches
>>> meta = adapter.list_branches()  # inspect available branches
>>> slim_project = om.Project()
>>> adapter.read_project(slim_project, branch_ids=[meta[0]['id']])  # load one branch

The adapter purposefully does *not* mutate ``project.file_adapter`` and can
co‑exist with the HDF swapping infrastructure.
"""

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Union, Dict, Any, List, TYPE_CHECKING
import json
import logging

from .utils import object_to_json_dict, object_to_json_str, objects_from_json_strs

import odeon.model as om

if TYPE_CHECKING:
    from odeon.model import Project, Branch

logger = logging.getLogger(name=f"enable.{__name__}")


class SQLiteAdapter:
    """Persist / load a project via per‑branch SQLite databases.

    The implementation mirrors the conceptual style of :class:`FileAdapter`
    (branch‑scoped storage, separation of temporal payload) while optimising
    for selective loading and simple external inspection (plain tables).
    """

    def __init__(self, dir: Union[str, Path]):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def write_project(self, project: "Project"):
        """
        Persist ``project`` into (dir)/(branch_<id>.sqlite) databases.
        Note that the object mapping between branches won't be stored.
        """
        assert isinstance(project, om.Project)
        logger.info("Writing project to SQLite adapter at %s", self.dir)

        # write each branch into its own db file:
        for branch in project.branches:
            self._write_branch(branch=branch)

        # write project metadata:
        self._write_project(project=project)

    def read_project(self) -> "Project":
        """
        The function loads a project from the SQLite adapter directory.
        All branches that are mapped in the project metadata will be loaded.

        Returns
        -------
        Project
            The loaded project with all branches.
        """

        # Find project database file
        project_db_files = list(self.dir.glob("project_*.sqlite"))
        assert len(project_db_files) == 1, f"Expected exactly one project_*.sqlite file, found {len(project_db_files)}"
        db_path = project_db_files[0]

        # read project metadata
        project_meta = self._read_project_meta(db_path=db_path)

        project = om.Project(
            name=project_meta.get("name"),
            boundary_wgs84=project_meta.get("boundary_wgs84_lat_lon"),
            projector=om.Projector(origin=project_meta.get("projector_origin_lat_lon")),
        )

        # load all branches into the project
        self.read_branches_into_project(project=project)

        # Set main branch
        main_branch_id = project_meta.get("main_branch_id")
        assert main_branch_id is not None, "Project main_branch_id is None"
        main_branch = next((b for b in project.branches if b.id == main_branch_id), None)
        assert main_branch is not None, f"Main branch with id {main_branch_id} not found in loaded branches"
        project.main_branch = main_branch

        return project

    def _read_project_meta(self, db_path: Path) -> Dict[str, Any]:
        """Read project metadata from given DB path."""
        con = self._connect(db_path)

        try:

            cur = con.cursor()
            cur.execute(
                """
                SELECT 
                name, boundary_wgs84_lat_lon, projector_origin_lat_lon, branches_ids, main_branch_id 
                FROM project_meta LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                (
                    name,
                    boundary_wgs84_lat_lon,
                    projector_origin_lat_lon,
                    branches_ids,
                    main_branch_id,
                ) = row
                metadata = {
                    "name": name,
                    "boundary_wgs84_lat_lon": boundary_wgs84_lat_lon,
                    "projector_origin_lat_lon": json.loads(projector_origin_lat_lon),
                    "branches_ids": json.loads(branches_ids) if branches_ids else None,
                    "main_branch_id": main_branch_id,
                }

        except Exception as e:
            try:
                con.close()
            except Exception as e:
                logger.warning("Failed closing connection for %s: %s", db_path, e)

            logger.warning("Failed reading metadata from %s: %s", db_path, e)
            raise

        con.close()

        return metadata

    def read_branches_into_project(  # read_branches ???
        self,
        project: "Project",
        branch_ids: List[int] = None,
        description_contains: Dict[str, Any] = None,
    ):
        """
        Load branches into ``project``.
        Note that the object mapping between branches won't be restored.

        Parameters
        ----------
        project : Project
            Target project (can already contain branches; ids must not clash).
        branch_ids : list[int], optional
            Explicit branch ids to load. If None, all available considered.
        description_contains : dict, optional
            Filter: only load branches whose description (stored JSON) contains
            all key/value pairs given here (exact match for those keys).
        """
        assert isinstance(project, om.Project)
        meta = self.list_branches()
        if branch_ids is not None:
            meta = [m for m in meta if m["id"] in branch_ids]
        if description_contains:

            def match(desc: Dict[str, Any]):
                return all(desc.get(k) == v for k, v in description_contains.items())

            meta = [m for m in meta if match(m.get("description") or {})]
        for m in meta:
            path = self.dir / m["filename"]
            self._read_branch_into_project(project, path, m)

    def _read_branch_into_project(self, project: "Project", path: Path, metadata: Dict[str, Any]):
        """Load branch from ``path`` and add it to ``project``."""
        branch = self._read_branch(path=path, metadata=metadata, restore_branch_id=True, restore_ids=True)
        project.add_branches(branch)

    def list_branches(self) -> List[Dict[str, Any]]:
        """Return metadata for all stored branch databases.

        Each dict has: id, filename, name, year, description (dict).
        """
        res = []
        for db_path in self.dir.glob("branch_*.sqlite"):
            try:

                con = self._connect(db_path)

                cur = con.cursor()
                cur.execute("SELECT id, name, year, description_json, object_ids FROM branch_meta LIMIT 1")
                row = cur.fetchone()
                if row:
                    bid, name, year, desc_json, obj_ids = row
                    res.append(
                        {
                            "id": bid,
                            "filename": db_path.name,
                            "name": name,
                            "year": year,
                            "description": json.loads(desc_json) if desc_json else None,
                            "object_ids": json.loads(obj_ids) if obj_ids else None,
                        }
                    )

            except Exception as e:
                try:
                    con.close()
                except Exception as e:
                    logger.warning("Failed closing connection for %s: %s", db_path, e)

                logger.warning("Failed reading metadata from %s: %s", db_path, e)
                raise

            con.close()

        return res

    # ------------------------------------------------------------------
    # Branch level helpers
    # ------------------------------------------------------------------
    def _branch_db_path(self, branch: "Branch") -> Path:
        return self.dir / f"branch_{branch.id}.sqlite"

    def _project_db_path(self, project: "Project") -> Path:
        return self.dir / f"project_{project.name}.sqlite"

    def _connect(self, path: Path):
        return sqlite3.connect(path)

    def _write_branch(self, branch: "Branch"):
        final_path = self._branch_db_path(branch)
        # Direct write (original approach) with explicit open/close to avoid lingering locks.
        con = self._connect(final_path)

        try:

            # ensure schema:
            self._init_schema_branch(con)

            # write branch metadata:
            con.execute(
                "INSERT INTO branch_meta (id, name, year, description_json, object_ids) VALUES (?,?,?,?,?)",
                (
                    branch.id,
                    getattr(branch, "name", None),
                    getattr(branch, "year", None),
                    json.dumps(getattr(branch, "description", None)),
                    json.dumps([o.id for o in branch.objects]),
                ),
            )

            # Collect all objects and temporals:
            objects = branch.objects  # TODO also export organizers
            all_objects = []
            for o in objects:
                all_objects.append(o)
                all_objects.extend(o._offspring_as_set())
            temporals = branch.temporals_recursive()

            # create records for temporals and write them to the db:
            t_rows = []
            for t in temporals:
                assert t.id is not None
                record = t.to_compressed_record()
                t_rows.append(
                    (
                        t.id,
                        record["kind"],
                        record.get("blob"),
                        record.get("dtype"),
                        record.get("length"),
                        record.get("compressed"),
                        record.get("total"),
                        record.get("fix"),
                        t.master.id if t.master is not None else None,
                        json.dumps(record.get("constraints")),
                    )
                )
            con.executemany(
                """
                INSERT INTO temporals
                (id, kind, blob, dtype, length, compressed, total, fix, master_id, constraints_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                t_rows,
            )

            # work records for objects and write them to the db:
            o_rows = []
            for o in all_objects:
                o: om.Object
                row_tuple = (
                    o.id,
                    o.__class__.__name__,
                    o.parent.id if o.parent is not None else None,
                    json.dumps([x.id for x in o.children]) if o.children else None,
                    json.dumps([x.id for x in o.associated]) if o.associated else None,
                    json.dumps([x.id for x in o.temporals]) if o.temporals else None,
                    object_to_json_str(obj=o),
                )
                o_rows.append(row_tuple)
            con.executemany(
                "INSERT INTO objects (id, class, parent_id, children_ids, associated_ids, temporal_ids, json) VALUES (?,?,?,?,?,?,?)",
                o_rows,
            )

            con.commit()
            logger.info("Branch %s written (%d objects, %d temporals)", branch.id, len(all_objects), len(temporals))

        except Exception as e:
            try:
                con.close()
            except:
                logger.error("Failed to close connection after error for branch %s: %s", branch.id, e)
            logger.error("Failed writing branch %s to SQLite: %s", branch.id, e)
            raise

        con.close()

    def _write_project(self, project: "Project"):
        final_path = self._project_db_path(project)
        # Direct write (original approach) with explicit open/close to avoid lingering locks.
        con = self._connect(final_path)

        try:

            # ensure schema:
            self._init_schema_project(con)

            # write branch metadata:
            con.execute(
                """
                INSERT INTO project_meta 
                (name, boundary_wgs84_lat_lon, projector_origin_lat_lon, branches_ids, main_branch_id) 
                VALUES (?,?,?,?,?)
                """,
                (
                    getattr(project, "name", None),
                    getattr(project, "boundary_wgs84", None),
                    json.dumps(getattr(project.projector, "origin_lat_lon", None)),
                    json.dumps([br.id for br in project.branches]),
                    getattr(project.main_branch, "id", None),
                ),
            )

            con.commit()
            logger.info("Project %s written", project.name)

        except Exception as e:
            try:
                con.close()
            except:
                logger.error("Failed to close connection after error for project %s: %s", project.name, e)
            logger.error("Failed writing project %s to SQLite: %s", project.name, e)
            raise

        con.close()

    def _read_branch(
        self,
        path: Path,
        metadata: Dict[str, Any],
        restore_branch_id: bool = False,
        restore_ids: bool = False,
    ) -> "Branch":
        """
        Load branch from ``path``.

        Parameters
        ----------
        path : Path
            Path to branch_<id>.sqlite file.
        metadata : dict
            Metadata dict as returned by ``list_branches``.
        restore_branch_id : bool, optional
            If True, force the branch id to match the stored one. Otherwise,
            a new id will be assigned to the branch.
        restore_ids : bool, optional
            If True, force the restoration of all object ids to match the stored
            ones. Otherwise, new ids will be assigned to all objects.
        """

        con = self._connect(path)

        try:

            cur = con.cursor()
            # Load temporals
            cur.execute(
                "SELECT id, kind, blob, dtype, length, compressed, total, fix, master_id, constraints_json FROM temporals"
            )
            temporal_rows = cur.fetchall()

            # Create empty branch:
            branch = om.Branch(
                year=metadata.get("year"),
                name=metadata.get("name"),
                description=metadata.get("description"),
            )
            branch_object_ids = metadata.get("object_ids")

            # Use the stored id for the branch for the moment. Depending on the
            # parameter `restore_branch_id` we will either keep it or reassign
            # a new one later:
            branch_id = metadata.get("id")
            if restore_branch_id:
                branch._Identified__id = branch_id

            # Reconstruct temporals
            id_temporal_map: Dict[int, om.Temporal] = {}
            temporal_master_map: Dict[int, int] = {}
            for row in temporal_rows:
                (tid, kind, blob, dtype, length, compressed, total, fix, master_id, constraints_json) = row
                record = {
                    "kind": kind,
                    "blob": blob,
                    "dtype": dtype,
                    "length": length,
                    "compressed": compressed,
                    "total": total,
                    "fix": fix,
                    "constraints": json.loads(constraints_json) if constraints_json else {},
                }
                temporal = om.Temporal.from_compressed_record(record)
                temporal._Identified__id = tid
                id_temporal_map[tid] = temporal
                if master_id is not None:
                    temporal_master_map |= {temporal: master_id}
            temporals = list(id_temporal_map.values())

            # Reconstruct master-client relationships:
            for temporal, master_id in temporal_master_map.items():
                id_temporal_map.get(master_id).add_client(temporal)

            # Parse objects:
            cur.execute("SELECT id, class, parent_id, children_ids, associated_ids, temporal_ids, json FROM objects")
            object_rows = cur.fetchall()
            object_jsons = [row[6] for row in object_rows]
            objects = objects_from_json_strs(datas=object_jsons, temporals=temporals)

            # add those objects to the branch that have no parent (top-level):
            for o in objects:
                if o.parent is None:
                    if o.id not in branch_object_ids:
                        logger.warning(
                            "Top-level object %s (id %s) not listed in branch metadata; skipping",
                            o.__class__.__name__,
                            o.id,
                        )
                        continue

                    # branch.add_objects(o)  # deactivated
                    # Instead directly manipulate private attributes to add
                    # objects to avoid id mess up that is caused here by
                    # _set_parent which is called in branch.add_objects /MJ
                    branch._Branch__objects.add(o)
                    o._Object__parent = branch

            # Deal new object ids if desired:
            for o in objects:
                if not restore_ids:
                    o._set_new_id_from_authority()

        except Exception as e:
            try:
                con.close()
            except Exception as e:
                logger.warning("Failed closing connection for %s: %s", path, e)
            branch_id = metadata.get("id")
            logger.error("Failed reading branch %s from SQLite: %s", branch_id, e)
            raise

        con.close()

        logger.info(
            "Loaded branch %s from %s (%d temporals, %d objects)",
            branch_id,
            path,
            len(temporals),
            len(objects),
        )

        return branch

    def _init_schema_branch(self, con):
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS branch_meta (
                id INTEGER PRIMARY KEY,
                name TEXT,
                year INTEGER,
                description_json TEXT,
                object_ids TEXT
            );
            CREATE TABLE IF NOT EXISTS temporals (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                blob BLOB,
                dtype TEXT,
                length INTEGER,
                compressed INTEGER,
                total REAL,
                fix REAL,
                master_id INTEGER,
                constraints_json TEXT
            );
            CREATE TABLE IF NOT EXISTS objects (
                id INTEGER PRIMARY KEY,
                class TEXT NOT NULL,
                parent_id INTEGER,
                children_ids TEXT,
                associated_ids TEXT,
                temporal_ids TEXT,
                json TEXT NOT NULL
            );
            """
        )

    def _init_schema_project(self, con):
        con.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS project_meta (
                name TEXT PRIMARY KEY,
                boundary_wgs84_lat_lon TEXT,
                projector_origin_lat_lon TEXT,
                branches_ids TEXT,
                main_branch_id INTEGER
            );
            """
        )
