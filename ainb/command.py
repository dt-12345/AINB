from ainb.common import AINBReader, AINBWriter
from ainb.utils import JSONType

class Command:
    """
    Class representing an AI command
    """

    __slots__ = ["name", "guid", "root_node_index", "secondary_root_node_index"]

    def __init__(self) -> None:
        self.name: str = ""
        self.guid: str = "00000000-0000-0000-0000-000000000000"
        self.root_node_index: int = -1
        self.secondary_root_node_index: int = -1

    @classmethod
    def _read(cls, reader: AINBReader) -> "Command":
        cmd: Command = cls()
        cmd.name = reader.read_string_offset()
        cmd.guid = reader.read_guid()
        cmd.root_node_index = reader.read_u16()
        cmd.secondary_root_node_index = reader.read_u16() - 1
        return cmd
    
    def _as_dict(self) -> JSONType:
        if self.secondary_root_node_index < 0:
            return {
                "Name" : self.name,
                "GUID" : self.guid,
                "Root Node Index" : self.root_node_index,
            }
        else:
            return {
                "Name" : self.name,
                "GUID" : self.guid,
                "Root Node Index" : self.root_node_index,
                "Secondary Root Node Index" : self.secondary_root_node_index,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Command":
        cmd: Command = cls()
        cmd.name = data["Name"]
        cmd.guid = data["GUID"]
        cmd.root_node_index = data["Root Node Index"]
        cmd.secondary_root_node_index = data.get("Secondary Root Node Index", -1)
        return cmd
    
    def _write(self, writer: AINBWriter) -> None:
        writer.write_string_offset(self.name)
        writer.write_guid(self.guid)
        writer.write_u16(self.root_node_index)
        writer.write_u16(self.secondary_root_node_index + 1)