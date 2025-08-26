import dataclasses

from ainb.utils import JSONType

@dataclasses.dataclass(slots=True)
class UnknownSection0x58:
    description: str = ""
    unk04: int = 0
    unk08: int = 0
    unk0c: int = 0

    def _as_dict(self) -> JSONType:
        return {
            "Description" : self.description,
            "Unknown04" : self.unk04,
            "Unknown08" : self.unk08,
            "Unknown0C" : self.unk0c,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "UnknownSection0x58":
        return cls(
            data["Description"],
            data["Unknown04"],
            data["Unknown08"],
            data["Unknown0C"],
        )