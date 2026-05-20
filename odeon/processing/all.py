import odeon.model as om


def get_class_by_name(class_name: str) -> type:
    """
    Get a class from the odeon.model module by its name.

    Parameters
    ----------
    class_name : str
        The name of the class to retrieve

    Returns
    -------
    type
        The class with the specified name

    Raises
    ------
    ValueError
        If no class with the specified name is found
    """
    for cls in om.__dict__.values():
        if isinstance(cls, type) and cls.__name__ == class_name:
            return cls
    raise ValueError(f"No class found with the name '{class_name}'")