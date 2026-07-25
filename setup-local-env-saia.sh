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

# Set LLM provider for local development
export SPHINXSIM_LLM_PROVIDER=saia
export SAIA_MODEL="devstral-2-123b-instruct-2512"
export SAIA_BASE_URL="https://chat-ai.academiccloud.de/v1"
# Comma-separated alternatives tried automatically if the primary model is degraded/unavailable.
export SAIA_FALLBACK_MODELS="qwen3-coder-next,glm-4.7"

# API key loading order:
# 1) Existing SAIA_API_KEY in environment
# 2) Existing SAIA_API_KEY in environment (compatibility)
# 3) First line from SAIA_API_KEY_FILE (default: ~/.config/sphinxsim/SAIA_api_key)
export SAIA_API_KEY_FILE="${SAIA_API_KEY_FILE:-$HOME/.config/sphinxsim/saia_api_key}"

if [ -z "${SAIA_API_KEY:-}" ] && [ -n "${SAIA_API_KEY:-}" ]; then
    export SAIA_API_KEY="$SAIA_API_KEY"
fi

if [ -z "${SAIA_API_KEY:-}" ] && [ -f "$SAIA_API_KEY_FILE" ]; then
    export SAIA_API_KEY="$(head -n 1 "$SAIA_API_KEY_FILE" | tr -d '\r')"
fi

if [ -n "${SAIA_API_KEY:-}" ]; then
    echo "✅ SAIA API key loaded"
else
    echo "❌ SAIA API key not found"
    echo "Set SAIA_API_KEY, SAIA_API_KEY, or create: $SAIA_API_KEY_FILE"
fi

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
