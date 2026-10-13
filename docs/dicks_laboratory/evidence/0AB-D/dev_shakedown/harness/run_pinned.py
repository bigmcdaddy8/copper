"""0AB-D development shakedown: run the validation CLI with a pinned byte copy of drysdale_validation.py
(so later working-tree edits cannot reach a running date). Development corpus only."""
import importlib.util, sys
from pathlib import Path
here = Path(__file__).parent
import dicks_laboratory
spec = importlib.util.spec_from_file_location("dicks_laboratory.drysdale_validation", here / "dv_pinned.py")
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
dicks_laboratory.drysdale_validation = mod
spec2 = importlib.util.spec_from_file_location("cli_pinned", here / "cli_pinned.py")
cli = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(cli)
cli.REPO = Path.home() / "Documents/REPOs/copper"
cli.app()
