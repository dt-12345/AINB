import dataclasses
import os
import typing

from ainb.common import AINBReader, AINBWriter
from ainb.utils import calc_hash, DictDecodeError, IntEnumEx, JSONType, ValueType

class BBParamType(IntEnumEx):
    """
    Blackboard parameter type enum
    """

    String = 0
    S32 = 1
    F32 = 2
    Bool = 3
    Vec3f = 4
    VoidPtr = 5

class BBParam:
    """
    Blackboard parameter class
    """

    __slots__ = ["name", "type", "notes", "file_ref", "flags", "default_value"]

    def __init__(self, param_type: BBParamType) -> None:
        self.name: str = ""
        self.type: BBParamType = param_type
        self.notes: str = ""
        self.file_ref: str = ""
        # 2 bits, lower bit is set for params that are inheritable between modules
        # if not inheriting, then both bits must be zero in order for params to automatically be matched between modules
        self.flags: int = 0
        self.default_value: ValueType = None

    def _as_dict(self, index: int) -> JSONType:
        if self.file_ref != "":
            return {
                "Blackboard Index" : index,
                "Name" : self.name,
                "Notes" : self.notes,
                "Source File" : self.file_ref,
                "Flags" : self.flags,
                "Default Value" : self.default_value,
            }
        else:
            return {
                "Blackboard Index" : index,
                "Name" : self.name,
                "Notes" : self.notes,
                "Flags" : self.flags,
                "Default Value" : self.default_value,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType, param_type: BBParamType) -> "BBParam":
        param: BBParam = cls(param_type)
        param.name = data["Name"]
        param.notes = data["Notes"]
        if "Source File" in data:
            param.file_ref = data["Source File"]
        param.flags = data["Flags"]
        match (param_type):
            case BBParamType.String:
                param.default_value = str(data["Default Value"])
            case BBParamType.S32:
                param.default_value = int(data["Default Value"])
            case BBParamType.F32:
                param.default_value = float(data["Default Value"])
            case BBParamType.Bool:
                param.default_value = bool(data["Default Value"])
            case BBParamType.Vec3f:
                param.default_value = tuple(data["Default Value"])
            case BBParamType.VoidPtr:
                param.default_value = data["Default Value"]
                if param.default_value is not None:
                    raise DictDecodeError("Pointer params must have a default value of null")
        return param
    
    def _calc_size(self, file_refs: typing.Set[str]) -> int:
        if self.file_ref != "" and self.file_ref not in file_refs:
            file_refs.add(self.file_ref)
            return 0x18 + (0xc if self.type == BBParamType.Vec3f else 0 if self.type == BBParamType.VoidPtr else 4)
        else:
            return 8 + (0xc if self.type == BBParamType.Vec3f else 0 if self.type == BBParamType.VoidPtr else 4)

@dataclasses.dataclass(slots=True)
class BBParamHeader:
    param_count: int
    base_index: int
    offset: int

@dataclasses.dataclass(slots=True)
class BBParamInfo:
    file_ref_index: int
    name: str
    notes: str
    flags: int

