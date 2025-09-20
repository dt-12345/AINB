import abc
import builtins
import dataclasses
import re
import typing

from ainb.expression.common import ExpressionParseError, ExpressionReader, ExpressionWriter
from ainb.expression.write_context import ExpressionWriteContext
from ainb.utils import EnumEx, ParseError, ParseWarning, ValueType

OPERAND: re.Pattern[str] = re.compile(r"(?P<datatype>\w+?)\s+?(?P<argument>.+?)(,|$)")
MEMORY_OFFSET: re.Pattern[str] = re.compile(r"(?P<source>\w+)\[(?P<offset>(0x)?[0-9a-fA-F]+)\](\.(?P<component>[xyzXYZ]))?$")
STRING_LITERAL: re.Pattern[str] = re.compile(r"\"(?P<value>.*?)\"$")
VECTOR_LITERAL: re.Pattern[str] = re.compile(r"\((\s*(?P<x>([-\+])?(\d|\.)+)\s*,\s*(?P<y>([-\+])?(\d|\.)+)\s*,\s*(?P<z>([-\+])?(\d|\.)+)\s*)\)")
CALL_ARGS: re.Pattern[str] = re.compile(r"(?P<signature>(((\(\s*(?P<arg1>[^\s]+?)\s*\))|(\w+))\.)?(?P<name>\w+)\(\s*(?P<return>[^\s]+?)\s*(,\s*(?P<args>.+?))?\s*\)),\s*GMem\[(?P<offset>(0x)?[0-9a-fA-F]+?)\]$")

class InstType(EnumEx):
    """
    Expression instruction type enum
    """

    # I tried to make these all three-letter acronyms but some of them don't really work...
    END = 1     # command terminator instruction
    STR = 2     # memory store
    NEG = 3     # negate
    NOT = 4     # logical not
    ADD = 5     # addition
    SUB = 6     # subtraction
    MUL = 7     # multiplication
    DIV = 8     # division
    MOD = 9     # modulus
    INC = 0xa   # increment
    DEC = 0xb   # decrement
    VMS = 0xc   # vector3f multiplied by scalar
    VDS = 0xd   # vector3f divided by scalar
    LSH = 0xe   # logical left shift
    RSH = 0xf   # arithmetic right shift
    LST = 0x10  # less than
    LTE = 0x11  # less than or equal
    GRT = 0x12  # greater than
    GTE = 0x13  # greater than or equal
    EQL = 0x14  # equal
    NEQ = 0x15  # not equal
    AND = 0x16  # bitwise AND
    XOR = 0x17  # bitwise XOR
    ORR = 0x18  # bitwise OR
    LAN = 0x19  # logical AND
    LOR = 0x1a  # logical OR
    CFN = 0x1b  # call function
    JZE = 0x1c  # jump if zero (jump if false)
    JMP = 0x1d  # jump

class InstDataType(EnumEx):
    """
    Instruction operand datatype enum
    """

    NONE        = 0
    IMM         = 1 # only used for command input type
    BOOL        = 2
    INT         = 3
    FLOAT       = 4
    STRING      = 5
    VECTOR3F    = 6

class InstOpType(EnumEx):
    """
    Instruction operand type enum
    """

    Invalid             = -1 # fake type
    Immediate           = 0  # immediate value
    ImmediateString     = 1  # immediate string pool offset
    GlobalMemory        = 2  # global memory offset (global memory is shared across an entire AI context)
    ParamTable          = 3  # parameter table offset
    ParamTableString    = 4  # parameter table offset for a string pool offset
    ExpressionOutput    = 5  # expression output value
    ExpressionInput     = 6  # expression input value
    LocalMemory32       = 7  # offset into 32-bit aligned local memory (for most datatypes)
    LocalMemory64       = 8  # offset into 64-bit aligned local memory (for strings)
    Output              = 9  # node output parameter (for Element_Expression)
    Input               = 10 # node input parameter (for Element_Expression)

    def is_immediate_value(self) -> bool:
        """
        Returns True if this type represents an immediate value
        """
        return self in [InstOpType.Immediate, InstOpType.ImmediateString, InstOpType.ParamTable, InstOpType.ParamTableString]

DT_PREFIX: typing.Final[typing.Dict[InstDataType, str]] = {
    InstDataType.NONE : "",
    InstDataType.IMM : "",
    InstDataType.BOOL : "bool ",
    InstDataType.INT : "int ",
    InstDataType.FLOAT : "float ",
    InstDataType.STRING : "str ",
    InstDataType.VECTOR3F : "vec3f ",
}

REVERSE_DT_PREFIX: typing.Final[typing.Dict[str, InstDataType]] = {
    "bool" : InstDataType.BOOL,
    "int" : InstDataType.INT,
    "float" : InstDataType.FLOAT,
    "str" : InstDataType.STRING,
    "vec3f" : InstDataType.VECTOR3F,
}

OP_PREFIX: typing.Final[typing.Dict[InstOpType, str]] = {
    InstOpType.GlobalMemory : "GMem",
    InstOpType.ExpressionInput : "In",
    InstOpType.ExpressionOutput : "Out",
    InstOpType.LocalMemory32 : "LMem32",
    InstOpType.LocalMemory64 : "LMem64",
    InstOpType.Output : "UserOut",
    InstOpType.Input : "UserIn",
}

