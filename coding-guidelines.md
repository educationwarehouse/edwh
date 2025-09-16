# EDWH Coding Guidelines & Technical Constitution

## Project DNA & Architecture Profile

### Scale & Deployment Model
- **Architecture Type**: Plugin-based CLI framework with modular extensions
- **Scale Indicator**: Multi-module monolith with plugin ecosystem
- **Deployment Model**: PyPI distributed library, installed via pipx/pip
- **Lifecycle Stage**: Production-ready, actively maintained
- **Usage Pattern**: DevOps tooling for Docker Compose environments
- **Team Topology**: Small core team with community plugin contributors

### Technology Philosophy
- **Complexity Stance**: Pragmatic simplicity - powerful features with minimal cognitive overhead
- **Dependency Strategy**: Curated dependencies pinned at major versions for stability
- **Performance Priority**: Developer experience over runtime optimization
- **Future Vision**: Extensible platform supporting diverse workflows

## Programming Philosophy

### Core Principles
1. **Convention over Configuration**: Sensible defaults with escape hatches
2. **Progressive Disclosure**: Simple tasks simple, complex tasks possible
3. **Plugin-First Architecture**: Core functionality extensible via plugins
4. **Fail-Fast with Context**: Clear error messages with actionable solutions

### Decision Patterns

#### Build vs Buy
- **Prefer Libraries When**:
  - Well-maintained (e.g., `click` for CLI interactions)
  - Domain-specific expertise required (e.g., `docker`, `yaml`)
  - Security-critical (e.g., `paramiko` for SSH)
- **Build Custom When**:
  - Core business logic (task orchestration)
  - Cross-cutting concerns (logging, configuration)
  - Plugin integration points

#### Abstraction Levels
```python
# GOOD: Clear abstraction boundaries
def check_env(key: str, default: str | Callable, comment: str) -> str:
    """High-level API for environment configuration."""
    pass

# AVOID: Leaky abstractions
def check_env_with_docker_compose_yaml_parsing(...):
    """Mixing concerns."""
    pass
```

#### Technical Debt Management
- **Acceptable Debt**: Deprecated parameters kept for backward compatibility
- **Unacceptable Debt**: Security vulnerabilities, data corruption risks
- **Refactor Triggers**: 
  - 3+ duplicate implementations
  - Performance degradation >20%
  - Security advisory published

## Code Organization

### Module Structure
```
src/edwh/
├── __init__.py                      # Public API exports
├── __about__.py                     # Version management
├── cli.py                           # CLI entry point
├── tasks.py                         # Core task definitions
├── helpers.py                       # Shared utilities
├── constants.py                     # Configuration constants
├── discover.py                      # Service discovery helpers
├── health.py                        # Container/health inspection utilities
├── docker_compose_yml_support.py    # docker-compose.yml parsing helpers
├── meta.py                          # Meta tasks (plugins, self-update, etc.)
├── local_tasks/                     # Namespace-specific tasks
│   └── plugin.py                    # Plugin management tasks
└── *.py                             # Other feature-specific modules
```

### Naming Conventions

#### Functions & Variables
```python
# Task functions: verb_noun pattern
@task()
def setup_config(ctx: Context) -> None:
    pass

# Helper functions: descriptive action
def interactive_selected_checkbox_values(...) -> list[str]:
    pass

# Constants: SCREAMING_SNAKE_CASE
DOCKER_COMPOSE = "docker --log-level error compose"

# Type aliases: PascalCase with T_ prefix for complex types
from typing import Literal
T_Stream = Literal["stdout", "stderr", "out", "err", ""]
```

Note: In Python 3.12+, PEP 695 `type` aliases are also allowed. Choose one style per file and stay consistent; the assignment style above matches current usage in most modules.

#### File Organization
- **Single Responsibility**: Each file handles one domain (health.py, discover.py)
- **Size Guidance**: Aim to split files over ~500 lines. Exceptions: `src/edwh/tasks.py` and `src/edwh/helpers.py` may temporarily exceed this until planned refactors land.
- **Import Order**:
  1. Standard library
  2. Third-party packages
  3. Local imports
  4. Type imports

### State Management

#### Configuration Hierarchy
```python
# 1. Environment variables (highest priority)
os.environ.get("VARIABLE")

# 2. .env file
read_dotenv(Path(".env"))

# 3. TOML configuration
TomlConfig.load()

# 4. Defaults (lowest priority)
DEFAULT_DOTENV_PATH = Path(".env")
```

