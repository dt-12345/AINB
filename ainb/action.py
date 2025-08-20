import typing

from ainb.utils import JSONType

class Action(typing.NamedTuple):
    """
    Class representing an XLink action triggered by a node
    """

    action_slot: str = ""
    action: str = ""

    def _as_dict(self) -> JSONType:
        return {
            "Action Slot" : self.action_slot,
            "Action" : self.action,
        }