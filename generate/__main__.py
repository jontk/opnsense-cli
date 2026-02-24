"""Main entry point for the OPNsense Go SDK generator pipeline."""

from __future__ import annotations

from pathlib import Path

from generate.emitter.go_emitter import emit
from generate.model.ir import APISpec
from generate.parser.endpoint_resolver import resolve_endpoints
from generate.parser.markdown_parser import parse_all as parse_markdown
from generate.parser.xml_parser import match_model_to_url
from generate.parser.xml_parser import parse_all as parse_xml

DOCS_DIR = Path("docs/api")
MODELS_DIR = Path("docs/models")
OUTPUT_DIR = Path("opnsense")


def main() -> None:
    print("=== OPNsense Go SDK Generator ===\n")

    # Stage 1: Parse markdown docs
    print("Stage 1: Parsing markdown documentation...")
    modules = parse_markdown(DOCS_DIR)

    total_endpoints = 0
    total_controllers = 0
    for mod in modules:
        total_controllers += len(mod.controllers)
        for ctrl in mod.controllers:
            total_endpoints += len(ctrl.endpoints)

    print(f"  Parsed {len(modules)} modules, {total_controllers} controllers, {total_endpoints} endpoints\n")

    # Stage 2: Parse XML models
    print("Stage 2: Parsing XML models...")
    models = parse_xml(MODELS_DIR)
    print(f"  Parsed {len(models)} XML model files\n")

    # Link models to controllers
    linked = 0
    for mod in modules:
        for ctrl in mod.controllers:
            if ctrl.model_url:
                model = match_model_to_url(models, ctrl.model_url)
                if model:
                    ctrl.model = model
                    linked += 1
    print(f"  Linked {linked} controllers to XML models\n")

    # Stage 2.5: Resolve endpoint-to-item mappings
    print("Stage 2.5: Resolving endpoint-to-model-item mappings...")
    resolve_endpoints(modules)
    typed = sum(
        1
        for mod in modules
        for ctrl in mod.controllers
        for ep in ctrl.endpoints
        if ep.model_item
    )
    print(f"  Resolved {typed} typed CRUD endpoints\n")

    # Stage 3: Emit Go code
    print("Stage 3: Emitting Go code...")
    spec = APISpec(modules=modules, models=models)
    emit(spec, OUTPUT_DIR)

    # Count output
    go_files = list(OUTPUT_DIR.rglob("*.go"))
    generated = [f for f in go_files if f.name not in ("client.go", "request.go", "types.go")]
    print(f"  Generated {len(generated)} Go files\n")

    print("Done! Run 'gofmt -w opnsense/' and 'go build ./opnsense/...' to verify.")


if __name__ == "__main__":
    main()