REVERSE_OP_PREFIX: typing.Final[typing.Dict[str, InstOpType]] = {
    "GMem" : InstOpType.GlobalMemory,
    "In" : InstOpType.ExpressionInput,
    "Out" : InstOpType.ExpressionOutput,
    "LMem32" : InstOpType.LocalMemory32,
    "LMem64" : InstOpType.LocalMemory64,
    "UserOut" : InstOpType.Output,
    "UserIn" : InstOpType.Input,
}

VEC_OFFSET_MAP: typing.Final[typing.Dict[str, int]] = {
    "x" : 0,
    "y" : 4,
    "z" : 8,
}

DATATYPE_SIZES: typing.Final[typing.Dict[InstDataType, int]] = {
    InstDataType.BOOL : 4,
    InstDataType.INT : 4,
    InstDataType.FLOAT : 4,
    InstDataType.STRING : 8,
    InstDataType.VECTOR3F : 0xc,
}

IMMEDIATE_TYPES: typing.Final[typing.Tuple[InstOpType, ...]] = (
    InstOpType.Immediate, InstOpType.ImmediateString, InstOpType.ParamTable, InstOpType.ParamTableString,
)

def _get_dt_prefix(datatype: InstDataType) -> str:
    return DT_PREFIX[datatype]

def _get_op_prefix(op_type: InstOpType) -> str:
    return OP_PREFIX[op_type]

