import abc
import dataclasses
import enum
import typing

from ainb.action import Action
from ainb.attachment import Attachment
from ainb.common import AINBReader
from ainb.module import Module
from ainb.param import ParamSet
from ainb.param_common import ParamType
from ainb.property import PropertySet
from ainb.state import StateInfo
from ainb.utils import DictDecodeError, IntEnumEx, JSONType, ParseError, ParseWarning

NULL_INDEX: int = 0x7fff

def get_null_index() -> int:
    """
    Returns the value representing a null (ignored) node index
    """
    return NULL_INDEX

@dataclasses.dataclass(slots=True)
class Transition:
    """
    A transition command entry where the root node of the current context is swapped
    """

    # 0 = state end transition
    # 1 = generic transition
    transition_type: int = 0
    update_post_calc: bool = False
    command_name: str = ""

class NodeType(enum.Enum):
    """
    Node type enum
    """

    UserDefined                    = 0
    Element_S32Selector            = 1
    Element_Sequential             = 2
    Element_Simultaneous           = 3
    Element_F32Selector            = 4
    Element_StringSelector         = 5
    Element_RandomSelector         = 6
    Element_BoolSelector           = 7
    Element_Fork                   = 8
    Element_Join                   = 9
    Element_Alert                  = 10
    Element_Expression             = 20
    Element_ModuleIF_Input_S32     = 100
    Element_ModuleIF_Input_F32     = 101
    Element_ModuleIF_Input_Vec3f   = 102
    Element_ModuleIF_Input_String  = 103
    Element_ModuleIF_Input_Bool    = 104
    Element_ModuleIF_Input_Ptr     = 105
    Element_ModuleIF_Output_S32    = 200
    Element_ModuleIF_Output_F32    = 201
    Element_ModuleIF_Output_Vec3f  = 202
    Element_ModuleIF_Output_String = 203
    Element_ModuleIF_Output_Bool   = 204
    Element_ModuleIF_Output_Ptr    = 205
    Element_ModuleIF_Child         = 300
    Element_StateEnd               = 400
    Element_SplitTiming            = 500

class PlugType(IntEnumEx):
    """
    Plug types
    """

    Generic     = 0
    _01         = 1
    Child       = 2
    Transition  = 3
    String      = 4
    Int         = 5
    _06         = 6
    _07         = 7
    _08         = 8
    _09         = 9

@dataclasses.dataclass(slots=True)
class PlugInfo:
    plug_count: int
    base_index: int

class Plug(metaclass=abc.ABCMeta):
    """
    Class representing a plug between two nodes
    """

    __slots__ = ["node_index"]

    def __init__(self) -> None:
        self.node_index: int = NULL_INDEX

    @classmethod
    @abc.abstractmethod
    def get_type(cls) -> PlugType:
        pass

    @classmethod
    @abc.abstractmethod
    def _read(cls, reader: AINBReader) -> "Plug":
        pass

    @abc.abstractmethod
    def _as_dict(self) -> JSONType:
        pass

    @classmethod
    @abc.abstractmethod
    def _from_dict(cls, data: JSONType) -> "Plug":
        pass

