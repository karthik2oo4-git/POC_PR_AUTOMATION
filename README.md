# PR Validation Agent

A GitHub Actions-based pull request validation system that automatically runs tests and checks for merge conflicts before allowing PRs to be merged.

## 🎯 What It Does

When a pull request is created or updated, this system automatically:
- ✅ Copies test files from the base branch (prevents test tampering)
- ✅ Runs setup commands to prepare the environment
- ✅ Executes unit tests on the PR code
- ✅ Checks for merge conflicts with the base branch
- ✅ Posts detailed results as PR comments
- ✅ Enables/disables the merge button based on results

## 🚀 Quick Start

### 1. Add This Action to Your Repository

Create `.github/workflows/pr-validation.yml`:

```yaml
name: PR Validation

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read
  issues: write
  pull-requests: write
  statuses: write

jobs:
  validate:
    name: PR Unit Test Validation
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout pull request head
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.event.pull_request.head.sha }}

      - name: Run PR validation agent
        uses: karthik2oo4-git/POC_PR_AUTOMATION@main
        with:
          config-path: .github/pr-validation.yml
          python-version: "3.11"
          uv-version: "0.10.7"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 2. Create Configuration File

Create `.github/pr-validation.yml`:

```yaml
version: 1

status:
  context: "pr-unit-test-validation"

tests:
  command: "pytest -q --maxfail=1"
  timeout_seconds: 900

setup:
  commands:
    - "pip install -r requirements.txt"
  timeout_seconds: 600

labels:
  enabled: true
  test_failed: "test-failed"
  ready_for_review: "ready-for-review"
  merge_conflict: "merge-conflict"
```

### 3. Configure Branch Protection

1. Go to repository **Settings** → **Branches**
2. Add branch protection rule for `main`
3. Enable **"Require status checks to pass before merging"**
4. Select **"pr-unit-test-validation"** as required check
5. Save changes

## 📋 How It Works

```
PR Created → Workflow Starts → Copy Tests from Base Branch
                                        ↓
                                   Run Setup
                                        ↓
                                   Run Tests
                                        ↓
                              Check Merge Conflicts
                                        ↓
                              Post Results Comment
                                        ↓
                    ✅ Pass: Enable Merge  |  ❌ Fail: Block Merge
```

### Key Innovation: Test Integrity

Tests are **copied from the base branch** before running. This prevents developers from modifying tests in their PR to hide bugs.

**Example:**
```
Base Branch (main):
├── calculator.py: def add(a, b): return a + b  ✅
└── test.py: assert add(2, 3) == 5  ✅

PR Branch (feature):
├── calculator.py: def add(a, b): return a * b  ❌ Bug!
└── test.py: assert add(2, 3) == 6  ❌ Modified test!

Result:
- Base test runs: assert add(2, 3) == 5
- PR code: 2 * 3 = 6
- Test fails! ❌ Bug caught!
```

## 📖 Configuration Options

### Status Settings
```yaml
status:
  context: "pr-unit-test-validation"  # Status check name
  target_url: ""                       # Optional link in status
```

### Test Settings
```yaml
tests:
  command: "pytest -q"                 # Test command to run
  timeout_seconds: 900                 # Max test duration (15 min)
  log_max_bytes: 120000               # Max log size to capture
```

### Setup Settings
```yaml
setup:
  commands:                            # Commands run before tests
    - "npm install"
    - "pip install -r requirements.txt"
  timeout_seconds: 600                 # Max setup duration (10 min)
```

### Label Settings
```yaml
labels:
  enabled: true                        # Enable automatic labeling
  remove_stale: true                   # Remove old outcome labels
  create_missing: true                 # Create labels if they don't exist
  test_failed: "test-failed"          # Label for test failures
  ready_for_review: "ready-for-review" # Label for passing PRs
  merge_conflict: "merge-conflict"    # Label for merge conflicts
```

### Auto-Merge Settings
```yaml
auto_merge:
  enabled: false                       # Enable auto-merge after tests pass
  method: "SQUASH"                     # MERGE, SQUASH, or REBASE
```

## 🔍 Example Outputs

### ✅ Success Comment
```markdown
✅ All configured setup and unit-test checks passed.

GitHub can now allow merge when this workflow is marked as a required status check in branch protection.
```

### ❌ Test Failure Comment
```markdown
@username ❌ Unit tests failed

GitHub blocked this pull request because the validation workflow returned a failing status.

What to check in GitHub:
- Open the failed workflow run from the PR Checks tab
- Review the failing step logs
- Reproduce locally with `pytest -q`
- Push fixes to re-run validation automatically

Command: `pytest -q`
Exit code: `1`
Log excerpt:
```text
FAILED tests/test_calculator.py::test_add - AssertionError: assert 6 == 5
```
```

### ⚠️ Merge Conflict Comment
```markdown
@username ❌ Merge conflict detected

The PR branch could not merge `main` in CI. Resolve the conflict locally, push the updated branch, and the validation will run again.
```

## 🛠️ Advanced Usage

### Skip Test Copy (for debugging)
```bash
export PR_VALIDATION_SKIP_TEST_COPY=true
```

### Skip Merge Check (for testing)
```bash
export PR_VALIDATION_SKIP_MERGE=true
```

### Custom Test Paths
The system automatically detects test directories from your test command:
- `pytest tests/` → copies `tests/` directory
- `pytest test/` → copies `test/` directory
- Falls back to common patterns if not specified

## 📚 Documentation

- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** - Detailed technical documentation with code flow, architecture, and troubleshooting
- **[configs/pr-validation.example.yml](configs/pr-validation.example.yml)** - Example configuration file

## 🏗️ Project Structure

```
.
├── .github/workflows/          # Example workflow
├── src/pr_validation_agent/    # Python source code
│   ├── ci/runner.py           # Main validation logic
│   ├── github.py              # GitHub API integration
│   ├── comments.py            # Comment templates
│   ├── config.py              # Configuration schema
│   └── models.py              # Data models
├── tests/                      # Unit tests
├── action.yml                  # Composite action definition
├── Dockerfile                  # Optional container packaging
└── pyproject.toml             # Python project metadata
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `uv run pytest`
5. Submit a pull request

## 📝 License

This project is open source and available under the MIT License.

## 🙋 Support

For detailed implementation guidance, see [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md).

For issues or questions, please open a GitHub issue.

---

**Made with ❤️ for better code quality**
