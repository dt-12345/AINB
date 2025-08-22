import dataclasses

from ainb.utils import JSONType

@dataclasses.dataclass(slots=True)
class Module:
    """
    Class representing an external AI node module
    """

    path: str = ""
    category: str = ""
    instance_count: int = 0

    def _as_dict(self) -> JSONType:
        return {
            "Path" : self.path,
            "Category" : self.category,
            "Instance Count" : self.instance_count,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Module":
        return cls(
            data["Path"],
            data["Category"],
            data["Instance Count"],
        )