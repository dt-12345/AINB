import io
import typing

from ainb.expression.common import ExpressionReader
from ainb.expression.disassemble import disassemble
from ainb.expression.instruction import InstDataType, InstructionBase
from ainb.expression.parser import parse_instruction
from ainb.utils import JSONType, ParseError

# TODO: proper version 1 support => no setup expressions
SUPPORTED_VERSIONS: typing.Tuple[int, ...] = (1, 2)

def get_supported_versions() -> typing.Tuple[int, ...]:
    """
    Returns a tuple of all supported EXB versions
    """
    return SUPPORTED_VERSIONS

class Expression:
    """
    Class representing an expression
    """

    __slots__ = ["setup_command", "main_command", "global_mem_usage", "local32_mem_usage", "local64_mem_usage", "input_datatype", "output_datatype"]

    def __init__(self) -> None:
        self.setup_command: typing.List[InstructionBase] = []
        self.main_command: typing.List[InstructionBase] = []

        # these three values aren't necessary to store, they can be calculated later
        self.global_mem_usage: int = 0
        self.local32_mem_usage: int = 0
        self.local64_mem_usage: int = 0

        self.input_datatype: InstDataType = InstDataType.NONE
        self.output_datatype: InstDataType = InstDataType.NONE
    
    @classmethod
    def _read(cls, reader: ExpressionReader, instructions: typing.List[InstructionBase]) -> "Expression":
        expr: Expression = cls()
        setup_base_index: int = reader.read_s32()
        setup_inst_count: int = reader.read_u32()
        if setup_base_index != -1:
            expr.setup_command = instructions[setup_base_index:setup_base_index+setup_inst_count]

        main_base_index: int = reader.read_s32()
        main_inst_count: int = reader.read_u32()
        expr.main_command = instructions[main_base_index:main_base_index+main_inst_count]

        expr.global_mem_usage = reader.read_u32()
        expr.local32_mem_usage = reader.read_u16()
        expr.local64_mem_usage = reader.read_u16()

        expr.input_datatype = InstDataType(reader.read_u16())
        expr.output_datatype = InstDataType(reader.read_u16())

        # TODO: verify input/output types match with actual instructions

        return expr
    
    @staticmethod
    def _format_instruction(instruction: InstructionBase, addr: int) -> str:
        return f"{addr:#06x}    {instruction.format()}"

    @staticmethod
    def _format_instructions(instructions: typing.List[InstructionBase]) -> str:
        return "\n".join(f"        {Expression._format_instruction(inst, i * 8)}" for i, inst in enumerate(instructions))

    @staticmethod
    def _format_instructions_single_indent(instructions: typing.List[InstructionBase]) -> str:
        return "\n".join(f"    {Expression._format_instruction(inst, i * 8)}" for i, inst in enumerate(instructions))
    
    def _format(self) -> str:
        if self.setup_command:
            return f"    .setup\n{self._format_instructions(self.setup_command)}\n    .main\n{self._format_instructions(self.main_command)}\n"
        else:
            return f"    .main\n{self._format_instructions(self.main_command)}\n"
    
    def format(self) -> str:
        """
        Returns a formatted string of the expression
        """
        if self.setup_command:
            return f".setup\n{self._format_instructions_single_indent(self.setup_command)}\n.main\n{self._format_instructions_single_indent(self.main_command)}\n"
        else:
            return f".main\n{self._format_instructions_single_indent(self.main_command)}\n"
    
    def _as_dict(self, index: int) -> JSONType:
        if self.setup_command:
            return {
                "Expression Index" : index,
                "Input Type" : self.input_datatype.name,
                "Output Type" : self.output_datatype.name,
                "Setup" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.setup_command)],
                "Main" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.main_command)],
            }
        else:
            return {
                "Expression Index" : index,
                "Input Type" : self.input_datatype.name,
                "Output Type" : self.output_datatype.name,
                "Main" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.main_command)],
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Expression":
        expr: Expression = cls()
        expr.input_datatype = InstDataType[data["Input Type"]]
        expr.output_datatype = InstDataType[data["Output Type"]]
        if "Setup" in data:
            expr.setup_command = [
                parse_instruction(inst) for inst in data["Setup"]
            ]
        expr.main_command = [
            parse_instruction(inst) for inst in data["Main"]
        ]
        return expr