#### Singleton Pattern
```python
# Cached singletons for expensive operations
tomlconfig_singletons: dict[tuple[str, str], TomlConfig] = {}

@classmethod
def load(cls, fname: str = DEFAULT_TOML_NAME, cache: bool = True) -> TomlConfig:
    if cache and (instance := tomlconfig_singletons.get(singleton_key)):
        return instance
```

## Cross-Cutting Concerns

### Error Handling

#### User-Facing Errors
```python
# GOOD: Actionable error messages
if not dc_path.exists():
    cprint(
        "docker-compose.yml file is missing, setup could not be completed!",
        color="red"
    )
    return None

# AVOID: Technical jargon
raise FileNotFoundError(dc_path)
```

#### Recovery Strategies
```python
# Graceful degradation with warnings
try:
    config = load_dockercompose_with_includes(c)
except FileNotFoundError:
    cprint("docker-compose.yml missing, limited functionality", "yellow")
    return None
```

### Logging & Observability

#### Structured Output
```python
# Consistent color coding
cprint("Success message", "green")
cprint("Warning message", "yellow")  
cprint("Error message", "red")
cprint("Info message", "blue")

# Progress indication
with futures.ThreadPoolExecutor() as executor:
    for idx, item in enumerate(items, 1):
        cprint(f"{idx}/{len(items)}: processing {item}", "blue")
```

### Configuration Management

#### Environment Variables
```python
def check_env(
    key: str,
    default: str | Callable,  # Callable for lazy evaluation
    comment: str,
    allowed_values: Iterable[str] = ()
) -> str:
    """Ensure environment variable exists with validation."""
    pass
```

#### Feature Flags
```python
# Runtime configuration via TOML
if boolish(config["services"].get("include_celeries_in_minimal", "false")):
    minimal_services += celeries
```

## Type System & Safety

### Type Hints
```python
# Always use type hints for public APIs
def service_names(
    service_arg: Collection[str] | None,
    default: Literal["all", "minimal", "logs", "celeries"] | None = None
) -> list[str]:
    pass

# Use TypedDict for complex structures
class ServicesTomlConfig(TypedDict, total=False):
    services: Literal["discover"] | list[str]
    minimal: list[str]
```

### Generic Types
```python
# Use generics for reusable components
def interactive_selected_checkbox_values[H: Hashable](
    options: list[str] | dict[H, str],
    selected: Collection[H] = ()
) -> list[str] | None:
    pass
```

## Testing Strategy

### Test Organization
```
tests/
├── unit/           # Fast, isolated tests
├── integration/    # Docker/system integration
└── e2e/           # Full workflow tests
```

### Test Patterns
```python
# Arrange-Act-Assert pattern
def test_service_names():
    # Arrange
    config = mock_toml_config()
    
    # Act
    result = service_names(["web*"], default="minimal")
    
    # Assert
    assert "web" in result
```

## Plugin Development

### Plugin Structure
```python
# Plugin entry point
@task(name="my-command")
def my_plugin_command(ctx: Context) -> None:
    """Plugin command documentation."""
    pass

# Register in pyproject.toml
[project.entry-points."edwh.tasks"]
my_plugin = "my_package.tasks"
```

### Plugin Guidelines
1. **Namespace Isolation**: Use unique namespace to avoid conflicts
2. **Dependency Management**: Declare all dependencies explicitly
3. **Error Handling**: Never crash the main CLI
4. **Documentation**: Include help text for all commands

## Performance Guidelines

### Optimization Strategies
```python
# Lazy loading for expensive imports
def get_task(ctx: Context, identifier: str) -> Task | None:
    from .local_tasks import plugin  # Import only when needed
    pass

# Threading for I/O operations
with concurrent.futures.ThreadPoolExecutor() as executor:
    results = executor.map(fetch_data, urls)
```

### Caching Patterns
```python
# Module-level cache for expensive operations
_dotenv_settings: dict[str, dict[str, str]] = {}

def read_dotenv(env_path: Path) -> dict[str, str]:
    if existing := _dotenv_settings.get(str(env_path)):
        return existing
```

## Security Guidelines

### Input Validation
```python
# Validate user input
if allowed_values and value not in allowed_values:
    raise ValueError(f"Invalid value '{value}'. Choose from {allowed_values}")

# Sanitize shell commands
command = shlex.join(args)  # Proper escaping
ctx.run(command)
```

### Secret Management
```python
# Never log secrets
def generate_password(silent: bool = True, dice: int = 6) -> str:
    password = diceware.get_passphrase(options)
    if not silent:
        print("Password:", password)  # Only show when explicitly requested
    return password
```

