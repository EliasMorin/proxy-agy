import argparse
import sys
import uvicorn
from dotenv import load_dotenv

# Load .env file before importing settings
load_dotenv()

from app.config import settings
from app.auth import auth_manager


def parse_args():
    parser = argparse.ArgumentParser(description="Antigravity CLI OpenAI-Compatible Local Proxy Server")
    parser.add_argument(
        "--host",
        type=str,
        default=settings.HOST,
        help=f"Host address to bind to (default: {settings.HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.PORT,
        help=f"Port number to listen on (default: {settings.PORT})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (for development)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=settings.API_KEY,
        help="Require Bearer API Key for requests",
    )
    parser.add_argument(
        "--agy-bin",
        type=str,
        default=settings.AGY_BIN_PATH,
        help=f"Path to agy binary (default: {settings.AGY_BIN_PATH})",
    )
    parser.add_argument(
        "--default-model",
        type=str,
        default=settings.DEFAULT_MODEL,
        help=f"Default model to use (default: {settings.DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--default-effort",
        type=str,
        choices=["low", "medium", "high"],
        default=settings.DEFAULT_EFFORT,
        help=f"Default reasoning effort (default: {settings.DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--login",
        "-l",
        action="store_true",
        help="Launch interactive terminal login for Antigravity CLI before starting server",
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Check and print Antigravity CLI authentication status and exit",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Update runtime settings
    settings.HOST = args.host
    settings.PORT = args.port
    if args.api_key:
        settings.API_KEY = args.api_key
    if args.agy_bin:
        settings.AGY_BIN_PATH = args.agy_bin
    if args.default_model:
        settings.DEFAULT_MODEL = args.default_model
    if args.default_effort:
        settings.DEFAULT_EFFORT = args.default_effort

    # If --check-auth flag is passed
    if args.check_auth:
        print("🔍 Checking Antigravity CLI authentication...")
        is_auth, msg = auth_manager.probe_auth_sync(timeout=15)
        if is_auth:
            print("✅ Status: Authenticated (Ready)")
            sys.exit(0)
        else:
            print(f"⚠️ Status: Unauthenticated - {msg}")
            sys.exit(1)

    # If --login flag is passed
    if args.login:
        auth_manager.run_interactive_terminal_login()

    print("=" * 60)
    print("🚀 Starting Antigravity CLI OpenAI Proxy Server")
    print(f"📍 Local URL:     http://{args.host}:{args.port}")
    print(f"📡 API Base URL:  http://{args.host}:{args.port}/v1")
    print(f"🤖 agy Binary:    {settings.AGY_BIN_PATH}")
    print(f"🎯 Default Model: {settings.DEFAULT_MODEL} (effort: {settings.DEFAULT_EFFORT})")

    if settings.API_KEY:
        print(f"🔒 API Key Auth:  Bearer token enabled")
    else:
        print(f"🔓 API Key Auth:  Disabled (open access)")
    print("=" * 60)

    uvicorn.run(
        "app.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