class ExpressionModule:
    """
    Class representing a set of expressions belonging to a file
    """

    __slots__ = ["version", "global_mem_size", "instance_count", "local32_mem_size", "local64_mem_size", "expressions"]

    def __init__(self) -> None:
        self.version: int = 0

        # these are unnecessary to store
        self.global_mem_size: int = 0
        self.instance_count: int = 0 # how many expression instances exist in the containing file
        self.local32_mem_size: int = 0
        self.local64_mem_size: int = 0

        self.expressions: typing.List[Expression] = []

    @classmethod
    def read(cls, reader: ExpressionReader) -> "ExpressionModule":
        """
        Load an ExpressionModule from the provided binary reader
        """
        self: ExpressionModule = cls()
        
        magic: str = reader.read(4).decode()
        if magic != "EXB ":
            raise ParseError(reader, f"Invalid EXB section magic, expected \"EXB \" but got {magic}")
        self.version = reader.read_u32()
        if self.version not in SUPPORTED_VERSIONS:
            raise ParseError(reader, f"Unsupported EXB version: {self.version:#x} - see ainb.expression.get_supported_versions()")

        (
            self.global_mem_size,
            self.instance_count,
            self.local32_mem_size,
            self.local64_mem_size,
            expression_offset,
            instruction_offset,
            signature_table_offset,
            param_table_offset,
            string_pool_offset
        ) = typing.cast(typing.Tuple[int, ...], reader.unpack("<9I"))

        with reader.temp_seek(string_pool_offset):
            reader.init_string_pool(reader.read())

        reader.set_param_table_offset(param_table_offset)

        reader.seek(signature_table_offset)
        signature_count: int = reader.read_u32()
        reader.set_signatures([reader.read_string_offset() for i in range(signature_count)])

        reader.seek(instruction_offset)
        instruction_count: int = reader.read_u32()
        instructions: typing.List[InstructionBase] = [
            disassemble(reader) for i in range(instruction_count)
        ]

        reader.seek(expression_offset)
        expression_count: int = reader.read_u32()
        self.expressions = [
            Expression._read(reader, instructions) for i in range(expression_count)
        ]

        return self

    @classmethod
    def from_binary(cls, data: bytes | bytearray | typing.BinaryIO | io.BytesIO, reader_name: str = "Expression Reader") -> "ExpressionModule":
        """
        Load an ExpressionModule from the provided input buffer
        """
        if isinstance(data, bytes) or isinstance(data, bytearray):
            return cls.read(ExpressionReader(io.BytesIO(memoryview(data)), name = reader_name))
        else:
            return cls.read(ExpressionReader(data, name = reader_name))
    
    @staticmethod
    def _format_expression(expression: Expression, index: int) -> str:
        return f".expression{index}\n{expression._format()}"

    def _format_expressions(self) -> str:
        return "\n".join(self._format_expression(expr, i) for i, expr in enumerate(self.expressions))

    def to_text(self) -> str:
        """
        Converts this expression module into its corresponding disassembled source
        """
        return f".version {self.version}\n\n{self._format_expressions()}"
    
    def as_dict(self) -> JSONType:
        """
        Returns the expression module in dictionary form
        """
        return {
            "Version" : self.version,
            "Expressions" : [
                expr._as_dict(i) for i, expr in enumerate(self.expressions)
            ],
        }
    
    @classmethod
    def from_dict(cls, data: JSONType) -> "ExpressionModule":
        """
        Load an expression module from a dictionary
        """
        # TODO: instance count
        self: ExpressionModule = cls()
        self.version = data["Version"]
        self.expressions = [
            Expression._from_dict(expr) for expr in data["Expressions"]
        ]
        return self