class Operand:
    def __init__(self) -> None:
        self.type: InstOpType = InstOpType.Invalid
        self.datatype: InstDataType = InstDataType.NONE
        self.value: ValueType = None
        self.vec_offset: int | None = None

    @staticmethod
    def _get_vec_comp_name(offset: int) -> str:
        if offset == 0:
            return "x"
        elif offset == 4:
            return "y"
        elif offset == 8:
            return "z"
        else:
            raise ValueError(f"Invalid vector offset: {offset}")
        
    @staticmethod
    def _format_value(value: ValueType) -> str:
        if value is None:
            raise ValueError("Value cannot be None")
        if isinstance(value, tuple):
            return f"({value[0]}, {value[1]}, {value[2]})"
        elif isinstance(value, str):
            return f"\"{value}\""
        else:
            return str(value)

    def format(self) -> str:
        if self.type.is_immediate_value():
            return f"{_get_dt_prefix(self.datatype)}{self._format_value(self.value)}"
        else:
            if self.vec_offset is None:
                return f"{_get_dt_prefix(self.datatype)}{_get_op_prefix(self.type)}[{self.value:#x}]"
            else:
                return f"{_get_dt_prefix(self.datatype)}{_get_op_prefix(self.type)}[{self.value:#x}].{self._get_vec_comp_name(self.vec_offset)}"

    def _read_value(self, reader: ExpressionReader) -> None:
        raw: int = reader.read_u16()
        if self.datatype == InstDataType.NONE:
            self.value = raw
            return
        match (self.type):
            case InstOpType.Immediate:
                match (self.datatype):
                    case InstDataType.BOOL:
                        self.value = raw != 0
                    case InstDataType.INT:
                        self.value = raw
                    case InstDataType.FLOAT:
                        self.value = float(raw)
                    case _:
                        raise ParseError(reader, f"Invalid operand datatype for immediate value: {self.datatype}")
            case InstOpType.ImmediateString:
                self.value = reader.get_string(raw)
            case InstOpType.GlobalMemory:
                self.value = raw
            case InstOpType.ParamTable:
                match (self.datatype):
                    case InstDataType.BOOL:
                        self.value = reader.read_bool_param_table(raw)
                    case InstDataType.INT:
                        self.value = reader.read_s32_param_table(raw)
                    case InstDataType.FLOAT:
                        self.value = reader.read_f32_param_table(raw)
                    case InstDataType.VECTOR3F:
                        self.value = reader.read_vec3_param_table(raw)
                    case _:
                        raise ParseError(reader, f"Invalid operand datatype for parameter table: {self.datatype}")
            case InstOpType.ParamTableString:
                self.value = reader.read_string_param_table(raw)
            case InstOpType.ExpressionOutput:
                self.value = raw
            case InstOpType.ExpressionInput:
                self.value = raw
            case InstOpType.LocalMemory32:
                self.value = raw
            case InstOpType.LocalMemory64:
                self.value = raw
            case InstOpType.Input:
                if self.datatype == InstDataType.FLOAT and (raw >> 0xf & 1) != 0:
                    self.value = raw & 0xff
                    self.vec_offset = (raw & 0x7f00) >> 8
                else:
                    self.value = raw
            case InstOpType.Output:
                if self.datatype == InstDataType.FLOAT and (raw >> 0xf & 1) != 0:
                    self.value = raw & 0xff
                    self.vec_offset = (raw & 0x7f00) >> 8
                else:
                    self.value = raw
            case _:
                raise ParseError(reader, f"Invalid operand type")
    
    def _fixup_types(self, ctx: ExpressionWriteContext) -> None:
        if self.type not in IMMEDIATE_TYPES:
            return
        # static type checking seems to not be able to handle this case
        match(type(self.value)):
            case builtins.int:
                if self.value > 0xffff: # type: ignore
                    if (self.value, builtins.int) not in ctx.param_table:
                        ctx.param_table[(self.value, builtins.int)] = ctx.current_param_table_offset
                        ctx.current_param_table_offset += 4
                    self.type = InstOpType.ParamTable
                else:
                    self.type = InstOpType.Immediate
            case builtins.bool:
                self.type = InstOpType.Immediate
            case builtins.float:
                if self.value > 65535.0 or self.value < 0.0 or not self.value.is_integer() or ctx.version < 2: # type: ignore
                    if (self.value, builtins.float) not in ctx.param_table:
                        ctx.param_table[(self.value, builtins.float)] = ctx.current_param_table_offset
                        ctx.current_param_table_offset += 4
                    self.type = InstOpType.ParamTable
                else:
                    self.type = InstOpType.Immediate
            case builtins.str:
                offset: int = ctx.writer.add_string(self.value)
                if offset > 0xffff:
                    if (self.value, builtins.str) not in ctx.param_table:
                        ctx.param_table[(self.value, builtins.str)] = ctx.current_param_table_offset
                        ctx.current_param_table_offset += 4
                    self.type = InstOpType.ParamTableString
                else:
                    self.type = InstOpType.ImmediateString
            case builtins.tuple:
                if (self.value, builtins.tuple) not in ctx.param_table:
                    ctx.param_table[(self.value, builtins.tuple)] = ctx.current_param_table_offset
                    ctx.current_param_table_offset += 0xc
                self.type = InstOpType.ParamTable

    def _check_load_validity(self) -> bool:
        """
        Checks if an operand is loaded from a valid source (assumes the operand is being loaded from and not stored to)
        
        When loading datatypes from 32-bit aligned vs. 64-bit aligned memory, there are some restrictions:

        BOOL -- 1 byte, can only be loaded from 32-bit aligned memory\n
        INT -- 4 bytes, can only be loaded from 32-bit aligned memory\n
        FLOAT -- 4 bytes, can only be loaded from 32-bit aligned memory\n
        STRING -- 8 bytes, can only be loaded from 64-bit aligned memory\n
        VECTOR3F -- 4 bytes, can only be loaded from 32-bit aligned memory

        Interestingly, there isn't actually any alignment requirement for the offset
        """
        if self.type == InstOpType.LocalMemory32:
            if self.datatype not in [InstDataType.BOOL, InstDataType.INT, InstDataType.FLOAT, InstDataType.VECTOR3F]:
                return False
        elif self.type == InstOpType.LocalMemory64:
            if self.datatype != InstDataType.STRING:
                return False
            
        return True
    
    def _is_input(self) -> bool:
        return self.type == InstOpType.Input or self.type == InstOpType.ExpressionInput
    
    def _is_value(self) -> bool:
        return self.type.is_immediate_value()
    
    @classmethod
    def _parse_generic(cls, text: str) -> "Operand":
        op: Operand = cls()
        op_match: re.Match[str] | None = re.match(OPERAND, text.strip())
        argument: str
        if op_match is None:
            # assume NONE datatype, this case must match a memory access otherwise it throws an error (only shows up for JZE)
            op.datatype = InstDataType.NONE
            argument = text.strip()
        else:
            datatype: str = op_match.group("datatype")
            argument = op_match.group("argument")
            op.datatype = REVERSE_DT_PREFIX[datatype.lower()]
        arg_match: re.Match[str] | None = re.match(MEMORY_OFFSET, argument)
        if arg_match is not None:
            op.type = REVERSE_OP_PREFIX[arg_match.group("source")]
            offset: str = arg_match.group("offset")
            if offset.startswith("0x"):
                op.value = int(offset, 16)
            else:
                op.value = int(offset)
            if op.type in [InstOpType.Input, InstOpType.Output]:
                comp: str | None = arg_match.group("component")
                if comp is not None:
                    op.vec_offset = VEC_OFFSET_MAP[comp.lower()]
        else:
            op.type = InstOpType.Immediate # guess first, we'll fix this when serializing
            match (op.datatype):
                case InstDataType.BOOL:
                    op.value = argument.lower() == "true"
                case InstDataType.INT:
                    if argument.startswith("0x"):
                        op.value = int(argument, 16)
                    elif argument.startswith("0b"):
                        op.value = int(argument, 2)
                    else:
                        op.value = int(argument)
                case InstDataType.FLOAT:
                    op.value = float(argument)
                case InstDataType.STRING:
                    # maybe regex is overkill for this but whatever
                    str_match: re.Match[str] | None = re.match(STRING_LITERAL, argument)
                    if str_match is None:
                        raise ExpressionParseError(f"Could not decode string literal: {argument}")
                    op.value = str_match.group("value")
                case InstDataType.VECTOR3F:
                    vec_match: re.Match[str] | None = re.search(VECTOR_LITERAL, text)
                    if vec_match is None:
                        raise ExpressionParseError(f"Could not decode vector literal: {text}")
                    op.value = (
                        float(vec_match.group("x")), float(vec_match.group("y")), float(vec_match.group("z"))
                    )
                case _:
                    raise ExpressionParseError(f"Invalid operand datatype: {op.datatype}")
        return op
    
    def _write_value(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        if self.type not in IMMEDIATE_TYPES:
            if self.type in [InstOpType.Input, InstOpType.Output]:
                if self.vec_offset is not None:
                    writer.write_u16(self.value | 0x8000 | self.vec_offset << 8) # type: ignore
                else:
                    writer.write_u16(self.value) # type: ignore
            else:
                writer.write_u16(self.value) # type: ignore
        else:
            match(self.type):
                case InstOpType.Immediate:
                    match(type(self.value)):
                        case builtins.int:
                            writer.write_u16(self.value) # type: ignore
                        case builtins.bool:
                            writer.write_u16(1 if self.value else 0)
                        case builtins.float:
                            writer.write_u16(int(self.value)) # type: ignore
                case InstOpType.ImmediateString:
                    writer.write_u16(writer.get_string_offset(self.value)) # type: ignore
                case InstOpType.ParamTable:
                    writer.write_u16(ctx.param_table[(self.value, type(self.value))])
                case InstOpType.ParamTableString:
                    writer.write_u16(ctx.param_table[(self.value, builtins.str)])

@dataclasses.dataclass(slots=True)
class Sizes:
    global_mem: int = 0
    local32_mem: int = 0
    local64_mem: int = 0
    io_mem: int = 0

class InstructionBase(metaclass=abc.ABCMeta):
    """
    Abstract base class for instructions
    """

    __slots__ = ["_type"]

    def __init__(self, inst_type: InstType) -> None:
        self._type: InstType = inst_type

    @staticmethod
    @abc.abstractmethod
    def get_type() -> InstType:
        """
        Returns the type of this instructions
        """

    @classmethod
    @abc.abstractmethod
    def _read(cls, reader: ExpressionReader) -> "InstructionBase":
        pass

    @staticmethod
    def _read_ops_impl(reader: ExpressionReader, is_single: bool) -> typing.Tuple[Operand, Operand]:
        datatype: InstDataType = InstDataType(reader.read_u8())
        op1: Operand = Operand()
        op1.type = InstOpType(reader.read_u8())
        op1.datatype = datatype
        op2: Operand = Operand()
        op2.type = InstOpType(reader.read_u8())
        op2.datatype = datatype
        op1._read_value(reader)
        if not is_single:
            op2._read_value(reader)
        else:
            reader.read(2)
        return op1, op2
    
    @abc.abstractmethod
    def format(self) -> str:
        pass

    @classmethod
    @abc.abstractmethod
    def _parse(cls, matches: re.Match[str]) -> "InstructionBase":
        pass

    @abc.abstractmethod
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        pass

    @abc.abstractmethod
    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        pass
    
class SingleOpInstruction(InstructionBase):
    """
    Abstract base class for instructions which load a value and (maybe) modify it in place
    """
    __slots__ = ["op"]

    def __init__(self, inst_type: InstType) -> None:
        super().__init__(inst_type)
        self.op: Operand = Operand()

    @staticmethod
    def _read_ops(reader: ExpressionReader) -> Operand:
        op, _ = SingleOpInstruction._read_ops_impl(reader, True)
        return op
    
    def _is_valid_dst_op(self) -> bool:
        return not self.op._is_input() and not self.op._is_value()
    
    def format(self) -> str:
        return f"{self._type} {self.op.format()}"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "SingleOpInstruction":
        inst: SingleOpInstruction = cls() # type: ignore
        inst.op = Operand._parse_generic(matches.group("op1"))
        return inst
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self.get_type().value)
        writer.write_u8(self.op.datatype.value)
        writer.write_u8(self.op.type.value)
        writer.write_u8(0)
        self.op._write_value(writer, ctx)
        writer.write_u16(0)

    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        if typing.TYPE_CHECKING: # this should be inside the conditionals below, but that clutters it up too much
            assert isinstance(self.op.value, int)
        if self.op.type == InstOpType.ExpressionOutput:
            size.io_mem = max(size.io_mem, self.op.value + DATATYPE_SIZES[self.op.datatype])
        elif self.op.type == InstOpType.GlobalMemory:
            size.global_mem = max(size.global_mem, self.op.value + DATATYPE_SIZES[self.op.datatype])
        elif self.op.type == InstOpType.LocalMemory32:
            size.local32_mem = max(size.local32_mem, self.op.value + DATATYPE_SIZES[self.op.datatype])
        elif self.op.type == InstOpType.LocalMemory64:
            size.local64_mem = max(size.local64_mem, self.op.value + DATATYPE_SIZES[self.op.datatype])
        self.op._fixup_types(ctx)

