import contextlib
import enum
import io
import mmh3
import os
import struct
import typing
import warnings

def calc_hash(string: str) -> int:
    """
    Calculates a Murmur3 hash from a string
    """
    return mmh3.hash(string, signed = False)

def align_up(value: int, alignment: int) -> int:
    """
    Aligns a value up to the given alignment
    """
    return value + (-value & (alignment - 1))

class EnumEx(enum.Enum):
    """
    Enum but with a different string covnersion
    """
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self._name_}"
    
    def __str__(self) -> str:
        return self._name_

class IntEnumEx(enum.IntEnum):
    """
    IntEnum but with a different string conversion
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self._name_}"
    
    def __str__(self) -> str:
        return self._name_

# TODO: type Vector3f = ... once we drop 3.10/3.11 (same with the other ones)
Vector3f = typing.Tuple[float, float, float]
ValueType = int | bool | float | str | Vector3f | None
JSONType = typing.Dict[str, typing.Any]

class Endian(enum.Enum):
    """
    Endianness enum
    """

    BIG     = 0
    LITTLE  = 1

class Reader:
    """
    Simple binary reader class
    """

    __slots__ = ["_stream", "_endian", "_name"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        self._stream: typing.BinaryIO | io.BytesIO = stream
        self._endian: str = "<" if endian == Endian.LITTLE else ">"
        self._name: str = name

    def set_endian(self, endian: Endian) -> None:
        """
        Sets endianness
        """
        self._endian = "<" if endian == Endian.LITTLE else ">"

    def writable(self) -> bool:
        return self._stream.writable()
    
    def get_size(self) -> int:
        if isinstance(self._stream, io.BytesIO):
            return self._stream.getbuffer().nbytes
        raise NotImplementedError("Reader.get_size() is not implemented for BinaryIO")

    def tell(self) -> int:
        """
        Returns current position
        """
        return self._stream.tell()
    
    def seek(self, offset: int) -> None:
        """
        Sets current position
        """
        self._stream.seek(offset)

    def skip(self, offset: int) -> None:
        """
        Skips offset number of bytes from current position
        """
        self._stream.seek(offset, os.SEEK_CUR)

    def align_up(self, alignment: int) -> None:
        """
        Aligns the current position up to the specified alignment
        """
        self.seek(align_up(self.tell(), alignment))

    @property
    def name(self) -> str:
        """
        User-provided name for reader
        """
        return self._name

    def read(self, *args: int) -> bytes:
        """
        Reads from buffer
        """
        return self._stream.read(*args)
    
    def read_u8(self) -> int:
        """
        Reads unsigned 8-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}B", self.read(1))[0] # type: ignore
    
    def read_s8(self) -> int:
        """
        Reads signed 8-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}b", self.read(1))[0] # type: ignore
    
    def read_u16(self) -> int:
        """
        Reads unsigned 16-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}H", self.read(2))[0] # type: ignore
    
    def read_s16(self) -> int:
        """
        Reads signed 16-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}h", self.read(2))[0] # type: ignore
    
    def read_u32(self) -> int:
        """
        Reads unsigned 32-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}I", self.read(4))[0] # type: ignore
    
    def read_s32(self) -> int:
        """
        Reads signed 32-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}i", self.read(4))[0] # type: ignore
    
    def read_u64(self) -> int:
        """
        Reads unsigned 64-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}Q", self.read(8))[0] # type: ignore
    
    def read_s64(self) -> int:
        """
        Reads signed 64-bit integer from buffer
        """
        return struct.unpack(f"{self._endian}q", self.read(8))[0] # type: ignore
    
    def read_f16(self) -> float:
        """
        Reads 16-bit floating point value from buffer
        """
        return struct.unpack(f"{self._endian}e", self.read(4))[0] # type: ignore
    
    def read_f32(self) -> float:
        """
        Reads 32-bit floating point value from buffer
        """
        return struct.unpack(f"{self._endian}f", self.read(4))[0] # type: ignore
    
    def read_f64(self) -> float:
        """
        Reads 64-bit floating point value from buffer
        """
        return struct.unpack(f"{self._endian}d", self.read(4))[0] # type: ignore
    
    def read_vec3(self) -> Vector3f:
        """
        Reads three component f32 vector from buffer
        """
        return struct.unpack(f"{self._endian}fff", self.read(12))
    
    def read_guid(self) -> str:
        """
        Reads GUID from buffer
        """
        return f"{self.read_u32():08x}-{self.read_u16():04x}-{self.read_u16():04x}-{self.read_u8():02x}{self.read_u8():02x}-{self.read_u8():02x}{self.read_u8():02x}{self.read_u8():02x}{self.read_u8():02x}{self.read_u8():02x}{self.read_u8():02x}"
    
    def read_string(self, encoding: str = "utf-8") -> str:
        """
        Reads a null-terminated string from buffer (UTF-16/UTF-32 is unsupported)
        """
        data: bytes = self.peek_read()
        end: int
        end = data.find(b"\x00")
        return data[:end].decode(encoding)
        
    def unpack(self, format: str) -> typing.Tuple[typing.Any, ...]:
        return struct.unpack(format, self.read(struct.calcsize(format)))

    @contextlib.contextmanager
    def temp_seek(self, offset: int) -> typing.Generator["Reader", None, None]:
        """
        Temporarily seeks to the specified offset, returning to the original position on scope exit
        """
        pos: int = self.tell()
        self.seek(offset)

        yield self

        self.seek(pos)

    @contextlib.contextmanager
    def temp_skip(self, offset: int) -> typing.Generator["Reader", None, None]:
        """
        Temporarily skips offset number of bytes, returning to the original position on scope exit
        """
        pos: int = self.tell()
        self.skip(offset)

        yield self

        self.seek(pos)

    def peek_read(self, *args: int) -> bytes:
        """
        Peeks and reads at the current position
        """
        pos: int = self.tell()
        data: bytes = self.read(*args)
        self.seek(pos)
        return data
    
