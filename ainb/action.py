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
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Action":
        return cls(data["Action Slot"], data["Action"])