import io
import typing

from ainb.utils import Endian, ReaderWithStrPool, WriterWithStrPool

class AINBReader(ReaderWithStrPool):
    """
    AINB reader
    """

    __slots__ = ["version"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        super().__init__(stream, endian, name)
        self.version: int = 0

class AINBWriter(WriterWithStrPool):
    """
    AINB writer
    """

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        super().__init__(stream, endian, name)