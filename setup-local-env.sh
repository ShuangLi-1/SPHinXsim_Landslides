# Local development environment setup
# Source this file to set up vcpkg environment for local development

# Prevent Python from creating __pycache__ directories
export PYTHONDONTWRITEBYTECODE=1

# Set LLM provider and API keys for local development
export SPHINXSIM_LLM_PROVIDER=ollama
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"

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
