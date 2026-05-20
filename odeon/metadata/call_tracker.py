from dataclasses import dataclass, field
from datetime import datetime
import json
from numbers import Integral, Real
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
from importlib.metadata import version
import pandas as pd
import yaml
import inspect
import git
from ..processing.utils import utils


@dataclass
class Call:
    id: int
    name: str
    timestamp_open: datetime = None
    timestamp_close: datetime = None
    args: Dict[str, Any] = field(default_factory=lambda: {})
    log: List[str] = field(default_factory=lambda: [])
    calls: List["Call"] = field(default_factory=lambda: [])
    parent: "Call" = None
    open: bool = True
    package_versions: Dict[str, str] = field(default_factory=lambda: {})
    git_hashs: Dict[str, str] = field(default_factory=lambda: {})

    def add_call(self, c: "Call"):
        self.calls.append(c)
        c.parent = self

    @property
    def duration(self) -> Union[float, None]:
        if self.timestamp_open is not None and self.timestamp_close is not None:
            duration = self.timestamp_close - self.timestamp_open
        return duration.total_seconds()

    def to_dict(self, include_calls: bool = True) -> Dict[str, Any]:
        res = {
            "name": self.name,
            "timestamp_open": str(self.timestamp_open),
        }
        if self.args:
            res["args"] = self.args
        if self.package_versions:
            res["package_versions"] = self.package_versions
        if self.git_hashs:
            res["git_hashs"] = self.git_hashs
        if self.log:
            res["log"] = self.log
        if self.timestamp_close is not None:
            res["total_time"] = self.duration
        if include_calls and self.calls:
            res["calls"] = {c.id: c.to_dict() for c in self.calls}
        return res

    def print(self, include_calls: bool = False):
        d = self.to_dict(include_calls=include_calls)
        print(yaml.dump(data=d, sort_keys=False))


class CallTracker:
    _ids_calls: Dict[int, Call] = None
    _active_call: Call = None
    __hi: int = 0

    def __init__(self):
        self._ids_calls = {}
        self.__hi = -1

    def _get_id(self) -> int:
        self.__hi += 1
        return self.__hi

    @staticmethod
    def is_json_serializable(data):
        try:
            json.loads(data)
        except ValueError as e:
            return False
        return True

    def _get_git_repo_and_hash(self, module) -> Tuple[str, str]:
        path = inspect.getfile(module)
        path = Path(path).parent.absolute()
        cwd = os.getcwd()
        os.chdir(path)
        try:
            repo = git.Repo(search_parent_directories=True)
        except git.InvalidGitRepositoryError as e:
            raise Exception("No git repository found")
        sha = repo.head.object.hexsha
        repo_remote_url = repo.remotes[0].config_reader.get("url")
        repo_remote_name = os.path.splitext(os.path.basename(repo_remote_url))[0]
        os.chdir(cwd)
        return repo_remote_name, sha

    @staticmethod
    def to_str_if_complex_type(x) -> Union[str, bool, float, int]:
        if isinstance(x, Integral):
            return int(x)
        elif isinstance(x, Real):
            return float(x)
        elif isinstance(x, bool):
            return x
        elif isinstance(x, pd.Series):
            return utils.series_to_str(x)
        elif isinstance(x, pd.DataFrame):
            return utils.df_to_str(x)
        else:
            return str(x).split("\n")[0]

    def open(
        self,
        name: str,
        args: Dict[str, Any] = None,
        package_names: List[str] = None,
        git_modules: List = None,
    ) -> int:
        """
        Track the opening of a new call with `name` and `args`. Return
        its id.
        """
        package_names = package_names or []
        git_modules = git_modules or []

        id = self._get_id()
        git_hashs = {}
        for x in git_modules:
            repo, sha = self._get_git_repo_and_hash(x)
            git_hashs[repo] = sha
        call = Call(
            id=id,
            name=name,
            args={k: self.to_str_if_complex_type(v) for k, v in args.items()},
            timestamp_open=datetime.now(),
            package_versions={x: version(x) for x in package_names},
            git_hashs=git_hashs,
        )
        self._ids_calls[id] = call
        if self._active_call is not None:
            self._active_call.add_call(call)
        self._active_call = call
        return id

    def close(self, id: int):
        """
        Track the closing of the call with `id`. All subcalls will be closed,
        too.
        """
        call = self._ids_calls[id]
        assert call.open
        for c in call.calls:
            if c.open:
                self.close(c.id)
        call.open = False
        call.timestamp_close = datetime.now()
        self._active_call = call.parent

    def open_close(self, name: str, args: Dict[str, Any]):
        self.open(name=name, args=args)
        self.close(name=name)

    def log(self, message: str):
        """
        Add a log line to the current call.
        """
        if self._active_call is None:
            raise Exception("No call open")
        assert isinstance(message, str)
        self._active_call.log.append(message)

    def _to_dict(self):
        top_calls = [c for c in self._ids_calls.values() if c.parent is None]
        res = {
            "calls": {tp.id: tp.to_dict() for tp in top_calls},
        }
        return res

    def print(self):
        d = self._to_dict()
        print(yaml.dump(data=d, sort_keys=False))

    def to_file(self, path: Union[str, Path]):
        if not isinstance(path, Path):
            path = Path(path)
        d = self._to_dict()
        if path.suffix == "yml":
            with open(path, "w") as file:
                yaml.dump(d, file, sort_keys=False)
        elif path.suffix == "json":
            with open(path, "w") as file:
                json.dump(d, file, sort_keys=False)
        else:
            Exception("Don't know what to do with this file extension")

    def get_calls_by_name(self, name: str) -> List[Call]:
        return [call for call in self._ids_calls.values() if call.name == name]