class DualOpInstruction(InstructionBase):
    """
    Abstract base class for instructions which load a value, modify it, and store it somewhere else
    """
    __slots__ = ["op1", "op2"]

    def __init__(self, inst_type: InstType) -> None:
        super().__init__(inst_type)
        self.op1: Operand = Operand()
        self.op2: Operand = Operand()

    @staticmethod
    def _read_ops(reader: ExpressionReader) -> typing.Tuple[Operand, Operand]:
        return DualOpInstruction._read_ops_impl(reader, False)
    
    def _is_valid_dst_op(self) -> bool:
        return not self.op1._is_input() and not self.op1._is_value()
    
    def format(self) -> str:
        return f"{self._type} {self.op1.format()}, {self.op2.format()}"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "DualOpInstruction":
        inst: DualOpInstruction = cls() # type: ignore
        inst.op1 = Operand._parse_generic(matches.group("op1"))
        inst.op2 = Operand._parse_generic(matches.group("op2"))
        return inst
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self.get_type().value)
        writer.write_u8(self.op1.datatype.value)
        writer.write_u8(self.op1.type.value)
        writer.write_u8(self.op2.type.value)
        self.op1._write_value(writer, ctx)
        self.op2._write_value(writer, ctx)
    
    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        if typing.TYPE_CHECKING: # this should be inside the conditionals below, but that clutters it up too much
            assert isinstance(self.op1.value, int)
            assert isinstance(self.op2.value, int)
        if self.op1.type == InstOpType.ExpressionOutput:
            if self.get_type() in [InstType.VMS, InstType.VDS]:
                size.io_mem = max(size.io_mem, self.op1.value + 4)
            else:
                size.io_mem = max(size.io_mem, self.op1.value + DATATYPE_SIZES[self.op1.datatype])
        elif self.op1.type == InstOpType.GlobalMemory:
            if self.get_type() in [InstType.VMS, InstType.VDS]:
                size.global_mem = max(size.global_mem, self.op1.value + 4)
            else:
                size.global_mem = max(size.global_mem, self.op1.value + DATATYPE_SIZES[self.op1.datatype])
        elif self.op1.type == InstOpType.LocalMemory32:
            if self.get_type() in [InstType.VMS, InstType.VDS]:
                size.local32_mem = max(size.local32_mem, self.op1.value + 4)
            else:
                size.local32_mem = max(size.local32_mem, self.op1.value + DATATYPE_SIZES[self.op1.datatype])
        elif self.op1.type == InstOpType.LocalMemory64:
            if self.get_type() in [InstType.VMS, InstType.VDS]:
                size.local64_mem = max(size.local64_mem, self.op1.value + 4)
            else:
                size.local64_mem = max(size.local64_mem, self.op1.value + DATATYPE_SIZES[self.op1.datatype])
        if self.op2.type == InstOpType.ExpressionInput:
            size.io_mem = max(size.io_mem, self.op2.value + DATATYPE_SIZES[self.op2.datatype])
        elif self.op2.type == InstOpType.GlobalMemory:
            size.global_mem = max(size.global_mem, self.op2.value + DATATYPE_SIZES[self.op2.datatype])
        elif self.op2.type == InstOpType.LocalMemory32:
            size.local32_mem = max(size.local32_mem, self.op2.value + DATATYPE_SIZES[self.op2.datatype])
        elif self.op2.type == InstOpType.LocalMemory64:
            size.local64_mem = max(size.local64_mem, self.op2.value + DATATYPE_SIZES[self.op2.datatype])
        self.op1._fixup_types(ctx)
        self.op2._fixup_types(ctx)

