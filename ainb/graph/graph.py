import os
import typing

import graphviz # type: ignore

from ainb.ainb import AINB
from ainb.command import Command
from ainb.expression import InstDataType
from ainb.node import Node, NodeType, S32SelectorPlug, F32SelectorPlug, StringSelectorPlug, RandomSelectorPlug
from ainb.param import InputParam, OutputParam, ParamSource
from ainb.param_common import ParamType
from ainb.property import Property

# TODO: blackboard + expression in some way or another
# TODO: (probably not) expression control flow graph?

EXPRESSION_TYPE_MAP: typing.Dict[InstDataType, ParamType] = {
    InstDataType.BOOL       : ParamType.Bool,
    InstDataType.INT        : ParamType.Int,
    InstDataType.FLOAT      : ParamType.Float,
    InstDataType.STRING     : ParamType.String,
    InstDataType.VECTOR3F   : ParamType.Vector3F,
}

ID_ITER: int = 0
def get_id() -> str:
    global ID_ITER
    id: int = ID_ITER
    ID_ITER += 1
    return str(id)

class GraphError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)

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
        self.id: str = f"cluster_{get_id()}"
        self.dummy_id: str = get_id()

    @staticmethod
    def _format_input(id: str, param_type: ParamType, param: InputParam) -> str:
        if param_type == ParamType.Pointer:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.classname}*] {param.name} (default = nullptr)</td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param_type.name}] {param.name} (default = {param.default_value})</td>"
                    </tr>
                    """
        
    @staticmethod
    def _format_output(id: str, param_type: ParamType, param: OutputParam) -> str:
        if param_type == ParamType.Pointer:
            return f"""
                    <tr>
                        <td port=\"{id}\">[{param.classname}*] {param.name} (default = nullptr)</td>"
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
                        <td>[{prop.classname}*] {prop.name} (default = nullptr)</td>"
                    </tr>
                    """
        else:
            return f"""
                    <tr>
                        <td>[{param_type.name}] {prop.name} (default = {prop.default_value})</td>"
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

    def _add_to_graph(self, dot: graphviz.Digraph) -> None:
        with dot.subgraph(name=self.id) as sg:
            sg.attr(style="filled", color="lightgray")
            sg.node(
                name=self.dummy_id,
                label=f"""<
                        <table border="0" cellborder="1" cellspacing="0">
                            <tr>
                                <td><b>{self._get_name()}</b></td>
                            </tr>
                            {self._format_property_table()}
                            {self._format_input_table()}
                            {self._format_output_table()}
                        </table>
                    >""",
                style="bold"
            )

