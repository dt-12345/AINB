import typing

from ainb.attachment import Attachment
from ainb.expression.write_context import ExpressionWriteContext
from ainb.param import ParamSet, ParamSource
from ainb.property import PropertySet
from ainb.state import StateInfo
from ainb.transition import Transition

class WriteContext:
    def __init__(self) -> None:
        self.command_count: int = 0
        self.node_count: int = 0
        self.query_count: int = 0
        self.attachment_count: int = 0
        self.output_count: int = 0
        self.blackboard_offset: int = 0
        self.string_pool_offset: int = 0
        self.enum_resolve_offset: int = 0
        self.property_offset: int = 0
        self.transition_offset: int = 0
        self.io_param_offset: int = 0
        self.multi_param_offset: int = 0
        self.attachment_offset: int = 0
        self.attachment_index_offset: int = 0
        self.expression_offset: int = 0
        self.replacement_table_offset: int = 0
        self.query_offset: int = 0
        self.x50_offset: int = 0
        self.x54_value: int = 0
        self.x58_offset: int = 0
        self.module_offset: int = 0
        self.action_offset: int = 0
        self.x6c_offset: int = 0
        self.bb_id_offset: int = 0

        self.version: int = 0

        self.expression_ctx: ExpressionWriteContext = ExpressionWriteContext()

        self.attachments: typing.List[Attachment] = []
        self.attachment_indices: typing.List[int] = []
        self.multi_params: typing.List[ParamSource] = []
        self.actions: typing.List[typing.Tuple[int, str, str]] = []
        self.curr_attachment_index: int = 0
        self.base_attachment_indices: typing.List[int] = []
        self.attachment_expression_counts: typing.List[int] = []
        self.attachment_expression_sizes: typing.List[int] = []
        self.attachment_prop_offset: int = 0
        self.attachment_prop_offsets: typing.List[int] = []
        self.curr_query_index: int = 0
        self.queries: typing.List[int] = []
        self.query_base_indices: typing.List[int] = []
        self.query_map: typing.Dict[int, int] = {}
        self.node_expression_counts: typing.List[int] = []
        self.node_expression_sizes: typing.List[int] = []
        self.multi_param_counts: typing.List[int] = []

        self.curr_node_param_offset: int = 0
        self.node_param_offsets: typing.List[int] = []

        self.node_state_offsets: typing.List[int] = []
        self.state_info: typing.List[StateInfo] = []

        self.transitions: typing.List[Transition] = []

        self.props: PropertySet = PropertySet()
        self.params: ParamSet = ParamSet()

        self.prop_indices: typing.List[int] = [0, 0, 0, 0, 0, 0]
        self.input_indices: typing.List[int] = [0, 0, 0, 0, 0, 0]
        self.output_indices: typing.List[int] = [0, 0, 0, 0, 0, 0]

        self.expression_binary: bytes = b""