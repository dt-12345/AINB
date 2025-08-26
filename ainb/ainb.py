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
from ainb.common import AINBReader, AINBWriter
from ainb.enum_resolve import EnumEntry
from ainb.expression.module import ExpressionModule
from ainb.module import Module
from ainb.node import Node
from ainb.param import ParamSet, ParamSource
from ainb.param_common import ParamType
from ainb.property import PropertySet
from ainb.replacement import ReplacementEntry, ReplacementType
from ainb.transition import Transition
from ainb.unknown import UnknownSection0x58
from ainb.utils import DictDecodeError, JSONType, ParseError, ParseWarning
from ainb.write_context import WriteContext

# TODO: editing API (at least add/remove nodes/plugs/etc.)

# TODO: version 0x408 support if it's not too hard (seems to be u32 blackboard type)
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

class AINB:
    """
    Class representing an AINB file
    """

    _ENUM_DB: typing.Dict[str, typing.Dict[str, int]] = {}

    __slots__ = ["version", "filename", "category", "commands", "nodes", "blackboard", "expressions",
                 "replacement_table", "modules", "unk_section0x58", "blackboard_id", "parent_blackboard_id",
                 "exists_section_0x6c"]

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
        self.exists_section_0x6c: bool = False

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
            updated_node_count: int = reader.read_s16()       # file node count post-replacements
            updated_attachment_count: int = reader.read_s16() # file attachment count post-replacements
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
            self.exists_section_0x6c = True
        else:
            assert False

        return self
    
    @classmethod
    def from_binary(cls, data: bytes | bytearray, reader_name: str = "AINB Reader") -> "AINB":
        """
        Load an AINB from the provided input buffer

        data is the input buffer

        reader_name is an optional name for the binary reader instance (the name that will be shown if an error is thrown by the reader)
        """
        return cls.read(AINBReader(io.BytesIO(memoryview(data)), name = reader_name))

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
                "Has Section 0x6C" : self.exists_section_0x6c,
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
                "Has Section 0x6C" : self.exists_section_0x6c,
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

        if (bb := data.get("Blackboard", {})) != {}:
            self.blackboard = Blackboard._from_dict(bb)
        
        if (expr := data.get("Expressions", {})) != {}:
            self.expressions = ExpressionModule.from_dict(expr)

        if self.version >= 0x407:
            self.replacement_table = [
                ReplacementEntry._from_dict(entry) for entry in data["Replacement Table"]
            ]
        
        self.modules = [
            Module._from_dict(module) for module in data["Modules"]
        ]

        if (unk_section := data.get("Unknown Section 0x58", {})) != {}:
            self.unk_section0x58 = UnknownSection0x58._from_dict(unk_section)
        
        self.exists_section_0x6c = data.get("Has Section 0x6C", False)

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
    
    def _build_context(self, ctx: WriteContext) -> None:
        node_size: int = 0x3c if self.version > 0x404 else 0x38
        attachment_size: int = 0x10 if self.version > 0x404 else 0xc
        ctx.version = self.version
        ctx.command_count = len(self.commands)
        ctx.node_count = len(self.nodes)
        ctx.output_count = sum(1 for node in self.nodes if node.type.value >= 200 and node.type.value < 300)
        ctx.query_count = sum(1 for node in self.nodes if node.flags.is_query())
        ctx.blackboard_offset = 0x74 + 0x18 * ctx.command_count + node_size * ctx.node_count
        if self.expressions is not None:
            ctx.expression_ctx.version = self.expressions.version
            for expr in self.expressions.expressions:
                expr._preprocess(ctx.expression_ctx)
        curr_query_index: int = 0
        for i, node in enumerate(self.nodes):
            if node.flags.is_query():
                ctx.query_map[i] = curr_query_index
                curr_query_index += 1
        if self.blackboard is not None:
            ctx.curr_node_param_offset = ctx.blackboard_offset + self.blackboard._calc_size()
        else:
            ctx.curr_node_param_offset = ctx.blackboard_offset + 0x30
        for node in self.nodes:
            node._preprocess(ctx)
        for attachment in ctx.attachments:
            attachment_io_size: int = 0
            attachment_expr_count: int = 0
            for p_type in ParamType:
                for prop in attachment.properties.get_properties(p_type):
                    ctx.props._properties[p_type].append(prop)
                    if prop.flags.is_expression():
                        ctx.expression_ctx.instance_count += 1
                        attachment_expr_count += 1
                        attachment_io_size += ctx.expression_ctx.io_mem_sizes[prop.flags.get_index()]
            ctx.attachment_expression_counts.append(attachment_expr_count)
            ctx.attachment_expression_sizes.append(attachment_io_size)
        ctx.attachment_index_offset = ctx.curr_node_param_offset
        ctx.attachment_offset = ctx.attachment_index_offset + 4 * len(ctx.attachment_indices)
        ctx.attachment_count = len(ctx.attachments)
        ctx.attachment_prop_offset = ctx.attachment_offset + attachment_size * ctx.attachment_count
        ctx.attachment_prop_offsets = [ctx.attachment_prop_offset + 0x64 * i for i in range(ctx.attachment_count)]
        ctx.property_offset = ctx.attachment_prop_offset + 0x64 * ctx.attachment_count
        ctx.io_param_offset = ctx.property_offset + 0x18 + sum(prop._get_binary_size(p_type) for p_type in ParamType for prop in ctx.props.get_properties(p_type))
        ctx.multi_param_offset = ctx.io_param_offset + 0x30 \
                                    + sum(param._get_binary_size(p_type) for p_type in ParamType for param in ctx.params.get_inputs(p_type)) \
                                    + sum((8 if p_type == ParamType.Pointer else 4) * len(ctx.params.get_outputs(p_type)) for p_type in ParamType)
        ctx.x50_offset = ctx.multi_param_offset + 0x8 * len(ctx.multi_params)
        ctx.transition_offset = ctx.x50_offset
        ctx.query_offset = ctx.transition_offset + sum(4 + (8 if transition.transition_type == 0 else 4) for transition in ctx.transitions)
        if self.expressions is not None:
            ctx.expression_binary = self.expressions.to_binary(ctx.expression_ctx)
            ctx.expression_offset = ctx.query_offset + 4 * len(ctx.queries)
            ctx.module_offset = ctx.expression_offset + len(ctx.expression_binary)
        else:
            ctx.expression_offset = 0
            ctx.module_offset = ctx.query_offset + 4 * len(ctx.queries)
        ctx.action_offset = ctx.module_offset + 4 + 0xc * len(self.modules)
        ctx.bb_id_offset = ctx.action_offset + 4 + 0xc * len(ctx.actions)
        state_offset: int
        if self.unk_section0x58 is not None:
            ctx.x58_offset = ctx.bb_id_offset + 8
            state_offset = ctx.x58_offset + 0x10
        else:
            ctx.x58_offset = 0
            state_offset = ctx.bb_id_offset + 8
        if self.version < 0x407:
            ctx.node_state_offsets = [state_offset + 0x14 * i for i, node in enumerate(self.nodes) if node.state_info is not None]
            ctx.replacement_table_offset = 0
            if self.exists_section_0x6c:
                ctx.x6c_offset = ctx.node_state_offsets[-1] + 0x14
                ctx.enum_resolve_offset = ctx.x6c_offset + 4
            else:
                ctx.x6c_offset = 0
                ctx.enum_resolve_offset = ctx.node_state_offsets[-1] + 0x14
        else:
            ctx.replacement_table_offset = state_offset
            if self.exists_section_0x6c:
                ctx.x6c_offset = ctx.replacement_table_offset + 8 + 8 * len(self.replacement_table)
                ctx.enum_resolve_offset = ctx.x6c_offset + 4
            else:
                ctx.x6c_offset = 0
                ctx.enum_resolve_offset = ctx.replacement_table_offset + 8 + 8 * len(self.replacement_table)
        # inline all enums when serializing
        ctx.string_pool_offset = ctx.enum_resolve_offset + 4

    def _write_header(self, writer: AINBWriter, ctx: WriteContext) -> None:
        writer.write(b"AIB ")
        writer.write_u32(self.version)
        writer.write_string_offset(self.filename)
        writer.write_u32(ctx.command_count)
        writer.write_u32(ctx.node_count)
        writer.write_u32(ctx.query_count)
        writer.write_u32(ctx.attachment_count)
        writer.write_u32(ctx.output_count)
        writer.write_u32(ctx.blackboard_offset)
        writer.write_u32(ctx.string_pool_offset)
        writer.write_u32(ctx.enum_resolve_offset)
        writer.write_u32(ctx.property_offset)
        writer.write_u32(ctx.transition_offset)
        writer.write_u32(ctx.io_param_offset)
        writer.write_u32(ctx.multi_param_offset)
        writer.write_u32(ctx.attachment_offset)
        writer.write_u32(ctx.attachment_index_offset)
        writer.write_u32(ctx.expression_offset)
        writer.write_u32(ctx.replacement_table_offset)
        writer.write_u32(ctx.query_offset)
        writer.write_u32(ctx.x50_offset)
        writer.write_u32(ctx.x54_value)
        writer.write_u32(ctx.x58_offset)
        writer.write_u32(ctx.module_offset)
        writer.write_string_offset(self.category)
        if self.version > 0x404:
            writer.write_u32(FileCategory[self.category].value)
        else:
            writer.write_u32(0)
        writer.write_u32(ctx.action_offset)
        writer.write_u32(ctx.x6c_offset)
        writer.write_u32(ctx.bb_id_offset)

    @staticmethod
    def _write_transition(writer: AINBWriter, transition: Transition) -> None:
        if transition.update_post_calc:
            writer.write_u32(transition.transition_type | 0x80000000)
        else:
            writer.write_u32(transition.transition_type)
        if transition.transition_type == 0:
            writer.write_string_offset(transition.command_name)

    @staticmethod
    def _write_module(writer: AINBWriter, module: Module) -> None:
        writer.write_string_offset(module.path)
        writer.write_string_offset(module.category)
        writer.write_u32(module.instance_count)

    @staticmethod
    def _write_action(writer: AINBWriter, index: int, action_slot: str, action: str) -> None:
        writer.write_s32(index)
        writer.write_string_offset(action_slot)
        writer.write_string_offset(action)

    @staticmethod
    def _write_replacement(writer: AINBWriter, replacement: ReplacementEntry) -> None:
        writer.write_u8(replacement.type.value)
        writer.write_u8(0)
        writer.write_s16(replacement.node_index)
        writer.write_s16(replacement.replace_index)
        writer.write_s16(replacement.new_index)

    def write(self, writer: AINBWriter) -> None:
        """
        Serialize an AINB object to bytes using the provided writer
        """
        ctx: WriteContext = WriteContext()
        self._build_context(ctx)

        """
        Section order:
            - Header
            - Commands
            - Nodes
            - Blackboard
            - Node Params
            - Attachment Indices
            - Attachments
            - Attachment Params
            - Properties
            - Input/Output Params
            - Multi-Params
            - 0x50 Section
            - Transitions
            - Queries
            - Expressions
            - Modules
            - Actions
            - Blackboard IDs
            - 0x58 Section
            - Node State Info
            - Replacement Table
            - 0x6c Section
            - Enum Resolve Table
            - String Pool
        """

        self._write_header(writer, ctx)

        for cmd in self.commands:
            cmd._write(writer)
        
        for i, node in enumerate(self.nodes):
            node._write(writer, ctx, i)
        
        if self.blackboard:
            self.blackboard._write(writer)
        else:
            writer.write(b"\x00" * 0x30) # files always have a blackboard section, just in case the user deleted it from the json
        
        for node in self.nodes:
            node._write_params(writer, ctx)
        
        for i in ctx.attachment_indices:
            writer.write_u32(i)
        
        param_offset: int = writer.tell() + (0x10 if self.version > 0x404 else 0xc) * len(ctx.attachments)
        for i, attachment in enumerate(ctx.attachments):
            attachment._write(writer, param_offset, i, ctx.attachment_expression_counts, ctx.attachment_expression_sizes, self.version > 0x404)
            param_offset += 0x64
        
        for attachment in ctx.attachments:
            attachment._write_params(writer, ctx.prop_indices)
        
        ctx.props._write(writer)
        ctx.params._write(writer, ctx.multi_params)

        for multi_param in ctx.multi_params:
            multi_param._write(writer)
        
        trans_offset: int = writer.tell() + 4 * len(ctx.transitions)
        for transition in ctx.transitions:
            writer.write_u32(trans_offset)
            trans_offset += (8 if transition.transition_type == 0 else 4)
        for transition in ctx.transitions:
            self._write_transition(writer, transition)
        
        for query in ctx.queries:
            writer.write_u16(query)
            writer.write_u16(0)
        
        if self.expressions is not None:
            writer.write(ctx.expression_binary)
        
        writer.write_u32(len(self.modules))
        for module in self.modules:
            self._write_module(writer, module)
        
        writer.write_u32(len(ctx.actions))
        for index, action_slot, action in ctx.actions:
            self._write_action(writer, index, action_slot, action)
        
        writer.write_u32(self.blackboard_id)
        writer.write_u32(self.parent_blackboard_id)

        if self.unk_section0x58 is not None:
            writer.write_string_offset(self.unk_section0x58.description)
            writer.write_u32(self.unk_section0x58.unk04)
            writer.write_u32(self.unk_section0x58.unk08)
            writer.write_u32(self.unk_section0x58.unk0c)
        
        if ctx.state_info:
            for state_info in ctx.state_info:
                writer.write_string_offset(state_info.desired_state)
                writer.write_u32(state_info.unk04)
                writer.write_u32(state_info.unk08)
                writer.write_u32(state_info.unk0c)
                writer.write_u32(state_info.unk10)
        
        if self.version > 0x404:
            writer.write_u16(0)
            writer.write_u16(len(self.replacement_table))
            exist_node: bool = False
            exist_attach: bool = False
            new_attach_count: int = ctx.attachment_count
            new_node_count: int = ctx.node_count
            for replacement in self.replacement_table:
                if replacement.type == ReplacementType.RemoveAttachment:
                    exist_attach = True
                    new_attach_count -= 1
                else:
                    exist_node = True
                    new_node_count -= (1 if replacement.type == ReplacementType.RemoveChild else 2)
            if exist_node:
                writer.write_s16(new_node_count)
            else:
                writer.write_s16(-1)
            if exist_attach:
                writer.write_s16(new_attach_count)
            else:
                writer.write_s16(-1)
            for replacement in self.replacement_table:
                self._write_replacement(writer, replacement)
        
        if self.exists_section_0x6c:
            writer.write_u32(0)
        
        writer.write_u32(0) # enum resolve table

        writer.write_string_pool()

    def to_binary(self) -> bytes:
        """
        Serialize an AINB object to bytes
        """
        writer: AINBWriter = AINBWriter(io.BytesIO(), name = "AINB Writer")
        self.write(writer)
        return writer.get_buffer()
    
    def save_ainb(self, output_path: str = "", override_filename: str = "") -> None:
        if output_path:
            os.makedirs(output_path, exist_ok=True)
        output_filename: str = override_filename if override_filename else f"{self.filename}.ainb"
        with open(os.path.join(output_path, output_filename), "wb") as f:
            self.write(AINBWriter(f, name = output_filename))

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