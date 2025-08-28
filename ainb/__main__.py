import argparse
import importlib.resources
import json
import os
import sys
import typing

from ainb.ainb import AINB

# TODO: move this into ainb.py?
GAME_TO_VERSION_MAP: typing.Dict[str, int | None] = {
    "s3"    : 0x404,
    "totk"  : 0x407,
    "smw"   : 0x407,
    "other" : None,
}

def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="Command Line AINB Tool",
        description="Simple command line utility for working with AINB files",
        epilog="Example usage:\n    ainb MyAINBFile.ainb\n    ainb MyConvertedAINBFile.json\n    ainb AnotherAINBFile.ainb -o output",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--intype", help="Input file type (either JSON or AINB) - resolved by default based on file extension", default="")
    parser.add_argument("--outtype", help="Output file type (either JSON or AINB) - defaults to the opposite of the input file type", default="")
    parser.add_argument("--output-path", "-o", help="Path to directory to output file", default="")
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

    if args.output_path:
        os.makedirs(args.output_path, exist_ok=True)
    
    in_file_type: str = args.intype.lower()
    if in_file_type == "":
        in_file_type = os.path.splitext(args.input_file_path)[1][1:]
    
    out_file_type: str = args.outtype.lower()
    
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

    if os.path.isdir(args.input_file_path):
        for file in os.listdir(args.input_file_path):
            print(file)
            if file.endswith(".ainb"):
                AINB.from_file(os.path.join(args.input_file_path, file), read_only=False).save_json(args.output_path)
            elif file.endswith(".json"):
                AINB.from_json(os.path.join(args.input_file_path, file)).save_ainb(args.output_path)
            else:
                print(f"Unknown file extension: {file}")
    else:
        if in_file_type == "ainb":
            if out_file_type == "" or out_file_type == "json":
                if expected_version is None or expected_version < 0x407:
                    AINB.from_file(args.input_file_path, read_only=False).save_json(args.output_path)
                else:
                    AINB.from_file(args.input_file_path).save_json(args.output_path)
            elif out_file_type == "ainb": # not sure why you'd need this but sure
                if expected_version is None or expected_version < 0x407:
                    AINB.from_file(args.input_file_path, read_only=False).save_ainb(args.output_path)
                else:
                    AINB.from_file(args.input_file_path).save_ainb(args.output_path)
            else:
                print(f"Unknown output file type: {out_file_type}")
        elif in_file_type == "json":
            if out_file_type == "" or out_file_type == "ainb":
                AINB.from_json(args.input_file_path).save_ainb(args.output_path)
            elif out_file_type == "json": # not sure why you'd need this but sure
                AINB.from_json(args.input_file_path).save_json(args.output_path)
            else:
                print(f"Unknown output file type: {out_file_type}")
        else:
            print(f"Unknown input file type: {in_file_type}")

if __name__ == "__main__":
    main()