import warnings
from pathlib import Path
import importlib.resources as pkg_resources
import os
import yaml
from logging import config as lconfig
import logging
from . import config

FOLDER = os.path.dirname(os.path.abspath(__file__))

# prepare output directory:

if not os.path.exists(Path(os.getcwd()) / "out"):
    os.mkdir(Path(os.getcwd()) / "out")

# prepare logging:


def load_logging_config():

    filename = Path(os.getcwd()) / "config" / "logging.yml"
    if not filename.is_file():
        filename = pkg_resources.files(config) / "logging.yml"
        if not filename.is_file():
            warnings.warn("logging config file not found")

    if filename.is_file():
        print(f"configured logger with file {filename}")
        with open(filename, "r") as stream:
            logging_config_dict = yaml.load(stream, Loader=yaml.FullLoader)
        lconfig.dictConfig(logging_config_dict)
        logging.root.setLevel(logging.DEBUG)  # set root level to debug. doesn't work from dict config...


load_logging_config()