class GenericPlug(Plug):
    __slots__ = ["name"]

    def __init__(self) -> None:
        super().__init__()
        self.name: str = ""

    @classmethod
    def get_type(cls) -> PlugType:
        return PlugType.Generic
    
    @classmethod
    def _read(cls, reader: AINBReader) -> "GenericPlug":
        plug: GenericPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        return plug
    
    def _as_dict(self) -> JSONType:
        return {
            "Node Index" : self.node_index,
            "Name" : self.name,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "GenericPlug":
        plug: GenericPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        return plug
    
class ChildPlug(Plug):
    __slots__ = ["name"]

    def __init__(self) -> None:
        super().__init__()
        self.name: str = ""

    @classmethod
    def get_type(cls) -> PlugType:
        return PlugType.Child
    
    @classmethod
    def _read(cls, reader: AINBReader) -> "ChildPlug":
        plug: ChildPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        return plug
    
    def _as_dict(self) -> JSONType:
        return {
            "Node Index" : self.node_index,
            "Name" : self.name,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "ChildPlug":
        plug: ChildPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        return plug

class S32SelectorPlug(ChildPlug):
    __slots__ = ["condition", "is_default", "blackboard_index"]

    def __init__(self) -> None:
        super().__init__()
        self.condition: int = 0
        self.is_default: bool = False # is default condition for this selector
        self.blackboard_index: int = -1

    @classmethod
    def _read(cls, reader: AINBReader, is_last: bool = False) -> "S32SelectorPlug":
        plug: S32SelectorPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        index: int = reader.read_s16()
        flag: int = reader.read_u16()
        if flag >> 0xf != 0:
            plug.blackboard_index = index
        if is_last:
            plug.is_default = True
            if (value := reader.read_s32()) != 0:
                raise ParseError(reader, f"S32SelectorPlug expected empty padding for default case, got {value}")
        else:
            plug.condition = reader.read_s32()
        return plug
    
    def _as_dict(self) -> JSONType:
        if self.is_default:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Is Default" : self.is_default,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Condition" : self.condition,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "S32SelectorPlug":
        plug: S32SelectorPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        if "Condition" in data:
            plug.condition = data["Condition"]
        else:
            plug.is_default = data["Is Default"]
        return plug

class F32SelectorPlug(ChildPlug):
    __slots__ = ["condition_min", "blackboard_index_min", "condition_max", "blackboard_index_max", "is_default"]

    def __init__(self) -> None:
        super().__init__()
        self.condition_min: float = 0.0
        self.blackboard_index_min: int = -1
        self.condition_max: float = 0.0
        self.blackboard_index_max: int = -1
        self.is_default: bool = False # is default condition for this selector

    @classmethod
    def _read(cls, reader: AINBReader, is_last: bool = False) -> "F32SelectorPlug":
        plug: F32SelectorPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        if is_last:
            plug.is_default = True
            if (string := reader.read_string_offset()) != "その他":
                raise ParseError(reader, f"F32SelectorPlug expected \"その他\" as default case string, got \"{string}\"")
        else:
            index: int = reader.read_s16()
            flag: int = reader.read_u16()
            if flag >> 0xf != 0:
                plug.blackboard_index_min = index
                reader.read_f32()
            else:
                plug.condition_min = reader.read_f32()
            index = reader.read_s16()
            flag = reader.read_u16()
            if flag >> 0xf != 0:
                plug.blackboard_index_max = index
                reader.read_f32()
            else:
                plug.condition_max = reader.read_f32()
        return plug
    
    @staticmethod
    def _format_condition(condition: float, bb_index: int, is_min: bool) -> JSONType:
        if bb_index == -1:
            if is_min:
                return { "Condition Min" : condition }
            else:
                return { "Condition Max" : condition }
        else:
            if is_min:
                return { "Condition Min Blackboard Index" : bb_index }
            else:
                return { "Condition Max Blackboard Index" : bb_index }

    def _as_dict(self) -> JSONType:
        if self.is_default:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Is Default" : self.is_default,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
            } | self._format_condition(self.condition_min, self.blackboard_index_min, True) | self._format_condition(self.condition_max, self.blackboard_index_max, False)

    @classmethod
    def _from_dict(cls, data: JSONType) -> "F32SelectorPlug":
        plug: F32SelectorPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        if "Is Default" in data:
            plug.is_default = data["Is Default"]
        else:
            if "Condition Min" in data:
                plug.condition_min = data["Condition Min"]
            else:
                plug.blackboard_index_min = data["Condition Min Blackboard Index"]
            if "Condition Max" in data:
                plug.condition_max = data["Condition Max"]
            else:
                plug.blackboard_index_max = data["Condition Max Blackboard Index"]
        return plug

class StringSelectorPlug(ChildPlug):
    __slots__ = ["condition", "is_default", "blackboard_index"]

    def __init__(self) -> None:
        super().__init__()
        self.condition: str = ""
        self.is_default: bool = False # is default condition for this selector
        self.blackboard_index: int = -1

    @classmethod
    def _read(cls, reader: AINBReader, is_last: bool = False) -> "StringSelectorPlug":
        plug: StringSelectorPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        index: int = reader.read_s16()
        flag: int = reader.read_u16()
        if flag >> 0xf != 0:
            plug.blackboard_index = index
        if is_last:
            plug.is_default = True
            if (string := reader.read_string_offset()) != "その他":
                raise ParseError(reader, f"StringSelectorPlug expected \"その他\" as default case string, got \"{string}\"")
        else:
            plug.condition = reader.read_string_offset()
        return plug
    
    def _as_dict(self) -> JSONType:
        if self.is_default:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Is Default" : self.is_default,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Condition" : self.condition,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "StringSelectorPlug":
        plug: StringSelectorPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        if "Condition" in data:
            plug.condition = data["Condition"]
        else:
            plug.is_default = data["Is Default"]
        return plug

class RandomSelectorPlug(ChildPlug):
    __slots__ = ["weight"]

    def __init__(self) -> None:
        super().__init__()
        self.weight: float = 0.0

    @classmethod
    def _read(cls, reader: AINBReader) -> "RandomSelectorPlug":
        plug: RandomSelectorPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        plug.weight = reader.read_f32()
        return plug
    
    def _as_dict(self) -> JSONType:
        return {
            "Node Index" : self.node_index,
            "Name" : self.name,
            "Weight" : self.weight,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "RandomSelectorPlug":
        plug: RandomSelectorPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        plug.weight = data["Weight"]
        return plug

class BSASelectorUpdaterPlug(ChildPlug):
    __slots__ = ["unk0", "unk1"]

    def __init__(self) -> None:
        super().__init__()
        self.unk0: int = 0
        self.unk1: int = 0

    @classmethod
    def _read(cls, reader: AINBReader) -> "BSASelectorUpdaterPlug":
        plug: BSASelectorUpdaterPlug = cls()
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        plug.unk0 = reader.read_u32()
        plug.unk1 = reader.read_u32()
        return plug
    
    def _as_dict(self) -> JSONType:
        return {
            "Node Index" : self.node_index,
            "Name" : self.name,
            "Unknown0" : self.unk0,
            "Unknown1" : self.unk1,
        }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "BSASelectorUpdaterPlug":
        plug: BSASelectorUpdaterPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        plug.unk0 = data["Unknown0"]
        plug.unk1 = data["Unknown1"]
        return plug

class TransitionPlug(Plug):
    __slots__ = ["transition"]

    def __init__(self) -> None:
        super().__init__()
        self.transition: Transition = Transition()
    
    @classmethod
    def get_type(cls) -> PlugType:
        return PlugType.Transition

    @classmethod
    def _read(cls, reader: AINBReader, info_list: typing.List[Transition] | None = None) -> "TransitionPlug":
        if info_list is None:
            info_list = []
        plug: TransitionPlug = cls()
        plug.node_index = reader.read_s32()
        index: int = reader.read_u32()
        try:
            plug.transition = info_list[index]
        except IndexError as e:
            raise ParseError(reader, f"TransitionPlug has out-of-bounds entry index: {index}") from e
        return plug
    
    def _as_dict(self) -> JSONType:
        if self.transition.transition_type == 0:
            return {
                "Node Index" : self.node_index,
                "Transition Type" : self.transition.transition_type,
                "Update Post Calc" : self.transition.update_post_calc,
                "Transition Name" : self.transition.command_name,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Transition Type" : self.transition.transition_type,
                "Update Post Calc" : self.transition.update_post_calc,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "TransitionPlug":
        plug: TransitionPlug = cls()
        plug.node_index = data["Node Index"]
        if "Transition Name" in data:
            plug.transition = Transition(
                data["Transition Type"],
                data["Update Post Calc"],
                data["Transition Name"],
            )
        else:
            plug.transition = Transition(
                data["Transition Type"],
                data["Update Post Calc"],
            )
        return plug

class StringInputPlug(Plug):
    __slots__ = ["name", "unknown", "default_value", "_version"]

    def __init__(self) -> None:
        super().__init__()
        self.name: str = ""
        self.unknown: int = 0
        self.default_value: str = ""
        self._version: int = 0 # fake member to track the version this plug was read from

    @classmethod
    def get_type(cls) -> PlugType:
        return PlugType.String
    
    @classmethod
    def _read(cls, reader: AINBReader) -> "StringInputPlug":
        plug: StringInputPlug = cls()
        plug._version = reader.version
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        if reader.version > 0x404:
            # TODO: so an issue here is that there is no stored default value here if the source node's output isn't a string type (in the case an expression transforms it)
            # not that it really makes a difference or anything since these plugs are never read by the game afaik
            # and it should be guaranteed to never throw an error either since the string offset is 0 which is always a valid offset
            plug.unknown = reader.read_u32()
            plug.default_value = reader.read_string_offset()
        return plug
    
    def _as_dict(self) -> JSONType:
        if self._version > 0x404:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Unknown" : self.unknown,
                "Default Value" : self.default_value,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "StringInputPlug":
        plug: StringInputPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        if "Unknown" in data:
            plug.unknown = data["Unknown"]
            plug.default_value = data["Default Value"]
            plug._version = 0x407
        return plug

class IntInputPlug(Plug):
    __slots__ = ["name", "unknown", "default_value", "_version"]

    def __init__(self) -> None:
        super().__init__()
        self.name: str = ""
        self.unknown: int = 0
        self.default_value: int = 0
        self._version: int = 0 # fake member to track the version this plug was read from

    @classmethod
    def get_type(cls) -> PlugType:
        return PlugType.Int
    
    @classmethod
    def _read(cls, reader: AINBReader) -> "IntInputPlug":
        plug: IntInputPlug = cls()
        plug._version = reader.version
        plug.node_index = reader.read_s32()
        plug.name = reader.read_string_offset()
        if reader.version > 0x404:
            # TODO: same issue as with the string input plugs though even less relevant
            plug.unknown = reader.read_u32()
            plug.default_value = reader.read_s32()
        return plug
    
    def _as_dict(self) -> JSONType:
        if self._version > 0x404:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
                "Unknown" : self.unknown,
                "Default Value" : self.default_value,
            }
        else:
            return {
                "Node Index" : self.node_index,
                "Name" : self.name,
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "IntInputPlug":
        plug: IntInputPlug = cls()
        plug.node_index = data["Node Index"]
        plug.name = data["Name"]
        if "Unknown" in data:
            plug.unknown = data["Unknown"]
            plug.default_value = data["Default Value"]
            plug._version = 0x407
        return plug

class NodeFlag(int):
    """
    Node flags
    """

    def is_query(self) -> bool:
        return self & 1 != 0
    
    def is_module(self) -> bool:
        return self & 2 != 0
    
    def is_root_node(self) -> bool:
        return self & 4 != 0
    
    def is_multi_param_type2(self) -> bool:
        return self & 8 != 0
    
    def set_query(self, b: bool = True) -> "NodeFlag":
        return NodeFlag(self & 0xfe | int(b))
    
    def set_module(self, b: bool = True) -> "NodeFlag":
        return NodeFlag(self & 0xfd | int(b) << 1)

    def set_root_node(self, b: bool = True) -> "NodeFlag":
        return NodeFlag(self & 0xfb | int(b) << 2)

    def set_multi_param_type2(self, b: bool = True) -> "NodeFlag":
        return NodeFlag(self & 0xf7 | int(b) << 3)

    def _get_flag_list(self) -> typing.List[str]:
        out: typing.List[str] = []
        if self.is_query():
            out.append("Is Query")
        if self.is_module():
            out.append("Is Module")
        if self.is_root_node():
            out.append("Is Root Node")
        if self.is_multi_param_type2():
            out.append("Use MultiParam Type 2")
        return out
    
    @classmethod
    def _from_flag_list(cls, data: JSONType) -> "NodeFlag":
        flag: NodeFlag = cls()
        if "Is Query" in data:
            flag = flag.set_query()
        if "Is Module" in data:
            flag = flag.set_module()
        if "Is Root Node" in data:
            flag = flag.set_root_node()
        if "Use MultiParam Type 2" in data:
            flag = flag.set_multi_param_type2()
        return flag

class Node:
    """
    Class representing a single AI node
    """

    __slots__ = [
        "name", "type", "index", "flags", "queries", "attachments", "properties", "params", "actions", "guid", "state_info", "_plugs"
    ]

    def __init__(self, node_type: NodeType) -> None:
        self.name: str = ""
        self.type: NodeType = node_type
        self.index: int = -1
        self.flags: NodeFlag = NodeFlag()
        self.queries: typing.List[int] = []
        self.attachments: typing.List[Attachment] = []
        self.properties: PropertySet = PropertySet()
        self.params: ParamSet = ParamSet()
        self.actions: typing.List[Action] = []
        self.guid: str = "00000000-0000-0000-0000-000000000000"
        self.state_info: StateInfo | None = None
        self._plugs: typing.List[typing.List[Plug]] = [ # node "plugs" (connections between nodes)
            [], [], [], [], [], [], [], [], [], []
        ]
        
    @property
    def generic_plugs(self) -> typing.List[GenericPlug]:
        """
        Generic plugs used for inputs (bool/float) and outputs
        """
        return typing.cast(typing.List[GenericPlug], self._plugs[PlugType.Generic])
    
    @property
    def _01_plugs(self) -> typing.List[Plug]: # unused
        return self._plugs[PlugType._01]
    
    @property
    def child_plugs(self) -> typing.List[ChildPlug]:
        """
        Plugs used for control flow
        """
        return typing.cast(typing.List[ChildPlug], self._plugs[PlugType.Child])
    
    @property
    def transition_plugs(self) -> typing.List[TransitionPlug]:
        """
        Transition plugs
        """
        return typing.cast(typing.List[TransitionPlug], self._plugs[PlugType.Transition])
    
    @property
    def string_plugs(self) -> typing.List[StringInputPlug]:
        """
        String input plugs
        """
        return typing.cast(typing.List[StringInputPlug], self._plugs[PlugType.String])
    
    @property
    def int_plugs(self) -> typing.List[IntInputPlug]:
        """
        Int input plugs
        """
        return typing.cast(typing.List[IntInputPlug], self._plugs[PlugType.Int])
    
    @property
    def _06_plugs(self) -> typing.List[Plug]: # unused
        return self._plugs[PlugType._06]
    
    @property
    def _07_plugs(self) -> typing.List[Plug]: # unused
        return self._plugs[PlugType._07]
    
    @property
    def _08_plugs(self) -> typing.List[Plug]: # unused
        return self._plugs[PlugType._08]
    
    @property
    def _09_plugs(self) -> typing.List[Plug]: # unused
        return self._plugs[PlugType._09]
    
    def get_plugs(self, plug_type: PlugType) -> typing.List[Plug]:
        return self._plugs[plug_type]
    
    def has_inputs(self) -> bool:
        return self.params.has_inputs()
    
    def has_outputs(self) -> bool:
        return self.params.has_outputs()

    @classmethod
    def _read(cls,
        reader: AINBReader,
        attachments: typing.List[Attachment],
        attachment_indices: typing.List[int],
        properties: PropertySet,
        io_params: ParamSet,
        transitions: typing.List[Transition],
        queries: typing.List[int],
        actions: typing.Dict[int, typing.List[Action]],
        modules: typing.List[Module], # not needed for parsing, just to raise a warning if there is a missing module,
        index: int # not needed for parsing, just to raise a warning if a node's index doesn't match its actual index
    ) -> "Node":
        node: Node = cls(NodeType(reader.read_u16()))
        node.index = reader.read_s16()
        if node.index != index:
            ParseWarning(reader, f"Node claims it is index {node.index} when it is index {index}")
        attachment_count: int = reader.read_u16()
        node.flags = NodeFlag(reader.read_u8())
        _ = reader.read_u8() # padding
        node.name = reader.read_string_offset()
        if node.flags.is_module():
            if f"{node.name}.ainb" not in [module.path for module in modules]:
                ParseWarning(reader, f"Node {node.index} is a module ({node.name}) but corresponding module does not exist in file")
        if reader.version >= 0x407:
            name_hash: int = reader.read_u32() # murmur3 hash of node name
        unk1: int = reader.read_u32()
        node_param_offset: int = reader.read_u32()
        expression_count: int = reader.read_u16()       # number of expressions used by this node
        expression_io_mem_size: int = reader.read_u16() # size of the input/output memory reserved for expressions
        multi_param_count: int = reader.read_u16()      # number of multi-params used by this node
        _ = reader.read_u16() # padding
        base_attachment_index: int = reader.read_u32()
        base_query_index: int = reader.read_u16()
        query_count: int = reader.read_u16()
        # offset into some unknown section, used in splatoon 3
        # struct { u32 str_pool_offset, _04, _08, _0c, _10; };
        state_info_offset: int = reader.read_u32()
        if reader.version < 0x407:
            with reader.temp_seek(state_info_offset):
                node.state_info = StateInfo(
                    reader.read_string_offset(),
                    reader.read_u32(),
                    reader.read_u32(),
                    reader.read_u32(),
                    reader.read_u32(),
                )
        elif state_info_offset != 0:
            ParseWarning(reader, f"Non-zero state info offset in file version that does not support node state info: {state_info_offset}")
        node.guid = reader.read_guid()

        node.queries = queries[base_query_index:base_query_index+query_count] # stored as an index into an array of all query nodes, converted later
        node.attachments = [attachments[i] for i in attachment_indices[base_attachment_index:base_attachment_index+attachment_count]]

        # node parameters + plugs
        with reader.temp_seek(node_param_offset):
            for p_type in ParamType:
                base_index: int = reader.read_u32()
                count: int = reader.read_u32()
                node.properties._properties[p_type] = properties.get_properties(p_type)[base_index:base_index+count]
            
            for p_type in ParamType:
                base_input_index: int = reader.read_u32()
                input_count: int = reader.read_u32()
                node.params._inputs[p_type] = io_params.get_inputs(p_type)[base_input_index:base_input_index+input_count]

                base_output_index: int = reader.read_u32()
                output_count: int = reader.read_u32()
                node.params._outputs[p_type] = io_params.get_outputs(p_type)[base_output_index:base_output_index+output_count]
            
            plug_info: typing.List[PlugInfo] = [
                PlugInfo(reader.read_u8(), reader.read_u8()) for plug_type in PlugType
            ]
            base_offset: int = reader.tell()

            for plug_type in PlugType:
                with reader.temp_seek(base_offset + plug_info[plug_type].base_index * 4):
                    offsets: typing.List[int] = [
                        reader.read_u32() for i in range(plug_info[plug_type].plug_count)
                    ]
                    node._plugs[plug_type] = [
                        node._read_plug(reader, offset, plug_type, i == len(offsets) - 1, transitions) for i, offset in enumerate(offsets)
                    ]

        node.actions = actions.get(node.index, [])

        return node
    
    def _read_plug(self, reader: AINBReader, offset: int, plug_type: PlugType, is_last: bool, trans_info_list: typing.List[Transition]) -> Plug:
        reader.seek(offset)
        if plug_type == PlugType.Generic:
            return GenericPlug._read(reader)
        elif plug_type == PlugType.Child:
            if self.type == NodeType.Element_S32Selector:
                return S32SelectorPlug._read(reader, is_last)
            elif self.type == NodeType.Element_F32Selector:
                return F32SelectorPlug._read(reader, is_last)
            elif self.type == NodeType.Element_StringSelector:
                return StringSelectorPlug._read(reader, is_last)
            elif self.type == NodeType.Element_RandomSelector:
                return RandomSelectorPlug._read(reader)
            elif self.name == "SelectorBSABrainVerbUpdater" or self.name == "SelectorBSAFormChangeUpdater":
                return BSASelectorUpdaterPlug._read(reader)
            else:
                return ChildPlug._read(reader)
        elif plug_type == PlugType.Transition:
            return TransitionPlug._read(reader, trans_info_list)
        elif plug_type == PlugType.String:
            return StringInputPlug._read(reader)
        elif plug_type == PlugType.Int:
            return IntInputPlug._read(reader)
        else:
            raise ParseError(reader, f"Unsupported plug type: {plug_type}")
    
    def _as_dict(self) -> JSONType:
        if self.state_info is not None:
            return {
                "Node Type" : self.type.name,
                "Node Index" : self.index,
                "Name" : self.name,
                "GUID" : self.guid,
                "Flags" : self.flags._get_flag_list(),
                "Queries" : self.queries,
                "Attachments" : [ attachment._as_dict() for attachment in self.attachments ],
                "Properties" : self.properties._as_dict(),
                "Parameters" : self.params._as_dict(),
                "XLink Actions" : [ action._as_dict() for action in self.actions ],
                "State Info" : self.state_info._as_dict(),
                "Plugs" : {
                    plug_type.name : [ plug._as_dict() for plug in self.get_plugs(plug_type) ] for plug_type in PlugType if self.get_plugs(plug_type)
                },
            }
        else:
            return {
                "Node Type" : self.type.name,
                "Node Index" : self.index,
                "Name" : self.name,
                "GUID" : self.guid,
                "Flags" : self.flags._get_flag_list(),
                "Queries" : self.queries,
                "Attachments" : [ attachment._as_dict() for attachment in self.attachments ],
                "Properties" : self.properties._as_dict(),
                "Parameters" : self.params._as_dict(),
                "XLink Actions" : [ action._as_dict() for action in self.actions ],
                "Plugs" : {
                    plug_type.name : [ plug._as_dict() for plug in self.get_plugs(plug_type) ] for plug_type in PlugType if self.get_plugs(plug_type)
                },
            }

    def _read_plug_from_dict(self, data: JSONType, plug_type: PlugType) -> Plug:
        if plug_type == PlugType.Generic:
            return GenericPlug._from_dict(data)
        elif plug_type == PlugType.Child:
            if self.type == NodeType.Element_S32Selector:
                return S32SelectorPlug._from_dict(data)
            elif self.type == NodeType.Element_F32Selector:
                return F32SelectorPlug._from_dict(data)
            elif self.type == NodeType.Element_StringSelector:
                return StringSelectorPlug._from_dict(data)
            elif self.type == NodeType.Element_RandomSelector:
                return RandomSelectorPlug._from_dict(data)
            elif self.name == "SelectorBSABrainVerbUpdater" or self.name == "SelectorBSAFormChangeUpdater":
                return BSASelectorUpdaterPlug._from_dict(data)
            else:
                return ChildPlug._from_dict(data)
        elif plug_type == PlugType.Transition:
            return TransitionPlug._from_dict(data)
        elif plug_type == PlugType.String:
            return StringInputPlug._from_dict(data)
        elif plug_type == PlugType.Int:
            return IntInputPlug._from_dict(data)
        else:
            raise DictDecodeError(f"Unsupported plug type: {plug_type}")

    @classmethod
    def _from_dict(cls, data: JSONType, index: int) -> "Node":
        node: Node = cls(NodeType[data["Node Type"]])
        node.index = data["Node Index"]
        if node.index != index:
            raise DictDecodeError(f"Node index {index} claims it has index {node.index}")
        node.name = data["Name"]
        node.guid = data["GUID"]
        node.flags = NodeFlag._from_flag_list(data["Flags"])
        node.queries = data["Queries"]
        node.attachments = [
            Attachment._from_dict(attachment) for attachment in data["Attachments"]
        ]
        node.properties = PropertySet._from_dict(data["Properties"])
        node.params = ParamSet._from_dict(data["Parameters"])
        node.actions = [
            Action._from_dict(action) for action in data["XLink Actions"]
        ]
        for plug_type in PlugType:
            if plug_type.name not in data["Plugs"]:
                continue
            node._plugs[plug_type] = [
                node._read_plug_from_dict(plug, plug_type) for plug in data["Plugs"][plug_type.name]
            ]
        if "State Info" in data:
            node.state_info = StateInfo._from_dict(data["State Info"])
        return node