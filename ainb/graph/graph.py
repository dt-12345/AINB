import os
import typing

import graphviz # type: ignore

from ainb.ainb import AINB
from ainb.blackboard import BBParamType, BBParam
from ainb.command import Command
from ainb.expression import InstDataType
from ainb.node import Node, NodeType, S32SelectorPlug, F32SelectorPlug, StringSelectorPlug, RandomSelectorPlug, get_null_index
from ainb.param import InputParam, OutputParam, ParamSource
from ainb.param_common import ParamType
from ainb.property import Property
from ainb.utils import WarningBase

# TODO: (probably not) expression control flow graph?
# TODO: root node colored differently? unsure if that's desirable
# TODO: state end colored differently? edge between state end and next state if possible?
# TODO: different colors for module input/outputs/children?

COLOR_MAP: typing.Dict[str, str] = {
    "graph-bg" : "lightgray",
    "node-font" : "black",
    "blackboard-font" : "black",
    "query-edge" : "webgreen",
    "query-edge-font" : "webgreen",
    "generic-edge" : "firebrick",
    "generic-edge-font" : "firebrick",
    "transition-edge" : "midnightblue",
    "transition-edge-font" : "midnightblue",
    "blackboard-edge" : "webgreen",
    "blackboard-edge-font" : "webgreen",
    "entry-point-bg" : "mediumpurple",
    "entry-point-font" : "white",
}

EXPRESSION_TYPE_MAP: typing.Dict[InstDataType, ParamType] = {
    InstDataType.BOOL       : ParamType.Bool,
    InstDataType.INT        : ParamType.Int,
    InstDataType.FLOAT      : ParamType.Float,
    InstDataType.STRING     : ParamType.String,
    InstDataType.VECTOR3F   : ParamType.Vector3F,
}

BLACKBOARD_TYPE_MAP: typing.Dict[ParamType, BBParamType] = {
    ParamType.Bool          : BBParamType.Bool,
    ParamType.Int           : BBParamType.S32,
    ParamType.Float         : BBParamType.F32,
    ParamType.String        : BBParamType.String,
    ParamType.Vector3F      : BBParamType.Vec3f,
    ParamType.Pointer       : BBParamType.VoidPtr,
}

ID_ITER: int = 0
def get_id() -> str:
    global ID_ITER
    id: int = ID_ITER
    ID_ITER += 1
    return str(id)

T = typing.TypeVar("T")

def escape_value(value: T | str) -> T | str:
    if isinstance(value, str):
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;")
    else:
        return value

class GraphError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(f"Graphing error: {msg}")

class GraphWarning(WarningBase):
    def __init__(self, msg: str) -> None:
        super().__init__(f"Graphing warning: {msg}")

class ParamLocation(typing.NamedTuple):
    param_type: ParamType
    param_index: int

class InputEdge(typing.NamedTuple):
    src_node_index: int
    src_param: ParamLocation
    dst_node_index: int
    dst_param: ParamLocation
    param_name: str

class GenericEdge(typing.NamedTuple):
    node_index0: int
    node_index1: int
    edge_name: str

class TransitionEdge(typing.NamedTuple):
    src_node_index: int
    dst_node_index: int
    edge_name: str = ""

class BlackboardLocation(typing.NamedTuple):
    param_type: BBParamType
    param_index: int

class BlackboardEdge(typing.NamedTuple):
    src_param: BlackboardLocation
    dst_node_index: int
    dst_param: ParamLocation
    param_name: str

