import dataclasses
import typing

from ainb.common import AINBReader, AINBWriter
from ainb.param_common import ParamType, ParamFlag
from ainb.utils import DictDecodeError, JSONType, ParseError, SerializeError, ValueType

@dataclasses.dataclass(slots=True)
class ParamSource:
    """
    Input parameter source information
    """

    src_node_index: int = -1
    src_output_index: int = 0
    flags: ParamFlag = ParamFlag()

    @classmethod
    def _read(cls, reader: AINBReader) -> "ParamSource":
        return cls(reader.read_s16(), reader.read_s16(), ParamFlag(reader.read_u32()))

    @property
    def is_multi(self) -> bool:
        return self.src_node_index <= -100
    
    @property
    def multi_index(self) -> int:
        return -100 - self.src_node_index
    
    @property
    def multi_count(self) -> int:
        return self.src_output_index
    
    def _as_dict(self) -> JSONType:
        return {
            "Node Index" : self.src_node_index,
            "Output Index" : self.src_output_index,
        } | self.flags._as_dict()

    @classmethod
    def _from_dict(cls, data: JSONType) -> "ParamSource":
        return cls(
            data["Node Index"], data["Output Index"], ParamFlag._from_dict(data)
        )
    
    def is_expression(self) -> bool:
        return self.flags.is_expression()
    
    def is_blackboard(self) -> bool:
        return self.flags.is_blackboard()

    def _write(self, writer: AINBWriter) -> None:
        writer.write_s16(self.src_node_index)
        writer.write_s16(self.src_output_index)
        writer.write_u32(self.flags)

INPUT_PARAM_SIZES: typing.Final[typing.Dict[ParamType, int]] = {
    ParamType.Int : 0x10,
    ParamType.Bool : 0x10,
    ParamType.Float : 0x10,
    ParamType.String : 0x10,
    ParamType.Vector3F : 0x18,
    ParamType.Pointer : 0x14,
}

class InputParam:
    """
    A single input parameter of a node
    """

    __slots__ = ["name", "classname", "type", "default_value", "source"]

    def __init__(self, param_type: ParamType) -> None:
        self.name: str = ""
        self.classname: str = ""
        self.type: ParamType = param_type
        self.default_value: ValueType = None

        self.source: ParamSource | typing.List[ParamSource] = ParamSource()

    @classmethod
    def _read(cls, reader: AINBReader, param_type: ParamType, multi_params: typing.List[ParamSource]) -> "InputParam":
        _input: InputParam = cls(param_type)
        _input.name = reader.read_string_offset()
        if param_type == ParamType.Pointer:
            _input.classname = reader.read_string_offset()
        _input.source = ParamSource._read(reader)
        _input.default_value = cls._read_value(reader, param_type)

        if _input.source.is_multi:
            _input.source = multi_params[_input.source.multi_index:_input.source.multi_index+_input.source.multi_count]
        # sometimes the top bit is set which seemingly does absolutely nothing (probably just debug stuff)
        # elif _input.source.src_output_index < 0:
        #     _input.source.src_output_index &= 0x7fff
        return _input

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
                val: int = reader.read_u32()
                if val == 0:
                    return None
                raise ParseError(reader, f"Non-zero default value for a pointer input parameter: {val}")
    
    @staticmethod
    def _get_binary_size(param_type: ParamType) -> int:
        return INPUT_PARAM_SIZES[param_type]
    
    def _as_dict(self) -> JSONType:
        output: JSONType = {
            "Name" : self.name,
        }
        if self.type == ParamType.Pointer:
            output["Classname"] = self.classname
        output["Default Value"] = self.default_value
        if isinstance(self.source, ParamSource):
            output |= self.source._as_dict()
        else:
            output["Sources"] = [ src._as_dict() for src in self.source ]
        return output
    
    @classmethod
    def _from_dict(cls, data: JSONType, param_type: ParamType) -> "InputParam":
        _input: InputParam = cls(param_type)
        _input.name = data["Name"]
        if param_type == ParamType.Pointer:
            _input.classname = data["Classname"]
        match (param_type):
            case ParamType.Int:
                _input.default_value = int(data["Default Value"])
            case ParamType.Bool:
                _input.default_value = bool(data["Default Value"])
            case ParamType.Float:
                _input.default_value = float(data["Default Value"])
            case ParamType.String:
                _input.default_value = str(data["Default Value"])
            case ParamType.Vector3F:
                _input.default_value = tuple(data["Default Value"])
            case ParamType.Pointer:
                _input.default_value = data["Default Value"]
                if _input.default_value is not None:
                    raise DictDecodeError("Pointer inputs must have a default value of null")
        if "Sources" in data:
            _input.source = [
                ParamSource._from_dict(src) for src in data["Sources"]
            ]
        else:
            _input.source = ParamSource._from_dict(data)
        return _input

    def _write_value(self, writer: AINBWriter, param_type: ParamType) -> None:
        match (param_type):
            case ParamType.Int:
                writer.write_s32(self.default_value)  # type: ignore
            case ParamType.Bool:
                writer.write_u32(1 if self.default_value else 0)
            case ParamType.Float:
                writer.write_f32(self.default_value) # type: ignore
            case ParamType.String:
                writer.write_string_offset(self.default_value) # type: ignore
            case ParamType.Vector3F:
                writer.write_vec3(self.default_value) # type: ignore
            case ParamType.Pointer:
                if self.default_value is not None:
                    raise SerializeError(writer, f"Non-zero default value for a pointer input parameter: {self.default_value}")
                writer.write_u32(0)

    def _write(self, writer: AINBWriter, param_type: ParamType, multi_params: typing.List[ParamSource]) -> None:
        writer.write_string_offset(self.name)
        if param_type == ParamType.Pointer:
            writer.write_string_offset(self.classname)
        if isinstance(self.source, list):
            src: ParamSource = ParamSource()
            src_count: int = len(self.source)
            for i in range(len(multi_params) - src_count + 1):
                if multi_params[i:i+src_count] == self.source:
                    src.src_node_index = -100 - i
                    break
            if src.src_node_index == -1:
                raise SerializeError(writer, f"Could not find matching multi-param window for input {self.name}")
            src.src_output_index = src_count
            src._write(writer)
        else:
            self.source._write(writer)
        self._write_value(writer, param_type)

