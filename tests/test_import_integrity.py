import ast
import importlib.util
from pathlib import Path

BASE_PACKAGE = "app"
BASE_DIR = Path(BASE_PACKAGE)


def _module_exists(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _resolve_relative(package: str, level: int, module: str | None) -> str | None:
    parts = package.split(".")[:-level]
    if module:
        parts.extend(module.split("."))
    if not parts:
        return BASE_PACKAGE
    return ".".join([BASE_PACKAGE] + parts)


def _python_files():
    return [p for p in BASE_DIR.rglob("*.py") if p.name != "__init__.py"]


def test_internal_imports_resolvable():
    for py_file in _python_files():
        package = ".".join(py_file.relative_to(BASE_DIR).with_suffix("").parts)
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(f"{BASE_PACKAGE}."):
                        assert _module_exists(alias.name), (
                            f"{alias.name} missing (from {py_file})"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if node.level:
                    target = _resolve_relative(package, node.level, module)
                else:
                    target = (
                        module
                        if module and module.startswith(f"{BASE_PACKAGE}.")
                        else None
                    )
                if target:
                    assert _module_exists(target), f"{target} missing (from {py_file})"
