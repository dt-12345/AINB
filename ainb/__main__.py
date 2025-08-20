import argparse
import importlib.resources
import json
import os
import sys
import typing

from ainb.ainb import AINB

GAME_TO_VERSION_MAP: typing.Dict[str, int | None] = {
    "s3"    : 0x404,
    "totk"  : 0x407,
    "smw"   : 0x407,
    "other" : None,
}

GAME_HELP_MSG: str = \
"Game the AINB file comes from/is for (nss = Nintendo Switch Sports, s3 = Splatoon 3, totk = The Legend of Zelda: Tears of the Kingdom, smw = Super Mario Bros. Wonder)"

def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="Command Line AINB Tool",
        description="Simple command line utility for working with AINB files",
    )
    parser.add_argument("--in_type", "-i", help="Input file type (either JSON or AINB)", default="")
    parser.add_argument("--out_type", "-o", help="Output file type (either JSON or AINB)", default="")
    parser.add_argument("--output_path", help="Path to directory to output file", default="")
    parser.add_argument(
        "--game",
        "-g",
        choices=[
            "nss", "s3", "totk", "smw", "other"
        ],
        help=GAME_HELP_MSG,
        default="totk"
    )
    parser.add_argument("input_file_path", nargs="?", help="Input file path (file should either be a JSON or AINB file)", default="")
    args, _ = parser.parse_known_args()

    if args.input_file_path == "":
        parser.print_help()
        sys.exit(0)

    if not os.path.exists(args.input_file_path):
        print(f"{args.input_file_path} does not exist")
        sys.exit(0)

    if args.output_path:
        os.makedirs(args.output_path)
    
    in_file_type: str = args.in_type.lower()
    if in_file_type == "":
        in_file_type = os.path.splitext(args.input_file_path)[1][1:]
    
    out_file_type: str = args.out_type.lower()
    
    expected_version: int | None = GAME_TO_VERSION_MAP.get(args.game, None)

    db_path: str = f"{args.game}.json"
    try:
        with importlib.resources.open_text("ainb.data", db_path) as f:
            db: typing.Dict[str, typing.Dict[str, int]] = json.load(f)
            AINB.set_enum_db(db)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if in_file_type == "ainb":
        if out_file_type == "" or out_file_type == "json":
            if expected_version is None or expected_version < 0x407:
                AINB.from_file(args.input_file_path, read_only=False).save_json(args.output_path)
            else:
                AINB.from_file(args.input_file_path).save_json(args.output_path)
        elif out_file_type == "ainb":
            pass # TODO
        else:
            print("Unknown output file type")
    elif in_file_type == "json":
        if out_file_type == "" or out_file_type == "ainb":
            pass # TODO
        elif out_file_type == "json":
            pass # TODO
        else:
            print("Unknown output file type")
    else:
        print("Unknown input file type")

if __name__ == "__main__":
    main()