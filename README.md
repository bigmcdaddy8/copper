# Copper

A Python CLI monorepo built with modern tooling and best practices. This project can house multiple related command-line applications that share common configuration and dependencies.

## Technology Stack

This project uses contemporary Python development tools:

- **Python 3.13+** - Modern Python with latest language features
- **[uv](https://docs.astral.sh/uv/)** - Fast, reliable package and project manager
- **[Typer](https://typer.tiangolo.com/)** - Type-hinted CLI framework built on Click
- **[Rich](https://rich.readthedocs.io/)** - Beautiful terminal formatting
- **[Ruff](https://docs.astral.sh/ruff/)** - Extremely fast Python linter and formatter
- **[pytest](https://pytest.org/)** - Comprehensive testing framework

## Project Structure

This is a **monorepo** workspace where each CLI application lives under the `apps/` directory:

```
copper/
├── setup.sh                    # Installation convenience script
├── pyproject.toml              # Workspace configuration
├── README.md                   # This file
├── GIT_SETUP.md                # Git initialization and GitHub setup guide
├── CLAUDE.md                   # AI development guidelines
├── .gitignore                  # Python ignore patterns
├── .ai/
│   ├── guidelines/             # AI development standards
│   │   ├── karpathy_claude.md  # Detailed coding guidelines for LLMs
│   │   └── development_methodology.md
│   └── memory/                 # Project decision tracking
│       ├── README.md           # How to use this directory
│       ├── decisions.md        # Architecture Decision Records (ADRs)
│       └── patterns.md         # Project-specific patterns
└── apps/
    └── trade_hunter/   # Your first CLI application
        ├── pyproject.toml      # App dependencies and metadata
        ├── src/
        │   └── trade_hunter/
        │       ├── __init__.py
        │       ├── __main__.py # Entry point for python -m
        │       └── cli.py      # Typer CLI app definition
        └── tests/
            └── test_smoke.py   # Basic smoke tests
```

### Key Concepts

- **Workspace Root**: The top-level `pyproject.toml` defines the workspace and shared settings (like Ruff configuration)
- **Apps**: Each CLI tool is a separate package under `apps/` with its own dependencies
- **Shared Tooling**: Testing and linting tools (pytest, ruff) are defined at the workspace level so they work across all apps
- **Two-Level Dependencies**: 
  - **Workspace** (`./pyproject.toml`): Shared dev tools (pytest, ruff, pytest-cov)
  - **Apps** (`apps/*/pyproject.toml`): App-specific dependencies (typer, rich, etc.)

## Quick Start

### Installation

#### Option 1: Quick Setup (Recommended)

Use the included convenience script:

```bash
./setup.sh
```

This will:
- Install workspace dependencies
- Install all workspace apps in editable mode
- Make CLI commands available

#### Option 2: Manual Installation

Install step-by-step:

```bash
# Install workspace dependencies
uv sync

# Install workspace apps in editable mode
uv pip install -e apps/trade_hunter

# If you add more apps later, install them too:
# uv pip install -e apps/another-app
```

> **Note**: The workspace configuration in `pyproject.toml` defines workspace members, but they need to be explicitly installed in editable mode for development. The `setup.sh` script handles this automatically.

### Running Your CLI Application

There are several ways to run your CLI apps:

#### Method 1: Using uv run (Recommended)

From the **workspace root**, use `uv run`:

```bash
# Run the CLI app
uv run python -m trade_hunter --help

# Run a specific command
uv run python -m trade_hunter hello --name "World"
```

#### Method 2: Activate the Virtual Environment

```bash
# Activate the environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run the CLI
python -m trade_hunter --help
trade_hunter --help  # Also works via installed console script

# When done
deactivate
```

#### Method 3: Using the Installed Script

After running `uv sync`, your app is installed with a console script:

```bash
uv run trade_hunter --help
```

### Example Commands

```bash
# Show help
uv run python -m trade_hunter --help

# Run the hello command
uv run python -m trade_hunter hello

# Run with options
uv run python -m trade_hunter hello --name "Developer"
```

## Development Workflow

### Adding New Commands

Edit `apps/trade_hunter/src/trade_hunter/cli.py` to add new commands:

```python
import typer

app = typer.Typer()

@app.command()
def hello(name: str = "world"):
    """Say hello to someone."""
    print(f"Hello {name}")

@app.command()
def goodbye(name: str = "world"):
    """Say goodbye to someone."""
    print(f"Goodbye {name}")
```

Then run your new command:

```bash
uv run python -m trade_hunter goodbye --name "Developer"
```

### Adding Dependencies

#### App-Specific Dependencies

To add a package dependency for a specific CLI app:

```bash
# Navigate to the app directory
cd apps/trade_hunter

# Add a runtime dependency
uv add requests

# Add a development dependency (app-specific)
uv add --dev mypy
```

Or manually edit `apps/trade_hunter/pyproject.toml`:

```toml
dependencies = [
  "typer>=0.12",
  "rich>=13",
  "requests>=2.31",  # Your new dependency
]
```

Then run `uv sync --all-groups` from the workspace root to install.

#### Workspace-Level Dependencies

For tools that all apps should use (testing, linting), add them to the workspace root `pyproject.toml`:

```toml
[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-cov>=6",
  "ruff>=0.8",
  "mypy>=1.0",  # Add workspace-wide tools here
]
```

Then run `uv sync --all-groups` from the workspace root.

### Running Tests

Run all tests from the workspace root:

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run tests for a specific app
cd apps/trade_hunter
uv run pytest

# Run with coverage
uv run pytest --cov=trade_hunter
```

### Writing Tests

Add tests in the `tests/` directory of each app. Here's an example:

```python
# apps/trade_hunter/tests/test_cli.py
import subprocess
import sys

def test_hello_command():
    """Test the hello command works."""
    result = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "hello", "--name", "Test"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Hello Test" in result.stdout
```

## Code Quality

### Linting and Formatting with Ruff

This project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

```bash
# Check for linting issues
uv run ruff check .

# Auto-fix issues where possible
uv run ruff check --fix .

# Format code
uv run ruff format .

# Check formatting without modifying files
uv run ruff format --check .
```

Configuration is in the workspace `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"
```

### Pre-commit Workflow

Before committing code, run:

```bash
# Format code
uv run ruff format .

# Fix linting issues
uv run ruff check --fix .

# Run tests
uv run pytest
```

## Adding More CLI Applications

The monorepo structure makes it easy to add related CLI tools:

### Step 1: Create the App Structure

```bash
# Navigate to apps directory
cd apps

# Create new app directory
mkdir my-new-tool
cd my-new-tool

# Create source structure
mkdir -p src/my_new_tool tests
touch src/my_new_tool/{__init__.py,__main__.py,cli.py}
touch tests/test_smoke.py
```

### Step 2: Create pyproject.toml

Create `apps/my-new-tool/pyproject.toml`:

```toml
[project]
name = "my-new-tool"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
  "typer>=0.12",
  "rich>=13"
]

[project.scripts]
my_new_tool = "my_new_tool.cli:app"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_new_tool"]
```

### Step 3: Add CLI Code

Edit `apps/my-new-tool/src/my_new_tool/cli.py`:

```python
import typer

app = typer.Typer()

@app.command()
def hello():
    """Your new command."""
    print("Hello from my-new-tool!")
```

Edit `apps/my-new-tool/src/my_new_tool/__main__.py`:

```python
from .cli import app

if __name__ == "__main__":
    app()
```

### Step 4: Install

From the workspace root:

```bash
# Option 1: Re-run the setup script (installs all apps)
./setup.sh

# Option 2: Install just the new app
uv pip install -e apps/my-new-tool
```

### Step 5: Run Your New App

```bash
uv run python -m my_new_tool hello
```

## Building and Distribution

### Building Packages

To build distribution packages for your CLI apps:

```bash
# Navigate to an app directory
cd apps/trade_hunter

# Build wheel and sdist
uv build

# Output will be in dist/
ls dist/
```

### Installing Locally

To install a CLI app system-wide for testing:

```bash
cd apps/trade_hunter
uv build
uv tool install .
```

### Publishing to PyPI

If you want to publish your CLI tool:

```bash
cd apps/trade_hunter

# Build the package
uv build

# Publish (requires PyPI credentials)
uv publish
```

> **Note**: Make sure to update version numbers in `pyproject.toml` before publishing new releases.

### Creating Executables

For distributing standalone executables, consider using:

- **PyInstaller**: Bundles Python apps into executables
- **Nuitka**: Compiles Python to C for better performance
- **Shiv**: Creates self-contained Python zipapps

Example with PyInstaller:

```bash
uv add --dev pyinstaller
uv run pyinstaller --onefile src/trade_hunter/__main__.py
```

## Updating from Template

This project was generated from the [python_project_template](https://github.com/bigmcdaddy8/python_project_template). You can update to get the latest template improvements, bug fixes, and new features.

### Why Update?

Template updates may include:
- Bug fixes and improvements
- New development tools or configurations
- Enhanced documentation
- New convenience scripts or features
- Updated best practices

### Before You Update

#### Prerequisites

**Your project must be a git repository**. Copier uses git to track changes and merge template updates.

If you haven't initialized git yet:

```bash
# Initialize git repository
git init

# Make initial commit
git add .
git commit -m "Initial commit"
```

See [GIT_SETUP.md](GIT_SETUP.md) for detailed git setup instructions including GitHub connection.

#### Save Your Work

**Important**: Commit or stash your changes first!

```bash
# Check for uncommitted changes
git status

# Commit your work
git add .
git commit -m "Save work before template update"

# Or stash if you prefer
git stash
```

### How to Update

```bash
# From your project root
uvx copier update

# To update to a specific version or branch:
uvx copier update --vcs-ref=v1.2.0
uvx copier update --vcs-ref=master
```

Copier will:
1. Fetch the latest template version
2. Show you what has changed
3. Prompt you to resolve any conflicts
4. Preserve your customizations

> **Note**: The `copier update` command reads the template source from `.copier-answers.yml`. If you get a "Template not found" error, see the Troubleshooting section below.

### Handling Conflicts

When Copier finds conflicts between template changes and your customizations:

```
 conflict  README.md
[1] Keep your version
[2] Use template version
[3] Show diff
[4] Edit manually
```

**Best practice**: Choose option `[3]` to see the diff first, then decide.

### After Updating

**First, verify the update succeeded:**

```bash
# Check that _commit advanced to latest
grep _commit .copier-answers.yml

# Should show a recent commit hash
# If it still shows an old commit, the update didn't complete properly
```

If the `_commit` hash didn't update, it means conflicts weren't fully resolved or changes weren't committed. See "Stuck on Old Template Version?" in the Troubleshooting section below.

**Then review and test the changes:**

```bash
# See what changed
git diff

# Commit the update (IMPORTANT - this advances _commit)
git add .
git commit -m "Update from template"

# Run setup again if dependencies or structure changed
./setup.sh

# Run tests to ensure everything still works
uv run pytest

# Check that your app still runs
uv run python -m trade_hunter --help
```

### Pinning to a Specific Template Version

If you want to update to a specific template version (not just latest):

```bash
# Update to a specific version tag
uvx copier update --vcs-ref=v1.2.0

# Update to master branch (latest unreleased)
uvx copier update --vcs-ref=master
```

### Viewing Template Changes

To see what changed in the template between versions:

```bash
# View template release notes on GitHub
# Visit: https://github.com/bigmcdaddy8/python_project_template/releases

# Or check the git log
git ls-remote --tags https://github.com/bigmcdaddy8/python_project_template
```

### Opting Out of Updates

If you've heavily customized your project and no longer want template updates:

```bash
# Remove copier metadata (prevents updates)
rm -rf .copier-answers.yml
```

**Note**: This is a one-way decision. You won't be able to use `copier update` anymore.

### Update Best Practices

1. **Update regularly**: Check for template updates monthly or quarterly
2. **Read release notes**: Review what's changed before updating
3. **Update in a branch**: For safety, create a branch: `git checkout -b update-template`
4. **Test thoroughly**: Run full test suite after updating
5. **Commit separately**: Keep template updates in their own commit for easy rollback

### Troubleshooting Updates

**Stuck on Old Template Version? (Recurring Conflicts)**

If you keep getting the **same conflicts every update**, your project may be stuck on an old template baseline.

Check your baseline commit:

```bash
grep _commit .copier-answers.yml
```

Compare it to the latest template commit:

```bash
git ls-remote https://github.com/bigmcdaddy8/python_project_template.git HEAD
```

If your `_commit` is much older, updates keep trying to merge all the accumulated changes, causing recurring conflicts.

**Why this happens:**
- Conflicts weren't fully resolved in a previous update
- Changes weren't committed after resolving conflicts
- Update process was interrupted

**Solution: Use `copier recopy` to reset cleanly:**

```bash
# First, commit or stash any current changes
git status
git add .
git commit -m "Save current state before recopy"

# Use recopy to regenerate from latest template
uvx copier recopy --force --skip-answered

# Review what changed
git diff

# Restore any customizations you want to keep
# (Edit files to add back custom sections)

# Commit the update
git add .
git commit -m "Update to latest template via recopy"

# Verify _commit is now current
grep _commit .copier-answers.yml
```

See the "Understanding Update vs Recopy" section above for more details.

**Error: "Updating is only supported in git-tracked subprojects"**

This means your project is not a git repository. Copier requires git to track changes and merge updates.

```bash
# Initialize git if you haven't already
git init

# Add and commit all files
git add .
git commit -m "Initial commit"

# Now try updating again
uvx copier update
```

See [GIT_SETUP.md](GIT_SETUP.md) for complete git setup instructions.

**Error: "Cannot update because cannot obtain old template references"**

This means `.copier-answers.yml` exists but is missing the `_commit` field. This happens when the project was generated from a template that wasn't a proper git repository at the time.

Check what's in your file:

```bash
cat .copier-answers.yml
```

If it's missing `_commit`, you need to add it manually. Get the template's current commit hash:

```bash
# Get the latest commit hash from the template repository
git ls-remote https://github.com/bigmcdaddy8/python_project_template.git HEAD
```

Then edit `.copier-answers.yml` to add the `_commit` field:

```yaml
# .copier-answers.yml
_commit: abc123def456...  # Use the actual commit hash from above
_src_path: git@github.com:bigmcdaddy8/python_project_template.git
repo_name: Copper
repo_slug: copper
author_name: Todd McKee
python_min: '3.13'
first_app_name: trade_hunter
first_app_pkg: trade_hunter
```

Alternatively, if you just generated the project and haven't customized it much, regenerate it now that the template has proper git history:

```bash
# Backup if needed, then regenerate
cd ..
mv ai-sandbox ai-sandbox.backup
uvx copier copy git@github.com:bigmcdaddy8/python_project_template.git ai-sandbox
```

**Error: "Template not found"**

This means the `.copier-answers.yml` file is missing or doesn't have the template source.

```bash
# Check if the file exists
ls -la .copier-answers.yml
cat .copier-answers.yml

# If missing or corrupted, recreate it with your original values:
cat > .copier-answers.yml << 'EOF'
_src_path: git@github.com:bigmcdaddy8/python_project_template.git
repo_name: Copper
repo_slug: copper
author_name: Todd McKee
python_min: '3.13'
first_app_name: trade_hunter
first_app_pkg: trade_hunter
EOF

# Then try updating again:
uvx copier update
```

**Error: "Argument of destination_path expected to be ExistingDirectory"**

This means you're trying to pass arguments in the wrong order. The `copier update` command doesn't accept a template URL:

```bash
# WRONG:
uvx copier update git@github.com:...

# CORRECT:
uvx copier update                    # Uses .copier-answers.yml for template source
uvx copier update --vcs-ref=master  # With specific branch/tag
```

**Want to force a fresh copy instead of updating?**

If you have many conflicts or want to start fresh:

```bash
# This will overwrite files (backup first!)
uvx copier copy --force git@github.com:bigmcdaddy8/python_project_template.git .
```

**Error: "conflicts" or merge issues**

```bash
# If you get conflicts you don't want to resolve:
# 1. Stash or commit your changes
# 2. Try the update again
# 3. Choose [4] Edit manually for complex conflicts
# 4. Use your editor to resolve, then continue
```

**Template URL has changed or you switched from HTTPS to SSH**

```bash
# Edit .copier-answers.yml and update _src_path:
nano .copier-answers.yml

# Change:
# _src_path: https://github.com/bigmcdaddy8/python_project_template.git
# To:
# _src_path: git@github.com:bigmcdaddy8/python_project_template.git

# Save and try update again
uvx copier update
```

### Understanding Update vs Recopy

Copier provides two ways to synchronize with template changes:

#### `copier update` (Incremental Updates)

Use this for normal template updates. It only modifies files that have changed in the template.

```bash
uvx copier update
```

**What it does:**
- ✅ Updates files that changed in the template
- ✅ Preserves your customizations
- ✅ Shows conflicts for you to resolve
- ❌ Won't create files that were missing from initial generation
- ❌ May leave phantom conflicts if local files drifted from template

**When to use:** Regular template updates when a new version is released

#### `copier recopy` (Full Regeneration)

Use this to regenerate all template files from scratch.

```bash
uvx copier recopy --force --skip-answered
```

**What it does:**
- ✅ Regenerates ALL template files (fixes missing files)
- ✅ Resolves persistent merge conflicts
- ✅ Uses your saved answers from `.copier-answers.yml`
- ⚠️ **Overwrites** any customizations you made to workspace-level files (README.md, .gitignore, etc.)
- ✅ Never touches your `apps/` directories or other non-template files

**When to use:**
- Files are missing (like GIT_SETUP.md never generated)
- Recurring merge conflicts that won't resolve cleanly
- You want a "clean slate" from the template
- Initial project generation had issues

**After using recopy:**
1. Review changes: `git diff`
2. Restore any custom modifications (e.g., custom .gitignore entries)
3. Verify your apps still work: `./setup.sh && uv run pytest`
4. Commit the changes

#### Quick Decision Guide

| Situation | Command |
|-----------|---------|
| Template released a new version | `copier update` |
| Same merge conflict appears every update | `copier recopy` |
| Template file never got created | `copier recopy` |
| Want to preserve all customizations | `copier update` |
| Need a clean reset to template defaults | `copier recopy` |

#### Example: Preserving Customizations After Recopy

```bash
# Before recopy, note your customizations
git diff .gitignore README.md > my-customizations.patch

# Do the recopy
uvx copier recopy --force --skip-answered

# Review what changed
git diff

# Manually re-apply your customizations
# (Edit files to restore custom sections)

# Or try applying the patch (may need manual resolution)
git apply my-customizations.patch
```

## Troubleshooting

### Virtual Environment Issues

If you encounter virtual environment problems:

```bash
# Remove the virtual environment
rm -rf .venv

# Recreate it with the setup script
./setup.sh

# Or manually
uv sync --all-groups
# Then reinstall apps
for app in apps/*/; do uv pip install -e "$app"; done
```

### Dependency Conflicts

If dependencies conflict between apps:

```bash
# Show dependency tree
uv tree

# Update all dependencies
uv sync --all-groups --upgrade
```

### Import Errors

If you get "No module named" errors:

```bash
# Re-run the setup script to install all apps
./setup.sh

# Or manually install apps in editable mode
uv pip install -e apps/trade_hunter
```

Make sure you're running commands from the workspace root.

## AI-Assisted Development

This project includes comprehensive AI development support:

### Guidelines (`.ai/guidelines/`)
- `CLAUDE.md` - Quick reference for AI-assisted coding
- `karpathy_claude.md` - Detailed coding standards based on Andrej Karpathy's LLM principles
- `development_methodology.md` - Development workflow and testing philosophy

### Project Memory (`.ai/memory/`)
- `decisions.md` - Architecture Decision Records (ADRs) documenting why choices were made
- `patterns.md` - Project-specific patterns and conventions
- `README.md` - How to use and maintain these files

**Best Practices**:
- AI assistants should review `.ai/memory/` to understand project context
- Document major decisions in `decisions.md` as you make them
- Update `patterns.md` when you establish new conventions
- Use these files to maintain consistency across AI-assisted sessions

### Coding Principles

The guidelines emphasize:
- Clear thinking before coding
- Simplicity and minimal abstractions
- Surgical, focused changes
- Goal-driven execution with verification
- Document "why" not just "what"

When working with AI assistants like Claude or GitHub Copilot, refer to these files to maintain code quality and preserve project knowledge.

## Project Conventions

### Code Style

- **Line length**: 100 characters (configured in Ruff)
- **Format**: Ruff handles all formatting automatically
- **Imports**: Ruff sorts and organizes imports
- **Type hints**: Use type hints for function signatures
- **Docstrings**: Use for public functions and classes

### Testing

- Place tests in `tests/` directory of each app
- Name test files `test_*.py`
- Name test functions `test_*`
- Include at least smoke tests that verify CLI is callable

### Naming Conventions

- **App names**: Use kebab-case (e.g., `my-cli-tool`)
- **Package names**: Use snake_case (e.g., `my_cli_tool`)
- **Module names**: Use snake_case
- **Class names**: Use PascalCase
- **Function names**: Use snake_case

## Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [Typer Documentation](https://typer.tiangolo.com/)
- [Typer Tutorial](https://typer.tiangolo.com/tutorial/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [pytest Documentation](https://pytest.org/)

## Contributing

### First-Time Git Setup

If you haven't initialized this project as a git repository yet, see [GIT_SETUP.md](GIT_SETUP.md) for detailed instructions on:
- Initializing the local repository with `master` branch
- Creating a GitHub repository
- Connecting and pushing your code
- Setting up SSH keys (if needed)

### Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd copper

# Run setup script to install everything
./setup.sh

# Run tests to verify setup
uv run pytest
```

### Making Changes

1. Create a feature branch
2. Make your changes
3. Run tests: `uv run pytest`
4. Format code: `uv run ruff format .`
5. Fix linting: `uv run ruff check --fix .`
6. Commit and push
7. Create a pull request

## License

[Specify your license here]

---

**Questions?** Check the [uv docs](https://docs.astral.sh/uv/) or [Typer docs](https://typer.tiangolo.com/) for detailed information about the tools used in this project.

