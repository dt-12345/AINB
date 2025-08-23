import dataclasses
import enum

from ainb.utils import JSONType

class ReplacementType(enum.Enum):
    Invalid = -1
    RemoveChild = 0
    ReplaceChild = 1
    RemoveAttachment = 2

@dataclasses.dataclass(slots=True)
class ReplacementEntry:
    """
    Class representing a runtime replacement entry
    """
    type: ReplacementType = ReplacementType.Invalid
    node_index: int = -1
    replace_index: int = -1 # child node index or attachment index
    new_index: int = -1 # for replacements

    def _as_dict(self) -> JSONType:
        output: JSONType = {
            "Type" : self.type.name,
            "Node Index" : self.node_index,
        }
        if self.type != ReplacementType.RemoveAttachment:
            output["Child Plug Index"] = self.replace_index
            if self.type == ReplacementType.ReplaceChild:
                output["Replacement Node Index"] = self.new_index
        else:
            output["Attachment Index"] = self.replace_index
        return output
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "ReplacementEntry":
        t: ReplacementType = ReplacementType[data["Type"]]
        if t == ReplacementType.RemoveAttachment:
            return cls(
                t, data["Node Index"], data["Attachment Index"]
            )
        elif t == ReplacementType.RemoveChild:
            return cls(
                t, data["Node Index"], data["Child Plug Index"]
            )
        else:
            return cls(
                t, data["Node Index"], data["Child Plug Index"], data["Replacement Node Index"]
            )