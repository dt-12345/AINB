import enum
import importlib.resources
import io
import json
import os
import struct
import typing

from ainb.action import Action
from ainb.attachment import Attachment
from ainb.blackboard import Blackboard
from ainb.command import Command
from ainb.common import AINBReader
from ainb.enum_resolve import EnumEntry
from ainb.expression import ExpressionModule
from ainb.module import Module
from ainb.node import Node, Transition
from ainb.param import ParamSet, ParamSource
from ainb.property import PropertySet
from ainb.replacement import ReplacementEntry, ReplacementType
from ainb.utils import DictDecodeError, JSONType, ParseError, ParseWarning

# TODO: serialization
# TODO: editing API (at least add/remove nodes/plugs/etc.)

# TODO: version 0x408 support if it's not too hard
SUPPORTED_VERSIONS: typing.Tuple[int, ...] = (0x404, 0x407)

def get_supported_versions() -> typing.Tuple[int, ...]:
    """
    Returns a tuple of all supported AINB versions
    """
    return SUPPORTED_VERSIONS

class FileCategory(enum.Enum):
    AI                  = 0
    Logic               = 1
    Sequence            = 2
    UniqueSequence      = enum.auto() # splatoon 3 only
    UniqueSequenceSPL   = enum.auto() # splatoon 3 only