class OutputParam:
    """
    A single output parameter of a node
    """

    __slots__ = ["name", "classname", "type", "is_output"]

    def __init__(self, param_type: ParamType) -> None:
        self.name: str = ""
        self.classname: str = ""
        self.type: ParamType = param_type
        self.is_output: bool = False # whether or not this param is output to another node

    @classmethod
    def _read(cls, reader: AINBReader, param_type: ParamType) -> "OutputParam":
        output: OutputParam = cls(param_type)
        flags: int = reader.read_u32()
        output.name = reader.get_string(flags & 0x3fffffff)
        if param_type == ParamType.Pointer:
            output.classname = reader.read_string_offset()
        output.is_output = (flags >> 0x1f & 1) != 0
        return output
    
    def _as_dict(self) -> JSONType:
        if self.type == ParamType.Pointer:
            return {
                "Name" : self.name,
                "Classname" : self.classname,
                "Is Output" : self.is_output,
            }
        else:
            return {
                "Name" : self.name,
                "Is Output" : self.is_output,
            }
        
    @classmethod
    def _from_dict(cls, data: JSONType, param_type: ParamType) -> "OutputParam":
        output: OutputParam = cls(param_type)
        output.name = data["Name"]
        if param_type == ParamType.Pointer:
            output.classname = data["Classname"]
        output.is_output = data["Is Output"]
        return output
    
    def _write(self, writer: AINBWriter, param_type: ParamType) -> None:
        if self.is_output:
            writer.write_u32(writer.add_string(self.name) | 0x80000000)
        else:
            writer.write_u32(writer.add_string(self.name))
        if param_type == ParamType.Pointer:
            writer.write_string_offset(self.classname)

@dataclasses.dataclass(slots=True)
class OffsetInfo:
    input_offset: int
    output_offset: int

