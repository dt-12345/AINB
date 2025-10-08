import argparse
import importlib.resources
import json
import os
import sys
import typing

from ainb.ainb import AINB
try:
    import ainb.graph as graph
except ImportError as e:
    raise ImportError(
        "Graphing utilities must be installed for this script - pip install ainb[graph]"
    ) from e

GAME_TO_VERSION_MAP: typing.Dict[str, int | None] = {
    "s3"    : 0x404,
    "totk"  : 0x407,
    "smw"   : 0x407,
    "other" : None,
}

def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="AINB Graphing Tool",
        description="Command line graphing tool for AINB files",
        epilog="Example usage:\n    ainb-graph --command \"Root\" MyAINBFile.ainb\n    ainb-graph --all-nodes MyAINBFile.ainb",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--intype", "-t", help="Input file type (either JSON or AINB) - resolved by default based on file extension", default="")
    parser.add_argument("--node-index", help="Node index to begin graph at", default=-1)
    parser.add_argument("--command-name", help="Command name to graph", default="")
    parser.add_argument("--all-nodes", action="store_true", help="Graph all nodes in file", default=False)
    parser.add_argument("--all-commands", action="store_true", help="Graph all commands in file", default=False)
    parser.add_argument("--format", "-f", help="Output graph format (default is svg)", default="svg")
    parser.add_argument("--view", "-v", action="store_true", help="Automatically open the rendered graph when finished", default=False)
    parser.add_argument("--no-unflatten", action="store_false", help="Don't unflatten graph", default=True)
    parser.add_argument("--outpath", "-o", help="Output directory path", default="")
    parser.add_argument("--line-type", choices=["line", "spline", "polyline", "ortho", "curved"], help="Edge line type", default="spline")
    parser.add_argument("--stagger", "-s", type=int, help="Node staggering", default=1)
    parser.add_argument("--dpi", type=float, help="Output image DPI (does not affect SVG)", default=96.0)
    parser.add_argument("--node-sep", type=float, help="Node separation", default=0.25)
    parser.add_argument("--split-blackboard", action="store_true", help="Split Blackboard into separate nodes", default=False)
    parser.add_argument(
        "--game",
        "-g",
        choices=["nss", "s3", "totk", "smw", "other"],
        help="""Game the AINB file comes from/is for (this only affects the enum database used):
                nss = Nintendo Switch Sports,
                s3 = Splatoon 3,
                totk = The Legend of Zelda: Tears of the Kingdom,
                smw = Super Mario Bros. Wonder,
                other = other (specify custom enum DB)""",
        default="totk"
    )
    parser.add_argument("--enum-db-path", help="Path to custom enum databse file (requires --game=other)", default="")
    parser.add_argument("input_file_path", nargs="?", help="Input file path (file should either be a JSON or AINB file)", default="")
    args, _ = parser.parse_known_args()

    if args.input_file_path == "":
        parser.print_help()
        sys.exit(0)

    if not os.path.exists(args.input_file_path):
        print(f"{args.input_file_path} does not exist")
        sys.exit(0)

    if args.outpath:
        os.makedirs(args.outpath, exist_ok=True)
    
    in_file_type: str = args.intype.lower()
    if in_file_type == "":
        in_file_type = os.path.splitext(args.input_file_path)[1][1:]
    
    expected_version: int | None = GAME_TO_VERSION_MAP.get(args.game, None)

    if args.game != "other":
        db_path: str = f"{args.game}.json"
        try:
            with importlib.resources.open_text("ainb.data", db_path) as f:
                AINB.set_enum_db(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    else:
        if args.enum_db_path != "":
            if os.path.exists(args.enum_db_path):
                with open(args.enum_db_path, "r", encoding="utf-8") as f:
                    AINB.set_enum_db(json.load(f))
            else:
                print(f"Provided enum database path does not exist: {args.enum_db_path}")
    
    ainb: AINB
    if in_file_type == "ainb":
        ainb = AINB.from_file(args.input_file_path, read_only=expected_version is None or expected_version < 0x407)
    else:
        ainb = AINB.from_json(args.input_file_path)
    
    if args.all_commands:
        graph.graph_all_commands(ainb, True, args.format, args.outpath, args.view, args.no_unflatten, args.stagger, args.dpi, args.node_sep, args.line_type, args.split_blackboard)
    elif args.all_nodes:
        graph.graph_all_nodes(ainb, True, args.format, args.outpath, args.view, args.no_unflatten, args.stagger, args.dpi, args.node_sep, args.line_type, args.split_blackboard)
    elif args.command_name != "":
        graph.graph_command(ainb, args.command_name, True, args.format, args.outpath, args.view, args.no_unflatten, args.stagger, args.dpi, args.node_sep, args.line_type, args.split_blackboard)
    elif args.node_index != -1:
        graph.graph_from_node(ainb, args.node_index, True, args.format, args.outpath, args.view, args.no_unflatten, args.stagger, args.dpi, args.node_sep, args.line_type, args.split_blackboard)
    else:
        print(f"Please specify an entry point with either --node-index, --command-name, --all-nodes, or --all-commands")

if __name__ == "__main__":
    main()