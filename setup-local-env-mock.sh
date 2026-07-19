# Local development environment setup
# Source this file to set up vcpkg environment for local development

# Prevent Python from creating __pycache__ directories
export PYTHONDONTWRITEBYTECODE=1

# Ensure local sphinxsim package is importable from any working directory.
_SPHINXSIM_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${PYTHONPATH:-}" ]; then
    export PYTHONPATH="$_SPHINXSIM_REPO_ROOT"
else
    export PYTHONPATH="$_SPHINXSIM_REPO_ROOT:$PYTHONPATH"
fi

# Provide a fallback launcher if the console script is not installed on PATH.
if ! command -v sphinxsim >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
        sphinxsim() { python -m sphinxsim "$@"; }
        echo "ℹ️ sphinxsim command not found on PATH; using python -m sphinxsim fallback"
    elif command -v python3 >/dev/null 2>&1; then
        sphinxsim() { python3 -m sphinxsim "$@"; }
        echo "ℹ️ sphinxsim command not found on PATH; using python3 -m sphinxsim fallback"
    else
        echo "❌ Neither python nor python3 was found in PATH"
    fi
fi

# Set LLM provider and API keys for local development
export SPHINXSIM_LLM_PROVIDER=mock

# Set VCPKG_ROOT for local development
export VCPKG_ROOT="$HOME/vcpkg"

# Verify vcpkg is available
if [ -f "$VCPKG_ROOT/vcpkg" ]; then
    echo "✅ vcpkg found at $VCPKG_ROOT"
else
    echo "❌ vcpkg not found at $VCPKG_ROOT"
    echo "Please adjust VCPKG_ROOT or install vcpkg"
fi

# Show available presets
echo ""
echo "Available build presets:"
echo "  cmake --preset integrated-build     # Build everything together"
echo "  cmake --preset python-binding-release # Build with pre-built SPHinXsys"
echo "  cmake --preset simple-binding       # Simple test binding"