class Blackboard:
    """
    Blackboard
    """

    __slots__ = ["_params"]

    def __init__(self) -> None:
        self._params: typing.List[typing.List[BBParam]] = [
            [], [], [], [], [], []
        ]

    @property
    def string_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.String]

    @property
    def s32_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.S32]

    @property
    def f32_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.F32]

    @property
    def bool_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.Bool]

    @property
    def vec3f_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.Vec3f]

    @property
    def void_ptr_params(self) -> typing.List[BBParam]:
        return self._params[BBParamType.VoidPtr]
    
    def get_params(self, param_type: BBParamType) -> typing.List[BBParam]:
        return self._params[param_type]

    @classmethod
    def _read(cls, reader: AINBReader) -> "Blackboard":
        bb: Blackboard = cls()
        type_headers: typing.List[BBParamHeader] = [
            cls._read_bb_header(reader) for i in range(len(BBParamType))
        ]
        param_info: typing.List[typing.List[BBParamInfo]] = [
            [
                cls._read_bb_param(reader) for i in range(type_headers[p_type].param_count)
            ] for p_type in BBParamType
        ]

        # offsets referenced in the headers are relative to this point
        base_offset: int = reader.tell()

        # file references come after all the default values (note that ptr types don't store a default, it's implicitly null)
        file_ref_offset: int = base_offset + type_headers[BBParamType.Vec3f].offset + type_headers[BBParamType.Vec3f].param_count * 0xc

        # technically we don't need these temp seeks since they should all be contiguous but just to be safe, we'll do this
        for p_type in BBParamType:
            with reader.temp_seek(base_offset + type_headers[p_type].offset):
                bb._params[p_type] = [
                    cls._create_bb_param(reader, param_info[p_type][i], p_type, file_ref_offset) for i in range(type_headers[p_type].param_count)
                ]

        return bb

    @staticmethod
    def _read_bb_header(reader: AINBReader) -> BBParamHeader:
        res: BBParamHeader = BBParamHeader(reader.read_u16(), reader.read_u16(), reader.read_u16())
        _ = reader.read_u16() # padding
        return res
    
    @staticmethod
    def _read_bb_param(reader: AINBReader) -> BBParamInfo:
        flags: int = reader.read_u32()
        if flags >> 0x1f:
            return BBParamInfo(
                flags >> 0x18 & 0x7f,                   # file reference index
                reader.get_string(flags & 0x3fffff),    # param name
                reader.read_string_offset(),            # param notes
                flags >> 0x16 & 3                       # flags
            )
        else:
            return BBParamInfo(
                -1,                                     # file reference index
                reader.get_string(flags & 0x3fffff),    # param name
                reader.read_string_offset(),            # param notes
                flags >> 0x16 & 3                       # flags
            )
        
    @staticmethod
    def _read_bb_param_value(reader: AINBReader, param_type: BBParamType) -> ValueType:
        match (param_type):
            case BBParamType.String:
                return reader.read_string_offset()
            case BBParamType.S32:
                return reader.read_s32()
            case BBParamType.F32:
                return reader.read_f32()
            case BBParamType.Bool:
                return reader.read_u32() != 0
            case BBParamType.Vec3f:
                return reader.read_vec3()
            case BBParamType.VoidPtr:
                return None

    @staticmethod
    def _read_file_reference(reader: AINBReader) -> str:
        filename: str = reader.read_string_offset()
        path_hash: int = reader.read_u32()
        filename_hash: int = reader.read_u32()
        extension_hash: int = reader.read_u32()
        return filename

    @staticmethod
    def _create_bb_param(reader: AINBReader, info: BBParamInfo, param_type: BBParamType, file_ref_offset: int) -> BBParam:
        param: BBParam = BBParam(param_type)
        param.name = info.name
        param.notes = info.notes
        param.flags = info.flags
        param.default_value = Blackboard._read_bb_param_value(reader, param_type)
        if info.file_ref_index != -1:
            # each file reference entry is 0x10 bytes
            with reader.temp_seek(file_ref_offset + 0x10 * info.file_ref_index):
                param.file_ref = Blackboard._read_file_reference(reader)
        return param
    
    def _as_dict(self) -> JSONType:
        return {
            p_type.name : [ param._as_dict(i) for i, param in enumerate(self.get_params(p_type)) ] for p_type in BBParamType if self.get_params(p_type)
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Blackboard":
        bb: Blackboard = cls()
        for p_type in BBParamType:
            if p_type.name not in data:
                continue
            bb._params[p_type] = [
                BBParam._from_dict(param, p_type) for param in data[p_type.name]
            ]
        return bb

    def _calc_size(self) -> int:
        file_refs: typing.Set[str] = set()
        return 0x30 + sum(param._calc_size(file_refs) for p_type in BBParamType for param in self.get_params(p_type))

    def _write(self, writer: AINBWriter) -> None:
        index: int = 0
        pos: int = 0
        for p_type in BBParamType:
            param_count: int = len(self.get_params(p_type))
            writer.write_u16(param_count)
            writer.write_u16(index)
            index += param_count
            writer.write_u16(pos)
            if p_type == BBParamType.Vec3f:
                pos += 0xc * param_count
            elif p_type == BBParamType.VoidPtr:
                pass
            else:
                pos += 4 * param_count
            writer.write_u16(0)
        file_refs: typing.List[str] = []
        for p_type in BBParamType:
            for param in self.get_params(p_type):
                name_offset: int = writer.add_string(param.name)
                if param.file_ref != "":
                    if param.file_ref not in file_refs:
                        file_refs.append(param.file_ref)
                    name_offset |= (1 << 0x1f) | (file_refs.index(param.file_ref) << 0x18) | (param.flags << 0x16)
                else:
                    name_offset |= (param.flags << 0x16)
                writer.write_u32(name_offset)
                writer.write_string_offset(param.notes)
        offset: int = 0
        for p_type in BBParamType:
            for param in self.get_params(p_type):
                match (p_type):
                    case BBParamType.String:
                        if typing.TYPE_CHECKING:
                            assert isinstance(param.default_value, str)
                        writer.write_string_offset(param.default_value)
                        offset += 4
                    case BBParamType.S32:
                        if typing.TYPE_CHECKING:
                            assert isinstance(param.default_value, int)
                        writer.write_s32(param.default_value)
                        offset += 4
                    case BBParamType.F32:
                        if typing.TYPE_CHECKING:
                            assert isinstance(param.default_value, float)
                        writer.write_f32(param.default_value)
                        offset += 4
                    case BBParamType.Bool:
                        if typing.TYPE_CHECKING:
                            assert isinstance(param.default_value, bool)
                        writer.write_u32(1 if param.default_value else 0)
                        offset += 4
                    case BBParamType.Vec3f:
                        if typing.TYPE_CHECKING:
                            assert isinstance(param.default_value, tuple)
                        writer.write_vec3(param.default_value)
                        offset += 0xc
                    # pointer types aren't written
        for file_ref in file_refs:
            writer.write_string_offset(file_ref)
            writer.write_u32(calc_hash(file_ref))
            writer.write_u32(calc_hash(os.path.splitext(os.path.basename(file_ref))[0]))
            writer.write_u32(calc_hash(os.path.splitext(file_ref)[1].replace('.', '')))