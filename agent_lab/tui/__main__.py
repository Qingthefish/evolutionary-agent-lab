"""Launch the control center: `python -m agent_lab.tui [--state-dir DIR]`.

Offline mode is the default and needs no credentials. Live mode must be
requested explicitly with a model ID and the *name* of an environment variable
holding the DeepSeek key; there is no implicit key discovery or fallback.
"""

import argparse
import sys

from ..core import WorkflowError
from ..runtime import add_live_arguments, live_config_from_args
from .controller import ControlCenter


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m agent_lab.tui",
                                     description="Evolutionary Agent Lab — Multi-Agent Control Center")
    parser.add_argument("--state-dir", default="runs/tui-session",
                        help="Persistent session directory (reused across restarts; ignored by Git)")
    parser.add_argument("--human", default="operator", help="Local human operator identifier (trusted local setup)")
    add_live_arguments(parser)
    parser.add_argument("--refresh-seconds", type=float, default=5.0, help="Automatic status refresh interval; 0 disables")
    args = parser.parse_args(argv)
    try:
        live = live_config_from_args(args)
    except WorkflowError as error:
        parser.error(str(error))
    try:
        from .app import ControlCenterApp
    except ImportError:
        parser.exit(2, "Textual is not installed. Install the optional UI dependency: "
                       "python3 -m pip install -r requirements-tui.txt\n")
    repositories = []
    if args.git_config:
        from ..git_tools import load_trusted_repositories
        try:
            repositories = load_trusted_repositories(args.git_config)
        except (OSError, ValueError, KeyError, WorkflowError) as error:
            parser.error(f"Invalid --git-config: {error}")
    try:
        controller = ControlCenter(args.state_dir, human=args.human, live=live, repositories=repositories)
    except (WorkflowError, OSError) as error:
        parser.exit(1, f"Cannot open session: {error}\n")
    try:
        ControlCenterApp(controller, refresh_seconds=args.refresh_seconds).run()
    finally:
        controller.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
