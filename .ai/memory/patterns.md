# Project Patterns and Conventions

Document Copper-specific patterns, conventions, and implementation guidelines here.

---

## Pattern Template

Use this format for documenting patterns:

```markdown
## Pattern: Brief Name

**Category**: Code Organization | Testing | CLI Commands | etc.
**When to Use**: Situation where this pattern applies
**How to Implement**: Step-by-step or code example
**Related**: Links to other patterns or decisions
```

---

## Example Patterns

Replace these examples with patterns specific to your project.

---

## Pattern: Adding a New CLI Command

**Category**: CLI Commands  
**When to Use**: Adding new functionality to trade_hunter or any app  

**How to Implement**:

```python
# In apps/trade_hunter/src/trade_hunter/cli.py

@app.command()
def my_command(
    required_arg: str,
    optional_arg: str = typer.Option("default", help="Description"),
    flag: bool = typer.Option(False, "--flag", help="Enable feature"),
) -> None:
    """
    Brief description of what this command does.
    
    This docstring becomes the command's help text.
    """
    # Implementation
    console.print(f"[green]Success![/green] {required_arg}")
```

**Then add test**:

```python
# In apps/trade_hunter/tests/test_my_command.py

def test_my_command():
    result = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "my-command", "test-value"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Success" in result.stdout
```

---

## Pattern: Testing CLI Commands

**Category**: Testing  
**When to Use**: Testing any CLI command end-to-end

**Standard Approach**:

```python
import subprocess
import sys

def test_command_name():
    """Test command works with expected arguments."""
    result = subprocess.run(
        [sys.executable, "-m", "trade_hunter", "command", "--arg", "value"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "expected output" in result.stdout
```

**Alternative for Unit Tests**:

```python
from trade_hunter.cli import my_function

def test_my_function():
    """Test function logic directly."""
    result = my_function("input")
    assert result == "expected"
```

**Rationale**: 
- `subprocess.run()` tests actual CLI invocation (smoke tests)
- Direct imports test business logic (unit tests)
- Both approaches are valid for different purposes

---

## Pattern: Code Organization per App

**Category**: Code Organization  
**When to Use**: Structuring code within any CLI app

**Directory Structure**:

```
apps/trade_hunter/
├── src/trade_hunter/
│   ├── __init__.py      # Package initialization, version
│   ├── __main__.py      # Entry point (python -m)
│   ├── cli.py           # Typer app and command definitions
│   ├── core.py          # Core business logic (if needed)
│   └── utils.py         # Helper functions (if needed)
└── tests/
    ├── test_smoke.py    # Smoke tests (CLI is callable)
    ├── test_cli.py      # CLI command tests
    └── test_core.py     # Business logic tests
```

**Guidelines**:
- Keep `cli.py` focused on CLI interface (thin layer)
- Move business logic to `core.py` or domain modules
- Keep utilities in `utils.py`
- One test file per module (approximately)

---

## Pattern: Error Handling in CLI

**Category**: CLI Commands  
**When to Use**: Any command that might fail

**Standard Pattern**:

```python
from rich.console import Console
import typer

console = Console()

@app.command()
def risky_command(file_path: str) -> None:
    """Command that might fail."""
    try:
        # Risky operation
        with open(file_path) as f:
            data = f.read()
        console.print("[green]✓[/green] Success!")
    except FileNotFoundError:
        console.print(f"[red]✗[/red] File not found: {file_path}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", err=True)
        raise typer.Exit(code=1)
```

**Rationale**:
- Rich formatting for better UX
- Specific error messages for common cases
- Exit code 1 for scripting/CI integration
- Generic exception handler for unexpected errors

---

## Pattern: Development Workflow

**Category**: Workflow  
**When to Use**: Day-to-day development

**Standard Commands**:

```bash
# Make changes to code
vim apps/trade_hunter/src/trade_hunter/cli.py

# Format code
uv run ruff format .

# Lint and fix
uv run ruff check --fix .

# Run tests
uv run pytest

# Run specific app
uv run python -m trade_hunter command

# Before committing
uv run ruff format .
uv run ruff check --fix .
uv run pytest
git add .
git commit -m "Clear message"
```

---

## Pattern: Adding Dependencies

**Category**: Dependencies  
**When to Use**: Need to add a new library

**For App-Specific Dependencies**:

```bash
cd apps/trade_hunter
uv add requests  # Runtime dependency
uv add --dev mypy  # Development dependency (app-specific)
```

**For Workspace-Wide Tools**:

```bash
# Edit pyproject.toml at workspace root
[dependency-groups]
dev = [
  "pytest>=8",
  "ruff>=0.8",
  "mypy>=1.0",  # Add here
]

# Then sync
uv sync --all-groups
```

**Rationale**:
- App dependencies stay with the app
- Development tools shared across workspace
- Clear separation of concerns

---

## Your Patterns Start Here

Document your project-specific patterns below. Delete or keep examples as reference.

---

## Pattern: [Your Pattern Name]

**Category**: 
**When to Use**: 
**How to Implement**: 

```python
# Code example
```

**Related**: 

---

## Notes

- Keep patterns actionable (include code examples)
- Link to related ADRs when patterns derive from decisions
- Update patterns when better approaches are discovered
- Remove obsolete patterns (mark as deprecated first)
- Patterns should be specific to THIS project (not general Python advice)

---

## Naming Conventions

Document any project-specific naming conventions here:

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **CLI Commands**: `kebab-case`
- **CLI Options**: `--kebab-case`
- **Constants**: `SCREAMING_SNAKE_CASE`

(These are standard Python conventions - override only if you have project-specific rules)

---

## Common Gotchas

Add project-specific gotchas here as you discover them:

### Issue: [Common Problem]
**Symptom**: What goes wrong
**Cause**: Why it happens  
**Solution**: How to fix it