class JumpInstructionBase(InstructionBase):
    __slots__ = ["jump_address"]

    def __init__(self, inst_type: InstType) -> None:
        super().__init__(inst_type)
        self.jump_address: int = 0

class EndInstruction(InstructionBase):
    """
    Command terminator instruction
    """

    def __init__(self) -> None:
        super().__init__(InstType.END)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.END

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "EndInstruction":
        _ = reader.read(7) # padding
        return cls()
    
    def format(self) -> str:
        return "END"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "EndInstruction":
        return cls()
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self._type.value)
        writer.write(b"\x00" * 7)
    
    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        pass

class StoreInstruction(DualOpInstruction):
    """
    Memory store instruction

    op1 = op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.STR)

    @staticmethod
    def get_type() -> InstType:
        return InstType.STR
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "StoreInstruction":
        inst: StoreInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Store instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Store instruction source operand ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        return inst
    
class NegateInstruction(SingleOpInstruction):
    """
    Negation instruction

    op = !op
    """
    def __init__(self) -> None:
        super().__init__(InstType.NEG)

    @staticmethod
    def get_type() -> InstType:
        return InstType.NEG
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "NegateInstruction":
        inst: NegateInstruction = cls()
        inst.op = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Negate instruction cannot store into {inst.op.type}")

        if inst.op.datatype not in [InstDataType.INT, InstDataType.FLOAT, InstDataType.VECTOR3F]:
            ParseWarning(reader, f"Invalid datatype for negate instruction: {inst.op.datatype}")
        
        return inst
        
class LogicalNotInstruction(SingleOpInstruction):
    """
    Logical NOT instruction

    op ^= 1
    """
    def __init__(self) -> None:
        super().__init__(InstType.NOT)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.NOT

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LogicalNotInstruction":
        inst: LogicalNotInstruction = cls()
        inst.op = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Logical NOT instruction cannot store into {inst.op.type}")

        if inst.op.datatype != InstDataType.BOOL:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Logical NOT instruction does not have BOOL datatype: {inst.op.datatype}")
        
        return inst
    
class AdditionInstruction(DualOpInstruction):
    """
    Addition instruction

    op1 += op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.ADD)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.ADD

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "AdditionInstruction":
        inst: AdditionInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Addition instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Addition instruction addend ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.FLOAT, InstDataType.VECTOR3F]:
            ParseWarning(reader, f"Invalid datatype for addition instruction: {inst.op2.datatype}")

        return inst

class SubtractionInstruction(DualOpInstruction):
    """
    Subtraction instruction

    op1 -= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.SUB)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.SUB

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "SubtractionInstruction":
        inst: SubtractionInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Subtraction instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Subtraction instruction subtrahend ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.FLOAT, InstDataType.VECTOR3F]:
            ParseWarning(reader, f"Invalid datatype for subtraction instruction: {inst.op2.datatype}")

        return inst

class MultiplicationInstruction(DualOpInstruction):
    """
    Multiplication instruction

    op1 *= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.MUL)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.MUL

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "MultiplicationInstruction":
        inst: MultiplicationInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Multiplication instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Multiplication instruction multiplier ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for multiplication instruction: {inst.op2.datatype}")

        return inst

