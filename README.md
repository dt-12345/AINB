# AINB
Python library for working with AINB files

## Install
Requires at least Python 3.10

```bash
pip install ainb
```

Optionally install graphing components with:
```bash
pip install ainb[graph]
```

Graphing requires installation of [Graphviz](https://www.graphviz.org/) (make sure to add it to your system path)

## Usage

### Python
```py
import ainb
import ainb.graph

# load an AINB file and save it as JSON
script = ainb.AINB.from_file("AWonderfullyNamedFile.root.ainb")
script.save_json("output_directory")

# graph a file
ainb.graph.graph_all_commands(script, output_format="png", dpi=120.0)
```

### Command Line
```bash
# load an AINB file and save it as JSON
ainb AWonderfullyNamedFile.root.ainb

# graph a file
ainb-graph -f png --dpi 120 --all-commands AWonderfullyNamedFile.root.ainb
```

## Documentation

TODO

## Building

To build from source:
```bash
pip install -e .
```

## License

This software is licensed under GPLv2.