import builtins
import io
import typing

from ainb.expression.common import ExpressionReader, ExpressionWriter
from ainb.expression.disassemble import disassemble
from ainb.expression.expression import Expression
from ainb.expression.instruction import InstructionBase
from ainb.expression.write_context import ExpressionWriteContext
from ainb.utils import JSONType, ParseError

# TODO: version 3 support => u32 datatype
SUPPORTED_VERSIONS: typing.Tuple[int, ...] = (1, 2)

def get_supported_versions() -> typing.Tuple[int, ...]:
    """
    Returns a tuple of all supported EXB versions
    """
    return SUPPORTED_VERSIONS

class ExpressionModule:
    """
    Class representing a set of expressions belonging to a file
    """

    __slots__ = ["version", "expressions"]

    def __init__(self) -> None:
        self.version: int = 0

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
        reader.version = self.version

        (
            # can be calculated later
            global_mem_size,
            instance_count,
            local32_mem_size,
            local64_mem_size,
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
        self: ExpressionModule = cls()
        self.version = data["Version"]
        self.expressions = [
            Expression._from_dict(expr) for expr in data["Expressions"]
        ]
        return self
    
    def build_context(self, instance_count: int) -> ExpressionWriteContext:
        ctx: ExpressionWriteContext = ExpressionWriteContext()
        ctx.version = self.version
        for expr in self.expressions:
            expr._preprocess(ctx)
        ctx.instance_count = instance_count
        return ctx

    def write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        writer.write(b"EXB ")
        writer.write_u32(self.version)
        writer.write_u32(max(ctx.global_mem_sizes))
        writer.write_u32(ctx.instance_count)
        writer.write_u32(sum(ctx.local32_mem_sizes))
        writer.write_u32(sum(ctx.local64_mem_sizes))
        offset: int = 0x2c # header size
        writer.write_u32(offset) # expression offset, should always be the same
        if self.version > 1:
            offset += 4 + 0x1c * len(self.expressions)
        else:
            offset += 4 + 0x14 * len(self.expressions)
        writer.write_u32(offset) # instruction offset
        offset += 4 + 8 * ctx.instruction_count
        writer.write_u32(offset) # signature table
        offset += 4 + 4 * len(ctx.signature_table)
        writer.write_u32(offset) # param table offset
        offset += ctx.current_param_table_offset
        writer.write_u32(offset) # string pool offset

        writer.write_u32(len(self.expressions))
        for i, expr in enumerate(self.expressions):
            expr._write(writer, ctx, i)
        
        writer.write_u32(ctx.instruction_count)
        for expr in self.expressions:
            expr._write_instructions(writer, ctx)
        
        writer.write_u32(len(ctx.signature_table))
        for off in ctx.signature_table:
            writer.write_u32(off)

        for value, value_t in ctx.param_table:
            match(value_t):
                case builtins.int:
                    writer.write_s32(value) # type: ignore
                case builtins.bool:
                    writer.write_u32(1 if value else 0)
                case builtins.float:
                    writer.write_f32(value) # type: ignore
                case builtins.str:
                    writer.write_string_offset(value)
                case builtins.tuple:
                    writer.write_vec3(value)
        
        writer.write_string_pool()

    def to_binary(self, ctx: ExpressionWriteContext) -> bytes:
        self.write(ctx.writer, ctx)
        return ctx.writer.get_buffer()