class DivisionInstruction(DualOpInstruction):
    """
    Division instruction

    Note: integer division by zero will result in zero

    op1 /= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.DIV)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.DIV

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "DivisionInstruction":
        inst: DivisionInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Division instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Division instruction divisor ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for division instruction: {inst.op2.datatype}")

        return inst

class ModulusInstruction(DualOpInstruction):
    """
    Modulus instruction

    Note: mod zero will result in zero

    op1 %= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.MOD)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.MOD

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "ModulusInstruction":
        inst: ModulusInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Modulus instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Modulus instruction divisor ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Modulus instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Modulus instruction does not have INT datatype: {inst.op2.datatype}")

        return inst

class IncrementInstruction(SingleOpInstruction):
    """
    Increment instruction

    op += 1
    """

    def __init__(self) -> None:
        super().__init__(InstType.INC)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.INC

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "IncrementInstruction":
        inst: IncrementInstruction = cls()
        inst.op = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Increment instruction cannot store into {inst.op.type}")

        if inst.op.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Increment instruction does not have INT datatype: {inst.op.datatype}")

        return inst

class DecrementInstruction(SingleOpInstruction):
    """
    Decrement instruction

    op -= 1
    """

    def __init__(self) -> None:
        super().__init__(InstType.INC)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.INC

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "DecrementInstruction":
        inst: DecrementInstruction = cls()
        inst.op = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Decrement instruction cannot store into {inst.op.type}")

        if inst.op.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Decrement instruction does not have INT datatype: {inst.op.datatype}")

        return inst
    
class ScalarMultiplicationInstruction(DualOpInstruction):
    """
    Scalar multiplication of a vector

    op1 *= op2    
    """

    def __init__(self) -> None:
        super().__init__(InstType.VMS)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.VMS
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "ScalarMultiplicationInstruction":
        inst: ScalarMultiplicationInstruction = cls()
        datatype: InstDataType = InstDataType(reader.read_u8())
        inst.op1.datatype = datatype
        inst.op2.datatype = InstDataType.FLOAT
        inst.op1.type = InstOpType(reader.read_u8())
        inst.op2.type = InstOpType(reader.read_u8())
        inst.op1._read_value(reader)
        inst.op2._read_value(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Scalar multiplication instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Scalar multiplication instruction multiplier ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.VECTOR3F:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Scalar multiplication instruction does not have VECTOR3F datatype: {inst.op1.datatype}")

        return inst
    
class ScalarDivisionInstruction(DualOpInstruction):
    """
    Scalar division of a vector

    op1 /= op2    
    """

    def __init__(self) -> None:
        super().__init__(InstType.VDS)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.VDS
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "ScalarDivisionInstruction":
        inst: ScalarDivisionInstruction = cls()
        datatype: InstDataType = InstDataType(reader.read_u8())
        inst.op1.datatype = datatype
        inst.op2.datatype = InstDataType.FLOAT
        inst.op1.type = InstOpType(reader.read_u8())
        inst.op2.type = InstOpType(reader.read_u8())
        inst.op1._read_value(reader)
        inst.op2._read_value(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Scalar multiplication instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Scalar division instruction divisor ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.VECTOR3F:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Scalar division instruction does not have VECTOR3F datatype: {inst.op1.datatype}")

        return inst
    
class LeftShiftInstruction(DualOpInstruction):
    """
    Left shift instruction

    op1 <<= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.LSH)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.LSH

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LeftShiftInstruction":
        inst: LeftShiftInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Left shift instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Left shift instruction shift ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Left shift instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Left shift instruction does not have INT datatype: {inst.op2.datatype}")

        return inst
    
class RightShiftInstruction(DualOpInstruction):
    """
    Arithmetic right shift instruction

    op1 >>= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.RSH)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.RSH

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "RightShiftInstruction":
        inst: RightShiftInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Right shift instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Right shift instruction shift ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Right shift instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Right shift instruction does not have INT datatype: {inst.op2.datatype}")

        return inst

class LessThanInstruction(DualOpInstruction):
    """
    Less than instruction

    op1 = op1 < op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.LST)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.LST
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LessThanInstruction":
        inst: LessThanInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Less than instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Less than instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Less than instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        if inst.op1.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for less than instruction: {inst.op1.datatype}")
        
        return inst

class LessThanEqualInstruction(DualOpInstruction):
    """
    Less than or equal instruction

    op1 = op1 <= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.LTE)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.LTE
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LessThanEqualInstruction":
        inst: LessThanEqualInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Less than equal instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Less than equal instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Less than equal instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        if inst.op1.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for less than equal instruction: {inst.op1.datatype}")
        
        return inst

class GreaterThanInstruction(DualOpInstruction):
    """
    Greater than instruction

    op1 = op1 > op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.GRT)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.GRT
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "GreaterThanInstruction":
        inst: GreaterThanInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Greater than instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Greater than instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Greater than instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        if inst.op1.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for greater than instruction: {inst.op1.datatype}")
        
        return inst

class GreaterThanEqualInstruction(DualOpInstruction):
    """
    Greater than or equal instruction

    op1 = op1 >= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.GTE)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.GTE
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "GreaterThanEqualInstruction":
        inst: GreaterThanEqualInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Greater than equal instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Greater than equal instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Greater than equal instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        if inst.op1.datatype not in [InstDataType.INT, InstDataType.FLOAT]:
            ParseWarning(reader, f"Invalid datatype for greater than equal instruction: {inst.op1.datatype}")
        
        return inst

