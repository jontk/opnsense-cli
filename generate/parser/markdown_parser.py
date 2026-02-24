"""Parse OPNsense API markdown documentation into IR objects."""

from __future__ import annotations

import re
from pathlib import Path

from generate.model.ir import Controller, Endpoint, Module, Parameter
from generate.parser.name_transform import go_method_name, snake_to_camel

# Matches section headers like:
#   Resources (AliasController.php) — extends : ApiMutableModelControllerBase
#   Service (ServiceController.php)
#   Abstract [non-callable] (FilterBaseController.php)
_SECTION_RE = re.compile(
    r"(Resources|Service|Abstract\s*\[non-callable\])\s*"
    r"\((\w+\.php)\)"
    r"(?:.*?extends\s*:\s*(\w+))?"
)

# Matches a markdown table row: | col1 | col2 | ... |
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")

# Matches separator rows: | --- | --- | ...
_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")


def parse_all(docs_dir: str | Path) -> list[Module]:
    """Parse all markdown files under docs_dir into Module objects."""
    docs_path = Path(docs_dir)
    modules: list[Module] = []

    for category in ("core", "plugins", "be"):
        cat_dir = docs_path / category
        if not cat_dir.is_dir():
            continue
        for md_file in sorted(cat_dir.glob("*.md")):
            module = parse_module(md_file, category)
            if module and module.controllers:
                modules.append(module)

    return modules


def parse_module(md_file: Path, category: str) -> Module | None:
    """Parse a single markdown file into a Module."""
    text = md_file.read_text(encoding="utf-8")

    # Normalize escaped underscores from markdownify
    text = text.replace("\\_", "_")

    # Extract module name from H1 — strip markdown link artifacts like [ï](#foo
    h1_match = re.match(r"^#\s+(\w+)", text)
    if not h1_match:
        return None
    module_name = h1_match.group(1)

    lines = text.split("\n")
    controllers: list[Controller] = []

    # Track abstract controllers for extends merging
    abstract_controllers: dict[str, Controller] = {}  # php_file -> Controller

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for section header
        section_match = _SECTION_RE.search(line)
        if section_match:
            section_type = section_match.group(1)
            php_file = section_match.group(2)
            base_class = section_match.group(3) or ""
            is_abstract = "Abstract" in section_type

            # Parse the table that follows
            i += 1
            endpoints, model_url = _parse_table(lines, i)
            i = _skip_table(lines, i)

            ctrl_name = php_file.replace(".php", "")
            ctrl = Controller(
                name=ctrl_name,
                php_file=php_file,
                base_class=base_class,
                is_abstract=is_abstract,
                endpoints=endpoints,
                model_url=model_url,
            )

            if is_abstract:
                abstract_controllers[php_file] = ctrl
            controllers.append(ctrl)
        else:
            # Check for headerless tables (like firmware.md)
            if _is_table_header(line, lines, i):
                endpoints, model_url = _parse_table(lines, i)
                i = _skip_table(lines, i)

                if endpoints:
                    # Infer controller from the first endpoint's Module column
                    first_ep = endpoints[0]
                    ctrl_name = first_ep.controller.title() + "Controller"
                    # Check if we already have a controller for this
                    existing = None
                    for c in controllers:
                        if c.endpoints and c.endpoints[0].controller == first_ep.controller:
                            existing = c
                            break
                    if existing:
                        existing.endpoints.extend(endpoints)
                        if model_url and not existing.model_url:
                            existing.model_url = model_url
                    else:
                        controllers.append(Controller(
                            name=ctrl_name,
                            php_file="",
                            endpoints=endpoints,
                            model_url=model_url,
                        ))
            else:
                i += 1
                continue

    # Merge abstract controller endpoints into children
    _merge_abstract_endpoints(controllers, abstract_controllers)

    if not controllers:
        return None

    return Module(
        name=module_name.lower(),
        category=category,
        controllers=controllers,
    )


def _is_table_header(line: str, lines: list[str], idx: int) -> bool:
    """Check if line starts a markdown table (header row followed by separator)."""
    if not _TABLE_ROW_RE.match(line):
        return False
    if idx + 1 < len(lines) and _SEPARATOR_RE.match(lines[idx + 1].strip()):
        # Check it looks like our 5-column API table
        cells = [c.strip() for c in line.split("|")[1:-1]]
        return len(cells) >= 5 and "Method" in cells[0]
    return False


