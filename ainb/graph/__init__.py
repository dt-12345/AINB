"""
Requires a Graphviz installation on the system path

Simple AINB Graphing Utilities
"""

from ainb.graph.graph import (
    COLOR_MAP as COLOR_MAP,
    GraphError as GraphError,
    GraphNode as GraphNode,
    Graph as Graph,
    graph_from_node as graph_from_node,
    graph_command as graph_command,
    graph_all_nodes as graph_all_nodes,
    graph_all_commands as graph_all_commands,
)