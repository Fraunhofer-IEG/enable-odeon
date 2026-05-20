from typing import TYPE_CHECKING, Dict, List, Literal, Type, Union

from ..processing.utils.utils import closest_parent_class

import odeon.model as om

if TYPE_CHECKING:
    from ..model.base import Object, Project, Object, Branch, Temporal


class TemporalManager:
    """
    A class that manages the swap mode of temporals in a project or branch(es).

    The TemporalManager doesn't write, read or manage files but just changes
    attributes in Objects.
    """

    # dictionary with types as keys and swap modes as values
    _settings: Dict[Type, str] = None
    _target: Union["Project", "Branch"] = None

    def __init__(self, settings: Union[Dict, Literal["lazy", "loaded", "swapped"]] = "loaded"):
        self.settings = settings

    @property
    def target(self):
        """
        The project or branch(es) whose temporals swap mode is managed by this
        TemporalManager.
        """
        return self._target

    def _set_target(self, target: Union["Project", "Branch"]):
        """
        Set the project or branch whose temporals swap mode is managed by
        this TemporalManager. Should not be called directly. Use the property
        setter in the Project or Branch class instead.
        """
        if not (
            isinstance(target, om.Project)
            or isinstance(target, om.Branch)
            or (isinstance(target, list) and all(isinstance(b, om.Branch) for b in target))
        ):
            raise TypeError("Expected a Project, Branch or list of Branches")
        assert target.temporal_manager is self, "The target's temporal manager is not this instance"
        self._target = target
        self.reset_swap_mode()

    @property
    def settings(self):
        """
        A copy of the settings for this TemporalManager.
        """
        return self._settings.copy()

    @settings.setter
    def settings(self, settings: Union[Dict, Literal["lazy", "loaded", "swapped"]]):
        """
        Set the settings for this TemporalManager. The settings should be a
        dictionary with types as keys and swap modes as values. The swap modes
        should be one of "lazy", "loaded" or "swapped". Alternatively, a
        single swap mode can be given, which will be applied to all types.

        The settings will be applied to all temporals in the target afterwards.
        """
        if not isinstance(settings, dict) and settings not in ["lazy", "loaded", "swapped"]:
            raise TypeError("Expected a dict or one of 'lazy', 'loaded', 'swapped'")
        if isinstance(settings, str):
            self._settings = {om.Object: settings}
        else:
            for key, value in settings.items():
                if not issubclass(key, om.Object):
                    raise TypeError("Expected keys to be types")
                if not isinstance(value, str):
                    raise TypeError("Expected values to be strings")
            self._settings = settings
        if self._target is not None:
            self.reset_swap_mode()

    def load_temporals(self):
        """
        Load all temporals in the currently loaded project (= set the
        swap mode to "loaded").
        """
        self.set_swap_mode(swap_mode="loaded")

    def swap_temporals(self):
        """
        Swap all temporals in the currently loaded project (= set the
        swap mode to "swapped").
        """
        self.set_swap_mode(swap_mode="swapped")

    def swap_or_load_temporals(self, threshold_swap: int = 1, threshold_load: int = 3):
        """
        Swap or load all temporals based on their access counter.

        Parameters
        ----------
        threshold_swap : int
            Temporals with an access counter below this threshold will be swapped.
            Default is 1.
        threshold_load : int
            Temporals with an access counter equal to or above this threshold will
            be loaded. Default is 3.
        """
        target = self._target
        if isinstance(target, om.Project):
            branches = target.branches
        elif isinstance(target, om.Branch):
            branches = [target]
        elif isinstance(target, list):
            assert all(isinstance(b, om.Branch) for b in target)
            branches = target
        else:
            raise TypeError("Expected a Project, Branch or list of Branches")

        for branch in branches:
            branch: om.Branch
            temporals = branch.temporals_recursive()
            for temporal in temporals:
                if temporal._n_accesses < threshold_swap:
                    temporal.swap_mode = "swapped"
                elif temporal._n_accesses >= threshold_load:
                    temporal.swap_mode = "loaded"
                else:
                    temporal.swap_mode = "lazy"

    def set_swap_mode(
        self,
        swap_mode: Literal["lazy", "loaded", "swapped"],
    ):
        """
        Set the swap mode for all temporals in the target, i.e. apply the
        given swap_mode to all temporals in the target. This won't change the
        settings defined in self.settings but may lead to temporals being
        loaded or swapped in contrast to what is defined in self.settings.
        """
        target = self._target
        if isinstance(target, om.Project):
            branches = target.branches
        elif isinstance(target, om.Branch):
            branches = [target]
        elif isinstance(target, list):
            assert all(isinstance(b, om.Branch) for b in target)
            branches = target
        else:
            raise TypeError("Expected a Project, Branch or list of Branches")

        for branch in branches:
            branch: om.Branch
            temporals = branch.temporals_recursive()
            for temporal in temporals:
                temporal.swap_mode = swap_mode

    def reset_swap_mode(self):
        """
        Reset the swap mode for all temporals in the target (i.e. apply
        settings defined in self.settings).
        """
        target = self._target
        if isinstance(target, om.Project):
            branches = target.branches
        elif isinstance(target, om.Branch):
            branches = [target]
        elif isinstance(target, list):
            assert all(isinstance(b, om.Branch) for b in target)
            branches = target
        else:
            raise TypeError("Expected a Project, Branch or list of Branches")

        for branch in branches:
            for object in branch.objects:
                self.apply_settings_for_object(base_object=object, deep=True)

    def apply_settings_for_object(self, base_object: Union["Object", "Temporal"], deep: bool = False):
        """
        Apply the temporal settings for the given object. From the settings,
        the closest parent class of the object that is a key in the settings
        will be used to set the swap mode of the object's temporal. If no parent
        class is found, the swap mode will not be changed.

        If base_object is a Temporal, the swap mode of that temporal will be
        set. If base_object is an Object, the swap modes of all its temporals
        will be set. This won't affect temporals of child objects.
        """
        if isinstance(base_object, om.Temporal):
            temporals = [base_object]
            object = base_object.parent
        else:
            object = base_object
            temporals = object.temporals

        if len(temporals) > 0:
            # find the closest parent class of the object that is a key in the settings:
            cls = closest_parent_class(type(object), list(self._settings.keys()))  # might return None
            if cls is not None:
                for temporal in temporals:
                    temporal.swap_mode = self._settings[cls]

        if deep:
            for child in object.children:
                self.apply_settings_for_object(child, deep=True)

    def reset_access_counters(self):
        """
        Reset the access counters of all temporals in the target. This may
        affect the swapping behaviour if swap_or_load_temporals is used.
        """
        target = self._target
        if isinstance(target, om.Project):
            branches = target.branches
        elif isinstance(target, om.Branch):
            branches = [target]
        elif isinstance(target, list):
            assert all(isinstance(b, om.Branch) for b in target)
            branches = target
        else:
            raise TypeError("Expected a Project, Branch or list of Branches")

        for branch in branches:
            branch: om.Branch
            temporals = branch.temporals_recursive()
            for temporal in temporals:
                temporal._reset_access_counter()
