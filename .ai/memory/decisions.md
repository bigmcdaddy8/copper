# Architecture Decision Records

Document major architectural decisions for **Copper** using this template.

---

## ADR Template

Use this format for each decision:

```markdown
## ADR-NNN: Brief Title

**Date**: YYYY-MM-DD
**Status**: Proposed | Accepted | Deprecated | Superseded
**Context**: What is the issue we're addressing?

**Decision**: What did we decide?

**Alternatives Considered**:
- Option 1: Why not?
- Option 2: Why not?

**Rationale**: Why is this the best choice?

**Consequences**: What does this decision enable or prevent?
```

---

## Example Entries

Below are example entries. Replace these with your actual project decisions.

---

## ADR-001: Initial CLI Application - trade_hunter

**Date**: 2026-04-03  
**Status**: Accepted  
**Context**: Need to create the first CLI application for this project

**Decision**: Create `trade_hunter` as the initial application using Typer framework

**Rationale**: 
- Template provides Typer scaffolding out of the box
- Type-safe CLI with automatic help generation
- Easy to extend with additional commands
- Well-documented and actively maintained

**Consequences**:
- All CLI commands should follow Typer patterns
- Type hints required for CLI parameters
- Can add more apps to monorepo as needed

---

## ADR-002: Workspace Structure

**Date**: 2026-04-03  
**Status**: Accepted  
**Context**: Generated from python_project_template which uses monorepo workspace structure

**Decision**: Keep monorepo structure with `apps/` directory even if starting with single app

**Rationale**:
- Easy to add related CLI tools later
- Shared dependencies (pytest, ruff) at workspace level
- Template provides this structure by default
- Modern Python best practice with uv

**Consequences**:
- Need `setup.sh` or manual `uv pip install -e apps/*` for development
- Workspace root is where you run tests and linting
- Each app can have independent versioning if needed

---

## ADR-003: Development Dependencies at Workspace Level

**Date**: 2026-04-03  
**Status**: Accepted  
**Context**: Template places pytest, ruff, and coverage at workspace level

**Decision**: Keep dev tools at workspace level, app-specific dependencies in each app's pyproject.toml

**Rationale**:
- Single version of testing/linting tools across all apps
- Simpler CI/CD configuration
- Faster installation (no duplicate dependencies)
- Consistent code quality across workspace

**Consequences**:
- All apps must work with same tool versions
- Adding workspace-wide tools requires workspace pyproject.toml edit
- App-specific tools can still be added per-app

---

## Your Decisions Start Here

Document your project-specific decisions below. Delete the examples above once you have real entries.

---

## ADR-004: [Your Decision Title]

**Date**: YYYY-MM-DD  
**Status**: Proposed  
**Context**: 

**Decision**: 

**Alternatives Considered**:
- 

**Rationale**: 

**Consequences**: 

---

## Notes

- Number ADRs sequentially (ADR-001, ADR-002, etc.)
- Don't delete old ADRs - mark them as "Superseded by ADR-NNN"
- Keep entries concise - link to external docs for details
- Update status when decisions change (Accepted → Deprecated)
- Focus on "why" - the code shows "what" and "how"
