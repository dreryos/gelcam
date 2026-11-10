"""Turn a design builder into a figcraft-cli script, so it runs without an MCP host.

    python design/record_cli.py build_tools > /tmp/tools.json
    figcraft-cli run --in design/gelcam-ui.figcraft --out design/gelcam-ui.figcraft /tmp/tools.json

Records every create_node call as a `node.create` step; parents are wired with
`$ref`. Builders that read the document back (design_errors.build_rest uses
get_node) are not supported.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
cmds = []


def mcp(server, tool, **kw):
    if tool != "create_node":
        sys.exit(f"record_cli: {tool} is not supported")
    ref = f"n{len(cmds)}"
    cmds.append({"command": "node.create", "as": ref, "params": {**kw, "select": False}})
    return {"id": {"$ref": ref}}


ns = {}
for name in ["design_wizard.py", "design_liveview.py", "design_tools.py"]:
    exec((HERE / name).read_text(encoding="utf-8"), ns)
ns[sys.argv[1]](mcp)
json.dump(cmds, sys.stdout, ensure_ascii=False)