class UnknownSection0x58(typing.NamedTuple):
    description: str = ""
    unk04: int = 0
    unk08: int = 0
    unk0c: int = 0

    def _as_dict(self) -> JSONType:
        return {
            "Description" : self.description,
            "Unknown04" : self.unk04,
            "Unknown08" : self.unk08,
            "Unknown0C" : self.unk0c,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "UnknownSection0x58":
        return cls(
            data["Description"],
            data["Unknown04"],
            data["Unknown08"],
            data["Unknown0C"],
        )

class AINB:
    """
    Class representing an AINB file
    """

    _ENUM_DB: typing.Dict[str, typing.Dict[str, int]] = {}

    __slots__ = ["version", "filename", "category", "commands", "nodes", "blackboard", "expressions", "replacement_table", "modules", "unk_section0x58", "blackboard_id", "parent_blackboard_id"]

    def __init__(self) -> None:
        self.version: int = 0
        self.filename: str = ""
        self.category: str = ""
        self.commands: typing.List[Command] = []
        self.nodes: typing.List[Node] = []
        self.blackboard: Blackboard | None = None
        self.expressions: ExpressionModule | None = None
        self.replacement_table: typing.List[ReplacementEntry] = []
        self.modules: typing.List[Module] = []
        self.unk_section0x58: UnknownSection0x58 | None = None
        self.blackboard_id: int = 0
        # id of parent module to inherit blackboard from (only inherits if non-zero)
        # note that blackboards can be inherited even if the ids don't match so long as the parent module calls the module in question
        self.parent_blackboard_id: int = 0

    @classmethod
    def read(cls, reader: AINBReader) -> "AINB":
        """
        Reads an AINB file from the provided binary stream reader
        """
        self: AINB = cls()

        magic: str = reader.read(4).decode()
        if magic != "AIB ":
            raise ParseError(reader, f"Invalid AINB file magic, expected \"AIB \" but got \"{magic}\"")
        self.version = reader.read_u32()
        if self.version not in SUPPORTED_VERSIONS:
            raise ParseError(reader, f"Unsupported AINB version: {self.version:#x} - see ainb.get_supported_versions()")
        reader.version = self.version

        (
            filename_offset, command_count, node_count, query_count, attachment_count, output_count, blackboard_offset, string_pool_offset,
        ) = typing.cast(typing.Tuple[int, ...], reader.unpack("<8I"))

        with reader.temp_seek(string_pool_offset):
            reader.init_string_pool(reader.read())

        self.filename = reader.get_string(filename_offset)

        (
            enum_resolve_offset, property_offset, transition_offset, io_param_offset, multi_param_offset,
            attachment_offset, attachment_index_offset, expression_offset, replacement_offset, query_offset,
            _x50, _x54, _x58, module_offset, category_name_offset, category, action_offset, _x6c, blackboard_id_offset,
        ) = typing.cast(typing.Tuple[int, ...], reader.unpack("<19I"))

        self.category = reader.get_string(category_name_offset)
        if self.version > 0x404:
            if self.category != FileCategory(category).name:
                ParseWarning(reader, f"Category name string and category enum do not match: {self.category} vs. {FileCategory(category).name}")
        else:
            if category != 0:
                ParseWarning(reader, f"Unused category field has a non-zero value: {category}")

        self.commands = [Command._read(reader) for i in range(command_count)]

        # defer node parsing until after we've filled out the other parts of the file
        node_offset: int = reader.tell()

        reader.seek(enum_resolve_offset)
        num_enums_to_resolve = reader.read_u32()
        enums_to_resolve: typing.List[EnumEntry] = [
            self._read_enum_entry(reader) for i in range(num_enums_to_resolve)
        ]

        if len(enums_to_resolve) > 0:
            if not reader.writable():
                raise ParseError(reader, "Required enum resolutions found but input stream is not writable")
            if len(AINB._ENUM_DB) == 0:
                ParseWarning(reader, "Enum database is empty, did you forget to register a database beforehand?")
            for entry in enums_to_resolve:
                self._process_enum_resolve(entry, reader)

        reader.seek(blackboard_offset)
        self.blackboard = Blackboard._read(reader)

        if expression_offset != 0:
            reader.seek(expression_offset)
            self.expressions = ExpressionModule.from_binary(reader.read(module_offset - expression_offset))

        reader.seek(property_offset)
        properties: PropertySet = PropertySet._read(reader, io_param_offset)

        reader.seek(attachment_offset)
        attachments: typing.List[Attachment] = [
            Attachment._read(reader, properties) for i in range(attachment_count)
        ]

        reader.seek(attachment_index_offset)
        attachment_indices: typing.List[int] = [
            reader.read_u32() for i in range(int((attachment_offset - attachment_index_offset) / 4))
        ]

        reader.seek(multi_param_offset)
        multi_sources: typing.List[ParamSource] = [
            ParamSource._read(reader) for i in range(int((transition_offset - multi_param_offset) / 8))
        ]

        reader.seek(io_param_offset)
        io_params: ParamSet = ParamSet._read(reader, multi_param_offset, multi_sources)

        transitions: typing.List[Transition] = []
        if transition_offset < query_offset:
            reader.seek(transition_offset)
            transitions = self._read_transitions(reader)

        # don't use query_count here bc query_count is the number of nodes that are queries, not the number of elements in this array
        queries: typing.List[int] = []
        end: int = expression_offset if expression_offset != 0 else module_offset
        if query_offset < end:
            reader.seek(query_offset)
            queries = [
                self._read_query(reader) for i in range(int((end - query_offset) / 4))
            ]

        actions: typing.Dict[int, typing.List[Action]] = {}
        reader.seek(action_offset)
        action_count: int = reader.read_u32()
        for i in range(action_count):
            self._read_action(reader, actions)

        reader.seek(module_offset)
        module_count: int = reader.read_u32()
        self.modules = [
            self._read_module(reader) for i in range(module_count)
        ]

        reader.seek(blackboard_id_offset)
        self.blackboard_id = reader.read_u32()
        self.parent_blackboard_id = reader.read_u32()

        # it doesn't seem to actually apply these in verisons < 0x407 but the header structure seems the same at least
        if reader.version >= 0x407:
            reader.seek(replacement_offset)
            replaced: int = reader.read_u8()
            if replaced != 0:
                ParseWarning(reader, "File indicates that replacements were already processed")
            _ = reader.read_u8() # padding
            replace_count: int = reader.read_u16()          # total entry count
            node_entry_count: int = reader.read_u16()       # node-related entry count
            attachment_entry_count: int = reader.read_u16() # attachment-related entry count
            self.replacement_table = [
                self._read_replacement(reader) for i in range(replace_count)
            ]
        else:
            if replacement_offset != 0:
                ParseWarning(reader, f"Replacement table found in file with version {self.version:#x} which is unsupported (minimum version with replacement table support: 0x407)")

        reader.seek(node_offset)
        self.nodes = [
            Node._read(reader, attachments, attachment_indices, properties, io_params, transitions, queries, actions, self.modules, i) for i in range(node_count)
        ]

        # convert query indices to canonical node indices
        query_indices: typing.List[int] = [
            i for i, node in enumerate(self.nodes) if node.flags.is_query()
        ]
        for node in self.nodes:
            self._fix_query_indices(node, query_indices)

        # TODO: unknown sections

        if _x50 != transition_offset:
            ParseWarning(reader, "Section 0x50 of the header appears to exist")
        
        if _x54 != 0:
            ParseWarning(reader, f"Offset 0x54 of the header is non-zero: {_x54}")
        
        # this section only seems to appear in version 0x404, but it should be allowable in later versions
        if _x58 != 0:
            reader.seek(_x58)
            self.unk_section0x58 = UnknownSection0x58(
                reader.read_string_offset(),
                reader.read_u32(),
                reader.read_u32(),
                reader.read_u32(),
            )

        if _x6c != 0:
            reader.seek(_x6c)
            count_maybe: int = reader.read_u32()
            if count_maybe != 0:
                ParseWarning(reader, f"Section 0x6c of the header appears to exist with value: {count_maybe}")

        return self
    
    @classmethod
    def from_binary(cls, data: bytes | bytearray | typing.BinaryIO | io.BytesIO, read_only: bool = True, reader_name: str = "AINB Reader") -> "AINB":
        """
        Load an AINB from the provided input buffer

        data is the input buffer

        read_only is whether or not to create a read-only binary reader - this must be set to False for files with enum resolutions, default is True

        reader_name is an optional name for the binary reader instance (the name that will be shown if an error is thrown by the reader)
        """
        if isinstance(data, bytes) or isinstance(data, bytearray):
            return cls.read(AINBReader(io.BytesIO(memoryview(data)), name = reader_name))
        else:
            if read_only:
                return cls.read(AINBReader(data, name = reader_name))
            else:
                return cls.read(AINBReader(io.BytesIO(memoryview(data.read())), name = reader_name))

    @classmethod
    def from_file(cls, file_path: str, read_only: bool = True) -> "AINB":
        """
        Load an AINB from the specified file path

        file_path is the path to the input AINB file

        read_only is whether or not to create a read-only binary reader (does not affect how the file is opened) - this must be set to False for files
        with enum resolutions, default is True
        """
        with open(file_path, "rb") as infile:
            if read_only:
                # not sure if it actually makes much of a difference or not
                # but just in case someone has a massive AINB file, we probably don't want to always read it all at once
                return cls.read(AINBReader(infile, name = file_path))
            else:
                return cls.read(AINBReader(io.BytesIO(memoryview(infile.read())), name = file_path))
        
    @staticmethod
    def _read_enum_entry(reader: AINBReader) -> EnumEntry:
        return EnumEntry(
            patch_offset = reader.read_u32(),
            classname = reader.read_string_offset(),
            value_name = reader.read_string_offset()
        )
    
    @classmethod
    def _search_enum_db(cls, classname: str, value_name: str) -> int | None:
        enum_info: typing.Dict[str, int] = cls._ENUM_DB.get(classname, {})
        return enum_info.get(value_name, None)

    @classmethod
    def _process_enum_resolve(cls, entry: EnumEntry, reader: AINBReader) -> None:
        if entry.patch_offset >= reader.get_size():
            ParseWarning(reader, f"Out-of-bounds enum patch with offset {entry.patch_offset:#x} (buffer size: {reader.get_size():#x})")
            return
        value: int | None = cls._search_enum_db(entry.classname, entry.value_name)
        if value is None:
            ParseWarning(reader, f"Could not find matching enum entry in database: {entry.classname}::{entry.value_name}")
            return
        with reader.temp_seek(entry.patch_offset):
            reader._stream.write(struct.pack("<i", value))

    @staticmethod
    def _read_transition(reader: AINBReader, offset: int) -> Transition:
        reader.seek(offset)
        flags: int = reader.read_u32()
        return Transition(
            transition_type = flags & 0xff,
            update_post_calc = (flags >> 0x1f & 1) != 0,
            command_name = reader.read_string_offset() if flags & 0xff == 0 else ""
        )

    @staticmethod
    def _read_transitions(reader: AINBReader) -> typing.List[Transition]:
        # would be nice to have something less seek-heavy (technically we can by just ignoring the offsets, but this is more "proper")
        offsets: typing.List[int] = [reader.read_u32()]
        while reader.tell() < offsets[0]:
            offsets.append(reader.read_u32())
        return [
            AINB._read_transition(reader, offset) for offset in offsets
        ]
    
    @staticmethod
    def _read_query(reader: AINBReader) -> int:
        index: int = reader.read_u16()
        unk: int = reader.read_u16() # always 0, maybe padding? but why would it exist
        return index
    
    @staticmethod
    def _read_action(reader: AINBReader, actions: typing.Dict[int, typing.List[Action]]) -> None:
        index: int = reader.read_s32()
        if index not in actions:
            actions[index] = [Action(reader.read_string_offset(), reader.read_string_offset())]
        else:
            actions[index].append(Action(reader.read_string_offset(), reader.read_string_offset()))

    @staticmethod
    def _read_module(reader: AINBReader) -> Module:
        return Module(
            reader.read_string_offset(),
            reader.read_string_offset(),
            reader.read_u32()
        )
    
    @staticmethod
    def _read_replacement(reader: AINBReader) -> ReplacementEntry:
        replace_type: ReplacementType = ReplacementType(reader.read_u8())
        _ = reader.read_u8() # padding
        return ReplacementEntry(
            replace_type,
            reader.read_s16(),
            reader.read_s16(),
            reader.read_s16()
        )
    
    def _fix_query_indices(self, node: Node, query_indices: typing.List[int]) -> None:
        node.queries = [query_indices[i] for i in node.queries]

    @staticmethod
    def _verify_enum_db(db: typing.Dict[str, typing.Dict[str, int]]) -> bool:
        if not isinstance(db, dict):
            return False
        
        for enum_name, values in db.items():
            if not isinstance(enum_name, str):
                return False
            if not isinstance(values, dict):
                return False
            for value_name, value in values.items():
                if not isinstance(value_name, str):
                    return False
                if not isinstance(value, int):
                    return False
        
        return True

    @classmethod
    def set_enum_db(cls, new_db: typing.Dict[str, typing.Dict[str, int]]) -> None:
        """
        Sets the current enum database used for processing enum resolutions, this should be called before loading any files with enums to be resolved

        Should be in the form of a dictionary in the form::
            
            {
                "EnumName1" : {
                    "Value1" : 1,
                    "Value2" : 2,
                },
                "EnumName2" : {
                    "Value1" : 1,
                }
            }
        """
        assert cls._verify_enum_db(new_db), f"Invalid database!"
        cls._ENUM_DB = new_db

    def as_dict(self) -> JSONType:
        """
        Returns an AINB object in dictionary form
        """
        if self.version < 0x407:
            return {
                "Version" : self.version,
                "Filename" : self.filename,
                "Category" : self.category,
                "Blackboard ID" : self.blackboard_id,
                "Parent Blackboard ID" : self.parent_blackboard_id,
                "Commands" : [ cmd._as_dict() for cmd in self.commands ],
                "Nodes" : [ node._as_dict() for node in self.nodes ],
                "Blackboard" : self.blackboard._as_dict() if self.blackboard is not None else {},
                "Expressions" : self.expressions.as_dict() if self.expressions is not None else {},
                "Modules" : [ module._as_dict() for module in self.modules ],
                "Unknown Section 0x58" : self.unk_section0x58._as_dict() if self.unk_section0x58 is not None else {},
            }
        else:
            return {
                "Version" : self.version,
                "Filename" : self.filename,
                "Category" : self.category,
                "Blackboard ID" : self.blackboard_id,
                "Parent Blackboard ID" : self.parent_blackboard_id,
                "Commands" : [ cmd._as_dict() for cmd in self.commands ],
                "Nodes" : [ node._as_dict() for node in self.nodes ],
                "Blackboard" : self.blackboard._as_dict() if self.blackboard is not None else {},
                "Expressions" : self.expressions.as_dict() if self.expressions is not None else {},
                "Replacement Table" : [ entry._as_dict() for entry in self.replacement_table ],
                "Modules" : [ module._as_dict() for module in self.modules ],
                "Unknown Section 0x58" : self.unk_section0x58._as_dict() if self.unk_section0x58 is not None else {},
            }
    
    def save_json(self, output_path: str = "", override_filename: str = "") -> None:
        """
        Save AINB to JSON file
        """
        if output_path:
            os.makedirs(output_path, exist_ok=True)
        output_filename: str = override_filename if override_filename else f"{self.filename}.json"
        with open(os.path.join(output_path, output_filename), "w", encoding="utf-8") as f:
            json.dump(self.as_dict(), f, indent=2, ensure_ascii=False)

    def to_json(self) -> str:
        """
        Convert AINB to JSON string
        """
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: JSONType, override_filename: str = "") -> "AINB":
        """
        Deserialize a dictionary into an AINB object
        """
        self: AINB = cls()

        self.version = data["Version"]
        if self.version not in SUPPORTED_VERSIONS:
            raise DictDecodeError(f"Unsupported AINB version: {self.version}")

        if override_filename != "":
            self.filename = override_filename
        else:
            self.filename = data["Filename"]

        self.category = data["Category"]
        if self.version > 0x404:
            if self.category not in FileCategory.__members__:
                raise DictDecodeError(f"Unknown file category: {self.category}")
        
        self.blackboard_id = data["Blackboard ID"]
        self.parent_blackboard_id = data["Parent Blackboard ID"]

        self.commands = [
            Command._from_dict(cmd) for cmd in data["Commands"]
        ]

        self.nodes = [
            Node._from_dict(node, i) for i, node in enumerate(data["Nodes"])
        ]

        if (bb := data["Blackboard"]) != {}:
            self.blackboard = Blackboard._from_dict(bb)
        
        if (expr := data["Expressions"]) != {}:
            self.expressions = ExpressionModule.from_dict(expr)

        if self.version >= 0x407:
            self.replacement_table = [
                ReplacementEntry._from_dict(entry) for entry in data["Replacement Table"]
            ]
        
        self.modules = [
            Module._from_dict(module) for module in data["Modules"]
        ]

        if (unk_section := data["Unknown Section 0x58"]) != {}:
            self.unk_section0x58 = UnknownSection0x58._from_dict(unk_section)

        return self
    
    @classmethod
    def from_json(cls, filepath: str, override_filename: str = "") -> "AINB":
        """
        Deserialize a JSON file into an AINB object
        """
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f), override_filename)
        
    @classmethod
    def from_json_text(cls, text: str, override_filename: str = "") -> "AINB":
        """
        Deserialize a JSON string into an AINB object
        """
        return cls.from_dict(json.loads(text), override_filename)
    
    def get_node(self, node_index: int) -> Node | None:
        if node_index < 0 or node_index >= len(self.nodes):
            return None
        return self.nodes[node_index]
    
    def get_command(self, cmd_index: int) -> Command | None:
        if cmd_index < 0 or cmd_index >= len(self.commands):
            return None
        return self.commands[cmd_index]

    def get_command_by_name(self, cmd_name: str) -> Command | None:
        for cmd in self.commands:
            if cmd.name == cmd_name:
                return cmd
        return None

def set_game(game: str) -> None:
    """
    Set the current game (only used to update the corresponding enum database)

    nss = Nintendo Switch Sports\n
    s3 = Splatoon 3
    """
    db_path: str = f"{game}.json"
    try:
        with importlib.resources.open_text("ainb.data", db_path) as f:
            db: typing.Dict[str, typing.Dict[str, int]] = json.load(f)
            AINB.set_enum_db(db)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to set {game}: {e.args}")

def set_nintendo_switch_sports() -> None:
    """
    Set the current game to Nintendo Switch Sports
    """
    set_game("nss")

def set_splatoon3() -> None:
    """
    Set the current game to Splatoon 3
    """
    set_game("s3")

def set_tears_of_the_kingdom() -> None:
    """
    Set the current game to The Legend of Zelda: Tears of the Kingdom
    """
    # no enum db needed
    return

def set_super_mario_bros_wonder() -> None:
    """
    Set the current game to Super Mario Bros. Wonder
    """
    # no enum db needed
    return