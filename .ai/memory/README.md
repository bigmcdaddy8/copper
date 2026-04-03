# AI Memory - Copper

This directory contains institutional knowledge about **Copper** - the architectural decisions, patterns, and conventions specific to this project.

## Purpose

This is a memory and context system for AI assistants (and human developers) working on this project. It helps answer:

- **Why** was this approach chosen over alternatives?
- **What** patterns and conventions does this project follow?
- **How** should new features be implemented consistently?
- **When** were key decisions made and by whom?

## Files in This Directory

- **`decisions.md`**: Architecture Decision Records (ADRs) documenting major technical choices
- **`patterns.md`**: Project-specific patterns, conventions, and implementation guidelines
- **`gotchas.md`**: Known issues, workarounds, and things to watch out for (create as needed)

## How to Use

### For AI Assistants

When working on this project:
1. Review these files to understand project context
2. Follow established patterns when adding features
3. Suggest updates when discovering new patterns
4. Maintain consistency with documented decisions

### For Human Developers

- **Before making big decisions**: Check if similar decisions are documented
- **After making decisions**: Document them here for future reference
- **When onboarding**: Read these files to understand "why" behind the code
- **During code review**: Reference these docs to validate consistency

## What to Document

### Good Candidates for decisions.md
- ✓ Choice of libraries or frameworks
- ✓ Architecture or structural decisions
- ✓ Performance trade-offs
- ✓ Security considerations
- ✓ Why you DIDN'T choose popular alternatives

### Good Candidates for patterns.md
- ✓ Naming conventions specific to this project
- ✓ File organization rules
- ✓ Testing patterns and strategies
- ✓ Common code snippets or recipes
- ✓ Development workflow steps

### Don't Document
- ✗ Things obvious from the code
- ✗ Standard Python conventions (already documented elsewhere)
- ✗ Temporary workarounds (use code comments instead)
- ✗ Implementation details (those belong in code/docstrings)

## Format Guidelines

Keep entries:
- **Concise**: Focus on "why" not "what" (code shows what)
- **Dated**: Include when decision was made
- **Actionable**: Clear enough for future developers to follow
- **Updated**: Mark decisions as "Superseded" rather than deleting

## Example Entry

```markdown
## ADR-003: Use Redis for Session Storage

**Date**: 2026-02-26
**Status**: Accepted
**Context**: Need fast, distributed session storage for CLI state

**Decision**: Use Redis over SQLite

**Alternatives Considered**:
- SQLite: Simpler but not distributed
- PostgreSQL: Overkill for key-value needs
- File-based: Security and concurrency issues

**Rationale**: 
- Need TTL support for temporary sessions
- May scale to multi-user in future
- Redis is lightweight and fast

**Consequences**:
- Redis must be running in development
- Added dependency and deployment complexity
```

## Maintenance

✓ **Update regularly**: Don't let these files get stale  
✓ **Review during PR**: Check if decisions match docs  
✓ **Refactor when needed**: Reorganize as project grows  
✓ **Delete outdated**: Remove superseded decisions to avoid confusion

---

**Note**: This project was generated from [python_project_template](https://github.com/bigmcdaddy8/python_project_template). See the template's `.ai/memory/` for decisions about the template structure itself.
