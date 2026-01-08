# Optional pre-commit hooks

This project does not require `pre-commit`, but you can enable local git hooks to run linters/tests before commits to improve the developer experience.

Suggested setup:

```bash
python -m pip install pre-commit
pre-commit install
```

Suggested `.pre-commit-config.yaml` (example):

```yaml
repos:
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.26.0
    hooks:
      - id: ruff
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.1
    hooks:
      - id: mypy
``` 

If you enable `pre-commit`, make sure CI still runs the linters/tests independently to ensure reproducible checks for PRs.