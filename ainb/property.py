import typing

from ainb.common import AINBReader, AINBWriter
from ainb.param_common import ParamType, ParamFlag
from ainb.utils import DictDecodeError, JSONType, ValueType

PROPERTY_SIZES: typing.Final[typing.Dict[ParamType, int]] = {
    ParamType.Int : 0xc,
    ParamType.Bool : 0xc,
    ParamType.Float : 0xc,
    ParamType.String : 0xc,
    ParamType.Vector3F : 0x14,
    ParamType.Pointer : 0xc,
}

class Property:
    """
    A node/attachment property
    """

    __slots__ = ["name", "classname", "type", "flags", "default_value"]

    def __init__(self, param_type: ParamType) -> None:
        self.name: str = ""
        self.classname: str = ""
        self.type: ParamType = param_type
        self.flags: ParamFlag = ParamFlag()
        self.default_value: ValueType = None

    @classmethod
    def _read(cls, reader: AINBReader, param_type: ParamType) -> "Property":
        property: Property = cls(param_type)
        property.name = reader.read_string_offset()
        if param_type == ParamType.Pointer:
            property.classname = reader.read_string_offset()
        property.flags = ParamFlag(reader.read_u32())
        property.default_value = cls._read_value(reader, param_type)
        return property

    @staticmethod
    def _read_value(reader: AINBReader, param_type: ParamType) -> ValueType:
        match (param_type):
            case ParamType.Int:
                return reader.read_s32()
            case ParamType.Bool:
                return reader.read_u32() != 0
            case ParamType.Float:
                return reader.read_f32()
            case ParamType.String:
                return reader.read_string_offset()
            case ParamType.Vector3F:
                return reader.read_vec3()
            case ParamType.Pointer:
                return None
            
    @staticmethod
    def _get_binary_size(param_type: ParamType) -> int:
        return PROPERTY_SIZES[param_type]
    
    def _as_dict(self) -> JSONType:
        if self.type == ParamType.Pointer:
            return {
                "Name" : self.name,
                "Classname" : self.classname,
                "Default Value" : self.default_value,
            } | self.flags._as_dict()
        else:
            return {
                "Name" : self.name,
                "Default Value" : self.default_value,
            } | self.flags._as_dict()
    
    @classmethod
    def _from_dict(cls, data: JSONType, param_type: ParamType) -> "Property":
        prop: Property = cls(param_type)
        prop.name = data["Name"]
        if param_type == ParamType.Pointer:
            prop.classname = data["Classname"]
        match (param_type):
            case ParamType.Int:
                prop.default_value = int(data["Default Value"])
            case ParamType.Bool:
                prop.default_value = bool(data["Default Value"])
            case ParamType.Float:
                prop.default_value = float(data["Default Value"])
            case ParamType.String:
                prop.default_value = str(data["Default Value"])
            case ParamType.Vector3F:
                prop.default_value = tuple(data["Default Value"])
            case ParamType.Pointer:
                prop.default_value = data["Default Value"]
                if prop.default_value is not None:
                    raise DictDecodeError("Pointer properties must have a default value of null")
        prop.flags = ParamFlag._from_dict(data)
        return prop
    
    def _write_value(self, writer: AINBWriter, param_type: ParamType) -> None:
        match (param_type):
            case ParamType.Int:
                writer.write_s32(self.default_value) # type: ignore
            case ParamType.Bool:
                writer.write_u32(self.default_value) != 0 # type: ignore
            case ParamType.Float:
                writer.write_f32(self.default_value) # type: ignore
            case ParamType.String:
                writer.write_string_offset(self.default_value) # type: ignore
            case ParamType.Vector3F:
                writer.write_vec3(self.default_value) # type: ignore
            case ParamType.Pointer:
                pass
    
    def _write(self, writer: AINBWriter, param_type: ParamType) -> None:
        writer.write_string_offset(self.name)
        if param_type == ParamType.Pointer:
            writer.write_string_offset(self.classname)
        writer.write_u32(self.flags)
        self._write_value(writer, param_type)

class PropertySet:
    """
    A set of node/attachment properties
    """

    __slots__ = ["_properties"]

    def __init__(self) -> None:
        self._properties: typing.List[typing.List[Property]] = [
            [], [], [], [], [], []
        ]

    @property
    def int_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.Int]
    
    @property
    def bool_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.Bool]
    
    @property
    def float_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.Float]
    
    @property
    def string_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.String]
    
    @property
    def vec3f_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.Vector3F]
    
    @property
    def ptr_properties(self) -> typing.List[Property]:
        return self._properties[ParamType.Pointer]
    
    def get_properties(self, param_type: ParamType) -> typing.List[Property]:
        return self._properties[param_type]

    @classmethod
    def _read(cls, reader: AINBReader, end_offset: int) -> "PropertySet":
        pset: PropertySet = cls()
        offsets: typing.Tuple[int, ...] = reader.unpack("<6I")
        end_offsets: typing.Tuple[int, ...] = (*offsets[1:], end_offset)
        for p_type in ParamType:
            with reader.temp_seek(offsets[p_type]):
                pset._properties[p_type] = [
                    Property._read(reader, p_type) for i in range(int((end_offsets[p_type] - offsets[p_type]) / Property._get_binary_size(p_type)))
                ]
        return pset
    
    def _as_dict(self) -> JSONType:
        return {
            p_type.name : [ prop._as_dict() for prop in self.get_properties(p_type) ] for p_type in ParamType if self.get_properties(p_type)
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "PropertySet":
        pset: PropertySet = cls()
        for p_type in ParamType:
            if p_type.name not in data:
                continue
            pset._properties[p_type] = [
                Property._from_dict(prop, p_type) for prop in data[p_type.name]
            ]
        return pset
    
    def __bool__(self) -> bool:
        return any(p for p in self._properties)
    
    def clear(self) -> None:
        self._properties = [[], [], [], [], [], []]

    def _write(self, writer: AINBWriter) -> None:
        base_offset: int = writer.tell() + 0x18
        for p_type in ParamType:
            writer.write_u32(base_offset)
            base_offset += Property._get_binary_size(p_type) * len(self.get_properties(p_type))
        for p_type in ParamType:
            for prop in self.get_properties(p_type):
                prop._write(writer, p_type)