class GraphNode:
    """
    Class representing a single AINB node as a node in a graph
    """
    def __init__(self, node: Node) -> None:
        self._node: Node = node
        self.input_id: str = get_id()
        self.output_id: str = get_id()
        self.input_map: typing.Dict[ParamLocation, str] = {}
        self.output_map: typing.Dict[ParamLocation, str] = {}
        self.id: str = get_id()

    @staticmethod
    def _format_input(id: str, param_type: ParamType, param: InputParam) -> str:
        if param_type == ParamType.Pointer:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.classname}*] {param.name} (default = nullptr) </td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param_type.name}] {param.name} (default = {escape_value(param.default_value)}) </td>"
                    </tr>
                    """
        
    @staticmethod
    def _format_output(id: str, param_type: ParamType, param: OutputParam) -> str:
        if param_type == ParamType.Pointer:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.classname}*] {param.name} (default = nullptr) </td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param_type.name}] {param.name}</td>"
                    </tr>
                    """
    
    @staticmethod
    def _format_property(param_type: ParamType, prop: Property) -> str:
        if param_type == ParamType.Pointer:
            return f"""
                    <tr>
                        <td>[{prop.classname}*] {prop.name} (default = nullptr) </td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td>[{param_type.name}] {prop.name} (default = {escape_value(prop.default_value)}) </td>"
                    </tr>
                    """
    
    def _get_name(self) -> str:
        if self._node.type == NodeType.UserDefined:
            return f"{self._node.name} ({self._node.index})"
        return f"{self._node.type.name} ({self._node.index})"

    def _add_input(self, index: int, param_type: ParamType, param: InputParam) -> str:
        id: str = get_id()
        self.input_map[ParamLocation(param_type, index)] = id
        return self._format_input(id, param_type, param)

    def _add_output(self, index: int, param_type: ParamType, param: OutputParam) -> str:
        id: str = get_id()
        self.output_map[ParamLocation(param_type, index)] = id
        return self._format_output(id, param_type, param)

    def _format_property_table(self) -> str:
        if self._node.properties:
            return f"""
                    <tr>
                        <td><b>Properties</b></td>
                    </tr>
                    {'\n'.join(self._format_property(p_type, prop) for p_type in ParamType for i, prop in enumerate(self._node.properties.get_properties(p_type)))}"""
        return ""

    def _format_input_table(self) -> str:
        if self._node.has_inputs():
            return f"""
                    <tr>
                        <td><b>Inputs</b></td>
                    </tr>
                    {'\n'.join(self._add_input(i, p_type, param) for p_type in ParamType for i, param in enumerate(self._node.params.get_inputs(p_type)))}"""
        return ""

    def _format_output_table(self) -> str:
        if self._node.has_outputs():
            return f"""
                    <tr>
                        <td><b>Outputs</b></td>
                    </tr>
                    {'\n'.join(self._add_output(i, p_type, param) for p_type in ParamType for i, param in enumerate(self._node.params.get_outputs(p_type)))}
                    """
        return ""

    def _format_expected_state(self) -> str:
        if self._node.state_info is not None and self._node.state_info.desired_state != "":
            return f"""
                    <tr>
                        <td>Expects: {self._node.state_info.desired_state} </td>
                    </tr>
                    """
        return ""

    def _add_to_graph(self, dot: graphviz.Digraph) -> None:
        if self._node.type == NodeType.Element_Sequential:
            dot.node(
                name=self.id,
                label=f"""<
                        <table border="1" cellborder="1" cellspacing="0">
                            <tr>
                                <td><b>{self._get_name()}</b></td>
                            </tr>
                            {self._format_expected_state()}
                            {self._format_property_table()}
                            {self._format_input_table()}
                            {self._format_output_table()}
                        </table>
                    >""",
                style="bold",
                fontcolor=COLOR_MAP["node-font"],
                ordering="out",
            )
        else:
            dot.node(
            name=self.id,
            label=f"""<
                    <table border="1" cellborder="1" cellspacing="0">
                        <tr>
                            <td><b>{self._get_name()}</b></td>
                        </tr>
                        {self._format_property_table()}
                        {self._format_input_table()}
                        {self._format_output_table()}
                    </table>
                >""",
            style="bold",
            fontcolor=COLOR_MAP["node-font"],
        )
