#!/usr/bin/env python3
# I'm not including any of the unedited files with this package so we are just not going to export the tests

import os
import unittest

import ainb
import ainb.graph

def fix_path(path: str) -> str:
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)

INPUT_DIRECTORY: str = fix_path("data")

class RoundtripTest(unittest.TestCase):
    def test_json_roundtrip(self) -> None:
        ainb.set_splatoon3()
        for file in os.listdir(INPUT_DIRECTORY):
            if not os.path.isfile(os.path.join(INPUT_DIRECTORY, file)):
                continue
            try:
                print(file)
                orig: ainb.AINB = ainb.AINB.from_file(os.path.join(INPUT_DIRECTORY, file), read_only=False)
                new: ainb.AINB = ainb.AINB.from_json_text(orig.to_json())
            except Exception as e:
                self.fail(f"{file} failed: {e.args}")
            self.assertDictEqual(orig.as_dict(), new.as_dict(), f"{file} is mismatching")
    
    def test_ainb_roundtrip(self) -> None:
        ainb.set_splatoon3()
        for file in os.listdir(INPUT_DIRECTORY):
            if not os.path.isfile(os.path.join(INPUT_DIRECTORY, file)):
                continue
            try:
                print(file)
                orig: ainb.AINB = ainb.AINB.from_file(os.path.join(INPUT_DIRECTORY, file), read_only=False)
                new: ainb.AINB = ainb.AINB.from_binary(orig.to_binary())
            except Exception as e:
                self.fail(f"{file} failed: {e.args}")
            self.assertDictEqual(orig.as_dict(), new.as_dict(), f"{file} is mismatching")

class GraphTest(unittest.TestCase):
    def test(self) -> None:
        ainb.set_splatoon3()
        for file in os.listdir(INPUT_DIRECTORY):
            if not os.path.isfile(os.path.join(INPUT_DIRECTORY, file)):
                continue
            try:
                if ".logic" in file:
                    ainb.graph.graph_all_nodes(ainb.AINB.from_file(os.path.join(INPUT_DIRECTORY, file), read_only=False), render=False)
                else:
                    ainb.graph.graph_all_nodes(ainb.AINB.from_file(os.path.join(INPUT_DIRECTORY, file), read_only=False), render=False)
            except Exception as e:
                self.fail(f"Failed to graph {file}: {e.args}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        INPUT_DIRECTORY = sys.argv[1]
        sys.argv = sys.argv[0:1] + sys.argv[2:]
    unittest.main()