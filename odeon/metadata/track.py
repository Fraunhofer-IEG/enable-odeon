from copy import copy
from functools import wraps
from typing import List, TYPE_CHECKING, Union

from .call_tracker import CallTracker

import odeon.model as om

if TYPE_CHECKING:
    from odeon.model import Branch, Object


def track(
    varname_git_branch: str | None = None,
    package_names: list[str] | None = None,
    git_modules: list | None = None,
    branch: Union["Branch", None] = None,
):
    """
    Decorator that will make calls of the decorated function appear in the
    branch's call history, together with the versions of the packages
    `package_names` and the git hashs of objects loaded from a local repository
    `git_modules`.

    The argument with name `varname_git_branch` (or the first argument, if None)
    of the decorated function must either be a branch or an object having a
    branch set. The call will be added to that branch's history.

    Parameters
    ----------
    varname_git_branch : str | None
        The name of the parameter that will be used for getting     the branch.
        If None, the first parameter will be used.
    package_names :
        e.g. "['pandas', 'scipy', 'odeon']"
    git_modules :
        List of any imported module or object from a local git repository. For
        example, if odeon was installed with `pip install -e .`, this could be
        "odeon" (imported as such) or any object like "Branch" (imported as
        `from odeon.model import Branch`)

    Examples
    --------
    Simple usage:
    ```python
        @track()
        def x(branch:Branch):
            ...
    ```
    ---
    With parameters:
    ```python
        from odeon import Object

        @track(
            varname_git_branch="my_var",
            package_names=["pandas"],
            git_modules=[Object]
        )
        def y(my_var:Branch):
            ...
    ```
    ---
    `track` can also be used directly in a script instead of decorator usage:
    ```python
        def sum(a,b):
            ...

        result = track(branch=project.root)(sum)(a=1, b=2)
    ```
    """

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):

            # collect args:
            arg_dict = {}
            arg_dict = {varname: arg for arg, varname in zip(args, func.__code__.co_varnames)}
            arg_dict |= kwargs

            # get branch:
            if branch is not None:
                assert isinstance(branch, om.Branch)
                target_branch = branch
            else:
                if varname_git_branch is not None:
                    varname = varname_git_branch
                else:
                    varname = func.__code__.co_varnames[0]
                arg_branch = arg_dict[varname]
                if isinstance(arg_branch, om.Branch):
                    target_branch = arg_branch
                elif isinstance(arg_branch, om.Object) and arg_branch.branch is not None:
                    target_branch = arg_branch.branch
                else:
                    msg = [
                        "The indicated argemunt, or the first argument of a tracked",
                        "call must either be a Branch instance or an instance of",
                        "Object with a branch set.",
                    ]
                    raise Exception(" ".join(msg))

            # open call:
            if not isinstance(target_branch.history, CallTracker):
                raise Exception("Can't decorate function: No CallTracker found in the branch")
            id = target_branch.history.open(
                name=func.__name__,
                args=arg_dict,
                package_names=copy(package_names),
                git_modules=copy(git_modules),
            )
            result = func(*args, **kwargs)

            # close call again:
            target_branch.history.close(id)
            return result

        return wrapper

    return decorator