def _parse_table(lines: list[str], start: int) -> tuple[list[Endpoint], str]:
    """Parse a markdown table starting at given line index.

    Returns (endpoints, model_xml_url).
    """
    endpoints: list[Endpoint] = []
    model_url = ""

    i = start
    # Skip to the table header
    while i < len(lines):
        line = lines[i].strip()
        if _TABLE_ROW_RE.match(line):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5 and "Method" in cells[0]:
                i += 1  # skip header
                break
        i += 1
    else:
        return endpoints, model_url

    # Skip separator
    if i < len(lines) and _SEPARATOR_RE.match(lines[i].strip()):
        i += 1

    # Parse data rows
    while i < len(lines):
        line = lines[i].strip()
        if not _TABLE_ROW_RE.match(line):
            break

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 5:
            i += 1
            continue

        method_str = cells[0].strip("`").strip()
        module = cells[1].strip()
        controller = cells[2].strip()
        command = cells[3].strip()
        params_str = cells[4].strip()

        # Skip empty rows
        if not method_str and not module:
            i += 1
            continue

        # Handle <<uses>> rows — extract model URL
        if "<<uses>>" in method_str:
            url_match = re.search(r"\[.*?\]\((https?://[^)]+\.xml)\)", params_str)
            if url_match:
                model_url = url_match.group(1)
            i += 1
            continue

        # Parse methods
        methods = [m.strip() for m in method_str.split(",")]

        # Parse parameters
        parameters = _parse_parameters(params_str)

        # Build command_camel for URL path
        command_camel = snake_to_camel(command)

        # Build URL path
        url_path = f"/api/{module}/{controller}/{command_camel}"

        # Build Go method name
        method_name = go_method_name(controller, command)

        endpoints.append(Endpoint(
            methods=methods,
            module=module,
            controller=controller,
            command=command,
            command_camel=command_camel,
            url_path=url_path,
            go_method_name=method_name,
            parameters=parameters,
        ))

        i += 1

    return endpoints, model_url


def _skip_table(lines: list[str], start: int) -> int:
    """Skip past a markdown table, returning the line index after it."""
    i = start
    in_table = False
    while i < len(lines):
        line = lines[i].strip()
        if _TABLE_ROW_RE.match(line) or _SEPARATOR_RE.match(line):
            in_table = True
            i += 1
        elif in_table:
            break
        else:
            i += 1
            if i - start > 5 and not in_table:
                break
    return i


def _parse_parameters(params_str: str) -> list[Parameter]:
    """Parse parameter string like '$uuid,$enabled=null' into Parameter objects."""
    if not params_str or params_str.isspace():
        return []

    # Remove markdown formatting
    params_str = params_str.strip("*").strip()
    if not params_str.startswith("$"):
        return []

    params: list[Parameter] = []
    for part in params_str.split(","):
        part = part.strip().lstrip("$")
        if not part:
            continue

        if "=" in part:
            name, default = part.split("=", 1)
            params.append(Parameter(
                name=name.strip(),
                required=False,
                default=default.strip(),
            ))
        else:
            params.append(Parameter(name=part.strip(), required=True))

    return params


def _merge_abstract_endpoints(
    controllers: list[Controller],
    abstract_controllers: dict[str, Controller],
) -> None:
    """Merge abstract controller endpoints into child controllers that extend them."""
    # Build a map from controller class name to abstract controller
    abstract_by_name: dict[str, Controller] = {}
    for ctrl in abstract_controllers.values():
        # Strip "Controller" suffix to get the base name
        base = ctrl.name.replace("Controller", "")
        abstract_by_name[base] = ctrl
        abstract_by_name[ctrl.name] = ctrl

    for ctrl in controllers:
        if ctrl.is_abstract or not ctrl.base_class:
            continue

        # Find the abstract parent
        parent = abstract_by_name.get(ctrl.base_class)
        if parent is None:
            # Try matching by php file pattern
            for abstract in abstract_controllers.values():
                if ctrl.base_class in abstract.name:
                    parent = abstract
                    break

        if parent is None:
            continue

        # Merge parent endpoints, adjusting module/controller to match child
        existing_commands = {ep.command for ep in ctrl.endpoints}
        for ep in parent.endpoints:
            if ep.command not in existing_commands:
                # Clone the endpoint with the child's module/controller
                child_ep = Endpoint(
                    methods=ep.methods,
                    module=ctrl.endpoints[0].module if ctrl.endpoints else ep.module,
                    controller=ctrl.endpoints[0].controller if ctrl.endpoints else ep.controller,
                    command=ep.command,
                    command_camel=ep.command_camel,
                    url_path=f"/api/{ctrl.endpoints[0].module if ctrl.endpoints else ep.module}/{ctrl.endpoints[0].controller if ctrl.endpoints else ep.controller}/{ep.command_camel}",
                    go_method_name=go_method_name(
                        ctrl.endpoints[0].controller if ctrl.endpoints else ep.controller,
                        ep.command,
                    ),
                    parameters=ep.parameters,
                )
                ctrl.endpoints.append(child_ep)

        # Inherit model URL if not set
        if not ctrl.model_url and parent.model_url:
            ctrl.model_url = parent.model_url
