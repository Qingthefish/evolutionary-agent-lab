"""Launch the control center: `python -m agent_lab.tui [--state-dir DIR]`.

Offline mode is the default and needs no credentials. Live mode must be
requested explicitly with a model ID and the *name* of an environment variable
holding the DeepSeek key; there is no implicit key discovery or fallback.
"""

import argparse
import os
import sys

from ..core import WorkflowError
from .controller import ControlCenter, LiveConfig


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m agent_lab.tui",
                                     description="Evolutionary Agent Lab — Multi-Agent Control Center")
    parser.add_argument("--state-dir", default="runs/tui-session",
                        help="Persistent session directory (reused across restarts; ignored by Git)")
    parser.add_argument("--human", default="operator", help="Local human operator identifier (trusted local setup)")
    parser.add_argument("--live", action="store_true", help="Enable live DeepSeek execution (requires --model and --api-key-env)")
    parser.add_argument("--model", help="Explicit course-approved DeepSeek model identifier")
    parser.add_argument("--api-key-env", help="Name of the environment variable holding the DeepSeek API key")
    parser.add_argument("--refresh-seconds", type=float, default=5.0, help="Automatic status refresh interval; 0 disables")
    args = parser.parse_args(argv)
    live = None
    if args.live:
        if not args.model or not args.api_key_env:
            parser.error("--live requires --model and --api-key-env")
        key = os.environ.get(args.api_key_env)
        if not key:
            parser.error(f"Environment variable {args.api_key_env} is not set; refusing to start live mode")
        live = LiveConfig(model=args.model, api_key=key)
    elif args.model or args.api_key_env:
        parser.error("--model/--api-key-env are only used with --live")
    try:
        from .app import ControlCenterApp
    except ImportError:
        parser.exit(2, "Textual is not installed. Install the optional UI dependency: "
                       "python3 -m pip install -r requirements-tui.txt\n")
    try:
        controller = ControlCenter(args.state_dir, human=args.human, live=live)
    except (WorkflowError, OSError) as error:
        parser.exit(1, f"Cannot open session: {error}\n")
    try:
        ControlCenterApp(controller, refresh_seconds=args.refresh_seconds).run()
    finally:
        controller.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
