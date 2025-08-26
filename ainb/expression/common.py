import io
import typing

from ainb.utils import Endian, ReaderWithStrPool, Vector3f, WriterWithStrPool

class ExpressionParseError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(f"An error occurred while parsing the expression: {msg}")

class ExpressionPreProcessError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(f"An error occurred while preprocessing the expression: {msg}")

class ExpressionReader(ReaderWithStrPool):
    """
    Expression reader
    """
    __slots__ = ["_param_table_offset", "_signatures", "version"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        super().__init__(stream, endian, name)
        self._param_table_offset: int = 0
        self._signatures: typing.List[str] = []
        self.version: int = 0

    def set_param_table_offset(self, offset: int) -> None:
        self._param_table_offset = offset

    def set_signatures(self, signatures: typing.List[str]) -> None:
        self._signatures = signatures
    
    def read_bool_param_table(self, offset: int) -> bool:
        with self.temp_seek(self._param_table_offset + offset):
            return self.read_u32() != 0
    
    def read_s32_param_table(self, offset: int) -> int:
        with self.temp_seek(self._param_table_offset + offset):
            return self.read_s32()
    
    def read_f32_param_table(self, offset: int) -> float:
        with self.temp_seek(self._param_table_offset + offset):
            return self.read_f32()
    
    def read_vec3_param_table(self, offset: int) -> Vector3f:
        with self.temp_seek(self._param_table_offset + offset):
            return self.read_vec3()
    
    def read_string_param_table(self, offset: int) -> str:
        with self.temp_seek(self._param_table_offset + offset):
            return self.read_string_offset()

    def get_signature(self, index: int) -> str:
        return self._signatures[index]
    
class ExpressionWriter(WriterWithStrPool):
    """
    Expression writer
    """