class Graph:
    """
    Class representing a node graph
    """
    def __init__(self, ainb: AINB) -> None:
        self.ainb: AINB = ainb
        self.nodes: typing.Dict[int, GraphNode] = {}
        self.input_edges: typing.Set[InputEdge] = set()
        self.generic_edges: typing.Set[GenericEdge] = set()
        self.transition_edges: typing.Set[TransitionEdge] = set()
        self.root_index: int = -1
        self.root_name: str = ""
        self.blackboard_id: str = ""
        self.bb_param_ids: typing.Dict[BlackboardLocation, str] = {}
        self.bb_edges: typing.Set[BlackboardEdge] = set()

        # always add module output nodes
        for node in self.ainb.nodes:
            if node.type.value >= 200 and node.type.value < 300:
                self.add_node(node)
    
    @staticmethod
    def _format_bb_param(id: str, param: BBParam) -> str:
        if param.file_ref != "":
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.type.name}] {param.name} (source = {escape_value(param.file_ref)}) </td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.type.name}] {param.name} (default = {escape_value(param.default_value)}) </td>"
                    </tr>
                    """

    def _add_bb_param(self, index: int, param: BBParam) -> str:
        id: str = get_id()
        self.bb_param_ids[BlackboardLocation(param.type, index)] = id
        return self._format_bb_param(id, param)

    def _format_blackboard(self) -> str:
        if self.ainb.blackboard is None:
            return ""
        return f"""
                <tr>
                    <td><b>Properties</b></td>
                </tr>
                {'\n'.join(self._add_bb_param(i, param) for p_type in BBParamType for i, param in enumerate(self.ainb.blackboard.get_params(p_type)))}"""

    def _add_blackboard(self, dot: graphviz.Digraph, split_bb: bool = False) -> None:
        if self.ainb.blackboard is None:
            return
        if len(self.bb_edges) == 0:
            return
        self.blackboard_id = get_id()
        if not split_bb:
            dot.node(
                name=self.blackboard_id,
                label=f"""<
                        <table border="0" cellborder="1" cellspacing="0">
                            <tr>
                                <td><b>Blackboard</b></td>
                            </tr>
                            {self._format_blackboard()}
                        </table>
                    >""",
                style="bold",
                fontcolor=COLOR_MAP["blackboard-font"],
            )
        else:
            for edge in self.bb_edges:
                if edge.src_param in self.bb_param_ids:
                    continue
                param: BBParam = self.ainb.blackboard.get_params(edge.src_param.param_type)[edge.src_param.param_index]
                id: str = get_id()
                self.bb_param_ids[edge.src_param] = id
                dot.node(
                    name=id,
                    label=f"[BB {param.type.name}] {param.name}\n(source = {param.file_ref}) " if param.file_ref else f"[BB {param.type.name}] {param.name}\n(default = {param.default_value}) ",
                    style="bold",
                    fontcolor=COLOR_MAP["blackboard-font"],
                )

    def _add_input_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.input_edges:
            try:
                src_node: GraphNode = self.nodes[edge.src_node_index]
                dst_node: GraphNode = self.nodes[edge.dst_node_index]
                src_id: str = f"{src_node.id}:{src_node.output_map[edge.src_param]}"
                dst_id: str = f"{dst_node.id}:{dst_node.input_map[edge.dst_param]}"
                dot.edge(src_id, dst_id, edge.param_name, minlen="1", style="dashed", color=COLOR_MAP["query-edge"], fontcolor=COLOR_MAP["query-edge-font"])
            except Exception as e:
                raise GraphError(f"Could not resolve edge: {edge}") from e
    
    def _add_generic_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.generic_edges:
            node0: GraphNode = self.nodes[edge.node_index0]
            node1: GraphNode = self.nodes[edge.node_index1]
            dot.edge(node0.id, node1.id, edge.edge_name, minlen="1", style="bold", color=COLOR_MAP["generic-edge"], fontcolor=COLOR_MAP["generic-edge-font"])
    
    def _add_transition_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.transition_edges:
            src_node: GraphNode = self.nodes[edge.src_node_index]
            dst_node: GraphNode = self.nodes[edge.dst_node_index]
            if edge.edge_name != "":
                dot.edge(src_node.id, dst_node.id, edge.edge_name, minlen="1", style="bold", color=COLOR_MAP["transition-edge"], fontcolor=COLOR_MAP["transition-edge-font"])
            else:
                dot.edge(src_node.id, dst_node.id, "Transition", minlen="1", style="bold", color=COLOR_MAP["transition-edge"], fontcolor=COLOR_MAP["transition-edge-font"])

    def _add_bb_edges(self, dot: graphviz.Digraph, split_bb: bool = False) -> None:
        dst_node: GraphNode
        src_id: str
        dst_id: str
        if not split_bb:
            for edge in self.bb_edges:
                dst_node = self.nodes[edge.dst_node_index]
                src_id = f"{self.blackboard_id}:{self.bb_param_ids[edge.src_param]}"
                dst_id = f"{dst_node.id}:{dst_node.input_map[edge.dst_param]}"
                dot.edge(src_id, dst_id, edge.param_name, minlen="1", style="dashed", color=COLOR_MAP["blackboard-edge"], fontcolor=COLOR_MAP["blackboard-edge-font"])
        else:
            for edge in self.bb_edges:
                dst_node = self.nodes[edge.dst_node_index]
                src_id = self.bb_param_ids[edge.src_param]
                dst_id = f"{dst_node.id}:{dst_node.input_map[edge.dst_param]}"
                dot.edge(src_id, dst_id, edge.param_name, minlen="1", style="dashed", color=COLOR_MAP["blackboard-edge"], fontcolor=COLOR_MAP["blackboard-edge-font"])

    def graph(self, dot: graphviz.Digraph, split_blackboard: bool = False) -> graphviz.Digraph:
        """
        Generate a graph onto the provided digraph
        """
        self._add_blackboard(dot, split_blackboard)
        for node in self.nodes.values():
            node._add_to_graph(dot)
        self._add_input_edges(dot)
        self._add_generic_edges(dot)
        self._add_transition_edges(dot)
        self._add_bb_edges(dot, split_blackboard)
        if self.root_index != -1:
            root_node: GraphNode = self.nodes[self.root_index]
            root_id: str = get_id()
            dot.node(name=root_id, label=f"<<b>{self.root_name}</b>>", color=COLOR_MAP["entry-point-bg"], fontcolor=COLOR_MAP["entry-point-font"], shape="ellipse", style="filled")
            dot.edge(root_id, root_node.id)
    
    def _process_param_source(self, node: Node, param_type: ParamType, param_index: int, param: InputParam, source: ParamSource) -> None:
        if isinstance(source, list):
            raise GraphError("Cannot have nested multi-params")
        if source.src_node_index != -1:
            if source.src_node_index not in self.nodes:
                self.add_node(self.ainb.nodes[source.src_node_index]) # sometimes this is necessary if the source node isn't a query for this node
            if source.is_expression():
                if self.ainb.expressions is None:
                    raise GraphError(f"Node {node.index} requests an expression but file {self.ainb.filename} has no expression section")
                # expressions are capable of transforming an output parameter from another node of a different datatype into the correct datatype
                self.input_edges.add(
                    InputEdge(
                        source.src_node_index,
                        ParamLocation(
                            EXPRESSION_TYPE_MAP[self.ainb.expressions.expressions[source.flags.get_index()].input_datatype], source.src_output_index & 0x7fff
                        ),
                        node.index,
                        ParamLocation(param_type, param_index),
                        f"{param.name} (EXPRESSION)",
                    )
                )
            else:
                self.input_edges.add(
                    InputEdge(
                        source.src_node_index,
                        ParamLocation(param_type, source.src_output_index & 0x7fff),
                        node.index,
                        ParamLocation(param_type, param_index),
                        param.name,
                    )
                )
        elif source.is_blackboard():
            self.bb_edges.add(
                BlackboardEdge(
                    BlackboardLocation(BLACKBOARD_TYPE_MAP[param_type], source.flags.get_index()),
                    node.index,
                    ParamLocation(param_type, param_index),
                    f"{param.name} (BLACKBOARD)",
                )
            )

    def add_node(self, node: Node, is_root: bool = False, root_name: str = "Entry Point") -> None:
        """
        Add an AINB node to the graph
        """
        if is_root:
            self.root_index = node.index
            self.root_name = root_name
        if node.index in self.nodes:
            return
        self.nodes[node.index] = GraphNode(node)
        for query in node.queries:
            query_node: Node | None = self.ainb.get_node(query)
            if query_node is None:
                raise GraphError(f"Node index {node.index} has query with index {query} which does not exist")
            self.add_node(query_node)
        for p_type in ParamType:
            for i, param in enumerate(node.params.get_inputs(p_type)):
                if isinstance(param.source, list):
                    for source in param.source:
                        self._process_param_source(node, p_type, i, param, source)
                else:
                    self._process_param_source(node, p_type, i, param, param.source)
        for plug in node.child_plugs:
            if plug.node_index == get_null_index():
                continue
            if node.type == NodeType.Element_S32Selector:
                s32_plug: S32SelectorPlug = typing.cast(S32SelectorPlug, plug)
                self.generic_edges.add(
                    GenericEdge(node.index, s32_plug.node_index, f"Default" if s32_plug.is_default else str(s32_plug.condition))
                )
            elif node.type == NodeType.Element_F32Selector:
                f32_plug: F32SelectorPlug = typing.cast(F32SelectorPlug, plug)
                self.generic_edges.add(
                    GenericEdge(node.index, f32_plug.node_index, "Default" if f32_plug.is_default else f"Min: {f32_plug.condition_min}, Max: {f32_plug.condition_max}")
                )
            elif node.type == NodeType.Element_StringSelector:
                str_plug: StringSelectorPlug = typing.cast(StringSelectorPlug, plug)
                self.generic_edges.add(
                    GenericEdge(node.index, str_plug.node_index, "Default" if str_plug.is_default else str_plug.condition)
                )
            elif node.type == NodeType.Element_RandomSelector:
                rand_plug: RandomSelectorPlug = typing.cast(RandomSelectorPlug, plug)
                self.generic_edges.add(
                    GenericEdge(node.index, rand_plug.node_index, str(rand_plug.weight))
                )
            else:
                self.generic_edges.add(
                    GenericEdge(node.index, plug.node_index, plug.name)
                )
            child_node: Node | None = self.ainb.get_node(plug.node_index)
            if child_node is None:
                raise GraphError(f"Node index {node.index} has child with index {plug.node_index} which does not exist")
            self.add_node(child_node)
        for transition in node.transition_plugs:
            if transition.transition.transition_type == 0:
                self.transition_edges.add(
                    TransitionEdge(node.index, transition.node_index, transition.transition.command_name)
                )
            else:
                self.transition_edges.add(
                    TransitionEdge(node.index, transition.node_index)
                )
            target_node: Node | None = self.ainb.get_node(transition.node_index)
            if target_node is None:
                raise GraphError(f"Node index {node.index} has transition target with index {transition.node_index} which does not exist")
            self.add_node(target_node)

def render_graph(graph: graphviz.Digraph, name: str, output_format: str = "svg", output_dir: str = "", view: bool = False, unflatten: bool = True, stagger: int = 1) -> None:
    if output_dir != "":
        os.makedirs(output_dir, exist_ok=True)
    if unflatten:
        src: graphviz.Source = graph.unflatten(stagger=stagger)
        src.format = output_format
        src.render(filename=name, directory=output_dir, view=view)
    else:
        graph.format = output_format
        graph.render(filename=name, directory=output_dir, view=view)

def graph_from_node(ainb: AINB,
                    node_index: int,
                    render: bool = True,
                    output_format: str = "svg",
                    output_dir: str = "",
                    view: bool = False,
                    unflatten: bool = True,
                    stagger: int = 1,
                    dpi: float = 96.0,
                    node_sep: float = 0.25,
                    line_type: str = "true",
                    split_blackboard: bool = False) -> graphviz.Digraph:
    """
    Graph an AINB file starting from the specified node

    Args:
        ainb: Input AINB object
        node_index: Index of the node to start graphing from
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        unflatten: Unflatten graph
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
        dpi: Pixels per inch for output image (does not affect SVG)
        node_sep: Node separation
        line_type: Edge line type
        split_blackboard: Split Blackboard into separate nodes
    """
    node: Node | None = ainb.get_node(node_index)
    if node is None:
        raise GraphError(f"File {ainb.filename} has no node index {node_index}")
    graph: Graph = Graph(ainb)
    graph.add_node(node, is_root=True)

    name: str = f"{node.name} ({node.index})" if node.type == NodeType.UserDefined else f"{node.type.name} ({node.index})"

    dot: graphviz.Digraph = graphviz.Digraph(name, node_attr={"shape" : "rectangle"})
    dot.attr(node_sep=str(node_sep), bgcolor=COLOR_MAP["graph-bg"], spline=line_type)
    if output_format != "svg":
        dot.attr(dpi=str(dpi))
    graph.graph(dot, split_blackboard)

    if render:
        render_graph(dot, name, output_format, output_dir, view, unflatten, stagger)

    return dot

def graph_command(ainb: AINB,
                  cmd_name: str,
                  render: bool = True,
                  output_format: str = "svg",
                  output_dir: str = "",
                  view: bool = False,
                  unflatten: bool = True,
                  stagger: int = 1,
                  dpi: float = 96.0,
                  node_sep: float = 0.25,
                  line_type: str = "true",
                  split_blackboard: bool = False) -> graphviz.Digraph:
    """
    Graph a command from the provided AINB file

    Args:
        ainb: Input AINB object
        cmd_name: Name of command to graph
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        unflatten: Unflatten graph
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
        dpi: Pixels per inch for output image (does not affect SVG)
        node_sep: Node separation
        line_type: Edge line type
        split_blackboard: Split Blackboard into separate nodes
    """
    cmd: Command | None = ainb.get_command_by_name(cmd_name)
    if cmd is None:
        raise GraphError(f"Command {cmd_name} not found in {ainb.filename}")
    root_node: Node | None = ainb.get_node(cmd.root_node_index)
    if root_node is None:
        raise GraphError(f"Command {cmd_name} has an invalid root node index: {cmd.root_node_index}")
    graph: Graph = Graph(ainb)
    graph.add_node(root_node, is_root=True, root_name=cmd_name)

    dot: graphviz.Digraph = graphviz.Digraph(cmd.name, node_attr={"shape" : "rectangle"})
    dot.attr(node_sep=str(node_sep), bgcolor=COLOR_MAP["graph-bg"], spline=line_type)
    if output_format != "svg":
        dot.attr(dpi=str(dpi))
    graph.graph(dot, split_blackboard)

    if render:
        render_graph(dot, cmd_name, output_format, output_dir, view, unflatten, stagger)

    return dot

def graph_all_nodes(ainb: AINB,
                    render: bool = True,
                    output_format: str = "svg",
                    output_dir: str = "",
                    view: bool = False,
                    unflatten: bool = True,
                    stagger: int = 1,
                    dpi: float = 96.0,
                    node_sep: float = 0.25,
                    line_type: str = "true",
                    split_blackboard: bool = False) -> graphviz.Digraph:
    """
    Graph all nodes in the provided AINB file (this is mostly useful for logic files which have no commands)

    Args:
        ainb: Input AINB object
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        unflatten: Unflatten graph
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
        dpi: Pixels per inch for output image (does not affect SVG)
        node_sep: Node separation
        line_type: Edge line type
        split_blackboard: Split Blackboard into separate nodes
    """
    
    graph: Graph = Graph(ainb)
    for node in ainb.nodes:
        graph.add_node(node)
    
    dot: graphviz.Digraph = graphviz.Digraph(ainb.filename, node_attr={"shape" : "rectangle"})
    dot.attr(node_sep=str(node_sep), bgcolor=COLOR_MAP["graph-bg"], spline=line_type)
    if output_format != "svg":
        dot.attr(dpi=str(dpi))
    graph.graph(dot, split_blackboard)

    if render:
        render_graph(dot, ainb.filename, output_format, output_dir, view, unflatten, stagger)

    return dot

def graph_all_commands(ainb: AINB,
                       render: bool = True,
                       output_format: str = "svg",
                       output_dir: str = "",
                       view: bool = False,
                       unflatten: bool = True,
                       stagger: int = 1,
                       dpi: float = 96.0,
                       node_sep: float = 0.25,
                       line_type: str = "true",
                       split_blackboard: bool = False) -> graphviz.Digraph:
    """
    Graph all commands in the provided AINB file

    Args:
        ainb: Input AINB object
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        unflatten: Unflatten graph
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
        dpi: Pixels per inch for output image (does not affect SVG)
        node_sep: Node separation
        line_type: Edge line type
        split_blackboard: Split Blackboard into separate nodes
    """

    dot: graphviz.Digraph = graphviz.Digraph(ainb.filename, node_attr={"shape" : "rectangle"})
    dot.attr(node_sep=str(node_sep), bgcolor=COLOR_MAP["graph-bg"], splines=line_type)
    if output_format != "svg":
        dot.attr(dpi=str(dpi))
    
    for cmd in ainb.commands:
        dot.subgraph(graph_command(ainb, cmd.name, render=False, node_sep=node_sep, line_type=line_type, split_blackboard=split_blackboard))

    if render:
        render_graph(dot, ainb.filename, output_format, output_dir, view, unflatten, stagger)

    return dot