class EqualityInstruction(DualOpInstruction):
    """
    Equality instruction

    op1 = op1 == op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.EQL)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.EQL
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "EqualityInstruction":
        inst: EqualityInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Equality instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Equality instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Equality instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        return inst

class InequalityInstruction(DualOpInstruction):
    """
    Inequality instruction

    op1 = op1 != op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.NEQ)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.NEQ
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "InequalityInstruction":
        inst: InequalityInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Inequality instruction cannot store into {inst.op1.type}")
        
        if not inst.op1._check_load_validity():
            ParseWarning(reader, f"Inequality instruction value ({inst.op1.datatype}) loaded from invalid source ({inst.op1.type})")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Inequality instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")
        
        return inst

class ANDInstruction(DualOpInstruction):
    """
    AND instruction

    op1 &= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.AND)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.AND

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "ANDInstruction":
        inst: ANDInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"AND instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"AND instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype not in [InstDataType.INT, InstDataType.BOOL]:
            # this is not a hard requirement as the game does not check the type and assumes INT instead
            ParseWarning(reader, f"AND instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.BOOL]:
            # this is not a hard requirement as the game does not check the type and assumes INT instead
            ParseWarning(reader, f"AND instruction does not have INT datatype: {inst.op2.datatype}")

        return inst

class XORInstruction(DualOpInstruction):
    """
    XOR instruction

    op1 ^= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.XOR)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.XOR

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "XORInstruction":
        inst: XORInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"XOR instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"XOR instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"XOR instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.INT:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"XOR instruction does not have INT datatype: {inst.op2.datatype}")

        return inst

class ORInstruction(DualOpInstruction):
    """
    OR instruction

    op1 |= op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.ORR)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.ORR

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "ORInstruction":
        inst: ORInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"OR instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"OR instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype not in [InstDataType.INT, InstDataType.BOOL]:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"OR instruction does not have INT datatype: {inst.op1.datatype}")

        if inst.op2.datatype not in [InstDataType.INT, InstDataType.BOOL]:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"OR instruction does not have INT datatype: {inst.op2.datatype}")

        return inst

class LogicalANDInstruction(DualOpInstruction):
    """
    Logical AND instruction

    op1 = op1 && op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.LAN)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.LAN

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LogicalANDInstruction":
        inst: LogicalANDInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Logical AND instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Logical AND instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.BOOL:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Logical AND instruction does not have BOOL datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.BOOL:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Logical AND instruction does not have BOOL datatype: {inst.op2.datatype}")

        return inst

class LogicalORInstruction(DualOpInstruction):
    """
    Logical OR instruction

    op1 = op1 || op2
    """

    def __init__(self) -> None:
        super().__init__(InstType.LOR)
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.LOR

    @classmethod
    def _read(cls, reader: ExpressionReader) -> "LogicalORInstruction":
        inst: LogicalORInstruction = cls()
        inst.op1, inst.op2 = inst._read_ops(reader)

        if not inst._is_valid_dst_op():
            ParseWarning(reader, f"Logical OR instruction cannot store into {inst.op1.type}")

        if not inst.op2._check_load_validity():
            ParseWarning(reader, f"Logical OR instruction value ({inst.op2.datatype}) loaded from invalid source ({inst.op2.type})")

        if inst.op1.datatype != InstDataType.BOOL:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Logical OR instruction does not have BOOL datatype: {inst.op1.datatype}")

        if inst.op2.datatype != InstDataType.BOOL:
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Logical OR instruction does not have BOOL datatype: {inst.op2.datatype}")

        return inst

class CallFunctionInstruction(InstructionBase):
    """
    Call a function
    """

    __slots__ = ["datatype", "args_offset", "func_signature"]

    def __init__(self) -> None:
        super().__init__(InstType.CFN)
        self.datatype: InstDataType = InstDataType.NONE # return type
        self.args_offset: int = 0                       # offset into global memory of function arguments
        self.func_signature: str = ""                   # function signature
    
    @staticmethod
    def get_type() -> InstType:
        return InstType.CFN
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "CallFunctionInstruction":
        inst: CallFunctionInstruction = cls()
        inst.datatype = InstDataType(reader.read_u8())
        inst.args_offset = reader.read_u16()
        inst.func_signature = reader.get_signature(reader.read_u32())

        # TODO: check return types match

        return inst
    
    def format(self) -> str:
        return f"CFN {self.func_signature}, GMem[{self.args_offset:#x}]"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "CallFunctionInstruction":
        inst: CallFunctionInstruction = cls()
        args_match: re.Match[str] | None = re.match(CALL_ARGS, matches.group("arguments"))
        if args_match is None:
            raise ExpressionParseError(f"Failed to decode {matches.group("arguments")}")
        inst.datatype = InstDataType[args_match.group("return").upper()]
        inst.func_signature = args_match.group("signature")
        offset: str = args_match.group("offset")
        if offset.startswith("0x"):
            inst.args_offset = int(offset, 16)
        else:
            inst.args_offset = int(offset)
        return inst
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self.get_type().value)
        writer.write_u8(self.datatype.value)
        writer.write_u16(self.args_offset)
        writer.write_u32(ctx.signature_list.index(self.func_signature))

    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        if self.func_signature not in ctx.signature_list:
            ctx.signature_table.append(ctx.writer.add_string(self.func_signature))
            ctx.signature_list.append(self.func_signature)

