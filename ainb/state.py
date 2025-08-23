import dataclasses

from ainb.utils import JSONType

@dataclasses.dataclass(slots=True)
class StateInfo:
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
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "StateInfo":
        return cls(
            data["Desired State"],
            data["Unknown04"],
            data["Unknown08"],
            data["Unknown0C"],
            data["Unknown10"],
        )