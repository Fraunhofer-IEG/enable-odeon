!!! warning "Under Construction"

    This documentation is still under construction and will receive major 
    additions and changes in the future. Please be considerate with us and the 
    documentation. However, if you already have any tips and remarks or if you 
    miss some super important aspects, we'd love to hear from you.

# File Adapter

The File Adapter in Odeon provides functionality to read from and write to disk in two file formats:
- **Pickle files** for storing the project including all objects and relations, and 
- **HDF5 files** for optional swapped storage of temporal data. 

## Set-up and pickle files

The File Adapter can operate in two general modes:
- Directory mode
- File mode

### Directory mode

 In this mode, the File Adapter reads from and writes to a directory on disk. The directory will be set as an attribute in the File Adapter; the File Adapter will usually be linked to a project, meaning that the project can be linked to the directory. The directory contains a main pickle file named `project.pk` by default that stores the entire project structure, including all objects and relations. Temporal data can optionally be stored in HDF5 files in the same directory with one file per branch, depending on the configuration of individual Temporals or the Temporal Manager for bulk operations. See [Optional HDF5 storage for temporal data](#optional-hdf5-storage-for-temporal-data) for details.

???+ example "Directory mode: Creating a File Adapter and loading a Project from directory"

    ```python
    from odeon.model import Project
    from odeon.io import FileAdapter

    project = Project()
    file_adapter = FileAdapter(project)

    # Read project from a directory
    file_adapter.read("path/to/project/directory")

    # Write project to a directory
    file_adapter.write("path/to/output/directory")
    ```

???+ exmaple "Directory mode: Writing a Project to directory"

    ```python
    from odeon.model import Project
    from odeon.io import FileAdapter

    project = Project()
    file_adapter = FileAdapter(project)

    # Write project to a directory
    file_adapter.write("path/to/output/directory")
    ```

???+ example "Directory mode: (Re)loading a Project from directory"

    ```python
    from odeon.model import Project
    from odeon.io import FileAdapter

    project = Project()
    file_adapter = FileAdapter(project)

    # Read project from a directory
    file_adapter.read("path/to/project/directory")
    ```


### File mode

In this mode, the File Adapter reads from and writes to a single pickle file. The path of the file won't be stored as an attribute in the File Adapter, and the File Adapter won't be linked to a project. The pickle file stores the entire project structure, including all objects and relations and temporals. Temporal data can not be swapped to HDF5 files in this mode.


???+ example "File mode: Creating a File Adapter and loading a Project from pickle file"

    ```python
    from odeon.model import Project
    from odeon.io import FileAdapter

    project = Project()
    file_adapter = FileAdapter()  # no project linked
    ```

## Optional HDF5 storage for temporal data

### General concept and manual swapping

???+ example "Using HDF5 for temporal data storage"

    ```python
    from odeon.model import Project, Temporal
    from odeon.io import FileAdapter

    project = Project()
    temporal = Temporal()

    file_adapter = FileAdapter(project)

    # Read project from a directory
    file_adapter.read("path/to/project/directory")

    # Write project to a directory
    file_adapter.write("path/to/output/directory")
    ```

### Bulk operations with Temporal Manager

???+ example "Using HDF5 for temporal data storage"

    ```python
    from odeon.model import Project, Temporal
    from odeon.io import FileAdapter

    project = Project()
    temporal = Temporal()

    file_adapter = FileAdapter(project)

    # Read project from a directory
    file_adapter.read("path/to/project/directory")

    # Write project to a directory
    file_adapter.write("path/to/output/directory")
    ```