class Graph:
    """
    Class representing a node graph
    """
    def __init__(self) -> None:
        self.nodes: typing.Dict[int, GraphNode] = {}
        self.input_edges: typing.Set[InputEdge] = set()
        self.generic_edges: typing.Set[GenericEdge] = set()
        self.transition_edges: typing.Set[TransitionEdge] = set()
        self.root_index: int = -1
        self.root_name: str = ""
    
    def _add_input_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.input_edges:
            try:
                src_node: GraphNode = self.nodes[edge.src_node_index]
                dst_node: GraphNode = self.nodes[edge.dst_node_index]
                src_id: str = f"{src_node.dummy_id}:{src_node.output_map[edge.src_param]}"
                dst_id: str = f"{dst_node.dummy_id}:{dst_node.input_map[edge.dst_param]}"
                dot.edge(src_id, dst_id, edge.param_name, minlen="1")
            except Exception as e:
                raise GraphError(f"Could not resolve edge: {edge}") from e
    
    def _add_generic_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.generic_edges:
            node0: GraphNode = self.nodes[edge.node_index0]
            node1: GraphNode = self.nodes[edge.node_index1]
            # it'd be nice to just link the subgraphs together, but it seems to end up cutting off parts of the edges occasionally when you do so
            # maybe there's a fix, but for now we'll just link the inner nodes
            dot.edge(node0.dummy_id, node1.dummy_id, minlen="1")
    
    def _add_transition_edges(self, dot: graphviz.Digraph) -> None:
        for edge in self.transition_edges:
            src_node: GraphNode = self.nodes[edge.src_node_index]
            dst_node: GraphNode = self.nodes[edge.dst_node_index]
            if edge.edge_name != "":
                dot.edge(src_node.dummy_id, dst_node.dummy_id, edge.edge_name, minlen="1")
            else:
                dot.edge(src_node.dummy_id, dst_node.dummy_id, "Transition", minlen="1")

    def graph(self, dot: graphviz.Digraph) -> graphviz.Digraph:
        """
        Generate a graph onto the provided digraph
        """
        for node in self.nodes.values():
            node._add_to_graph(dot)
        self._add_input_edges(dot)
        self._add_generic_edges(dot)
        self._add_transition_edges(dot)
        if self.root_index != -1:
            root_node: GraphNode = self.nodes[self.root_index]
            root_id: str = get_id()
            dot.node(name=root_id, label=f"<<b>{self.root_name}</b>>", color="mediumorchid", shape="diamond", style="filled")
            dot.edge(root_id, root_node.dummy_id)
    
    def _process_param_source(self, node: Node, ainb: AINB, param_type: ParamType, param_index: int, param: InputParam, source: ParamSource) -> None:
        if param.source.src_node_index != -1 and not param.source.is_blackboard():
            if not param.source.is_expression():
                self.input_edges.add(
                    InputEdge(
                        param.source.src_node_index,
                        ParamLocation(param_type, param.source.src_output_index),
                        node.index,
                        ParamLocation(param_type, param_index),
                        param.name,
                    )
                )
            else:
                # expressions are capable of transforming an output parameter from another node of a different datatype into the correct datatype
                self.input_edges.add(
                    InputEdge(
                        param.source.src_node_index,
                        ParamLocation(
                            EXPRESSION_TYPE_MAP[ainb.expressions.expressions[param.source.flags.get_index()].output_datatype], param.source.src_output_index
                        ),
                        node.index,
                        ParamLocation(param_type, param_index),
                        param.name,
                    )
                )

    def add_node(self, node: Node, ainb: AINB, is_root: bool = False, root_name: str = "Entry Point") -> None:
        """
        Add an AINB node to the graph
        """
        if is_root:
            self.root_index = node.index
            self.root_name = root_name
        if node.index in self.nodes:
            return
        self.nodes[node.index] = GraphNode(node)
        for p_type in ParamType:
            for i, param in enumerate(node.params.get_inputs(p_type)):
                if isinstance(param.source, list):
                    for source in param.source:
                        self._process_param_source(node, ainb, p_type, i, param, source)
                else:
                    self._process_param_source(node, ainb, p_type, i, param, param.source)
        for plug in node.child_plugs:
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
            child_node: Node | None = ainb.get_node(plug.node_index)
            if child_node is None:
                raise GraphError(f"Node index {node.index} has child with index {plug.node_index} which does not exist")
            self.add_node(child_node, ainb)
        for transition in node.transition_plugs:
            if transition.transition.transition_type == 0:
                self.transition_edges.add(
                    TransitionEdge(node.index, transition.node_index, transition.transition.command_name)
                )
            else:
                self.transition_edges.add(
                    TransitionEdge(node.index, transition.node_index)
                )
            target_node: Node | None = ainb.get_node(transition.node_index)
            if target_node is None:
                raise GraphError(f"Node index {node.index} has transition target with index {transition.node_index} which does not exist")
            self.add_node(target_node, ainb)
        for query in node.queries:
            query_node: Node | None = ainb.get_node(query)
            if query_node is None:
                raise GraphError(f"Node index {node.index} has query with index {query} which does not exist")
            self.add_node(query_node, ainb)

def render_graph(graph: graphviz.Digraph, name: str, output_format: str = "svg", output_dir: str = "", view: bool = False, stagger: int = 1) -> None:
    src: graphviz.Source = graph.unflatten(stagger=stagger)
    if output_dir != "":
        os.makedirs(output_dir, exist_ok=True)
    src.format = output_format
    src.render(filename=name, directory=output_dir, view=view)