class ParamSet:
    """
    A set of node input and output parameters
    """

    __slots__ = ["_inputs", "_outputs"]

    def __init__(self) -> None:
        self._inputs: typing.List[typing.List[InputParam]] = [
            [], [], [], [], [], []
        ]
        self._outputs: typing.List[typing.List[OutputParam]] = [
            [], [], [], [], [], []
        ]

    @property
    def int_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.Int]
    @property
    def bool_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.Bool]
    @property
    def float_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.Float]
    @property
    def string_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.String]
    @property
    def vec3f_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.Vector3F]
    @property
    def ptr_inputs(self) -> typing.List[InputParam]:
        return self._inputs[ParamType.Pointer]

    @property
    def int_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.Int]
    @property
    def bool_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.Bool]
    @property
    def float_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.Float]
    @property
    def string_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.String]
    @property
    def vec3f_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.Vector3F]
    @property
    def ptr_outputs(self) -> typing.List[OutputParam]:
        return self._outputs[ParamType.Pointer]
    
    def get_inputs(self, param_type: ParamType) -> typing.List[InputParam]:
        return self._inputs[param_type]
    
    def get_outputs(self, param_type: ParamType) -> typing.List[OutputParam]:
        return self._outputs[param_type]
    
    def has_inputs(self) -> bool:
        return any(p for p in self._inputs)

    def has_outputs(self) -> bool:
        return any(p for p in self._outputs)
    
    @classmethod
    def _read(cls, reader: AINBReader, end_offset: int, multi_params: typing.List[ParamSource]) -> "ParamSet":
        pset: ParamSet = cls()
        offsets: typing.List[OffsetInfo] = [
            cls._read_io_header(reader) for i in range(len(ParamType))
        ]
        output_end_offsets: typing.List[int] = [
            offsets[i + 1].input_offset if i < 5 else end_offset for i in range(len(ParamType))
        ]

        for p_type in ParamType:
            with reader.temp_seek(offsets[p_type].input_offset):
                pset._inputs[p_type] = [
                    InputParam._read(reader, p_type, multi_params) for i in range(int(
                        (offsets[p_type].output_offset - offsets[p_type].input_offset) / InputParam._get_binary_size(p_type)
                    ))
                ]

            with reader.temp_seek(offsets[p_type].output_offset):
                pset._outputs[p_type] = [
                    OutputParam._read(reader, p_type) for i in range(int(
                        (output_end_offsets[p_type] - offsets[p_type].output_offset) / (8 if p_type == ParamType.Pointer else 4)
                    ))
                ]

        return pset

    @staticmethod
    def _read_io_header(reader: AINBReader) -> OffsetInfo:
        return OffsetInfo(*reader.unpack("<2I"))
    
    def _as_dict(self) -> JSONType:
        return {
            "Inputs" : {
                p_type.name : [ param._as_dict() for param in self.get_inputs(p_type) ] for p_type in ParamType if self.get_inputs(p_type)
            },
            "Outputs" : {
                p_type.name : [ param._as_dict() for param in self.get_outputs(p_type) ] for p_type in ParamType if self.get_outputs(p_type)
            },
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "ParamSet":
        pset: ParamSet = cls()
        for p_type in ParamType:
            if p_type.name in data["Inputs"]:
                pset._inputs[p_type] = [
                    InputParam._from_dict(param, p_type) for param in data["Inputs"][p_type.name]
                ]
            if p_type.name in data["Outputs"]:
                pset._outputs[p_type] = [
                    OutputParam._from_dict(param, p_type) for param in data["Outputs"][p_type.name]
                ]
        return pset
    
    def clear_inputs(self) -> None:
        self._inputs = [[], [], [], [], [], []]
    
    def clear_outputs(self) -> None:
        self._outputs = [[], [], [], [], [], []]
    
    def clear(self) -> None:
        self.clear_inputs()
        self.clear_outputs()
    
    def _write(self, writer: AINBWriter, multi_params: typing.List[ParamSource]) -> None:
        offset: int = writer.tell() + 0x30
        for p_type in ParamType:
            writer.write_u32(offset)
            offset += len(self.get_inputs(p_type)) * InputParam._get_binary_size(p_type)
            writer.write_u32(offset)
            offset += len(self.get_outputs(p_type)) * (8 if p_type == ParamType.Pointer else 4)
        for p_type in ParamType:
            for input_param in self.get_inputs(p_type):
                input_param._write(writer, p_type, multi_params)
            for output_param in self.get_outputs(p_type):
                output_param._write(writer, p_type)