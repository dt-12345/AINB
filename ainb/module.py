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