from ainb.common import AINBReader
from ainb.param_common import ParamType
from ainb.property import PropertySet
from ainb.utils import JSONType

class Attachment:
    """
    Node attachment
    """

    __slots__ = ["name", "_expression_count", "_expression_io_size", "properties"]

    def __init__(self) -> None:
        self.name: str = ""

        # these aren't necessary to store, we can calculate them later
        self._expression_count: int = 0
        self._expression_io_size: int = 0

        self.properties: PropertySet = PropertySet()

    @classmethod
    def _read(cls, reader: AINBReader, properties: PropertySet) -> "Attachment":
        attachment: Attachment = cls()
        attachment.name = reader.read_string_offset()
        offset: int = reader.read_u32()
        attachment._expression_count = reader.read_u16()
        attachment._expression_io_size = reader.read_u16()
        if reader.version >= 0x407:
            name_hash: int = reader.read_u32()

        with reader.temp_seek(offset):
            unk: int = reader.read_u32()
            for p_type in ParamType:
                base_index: int = reader.read_u32()
                count: int = reader.read_u32()
                attachment.properties._properties[p_type] = properties._properties[p_type][base_index:base_index+count]
            # 0x30 unknown bytes
        
        return attachment
    
    def _as_dict(self) -> JSONType:
        return {
            "Name" : self.name,
            "Properties" : self.properties._as_dict(),
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Attachment":
        attachment: Attachment = cls()
        attachment.name = data["Name"]
        attachment.properties = PropertySet._from_dict(data["Properties"])
        return attachment