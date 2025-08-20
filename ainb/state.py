import typing

from ainb.utils import JSONType

class StateInfo(typing.NamedTuple):
    """
    Class representing game state information for a node

    In Splatoon 3, this is used to determine when to transition to a given node
    """

    desired_state: str
    unk04: int
    unk08: int
    unk0c: int
    unk10: int

    def _as_dict(self) -> JSONType:
        return {
            "Desired State" : self.desired_state,
            "Unknown04" : self.unk04,
            "Unknown08" : self.unk08,
            "Unknown0C" : self.unk0c,
            "Unknown10" : self.unk10,
        }