import argparse

from app.obsidian import build_obsidian_uri, open_obsidian_uri


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="打开 Obsidian 知识库中的笔记")
    commands = parser.add_subparsers(dest="command", required=True)
    open_command = commands.add_parser("open", help="唤醒 Obsidian 并定位笔记")
    open_command.add_argument("--vault", required=True, help="Obsidian Vault 名称")
    open_command.add_argument("--file", required=True, help="Vault 内的相对笔记路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "open":
        open_obsidian_uri(build_obsidian_uri(args.vault, args.file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

