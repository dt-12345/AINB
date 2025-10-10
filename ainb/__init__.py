"""
AINB Utilities
"""

# TODO: clean up public-facing API, proper editing support?

__version__: str = "0.2.8"

from ainb.action import Action as Action
from ainb.ainb import (
    get_supported_versions as get_supported_versions,
    AINB as AINB,
    set_nintendo_switch_sports as set_nintendo_switch_sports,
    set_splatoon3 as set_splatoon3,
    set_tears_of_the_kingdom as set_tears_of_the_kingdom,
    set_super_mario_bros_wonder as set_super_mario_bros_wonder,
)
from ainb.attachment import Attachment as Attachment
from ainb.blackboard import (
    BBParamType as BBParamType,
    BBParam as BBParam,
    Blackboard as Blackboard,
)
from ainb.command import Command as Command
from ainb.common import (
    AINBReader as AINBReader,
    AINBWriter as AINBWriter,
)
from ainb.module import Module as Module
from ainb.node import (
    get_null_index as get_null_index,
    NodeType as NodeType,
    PlugType as PlugType,
    GenericPlug as GenericPlug,
    BoolSelectorInputPlug as BoolSelectorInputPlug,
    F32SelectorInputPlug as F32SelectorInputPlug,
    ChildPlug as ChildPlug,
    S32SelectorPlug as S32SelectorPlug,
    F32SelectorPlug as F32SelectorPlug,
    StringSelectorPlug as StringSelectorPlug,
    RandomSelectorPlug as RandomSelectorPlug,
    BSASelectorUpdaterPlug as BSASelectorUpdaterPlug,
    TransitionPlug as TransitionPlug,
    StringSelectorInputPlug as StringSelectorInputPlug,
    S32SelectorInputPlug as S32SelectorInputPlug,
    NodeFlag as NodeFlag,
    Node as Node,
)
from ainb.param_common import (
    ParamType as ParamType,
    VectorComponent as VectorComponent,
    ParamFlag as ParamFlag,
)
from ainb.param import (
    ParamSource as ParamSource,
    InputParam as InputParam,
    OutputParam as OutputParam,
    ParamSet as ParamSet,
)
from ainb.property import (
    Property as Property,
    PropertySet as PropertySet,
)
from ainb.replacement import (
    ReplacementType as ReplacementType,
    ReplacementEntry as ReplacementEntry,
)
from ainb.state import StateInfo as StateInfo
from ainb.transition import Transition as Transition
from ainb.utils import (
    Reader as Reader,
    ReaderWithStrPool as ReaderWithStrPool,
    Vector3f as Vector3f,
    Writer as Writer,
    WriterWithStrPool as WriterWithStrPool,
    ParseError as ParseError,
    SerializeError as SerializeError,
    DictDecodeError as DictDecodeError,
)