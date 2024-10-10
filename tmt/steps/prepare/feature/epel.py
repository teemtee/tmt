from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from tmt.steps.prepare.feature import Feature, provides_feature


@provides_feature('epel')
class Epel(Feature):
    NAME = "epel"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def enable(self) -> None:
        self._run_playbook('enable', "epel-enable.yaml")

    def disable(self) -> None:
        self._run_playbook('disable', "epel-disable.yaml")
