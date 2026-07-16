from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN_ROOTS = frozenset({"fastapi", "celery", "sqlalchemy", "openai", "anthropic"})


def forbidden_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.split(".", maxsplit=1)[0] in FORBIDDEN_ROOTS:
                found.add(name)
    return found


def domain_files(root: Path) -> list[Path]:
    return sorted(root.glob("app/modules/*/domain/**/*.py"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in domain_files(root):
        for imported in sorted(forbidden_imports(path.read_text(encoding="utf-8"))):
            violations.append(f"{path.relative_to(root)} imports forbidden dependency {imported}")
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print(f"architecture check passed ({len(domain_files(root))} domain files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