class Writer:
    """
    Simple binary writer class
    """
    
    __slots__ = ["_stream", "_endian", "_name"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO | None = None, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        self._stream: typing.BinaryIO | io.BytesIO
        if stream is None:
            self._stream = io.BytesIO()
        else:
            self._stream = stream
        self._endian: str = "<" if endian == Endian.LITTLE else ">"
        self._name: str = name

    def set_endian(self, endian: Endian) -> None:
        """
        Sets endianness
        """
        self._endian = "<" if endian == Endian.LITTLE else ">"

    def get_size(self) -> int:
        if isinstance(self._stream, io.BytesIO):
            return self._stream.getbuffer().nbytes
        raise NotImplementedError("Writer.get_size() is not implemented for BinaryIO")

    def tell(self) -> int:
        """
        Returns current position
        """
        return self._stream.tell()
    
    def seek(self, offset: int) -> None:
        """
        Sets current position
        """
        self._stream.seek(offset)

    def skip(self, offset: int) -> None:
        """
        Skips offset number of bytes from current position
        """
        self._stream.seek(offset, os.SEEK_CUR)

    def align_up(self, alignment: int) -> None:
        """
        Aligns the current position up to the specified alignment
        """
        self.seek(align_up(self.tell(), alignment))

    def get_buffer(self) -> bytes:
        """
        Returns a copy of the current buffer
        """
        if isinstance(self._stream, io.BytesIO):
            return self._stream.getvalue()
        else:
            with self.temp_seek(0) as writer:
                return writer._stream.read()

    @property
    def name(self) -> str:
        """
        User-provided name for writer
        """
        return self._name

    def write(self, data: bytes) -> None:
        """
        Writes to buffer
        """
        self._stream.write(data)

    def write_u8(self, value: int) -> None:
        """
        Writes unsigned 8-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}B", value))
    
    def write_s8(self, value: int) -> None:
        """
        Writes signed 8-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}b", value))
    
    def write_u16(self, value: int) -> None:
        """
        Writes unsigned 16-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}H", value))
    
    def write_s16(self, value: int) -> None:
        """
        Writes signed 16-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}h", value))
    
    def write_u32(self, value: int) -> None:
        """
        Writes unsigned 32-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}I", value))
    
    def write_s32(self, value: int) -> None:
        """
        Writes signed 32-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}i", value))
    
    def write_u64(self, value: int) -> None:
        """
        Writes unsigned 64-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}Q", value))
    
    def write_s64(self, value: int) -> None:
        """
        Writes signed 64-bit integer to buffer
        """
        self.write(struct.pack(f"{self._endian}q", value))
    
    def write_f16(self, value: float) -> None:
        """
        Writes 16-bit floating point value to buffer
        """
        self.write(struct.pack(f"{self._endian}e", value))
    
    def write_f32(self, value: float) -> None:
        """
        Writes 32-bit floating point value to buffer
        """
        self.write(struct.pack(f"{self._endian}f", value))
    
    def write_f64(self, value: float) -> None:
        """
        Writes 64-bit floating point value to buffer
        """
        self.write(struct.pack(f"{self._endian}d", value))

    def write_vec3(self, value: Vector3f) -> None:
        """
        Writes three component f32 vector to buffer
        """
        self.write_f32(value[0])
        self.write_f32(value[1])
        self.write_f32(value[2])

    def write_guid(self, value: str) -> None:
        """
        Writes GUID to buffer
        """
        parts = value.split("-")
        assert len(parts) == 5, f"Invalid GUID: {value}"
        self.write_u32((int(parts[0], 16)))
        self.write_u16((int(parts[1], 16)))
        self.write_u16((int(parts[2], 16)))
        self.write_u8((int(parts[3][0:2], 16)))
        self.write_u8((int(parts[3][2:4], 16)))
        self.write_u8((int(parts[4][0:2], 16)))
        self.write_u8((int(parts[4][2:4], 16)))
        self.write_u8((int(parts[4][4:6], 16)))
        self.write_u8((int(parts[4][6:8], 16)))
        self.write_u8((int(parts[4][8:10], 16)))
        self.write_u8((int(parts[4][10:12], 16)))

    # utf-16/utf-32 unsupported
    def write_string(self, value: str, encoding: str = "utf-8") -> None:
        """
        Writes null-terminated string to buffer
        """
        self.write(value.encode(encoding))
        self.write(b"\x00")

    @contextlib.contextmanager
    def temp_seek(self, offset: int) -> typing.Generator["Writer", None, None]:
        """
        Temporarily seeks to the specified offset, returning to the original position on scope exit
        """
        pos: int = self.tell()
        self.seek(offset)

        yield self

        self.seek(pos)

    @contextlib.contextmanager
    def temp_skip(self, offset: int) -> typing.Generator["Writer", None, None]:
        """
        Temporarily skips offset number of bytes, returning to the original position on scope exit
        """
        pos: int = self.tell()
        self.skip(offset)

        yield self

        self.seek(pos)

class WarningBase(UserWarning):
    """
    Warning base class
    """
    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self._warn()
    
    def _warn(self) -> None:
        warnings.warn(self)

class ParseError(Exception):
    """
    Parsing error
    """

    def __init__(self, reader: Reader, msg: str) -> None:
        super().__init__(f"Parsing error at offset {reader.tell():#x} in reader ({reader.name}): {msg}")

class ParseWarning(WarningBase):
    """
    Parsing warning
    """

    def __init__(self, reader: Reader, msg: str) -> None:
        super().__init__(f"Parsing warning at offset {reader.tell():#x} in reader ({reader.name}): {msg}")

class DictDecodeError(Exception):
    """
    Dictionary decoding error
    """

    def __init__(self, msg: str) -> None:
        super().__init__(f"Dictionary decoding error: {msg}")

class DictDecodeWarning(WarningBase):
    """
    Dictionary decoding warning
    """

    def __init__(self, msg: str) -> None:
        super().__init__(f"Dictionary decoding warning: {msg}")

class SerializeError(Exception):
    """
    Serialization error
    """

    def __init__(self, writer: Writer, msg: str) -> None:
        super().__init__(f"Serialization error at offset {writer.tell():#x} in writer ({writer.name}): {msg}")

class SerializeWarning(WarningBase):
    """
    Serialization warning
    """

    def __init__(self, writer: Writer, msg: str) -> None:
        super().__init__(f"Serialization warning at offset {writer.tell():#x} in writer ({writer.name}): {msg}")

class StringPool:
    """
    Class representing a binary string pool composed of a sequence of null-terminated strings accessed by their offset from the start of the pool
    """

    __slots__ = ["_strings", "_offset", "_string_set", "_encoding"]

    def __init__(self, encoding: str = "utf-8") -> None:
        self._strings: typing.Dict[int, str] = {}
        self._offset: int = 0
        self._string_set: typing.Set[str] = set()
        self._encoding: str = encoding

    @classmethod
    def from_bytes(cls, data: bytes, format: str = "utf-8") -> "StringPool":
        """
        Creates a string pool from the provided bytes
        """
        str_pool: StringPool = cls(format)
        raw: typing.List[bytes] = data.split(b"\x00")
        if raw[-1] == b"":
            raw.pop(-1)
        for string in raw:
            decoded = string.decode(format)
            if decoded in str_pool._string_set:
                raise ValueError(f"Duplicate string {decoded} found in string pool at offset {str_pool._offset:#x}")
            str_pool._strings[str_pool._offset] = decoded
            str_pool._offset += len(string) + 1
            str_pool._string_set.add(decoded)
        return str_pool
    
    @classmethod
    def from_iterable(cls, strings: typing.Iterable[str], format: str = "utf-8") -> "StringPool":
        """
        Creates a string pool from an interable of strings
        """
        str_pool: StringPool = cls(format)
        for string in strings:
            if string in str_pool._string_set:
                continue
            str_pool._strings[str_pool._offset] = string
            str_pool._offset += len(string.encode(format)) + 1
            str_pool._string_set.add(string)
        return str_pool
    
    def write(self, writer: Writer) -> None:
        """
        Writes a string pool to the provided writer's stream
        """
        offset: int = 0
        for off, string in self._strings.items():
            assert offset == off, f"String \"{string}\" in string pool was written at offset {hex(offset)} but expected offset {hex(off)}"
            writer.write_string(string, self._encoding)
            offset += len(string.encode(self._encoding)) + 1
    
    def get_string(self, offset: int) -> str:
        """
        Get a string from the string pool by its offset
        """
        return self._strings[offset]
    
    def add_string(self, string: str) -> None:
        """
        Add a string to the string pool and calculate its offset
        """
        if string in self._string_set:
            return
        self._strings[self._offset] = string
        self._string_set.add(string)
        self._offset += len(string.encode(self._encoding)) + 1

    def contains(self, string: str) -> bool:
        """
        Returns whether or not a string is in the string pool
        """
        return string in self._string_set

    def get_strings(self) -> typing.ValuesView[str]:
        """
        Returns a view over all strings in the string pool
        """
        return self._strings.values()
    
class ReaderWithStrPool(Reader):
    """
    Binary reader class with attached string pool
    """

    __slots__ = ["_string_pool"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        super().__init__(stream, endian, name)
        self._string_pool: StringPool = StringPool()

    def init_string_pool(self, data: bytes) -> None:
        self._string_pool = StringPool.from_bytes(data)
    
    def get_string(self, offset: int) -> str:
        """
        Get string from string pool by offset

        String pool must be initialized first
        """
        try:
            return self._string_pool.get_string(offset)
        except KeyError as e:
            raise ParseError(self, f"KeyError when accessing string from StringPool: {e.args}") from e
    
    def read_string_offset(self) -> str:
        """
        Read string from buffer by reading a u32 offset

        String pool must be initialized first
        """
        return self.get_string(self.read_u32())
    
class WriterWithStrPool(Writer):
    """
    Binary writer class with attached string pool
    """

    __slots__ = ["_string_pool", "_string_map"]

    def __init__(self, stream: typing.BinaryIO | io.BytesIO, endian: Endian = Endian.LITTLE, name: str = "") -> None:
        super().__init__(stream, endian, name)
        self._string_pool: StringPool = StringPool()
        self._string_map: typing.Dict[str, int] = {}
    
    def add_string(self, string: str) -> int:
        """
        Adds a new string to the string pool
        """
        if string in self._string_map:
            return self._string_map[string]
        offset: int = self._string_pool._offset
        self._string_map[string] = offset
        self._string_pool.add_string(string)
        return offset
    
    def write_string_offset(self, string: str) -> None:
        """
        Writes the string offset associated with the input string, adding it into the pool if needed
        """
        offset: int | None = self._string_map.get(string, None)
        if offset is None:
            offset = self.add_string(string)
        self.write_u32(offset)
    
    def write_string_pool(self) -> None:
        """
        Writes the current string pool into the buffer
        """
        self._string_pool.write(self)

    def get_string_offset(self, string: str) -> int:
        return self._string_map[string]