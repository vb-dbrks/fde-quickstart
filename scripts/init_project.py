"""Turn the template into a project by filling in the {{placeholders}} in the deployment files.

    python3 scripts/init_project.py --name acme-claims --admins lead@example.com \\
        --dev-host https://adb-123.4.azuredatabricks.net --llm-endpoint <serving-endpoint> \\
        [--title "Acme Claims"] [--test-host URL] [--prod-host URL]

Run it again to fill in placeholders you skipped (e.g. the prod host, once you have it). Check what
is still unset with `python3 scripts/init_project.py --check` (`make deploy` does this for you).
Standard library only, so it works before `make setup`.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
# Files whose placeholders must all be filled before deploying.
DEPLOY_FILES = ["databricks.yml", "resources/*.yml", "app.yaml", "frontend/index.html"]
# The README keeps its checklist as-is; only its title is filled in.
README = "README.md"

NAME = re.compile(r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$")
EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")
HOST = re.compile(r"^https://[a-z0-9.-]+$")


def deploy_files() -> list[Path]:
    return sorted({path for pattern in DEPLOY_FILES for path in REPO.glob(pattern)})


def unset_placeholders() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in deploy_files():
        for name in PLACEHOLDER.findall(path.read_text()):
            found.setdefault(name, []).append(str(path.relative_to(REPO)))
    return found


def fill(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), text)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="list unset placeholders and exit")
    parser.add_argument("--name", help="kebab-case project name, 3-20 characters (app, bundle)")
    parser.add_argument("--title", help="human-readable name (default: from --name)")
    parser.add_argument("--admins", help="comma-separated emails that are always app admins")
    parser.add_argument("--dev-host", help="dev workspace URL")
    parser.add_argument("--test-host", help="test workspace URL")
    parser.add_argument("--prod-host", help="prod workspace URL")
    parser.add_argument("--llm-endpoint", help="Model Serving endpoint the agents call")
    return parser.parse_args(argv)


def collect(args: argparse.Namespace) -> dict[str, str]:
    errors: list[str] = []
    values: dict[str, str] = {}
    if args.name:
        if not NAME.match(args.name):
            errors.append(
                "--name: 3-20 lowercase letters, digits and hyphens, starting with a letter"
            )
        values["project_name"] = args.name
        values["project_title"] = args.title or args.name.replace("-", " ").title()
    elif args.title:
        values["project_title"] = args.title
    if args.admins:
        admins = [email.strip().lower() for email in args.admins.split(",") if email.strip()]
        if not admins or not all(EMAIL.match(email) for email in admins):
            errors.append("--admins: comma-separated email addresses")
        values["admin_emails"] = ",".join(admins)
    for target in ("dev", "test", "prod"):
        host = getattr(args, f"{target}_host")
        if host:
            host = host.rstrip("/")
            if not HOST.match(host):
                errors.append(
                    f"--{target}-host: a workspace URL like https://adb-123.4.azuredatabricks.net"
                )
            values[f"{target}_host"] = host
    if args.llm_endpoint:
        values["llm_endpoint"] = args.llm_endpoint
    if errors:
        sys.exit("\n".join(errors))
    return values


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.check:
        values = collect(args)
        for path in deploy_files():
            path.write_text(fill(path.read_text(), values))
        readme = REPO / README
        lines = readme.read_text().splitlines(keepends=True) if readme.exists() else []
        if lines and lines[0].startswith("# "):
            lines[0] = fill(lines[0], values)
            readme.write_text("".join(lines))

    remaining = unset_placeholders()
    if not remaining:
        print("All placeholders are set.")
        return
    print("Placeholders still to set:")
    for name, files in sorted(remaining.items()):
        print(f"  {name:<14} {', '.join(sorted(set(files)))}")
    if args.check:
        sys.exit(1)


if __name__ == "__main__":
    main()