def graph_from_node(ainb: AINB, node_index: int, render: bool = False, output_format: str = "svg", output_dir: str = "", view: bool = False, stagger: int = 1) -> graphviz.Digraph:
    """
    Graph an AINB file starting from the specified node

    Args:
        ainb: Input AINB object
        node_index: Index of the node to start graphing from
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
    """
    node: Node | None = ainb.get_node(node_index)
    if node is None:
        raise GraphError(f"File {ainb.filename} has no node index {node_index}")
    graph: Graph = Graph()
    graph.add_node(node, ainb, is_root=True)

    name: str = f"{node.name} ({node.index})" if node.type == NodeType.UserDefined else f"{node.type.name} ({node.index})"

    dot: graphviz.Digraph = graphviz.Digraph(name, node_attr={"shape" : "rectangle"})
    dot.attr(compound="true")
    graph.graph(dot)

    if render:
        render_graph(dot, name, output_format, output_dir, view, stagger)

    return dot

def graph_command(ainb: AINB, cmd_name: str, render: bool = False, output_format: str = "svg", output_dir: str = "", view: bool = False, stagger: int = 1) -> graphviz.Digraph:
    """
    Graph a command from the provided AINB file

    Args:
        ainb: Input AINB object
        cmd_name: Name of command to graph
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
    """
    cmd: Command | None = ainb.get_command_by_name(cmd_name)
    if cmd is None:
        raise GraphError(f"Command {cmd_name} not found in {ainb.filename}")
    root_node: Node | None = ainb.get_node(cmd.root_node_index)
    if root_node is None:
        raise GraphError(f"Command {cmd_name} has an invalid root node index: {cmd.root_node_index}")
    graph: Graph = Graph()
    graph.add_node(root_node, ainb, is_root=True, root_name=cmd_name)

    dot: graphviz.Digraph = graphviz.Digraph(cmd.name, node_attr={"shape" : "rectangle"})
    dot.attr(compound="true")
    graph.graph(dot)

    if render:
        render_graph(dot, cmd_name, output_format, output_dir, view, stagger)

    return dot

def graph_all_nodes(ainb: AINB, render: bool = False, output_format: str = "svg", output_dir: str = "", view: bool = True, stagger: int = 1) -> graphviz.Digraph:
    """
    Graph all nodes in the provided AINB file (this is mostly useful for logic files which have no commands)

    Args:
        ainb: Input AINB object
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
    """
    
    graph: Graph = Graph()
    for node in ainb.nodes:
        graph.add_node(node, ainb)
    
    dot: graphviz.Digraph = graphviz.Digraph(ainb.filename, node_attr={"shape" : "rectangle"})
    dot.attr(compound="true")
    graph.graph(dot)

    if render:
        render_graph(dot, ainb.filename, output_format, output_dir, view, stagger)

    return dot

def graph_all_commands(ainb: AINB, render: bool = False, output_format: str = "svg", output_dir: str = "", view: bool = True, stagger: int = 1) -> graphviz.Digraph:
    """
    Graph all commands in the provided AINB file

    Args:
        ainb: Input AINB object
        render: Render graph to file
        output_format: Output format of rendered graph (defaults to svg)
        output_dir: Output directory path for rendered graph
        view: Automatically open rendered graph for viewing
        stagger: Minimum length of leaf edges are staggered between 1 and stagger
    """
    
    dot: graphviz.Digraph = graphviz.Digraph(ainb.filename, node_attr={"shape" : "rectangle"})
    dot.attr(compound="true", nodesep="3")
    
    for cmd in ainb.commands:
        dot.subgraph(graph_command(ainb, cmd.name))

    dot = dot.unflatten(stagger=stagger)

    if render:
        render_graph(dot, ainb.filename, output_format, output_dir, view, stagger)

    return dot