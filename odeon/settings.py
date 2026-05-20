import importlib.resources as pkg_resources
import os
import warnings
from logging import config as lconfig
from pathlib import Path

import yaml

from . import config

# prepare settings:

filename = Path(os.getcwd()) / "config" / "config.yml"
if not filename.is_file():
    filename = pkg_resources.files(config) / "config.yml"
    if not filename.is_file():
        warnings.warn("settings file not found")

SETTINGS = {}
if filename.is_file():
    with open(filename, "r") as stream:
        SETTINGS = yaml.load(stream, Loader=yaml.FullLoader)
