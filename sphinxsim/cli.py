"""Command-line interface for SPHinXsys.

Usage examples
--------------
Generate a config from a natural-language description::

    sphinxsim generate "water flowing through a pipe at 2 m/s"

Validate an existing JSON config file::

    sphinxsim validate path/to/config.json

Run a simulation from a JSON config file::

    sphinxsim run path/to/config.json
"""

from __future__ import annotations

import os
import sys
import tempfile

# Set up sys.path FIRST, before any sphinxsim imports
def _find_project_root(start=None):
    start = start or os.getcwd()
    current = start
    while current != os.path.dirname(current):  # Not at root
        if os.path.exists(os.path.join(current, "pyproject.toml")):
            return current
        current = os.path.dirname(current)
    raise RuntimeError("Project root not found")

PROJECT_ROOT = _find_project_root()
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "build-integrated"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "sphinxsim", "bindings", "native"))
original_dir = os.getcwd()

# NOW import everything else
import argparse
import json
import shlex
from pathlib import Path
from typing import Tuple

from pydantic import ValidationError

from sphinxsim.config.schemas import SimulationConfig
from sphinxsim.llm import get_llm

# Convert PROJECT_ROOT to Path after imports
PROJECT_ROOT = Path(PROJECT_ROOT)

__version__ = "0.1.0"  # Keep in sync with sphinxsim/__init__.py

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _load_config(path: Path) -> Tuple[SimulationConfig | None, int]:
    """Load and validate a SimulationConfig from *path*.

    Returns ``(config, 0)`` on success or ``(None, 1)`` after printing an
    error message to stderr.
    """
    # If path is relative, resolve it under.build-temp directory
    if not path.is_absolute():
        path = PROJECT_ROOT / ".build-temp" / path
    
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return None, 1
    try:
        data = json.loads(path.read_text())
        return SimulationConfig(**data), 0
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return None, 1
    except ValidationError as exc:
        print(f"Config validation failed:\n{exc}", file=sys.stderr)
        return None, 1


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a SimulationConfig from a natural-language *description*."""
    llm = get_llm()
    try:
        config = llm.generate(args.description)
    except (ValueError, ValidationError) as exc:
        print(f"Error generating config: {exc}", file=sys.stderr)
        return 1

    output = config.model_dump_json(indent=2, exclude_none=True)
    if args.output:
        output_path = PROJECT_ROOT / ".build-temp" / args.output
        try:
            if output_path.parent and not output_path.parent.exists():
                output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output)
        except OSError as exc:
            print(f"Error writing config to {output_path}: {exc}", file=sys.stderr)
            return 1
        print(f"Config written to {output_path}")
    else:
        print(output)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update an existing SimulationConfig from a natural-language instruction."""
    config_path = Path(args.config_file)
    config, rc = _load_config(config_path)
    if rc != 0:
        return rc
    assert config is not None

    llm = get_llm()
    try:
        if not hasattr(llm, "update"):
            print(
                "The selected LLM provider does not support config updates. "
                "Please use a provider implementing update().",
                file=sys.stderr,
            )
            return 1
        updated_config = llm.update(config, args.description)
    except (ValueError, ValidationError) as exc:
        print(f"Error updating config: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else config_path
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / ".build-temp" / output_path

    output = updated_config.model_dump_json(indent=2, exclude_none=True)
    try:
        if output_path.parent and not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
    except OSError as exc:
        print(f"Error writing updated config to {output_path}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        print(f"Updated config written to {output_path}")
    else:
        print(f"Updated config in place: {output_path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a JSON config file against the SimulationConfig schema."""
    config, rc = _load_config(Path(args.config_file))
    if rc != 0:
        return rc
    assert config is not None
    print(f"✅ Generated configuration:")
    print(f"   Simulation type: {config.simulation_type.value}")
    print(f"   Shapes: {len(config.geometries.shapes)}")
    print(f"   Aligned boxes: {len(config.geometries.aligned_boxes)}")
    if config.geometries.system_domain is not None:
        print(f"   Domain lower bound: {config.geometries.system_domain.lower_bound}")
        print(f"   Domain upper bound: {config.geometries.system_domain.upper_bound}")
    if config.geometries.global_resolution is not None:
        print(f"   Global resolution: {config.geometries.global_resolution.model_dump(exclude_none=True)}")

    print(f"   Fluid bodies: {len(config.fluid_bodies)}")
    for body in config.fluid_bodies:
        print(
            "     - "
            f"{body.name}: "
            f"material={body.material.type.value}"
        )
    print(f"   Continuum bodies: {len(config.continuum_bodies)}")
    for body in config.continuum_bodies:
        print(
            "     - "
            f"{body.name}: "
            f"material={body.material.type.value}"
        )
    print(f"   Solid bodies: {len(config.solid_bodies)}")
    for body in config.solid_bodies:
        print(
            "     - "
            f"{body.name}: "
            f"material={body.material.type.value}"
        )
    if config.gravity is not None:
        print(f"   Gravity: {config.gravity}")
    print(f"   Observers: {len(config.observers)}")
    end_time = config.solver_parameters.end_time
    print(f"   End time: {end_time if end_time is not None else '(set by solver defaults)'}")
    
    # Validate config can round-trip through JSON
    config_json = config.model_dump_json(indent=2, exclude_none=True)
    print(f"\n📄 Configuration as JSON ({len(config_json)} bytes)")
    print(config_json[:200] + "..." if len(config_json) > 200 else config_json)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a simulation defined by a JSON config file."""
    config_path = Path(args.config_file)
    config, rc = _load_config(config_path)
    if rc != 0:
        return rc
    assert config is not None

    try:
        import _sphinxsys_core_2d as sph
    except ImportError:
        print("❌ C++ extension not available", file=sys.stderr)
        print("\n🔧 Please build the C++ extension:", file=sys.stderr)
        print("   cd sphinxsim/sphinxsys", file=sys.stderr)
        print("   cmake --preset integrated-build", file=sys.stderr)
        print("   ninja -C ../../build-integrated", file=sys.stderr)
        return 1

    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / ".build-temp" / config_path

    # Write the Pydantic-validated config to a temp file before passing to C++.
    tmp_cfg = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="sphinxsim_run_"
    )
    try:
        tmp_cfg.write(config.model_dump_json(indent=2, exclude_none=True))
        tmp_cfg.close()
        validated_config_path = tmp_cfg.name
    except OSError as exc:
        print(f"Error writing validated config: {exc}", file=sys.stderr)
        return 1

    try:
        sim = sph.SPHSimulation(validated_config_path)

        # Create temp directory in project root, not relative to cwd
        output_dir = PROJECT_ROOT / ".build-temp" / "test_simulation"
        output_dir.mkdir(exist_ok=True, parents=True)
        sim.resetOutputRoot(str(output_dir))
        print(f"📁 Now, the output folder is changed to: {output_dir}")

        sim.loadConfig()
        print("✅ Simulation configuration loaded")

        sim.initializeSimulation()
        print("✅ Simulation initialized")

        # Run simulation
        print("\n🚀 Running simulation...")
        sim.run()

        print("✅ Simulation completed successfully!")
        print(f"\n📊 Run summary:")
        configured_end_time = config.solver_parameters.end_time
        print(f"   End time: {configured_end_time if configured_end_time is not None else '(solver default)'}")
        if config.fluid_bodies:
            first_body_name = config.fluid_bodies[0].name
            print(f"   Fluid body: {first_body_name}")
        elif config.continuum_bodies:
            first_body_name = config.continuum_bodies[0].name
            print(f"   Continuum body: {first_body_name}")
        else:
            first_body_name = "simulation"
        print(f"   Run config: {config_path}")

        # Show output location
        safe_name = first_body_name.replace(' ', '_').replace('/', '_')[:50]
        output_dir = PROJECT_ROOT / ".build-temp" / "simulations" / safe_name
        print(f"\n📁 Simulation output saved to:")
        print(f"   {output_dir}")

        return 0

    except RuntimeError as e:
        if "C++ extension" in str(e):
            print("❌ C++ extension not available")
            print("\n🔧 Please build the C++ extension:")
            print("   cd sphinxsim/sphinxsys")
            print("   cmake --preset integrated-build")
            print("   ninja -C ../../build-integrated")
            return 1
        else:
            raise

    except NotImplementedError as e:
        print(f"❌ Feature not yet implemented: {e}")
        print("\n💡 Tip: Try a fluid-only simulation like:")
        print('   "water dam break for 1 second"')
        return 1

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Always clean up the validated temp config and restore original directory.
        try:
            os.unlink(validated_config_path)
        except OSError:
            pass
        os.chdir(original_dir)


def _schema_explore_context() -> str:
    schema = json.dumps(SimulationConfig.model_json_schema(), indent=2)
    return (
        "You are helping a user understand the SPHinXsim simulator schema and capabilities. "
        "Answer clearly and concisely using the schema as the source of truth. "
        "When relevant, include practical command examples.\n\n"
        "CLI capabilities:\n"
        "- generate: create a config from natural language\n"
        "- update: revise an existing config with natural language\n"
        "- validate: schema-validate and summarize a config\n"
        "- run: execute simulation from validated config\n"
        "- shell: interactive mode for generate/update/validate/run\n\n"
        "SimulationConfig JSON schema:\n"
        f"{schema}"
    )


def cmd_explore(args: argparse.Namespace) -> int:
    """Answer schema/functionality questions using the configured LLM provider."""
    question = args.question.strip() if args.question else ""
    if not question:
        print("question must not be empty", file=sys.stderr)
        return 1

    llm = get_llm()
    if not hasattr(llm, "explore"):
        print(
            "The selected LLM provider does not support schema exploration.",
            file=sys.stderr,
        )
        return 1

    try:
        answer = llm.explore(question, context=_schema_explore_context())
    except Exception as exc:
        print(f"Error exploring schema: {exc}", file=sys.stderr)
        return 1

    print("Top-level SimulationConfig fields and guidance:")
    print(answer)
    return 0


def _shell_resolve_config_path(config_file: str) -> Path:
    path = Path(config_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / ".build-temp" / path
    return path


def _shell_auto_validate(config_path: Path) -> bool:
    cfg, rc = _load_config(config_path)
    if rc != 0 or cfg is None:
        print("❌ Auto-validation failed", file=sys.stderr)
        return False
    print(f"✅ Auto-validation passed: {config_path}")
    return True


def cmd_shell(args: argparse.Namespace) -> int:
    """Interactive shell for generate/update/validate/run workflow."""
    config_path = _shell_resolve_config_path(args.config_file)
    provider = os.getenv("SPHINXSIM_LLM_PROVIDER", "mock")
    print("SPHinXsim interactive shell")
    print(f"LLM provider: {provider}")
    print(f"Config file: {config_path}")
    if not Path(args.config_file).is_absolute():
        print("Note: relative config paths are resolved under .build-temp/")
    print("Type: generate ..., update ..., explore ..., validate, run, exit")

    while True:
        try:
            line = input("sphinxsim> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue

        if line in {"exit", "quit"}:
            return 0

        if line == "help":
            print("Commands:")
            print("  generate DESCRIPTION")
            print("  update INSTRUCTION")
            print("  explore QUESTION")
            print("  validate")
            print("  run")
            print("  exit")
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            print(f"Invalid command syntax: {exc}", file=sys.stderr)
            continue

        if not parts:
            continue

        cmd = parts[0]

        if cmd == "generate":
            description = " ".join(parts[1:]).strip()
            if not description:
                print("Usage: generate DESCRIPTION", file=sys.stderr)
                continue
            llm = get_llm()
            try:
                config = llm.generate(description)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(config.model_dump_json(indent=2, exclude_none=True))
                print(f"Config written to {config_path}")
                _shell_auto_validate(config_path)
            except (ValueError, ValidationError) as exc:
                print(f"Error generating config: {exc}", file=sys.stderr)
            except OSError as exc:
                print(f"Error writing config to {config_path}: {exc}", file=sys.stderr)
            continue

        if cmd == "update":
            instruction = " ".join(parts[1:]).strip()
            if not instruction:
                print("Usage: update INSTRUCTION", file=sys.stderr)
                continue
            current, rc = _load_config(config_path)
            if rc != 0 or current is None:
                print("No valid config found. Run generate first.", file=sys.stderr)
                continue
            llm = get_llm()
            if not hasattr(llm, "update"):
                print(
                    "The selected LLM provider does not support config updates.",
                    file=sys.stderr,
                )
                continue
            try:
                updated = llm.update(current, instruction)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(updated.model_dump_json(indent=2, exclude_none=True))
                print(f"Updated config written to {config_path}")
                _shell_auto_validate(config_path)
            except (ValueError, ValidationError) as exc:
                print(f"Error updating config: {exc}", file=sys.stderr)
            except OSError as exc:
                print(f"Error writing config to {config_path}: {exc}", file=sys.stderr)
            continue

        if cmd == "explore":
            question = " ".join(parts[1:]).strip()
            if not question:
                print("Usage: explore QUESTION", file=sys.stderr)
                continue
            _ = cmd_explore(argparse.Namespace(question=question))
            continue

        if cmd == "validate":
            _ = cmd_validate(argparse.Namespace(config_file=str(config_path)))
            continue

        if cmd == "run":
            _ = cmd_run(argparse.Namespace(config_file=str(config_path)))
            continue

        print(f"Unknown command: {cmd}. Type 'help' for commands.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sphinxsim",
        description="Python UI for the SPHinXsys multi-physics C++ library.",
    )
    parser.add_argument("--version", action="version", version=f"sphinxsim {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    gen = subparsers.add_parser(
        "generate",
        help="Generate a simulation config from a natural-language description.",
    )
    gen.add_argument("description", help="Natural-language simulation description.")
    gen.add_argument(
        "-o", "--output", metavar="FILE", default=None, help="Write JSON config to FILE instead of stdout."
    )
    gen.set_defaults(func=cmd_generate)

    # validate
    val = subparsers.add_parser(
        "validate", help="Validate a JSON simulation config against the schema."
    )
    val.add_argument("config_file", nargs='?', default="config.json", help="Path to JSON config file.")
    val.set_defaults(func=cmd_validate)

    # update
    upd = subparsers.add_parser(
        "update",
        help="Update an existing simulation config from a natural-language instruction.",
    )
    upd.add_argument("config_file", help="Path to an existing JSON config file.")
    upd.add_argument("description", help="Natural-language update instruction.")
    upd.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Write updated JSON to FILE instead of updating in place.",
    )
    upd.set_defaults(func=cmd_update)

    # run
    run = subparsers.add_parser("run", help="Run a simulation from a JSON config file.")
    run.add_argument("config_file", nargs='?', default="config.json", help="Path to JSON config file.")
    run.set_defaults(func=cmd_run)

    # explore
    exp = subparsers.add_parser(
        "explore",
        help="Ask schema/functionality questions using the configured LLM provider.",
    )
    exp.add_argument("question", help="Question about the simulator schema or functionality.")
    exp.set_defaults(func=cmd_explore)

    # shell
    shell = subparsers.add_parser(
        "shell",
        help="Interactive command loop with auto-save and auto-validate.",
    )
    shell.add_argument(
        "--config",
        dest="config_file",
        default="config.json",
        help="Config file used by interactive commands (default: config.json).",
    )
    shell.set_defaults(func=cmd_shell)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``sphinxsim`` CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
