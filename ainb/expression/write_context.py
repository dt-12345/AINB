import io
import typing

from ainb.expression.common import ExpressionWriter
from ainb.utils import ValueType

class Sizes(typing.NamedTuple):
    global_mem: int
    local32_mem: int
    local64_mem: int
    io_mem: int

class ExpressionWriteContext:
    def __init__(self) -> None:
        self.global_mem_sizes: typing.List[int] = [] # main command
        self.local32_mem_sizes: typing.List[int] = []
        self.local64_mem_sizes: typing.List[int] = []
        self.io_mem_sizes: typing.List[int] = []
        self.base_setup_indices: typing.List[int] = []
        self.base_indices: typing.List[int] = []
        self.instance_count: int = 0
        self.instruction_count: int = 0
        self.current_param_table_offset: int = 0
        self.param_table: typing.Dict[typing.Tuple[ValueType, typing.Type[ValueType]], int] = {}
        self.signature_table: typing.List[int] = []
        self.signature_list: typing.List[str] = []
        self.writer: ExpressionWriter = ExpressionWriter(io.BytesIO(), name = "Expression Writer")
        self.version: int = 0