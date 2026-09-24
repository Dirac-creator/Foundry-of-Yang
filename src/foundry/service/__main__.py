"""Run the server, provision users, or make consistent backups."""
import argparse
import re
from pathlib import Path
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/local/foundry.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("add-user", "rotate-user"):
        cmd = commands.add_parser(name)
        cmd.add_argument("name")
        cmd.add_argument("--token-file", required=True)
        if name == "add-user":
            cmd.add_argument("--role", choices=["reader", "editor"], default="editor")
    run = commands.add_parser("serve")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8000)
    backup = commands.add_parser("backup")
    backup.add_argument("destination")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(args.database), host=args.host, port=args.port)
        return
    store = Store(args.database)
    if args.command == "backup":
        store.backup(args.destination)
        print("Backup created")
        return
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", args.name):
        parser.error("Use 1-80 ASCII letters, digits, dots, underscores or hyphens for usernames")
    target = Path(args.token_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Create exclusively before changing the credential, so an existing secret isn't overwritten.
    with target.open("x", encoding="utf-8") as stream:
        try:
            token = store.add_user(args.name, args.role) if args.command == "add-user" else store.rotate_user(args.name)
        except Exception:
            stream.close()
            target.unlink()
            raise
        stream.write(token + "\n")
    print("Token saved to the specified local file. Keep it private.")


if __name__ == "__main__":
    main()
