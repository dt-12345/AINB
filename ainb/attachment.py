import typing

from ainb.common import AINBReader, AINBWriter
from ainb.param_common import ParamType
from ainb.property import PropertySet
from ainb.utils import calc_hash, JSONType

class Attachment:
    """
    Node attachment
    """

    __slots__ = ["name", "debug", "_expression_count", "_expression_io_size", "properties"]

    def __init__(self) -> None:
        self.name: str = ""
        self.debug: int = 0

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
            attachment.debug = reader.read_u32()
            for p_type in ParamType:
                base_index: int = reader.read_u32()
                count: int = reader.read_u32()
                attachment.properties._properties[p_type] = properties._properties[p_type][base_index:base_index+count]
            # 0x30 unknown bytes
        
        return attachment
    
    def _as_dict(self) -> JSONType:
        return {
            "Name" : self.name,
            "Debug" : self.debug,
            "Properties" : self.properties._as_dict(),
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Attachment":
        attachment: Attachment = cls()
        attachment.name = data["Name"]
        attachment.debug = data["Debug"]
        attachment.properties = PropertySet._from_dict(data["Properties"])
        return attachment
    
    def _write(self, writer: AINBWriter, offset: int, index: int, expression_counts: typing.List[int], expression_sizes: typing.List[int], write_hash: bool) -> None:
        writer.write_string_offset(self.name)
        writer.write_u32(offset)
        writer.write_u16(expression_counts[index])
        writer.write_u16(expression_sizes[index])
        if write_hash:
            writer.write_u32(calc_hash(self.name))
    
    def _write_params(self, writer: AINBWriter, prop_indices: typing.List[int]) -> None:
        writer.write_u32(self.debug)
        for p_type in ParamType:
            prop_count: int = len(self.properties.get_properties(p_type))
            writer.write_u32(prop_indices[p_type])
            writer.write_u32(prop_count)
            prop_indices[p_type] += prop_count
        # what is this
        # I wonder if attachments can also have plugs/inputs or something and that's what this is for
        offset: int = writer.tell() + 0x30
        for i in range(6):
            writer.write_u32(0)
            writer.write_u32(offset)