class JumpIfZeroInstruction(JumpInstructionBase):
    """
    Jump to address if boolean is false
    """

    __slots__ = ["condition"]

    def __init__(self) -> None:
        super().__init__(InstType.JZE)
        self.condition: Operand = Operand()

    @staticmethod
    def get_type() -> InstType:
        return InstType.JZE
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "JumpIfZeroInstruction":
        inst: JumpIfZeroInstruction = cls()
        inst.condition.datatype = InstDataType(reader.read_u8())
        inst.condition.type = InstOpType(reader.read_u8())
        _ = reader.read_u8() # padding
        inst.condition._read_value(reader)
        inst.jump_address = reader.read_u16() * 8

        if not inst.condition._check_load_validity():
            ParseWarning(reader, f"Jump if zero instruction condition ({inst.condition.datatype}) loaded from invalid source ({inst.condition.type})")
        
        if inst.condition.datatype not in [InstDataType.BOOL, InstDataType.NONE]: # game uses NONE normally
            # this is not a hard requirement as the game does not check the type and assumes it instead
            ParseWarning(reader, f"Jump if zero instruction condition does not have BOOL datatype: {inst.condition.datatype}")

        return inst
    
    def format(self) -> str:
        return f"JZE {self.condition.format()}, {self.jump_address:#x}"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "JumpIfZeroInstruction":
        inst: JumpIfZeroInstruction = cls()
        inst.condition = Operand._parse_generic(matches.group("op1"))
        offset: str = matches.group("op2")
        if offset.startswith("0x"):
            inst.jump_address = int(offset, 16)
        else:
            inst.jump_address = int(offset)
        return inst
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self.get_type().value)
        writer.write_u8(self.condition.datatype.value)
        writer.write_u8(self.condition.type.value)
        writer.write_u8(0)
        self.condition._write_value(writer, ctx)
        writer.write_u16(int(self.jump_address / 8))
    
    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        if typing.TYPE_CHECKING: # this should be inside the conditionals below, but that clutters it up too much
            assert isinstance(self.condition.value, int)
        if self.condition.type == InstOpType.ExpressionInput:
            size.io_mem = max(size.io_mem, self.condition.value + 1)
        elif self.condition.type == InstOpType.GlobalMemory:
            size.global_mem = max(size.global_mem, self.condition.value + 1)
        elif self.condition.type == InstOpType.LocalMemory32:
            size.local32_mem = max(size.local32_mem, self.condition.value + 1)
        elif self.condition.type == InstOpType.LocalMemory64:
            size.local64_mem = max(size.local64_mem, self.condition.value + 1)
        self.condition._fixup_types(ctx)

class JumpInstruction(JumpInstructionBase):
    """
    Jump to address
    """

    def __init__(self) -> None:
        super().__init__(InstType.JMP)

    @staticmethod
    def get_type() -> InstType:
        return InstType.JMP
    
    @classmethod
    def _read(cls, reader: ExpressionReader) -> "JumpInstruction":
        inst: JumpInstruction = cls()
        _ = reader.read(5) # ignored
        inst.jump_address = reader.read_u16() * 8

        return inst
    
    def format(self) -> str:
        return f"JMP {self.jump_address:#x}"
    
    @classmethod
    def _parse(cls, matches: re.Match[str]) -> "JumpInstruction":
        inst: JumpInstruction = cls()
        offset: str = matches.group("op1")
        if offset.startswith("0x"):
            inst.jump_address = int(offset, 16)
        else:
            inst.jump_address = int(offset)
        return inst
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write_u8(self.get_type().value)
        writer.write_u8(InstDataType.NONE.value)
        writer.write_u8(0)
        writer.write_u8(0)
        writer.write_u16(0)
        writer.write_u16(int(self.jump_address / 8))
    
    def _preprocess(self, ctx: ExpressionWriteContext, size: Sizes) -> None:
        pass

INSTRUCTION_TABLE: typing.Final[typing.Dict[InstType, typing.Type[InstructionBase]]] = {
    InstType.END : EndInstruction,
    InstType.STR : StoreInstruction,
    InstType.NEG : NegateInstruction,
    InstType.NOT : LogicalNotInstruction,
    InstType.ADD : AdditionInstruction,
    InstType.SUB : SubtractionInstruction,
    InstType.MUL : MultiplicationInstruction,
    InstType.DIV : DivisionInstruction,
    InstType.MOD : ModulusInstruction,
    InstType.INC : IncrementInstruction,
    InstType.DEC : DecrementInstruction,
    InstType.VMS : ScalarMultiplicationInstruction,
    InstType.VDS : ScalarDivisionInstruction,
    InstType.LSH : LeftShiftInstruction,
    InstType.RSH : RightShiftInstruction,
    InstType.LST : LessThanInstruction,
    InstType.LTE : LessThanEqualInstruction,
    InstType.GRT : GreaterThanInstruction,
    InstType.GTE : GreaterThanEqualInstruction,
    InstType.EQL : EqualityInstruction,
    InstType.NEQ : InequalityInstruction,
    InstType.AND : ANDInstruction,
    InstType.XOR : XORInstruction,
    InstType.ORR : ORInstruction,
    InstType.LAN : LogicalANDInstruction,
    InstType.LOR : LogicalORInstruction,
    InstType.CFN : CallFunctionInstruction,
    InstType.JZE : JumpIfZeroInstruction,
    InstType.JMP : JumpInstruction,
}