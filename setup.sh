#!/usr/bin/env bash
# Setup script for workspace installation
# This installs all workspace apps in editable mode

set -e  # Exit on error

echo "🔧 Setting up workspace..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed"
    echo "Install it from: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Sync workspace dependencies (including dev dependencies)
echo "📦 Installing workspace dependencies..."
uv sync --all-groups

# Install all apps in editable mode
echo "📦 Installing workspace apps..."
for app in apps/*/; do
    if [ -d "$app" ] && [ -f "${app}pyproject.toml" ]; then
        app_name=$(basename "$app")
        echo "  → Installing $app_name..."
        uv pip install -e "$app"
    fi
done

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  • Run tests: uv run pytest"
echo "  • See available apps in the apps/ directory"
echo "  • Run an app: uv run python -m <app-name> --help"
