# Development Methodology

## Development Roles

- **Vibe Engineer**: The human product owner of the project who directs the "AI Developer" on what work to do. The "Vibe Engineer" is responsible for making the final decision on project direction and options.
- **AI Developer**: An AI Engine (i.e., Claude Sonnet 4.6 is the current choice) (via GitHub Copilot in VS Code) is the AI engine doing the actual work per the guidance of the "Vibe Engineer". The AI engine also offers suggestions and asks questions to help understand, clarify and optimize the project development direction.

## Development Environment

- **IDE**: Visual Studio Code
- **AI Assistant**: GitHub Copilot configured to use the preferred AI Engine (e.g., Claude Sonnet 4.5 is the preferred AI Engine du jour) as the AI Developer
- **AI Context Management**: `.ai/` directory structure for maintaining coding patterns, decisions, and project memory
- **Coding Standards**: See [Claude Code Guidelines](./karpathy_claude.md) for detailed coding standards and patterns

## Technology Stack

This template provides a foundation with standard Python development tools. Additional technologies can be added based on your project's specific needs.

### Core Technologies
- **Python**: 3.13+ (modern async/await support, type hints)
- **uv**: Fast, reliable package and project manager
- **Typer**: CLI framework with type hints and automatic help generation
- **Rich**: Beautiful terminal output formatting
- **Git/GitHub**: Version control and remote repository

### Development Tools
- **VS Code**: Recommended IDE with GitHub Copilot extension
- **GitHub Copilot**: AI-assisted development (Claude Sonnet 4.5 or other models)
- **pytest**: Testing framework with fixtures and parametrization
- **ruff**: Modern Python linter and formatter (fast, comprehensive)
- **mypy**: Static type checking (optional but recommended)

### Project Configuration
- **pyproject.toml**: Modern Python project configuration (PEP 621 compliant)
- **.gitignore**: Standard Python + IDE ignore patterns
- **README.md**: Project documentation and setup instructions

## Development Workflow

1. **Story Preparation**: AI Developer drafts story with Vibe Engineer consultation
2. **Implementation**: AI Developer implements with tests
3. **Validation**: Vibe Engineer reviews and approves
4. **Commit**: Small, atomic commits with clear messages
5. **Iterate**: Continuous feedback loop

A story board is kept and maintained by the AI Developer in 'docs/STORY_BOARD.md' and the individual stories written and maintained by the AI Developer are in the 'docs/stories' directory.

## Testing Philosophy

- **Smoke tests**: Ensure CLI entry points are callable and basic functionality works
- **Unit tests**: For core business logic, data processing, and utility functions
- **Integration tests**: For CLI command workflows and external dependencies
- **Manual testing**: For end-to-end user workflows and UX validation (Vibe Engineer)
- **Test data**: Use fixtures or generated test data appropriate to your domain