## Migration & Deprecation

### Deprecation Pattern
```python
from typing_extensions import deprecated

@deprecated("Use new_function instead")
def old_function():
    warnings.warn("Deprecated", DeprecationWarning)
    return new_function()
```

### Backward Compatibility
```python
def check_env(
    key: str,
    default: str,
    comment: str,
    postfix: str = None,  # Deprecated
    suffix: str = None,   # New parameter
):
    if postfix:
        warnings.warn("Use 'suffix' instead of 'postfix'", DeprecationWarning)
        suffix = suffix or postfix
```

## Development Workflow

### Quick Start
```bash
# Install for development
pip install -e ".[dev]"

# Run formatting
edwh fmt

# Run linting
edwh lint

# Run tests
pytest tests/
```

### Pre-commit Checks
```python
# Format code
ruff format .

# Sort imports
ruff check --select I --fix .

# Lint
ruff check .
```

### Release Process
```bash
# Semantic versioning
edwh plugin.release --minor  # 1.0.0 -> 1.1.0
edwh plugin.release --patch  # 1.1.0 -> 1.1.1
edwh plugin.release --major  # 1.1.1 -> 2.0.0
```

## Anti-Patterns to Avoid

### Code Smells
```python
# AVOID: God functions
def do_everything(ctx, flag1, flag2, ..., flag20):
    # 500 lines of code
    pass

# PREFER: Composed functions
def setup(ctx):
    check_prerequisites(ctx)
    configure_environment(ctx)
    validate_setup(ctx)
```

### Common Pitfalls
1. **Mutable Default Arguments**: Use `None` and create inside function
2. **Bare Exceptions**: Always specify exception types
3. **Print Debugging**: Use proper logging instead
4. **Global State**: Use context objects or dependency injection
5. **String Concatenation for Paths**: Use `pathlib.Path`

## Decision Matrix

| Scenario | Small Project | Medium Project | Large Project |
|----------|--------------|----------------|---------------|
| Config Management | .env files | TOML + .env | Consul/Vault |
| Error Handling | Print & exit | Exceptions | Structured errors |
| Logging | print/cprint | Logger class | Structured logging |
| Testing | Manual testing | Unit tests | Full test pyramid |
| Dependencies | Minimal | Curated | Dependency injection |
| Documentation | README | Docstrings | Full docs site |

## Performance Baselines

### Expected Characteristics
- **Startup Time**: <500ms for simple commands
- **Plugin Load**: <100ms per plugin
- **Config Parse**: <50ms for typical TOML
- **Docker Commands**: Network-bound, expect 1-5s

### Optimization Triggers
- Commands taking >1s for non-Docker operations
- Memory usage >100MB for CLI operations
- CPU usage >50% for non-computational tasks

## Troubleshooting Decision Tree

```
Problem occurs
├── Is it reproducible?
│   ├── Yes: Check recent changes
│   └── No: Check environment differences
├── Is it a known issue?
│   ├── Yes: Apply documented fix
│   └── No: Create minimal reproduction
├── Is it plugin-related?
│   ├── Yes: Isolate plugin, test core
│   └── No: Check core functionality
└── Escalation needed?
    ├── Yes: Document steps, create issue
    └── No: Document solution for future
```

## Universal Principles

1. **Explicit is Better than Implicit**: Clear function signatures and return types
2. **Errors Should Never Pass Silently**: Always handle or propagate meaningfully
3. **Composition over Inheritance**: Use mixins and protocols over deep hierarchies
4. **Convention with Flexibility**: Defaults that work, options when needed
5. **Developer Joy**: Fast feedback loops, clear errors, helpful documentation

## Contributing Guidelines

### Code Submission
1. Fork repository
2. Create feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Format with `edwh fmt`
6. Submit PR with clear description

### Review Criteria
- [ ] Tests included and passing
- [ ] Documentation updated
- [ ] Type hints complete
- [ ] No security vulnerabilities
- [ ] Backward compatibility maintained
- [ ] Performance impact assessed

## Conclusion

This codebase prioritizes **developer experience** and **extensibility** while maintaining **production readiness**. The plugin architecture allows scaling from simple Docker Compose management to complex DevOps workflows without sacrificing simplicity for basic use cases.

Key success factors:
- **Clear boundaries** between core and plugins
- **Consistent patterns** across all modules
- **Progressive complexity** - simple things stay simple
- **Excellent error messages** with solutions
- **Strong typing** for maintainability
- **Pragmatic choices** over dogma
