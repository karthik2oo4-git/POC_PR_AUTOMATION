# PR Validation Agent

A GitHub Actions-based pull request validation system that automatically runs tests and checks for merge conflicts before allowing PRs to be merged. Features **intelligent test selection** with **tamper-proof test integrity**.

## 📑 Table of Contents

- [What It Does](#-what-it-does)
- [Key Features](#-key-features)
- [Quick Start](#-quick-start)
- [How It Works](#-how-it-works)
  - [Set Theory Approach](#set-theory-approach-a--n)
  - [Workflow Diagram](#workflow-diagram)
- [Security Features](#-security-features)
- [Configuration](#-configuration)
- [Examples](#-examples)
- [Common Use Cases](#-common-use-cases)
- [Troubleshooting](#-troubleshooting)
- [Technical Details](#-technical-details)
- [Recent Updates](#-recent-updates)
- [Documentation](#-documentation)
- [Contributing](#-contributing)

---

## 🎯 What It Does

When a pull request is created or updated, this system automatically:
- ✅ **Intelligently selects tests** using set theory (base tests + new tests)
- ✅ **Prevents test tampering** by copying base tests from the main branch
- ✅ **Runs setup commands** to prepare the environment
- ✅ **Executes unit tests** on the PR code
- ✅ **Checks for merge conflicts** with the base branch
- ✅ **Posts detailed results** as PR comments
- ✅ **Controls merge button** based on validation results

---

## ⭐ Key Features

### 🛡️ Test Integrity Protection
- **Base tests cannot be modified** - PRs can't change existing tests to hide bugs
- **Base tests cannot be deleted** - All existing tests always run
- **Tamper-proof validation** - Uses base branch version of test files

### 🧪 Intelligent Test Selection
- **New tests are welcomed** - PRs can add new tests to improve coverage
- **Set theory approach** - Final tests = Base tests ∪ New tests (A ∪ N)
- **Automatic detection** - Identifies which tests are new vs. existing

### 🚀 Developer-Friendly
- **Fast feedback** - Results posted as PR comments within minutes
- **Clear error messages** - Detailed logs help debug failures quickly
- **Automatic labeling** - PRs tagged with status (test-failed, ready-for-review, etc.)
- **Branch protection integration** - Blocks merge on failure, enables on success

### 🔧 Highly Configurable
- **Custom test commands** - Works with pytest, unittest, nose, etc.
- **Setup commands** - Install dependencies, prepare environment
- **Timeout controls** - Prevent runaway tests
- **Label customization** - Use your own label names

---

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

**That's it!** Your PRs are now protected. 🎉

---

## 📖 How It Works

### Set Theory Approach (A ∪ N)

The system uses **set theory** to intelligently select which tests to run:

```
A = Tests from base branch (main)
B = Tests from PR branch (feature)
N = B - A (new tests introduced in PR)

Final Tests = A ∪ N
```

**Why this matters:**

| Scenario | What Happens | Result |
|----------|--------------|--------|
| **PR modifies existing test** | Test is in both A and B<br/>N = ∅ (empty)<br/>Use base version | ✅ Base test runs, catches bugs |
| **PR deletes test** | Test is in A but not B<br/>N = ∅ (empty)<br/>Use base version | ✅ Deleted test still runs |
| **PR adds new test** | Test is in B but not A<br/>N = {new test}<br/>Use PR version | ✅ New test runs alongside base tests |
| **PR renames test** | Old name in A, new name in B<br/>N = {new name}<br/>Both versions run | ✅ Both old and new tests run |

### Workflow Diagram

```
PR Created/Updated
       ↓
┌──────────────────────────────────────────┐
│  1. Discover Base Tests (Set A)          │
│     - Checkout base branch temporarily   │
│     - Parse test files with AST          │
│     - Extract test identifiers           │
│     - Return to PR branch                │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  2. Discover PR Tests (Set B)            │
│     - Parse test files in PR branch      │
│     - Extract test identifiers           │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  3. Compute New Tests (N = B - A)        │
│     - Set difference operation           │
│     - Identify genuinely new tests       │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  4. Build Final Test Set (A ∪ N)         │
│     - Union of base and new tests        │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  5. Prepare Test Environment             │
│     - For tests in A: Copy from base     │
│     - For tests in N: Copy from PR       │
│     - Create isolated temp directory     │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  6. Run Setup Commands                   │
│     - Install dependencies               │
│     - Prepare environment                │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  7. Run Tests                            │
│     - Execute test command               │
│     - Capture output and exit code       │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  8. Check Merge Conflicts                │
│     - Try merging base into PR           │
│     - Detect conflicts                   │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  9. Post Results & Update Status         │
│     - Comment on PR with details         │
│     - Set commit status (✅ or ❌)       │
│     - Apply labels                       │
│     - Enable/disable merge button        │
└──────────────────────────────────────────┘
```

---

## 🛡️ Security Features

### Test Tampering Prevention

**The Problem:**
Without protection, a developer could:
1. Introduce a bug in their code
2. Modify the test to expect the wrong result
3. Both code and test pass validation
4. Bug gets merged into production

**Our Solution:**
Tests are **always copied from the base branch** before running, making tampering impossible.

**Example Attack Scenario:**

```python
# Base Branch (main) - Correct Implementation
# calculator.py
def add(a, b):
    return a + b

# test_calculator.py
def test_add():
    assert add(2, 3) == 5  ✅ Correct test
```

```python
# PR Branch (malicious) - Attempted Tampering
# calculator.py
def add(a, b):
    return a * b  ❌ BUG: Multiplies instead of adds!

# test_calculator.py
def test_add():
    assert add(2, 3) == 6  ❌ Modified test to hide bug!
```

**What Happens:**
```
1. System copies test_calculator.py from base branch
2. Runs base test: assert add(2, 3) == 5
3. PR code executes: 2 * 3 = 6
4. Test fails: 6 ≠ 5
5. ❌ Bug caught! PR blocked from merging
```

### File-Level Granularity

The system operates at the **file level** for efficiency:

- If a test file contains **any base test** → entire file copied from base
- If a test file contains **only new tests** → entire file copied from PR

**Implication:**
Adding new tests to an existing test file won't include them in validation (they'll run after merge). To include new tests immediately, create a new test file.

---

## 📋 Configuration

### Complete Configuration Reference

```yaml
version: 1

# Commit status settings
status:
  context: "pr-unit-test-validation"  # Status check name in GitHub
  target_url: ""                       # Optional link in status (e.g., docs)

# Test execution settings
tests:
  command: "pytest -q --maxfail=1"     # Command to run tests
  timeout_seconds: 900                 # Max test duration (15 min)
  log_max_bytes: 120000               # Max log size to capture

# Setup commands (run before tests)
setup:
  commands:
    - "uv sync --frozen"               # Install dependencies
    - "npm install"                    # Additional setup
  timeout_seconds: 600                 # Max setup duration (10 min)

# PR label management
labels:
  enabled: true                        # Enable automatic labeling
  remove_stale: true                   # Remove old outcome labels
  create_missing: true                 # Create labels if they don't exist
  test_failed: "test-failed"          # Label for test failures
  ready_for_review: "ready-for-review" # Label for passing PRs
  merge_conflict: "merge-conflict"    # Label for merge conflicts

# Comment settings
comments:
  marker: "pr-validation-agent:summary"  # HTML comment marker

# Auto-merge settings (optional)
auto_merge:
  enabled: false                       # Enable auto-merge after tests pass
  method: "SQUASH"                     # MERGE, SQUASH, or REBASE
```

### Test Path Detection

The system automatically detects test directories from your test command:

```yaml
tests:
  command: "pytest tests/"           # Detects "tests/" as test path
```

Multiple paths:
```yaml
tests:
  command: "pytest tests/ integration/"  # Detects both paths
```

Default fallback if no paths detected: `["tests/", "test/"]`

---

## 🔍 Examples

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
- Reproduce locally with `pytest -q --maxfail=1`
- Push fixes to re-run validation automatically

Command: `pytest -q --maxfail=1`
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

Steps to resolve:
1. git checkout feature-branch
2. git pull origin main
3. Resolve conflicts in affected files
4. git add .
5. git commit -m "Resolve merge conflicts"
6. git push
```

### 🆕 New Tests Detected

```markdown
✅ All tests passed (including 2 new tests from this PR)

New tests added:
  + tests/test_calculator.py::test_multiply
  + tests/test_advanced.py::test_complex_calculation

These new tests will be included in the base test suite after merge.
```

---

## 💡 Common Use Cases

### Use Case 1: Code-Only Changes

**Scenario:** Developer fixes a bug without modifying tests

```
Base tests: test_add, test_subtract
PR tests:   test_add, test_subtract (unchanged)
New tests:  N = ∅ (empty)
Final:      A = {test_add, test_subtract}
```

**Result:** Base tests run, validate the fix works correctly

### Use Case 2: Adding New Feature with Tests

**Scenario:** Developer adds multiplication feature with new test

```
Base tests: test_add, test_subtract
PR tests:   test_add, test_subtract, test_multiply
New tests:  N = {test_multiply}
Final:      A ∪ N = {test_add, test_subtract, test_multiply}
```

**Result:** All base tests + new test run, ensuring no regressions

### Use Case 3: Attempted Test Tampering

**Scenario:** Developer tries to hide bug by modifying test

```
Base tests: test_add (expects 5)
PR tests:   test_add (modified to expect 6)
New tests:  N = ∅ (not considered new, same identifier)
Final:      A = {test_add from base}
```

**Result:** Base test runs, catches the bug, PR blocked

### Use Case 4: Test Refactoring

**Scenario:** Developer improves test organization

```
Base tests: test_addition (old name)
PR tests:   test_add (renamed)
New tests:  N = {test_add}
Final:      A ∪ N = {test_addition, test_add}
```

**Result:** Both versions run (treated as old + new)

---

## 🔧 Troubleshooting

### Issue: Tests Pass Locally But Fail in CI

**Possible Causes:**
- Different Python version
- Missing dependencies
- Environment variables not set
- Different test data or fixtures

**Solutions:**
```yaml
# 1. Match Python version
- name: Run PR validation agent
  uses: karthik2oo4-git/POC_PR_AUTOMATION@main
  with:
    python-version: "3.11"  # Match your local version

# 2. Verify dependencies
setup:
  commands:
    - "pip install -r requirements.txt"
    - "pip list"  # Debug: Show installed packages

# 3. Set environment variables
env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  API_KEY: ${{ secrets.API_KEY }}
```

### Issue: New Tests Not Running

**Cause:** New tests added to existing test file

**Explanation:** 
If you add new tests to a file that already contains base tests, the entire file is copied from the base branch (for integrity). Your new tests won't run until after merge.

**Solution:**
Create a new test file for new tests:
```
tests/
  test_calculator.py      # Existing tests (base version used)
  test_calculator_new.py  # New tests (PR version used) ✅
```

### Issue: Status Check Not Appearing

**Possible Causes:**
- Wrong status context name
- Workflow not triggered
- Permissions issue

**Solutions:**
```yaml
# 1. Verify status context matches branch protection
status:
  context: "pr-unit-test-validation"  # Must match exactly

# 2. Check workflow triggers
on:
  pull_request:
    types: [opened, synchronize, reopened]

# 3. Ensure correct permissions
permissions:
  contents: read
  pull-requests: write
  statuses: write
```

### Issue: Merge Conflicts Not Detected

**Possible Causes:**
- Git index not reset after test copy
- Merge check skipped via environment variable

**Solutions:**
```bash
# Don't set this variable (it skips merge check)
# PR_VALIDATION_SKIP_MERGE=true

# Ensure git reset runs after test copy (automatic in latest version)
```

### Issue: Setup Commands Failing

**Common Problems:**
```yaml
# ❌ Wrong: Commands run in separate shells
setup:
  commands:
    - "cd backend"
    - "npm install"  # Runs in original directory!

# ✅ Correct: Chain commands
setup:
  commands:
    - "cd backend && npm install"

# ✅ Alternative: Use working directory
setup:
  commands:
    - "npm install"
  # Note: All commands run in repo root by default
```

### Issue: Tests Timeout

**Solutions:**
```yaml
# Increase timeout
tests:
  timeout_seconds: 1800  # 30 minutes

# Or optimize tests
tests:
  command: "pytest -q --maxfail=1 -n auto"  # Parallel execution
```

### Debug Mode

Enable detailed logging:
```bash
# In your workflow
- name: Run PR validation agent
  uses: karthik2oo4-git/POC_PR_AUTOMATION@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    RUNNER_DEBUG: 1  # Enable debug logging
```

---

## 🔬 Technical Details

### For Developers

#### Test Discovery Algorithm

Uses Python AST (Abstract Syntax Tree) parsing to extract test identifiers:

```python
# Discovers:
def test_add():           # → "test_add"
    pass

class TestCalculator:
    def test_add(self):   # → "TestCalculator::test_add"
        pass
```

#### Test Identifier Structure

```python
@dataclass(frozen=True)
class TestIdentifier:
    file_path: str  # "tests/test_calc.py"
    test_name: str  # "test_add" or "TestCalculator::test_add"
```

Two tests are considered identical if both `file_path` AND `test_name` match.

#### Set Operations

```python
# Compute new tests
new_tests = pr_tests - base_tests  # Set difference

# Build final set
final_tests = base_tests | new_tests  # Set union
```

#### Performance Characteristics

- **Test discovery:** O(n) where n = number of test files
- **Set operations:** O(m) where m = number of tests
- **File preparation:** O(k) where k = number of unique test files
- **Typical overhead:** < 5 seconds for 100 tests

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Pull Request                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions Workflow                         │
│           (.github/workflows/pr-validation.yml)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 Composite Action (action.yml)                │
│  - Installs uv (Python package manager)                     │
│  - Installs Python                                           │
│  - Syncs dependencies                                        │
│  - Runs pr-validation-ci command                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         Python Validation Runner (runner.py)                 │
│  1. Load configuration                                       │
│  2. Get PR context from GitHub                              │
│  3. Discover base tests (Set A)                             │
│  4. Discover PR tests (Set B)                               │
│  5. Compute new tests (N = B - A)                           │
│  6. Build final test set (A ∪ N)                            │
│  7. Prepare test environment                                │
│  8. Run setup commands                                      │
│  9. Run tests                                               │
│  10. Check for merge conflicts                              │
│  11. Post results comment                                   │
│  12. Set final status (success/failure)                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub API Updates                        │
│  - Commit status (✅ or ❌)                                  │
│  - PR comment (detailed results)                            │
│  - Labels (test-failed, ready-for-review, etc.)             │
└─────────────────────────────────────────────────────────────┘
```

### Deep Dive Documentation

For comprehensive technical documentation, see:
- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** - Complete code flow, architecture, and troubleshooting
- **[TEST_SELECTION_GUIDE.md](TEST_SELECTION_GUIDE.md)** - Detailed explanation of intelligent test selection algorithm

---

## 🆕 Recent Updates

### Version 2.0 - Intelligent Test Selection (Latest)

**Major Features:**
- ✨ **Intelligent test selection** using set theory (A ∪ N)
- ✨ **Support for new tests in PRs** while maintaining integrity
- ✨ **AST-based test discovery** for accurate test identification
- ✨ **File-level granularity** for efficient test copying

**Bug Fixes:**
- 🐛 Fixed issue where new tests couldn't be added in PRs
- 🐛 Improved handling of renamed test files
- 🐛 Better error messages for test discovery failures

**Breaking Changes:**
- None - fully backward compatible

### Version 1.0 - Initial Release

**Features:**
- ✅ Test integrity protection (copy all tests from base)
- ✅ Setup command execution
- ✅ Merge conflict detection
- ✅ PR commenting and labeling
- ✅ Branch protection integration

---

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
```yaml
tests:
  command: "pytest tests/ integration/"  # Multiple paths
```

### Python Version Matrix
```yaml
jobs:
  validate:
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11"]
    steps:
      - uses: karthik2oo4-git/POC_PR_AUTOMATION@main
        with:
          python-version: ${{ matrix.python-version }}
```

---

## 📚 Documentation

- **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** - Detailed technical documentation with code flow, architecture, and troubleshooting
- **[TEST_SELECTION_GUIDE.md](TEST_SELECTION_GUIDE.md)** - Deep dive into intelligent test selection algorithm
- **[configs/pr-validation.example.yml](configs/pr-validation.example.yml)** - Example configuration file

---

## 🏗️ Project Structure

```
.
├── .github/workflows/          # Example workflow
├── src/pr_validation_agent/    # Python source code
│   ├── ci/runner.py           # Main validation logic
│   ├── test_selector.py       # Intelligent test selection
│   ├── github.py              # GitHub API integration
│   ├── comments.py            # Comment templates
│   ├── config.py              # Configuration schema
│   └── models.py              # Data models
├── tests/                      # Unit tests
├── action.yml                  # Composite action definition
├── Dockerfile                  # Optional container packaging
└── pyproject.toml             # Python project metadata
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests: `uv run pytest`
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

**Development Setup:**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/karthik2oo4-git/POC_PR_AUTOMATION.git
cd POC_PR_AUTOMATION

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```

---

## 📝 License

This project is open source and available under the MIT License.

---

## 🙋 Support

- **Issues:** [GitHub Issues](https://github.com/karthik2oo4-git/POC_PR_AUTOMATION/issues)
- **Discussions:** [GitHub Discussions](https://github.com/karthik2oo4-git/POC_PR_AUTOMATION/discussions)
- **Documentation:** See [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for detailed guidance

---

## 🌟 Why Use This?

### For Teams
- ✅ **Enforce quality standards** automatically
- ✅ **Reduce code review burden** - automated checks catch common issues
- ✅ **Prevent regressions** - all tests must pass before merge
- ✅ **Improve test coverage** - encourages adding tests with new features

### For Developers
- ✅ **Fast feedback** - know immediately if code works
- ✅ **Clear error messages** - easy to understand what went wrong
- ✅ **No manual testing** - automated validation on every push
- ✅ **Confidence in merges** - know your code won't break production

### For Security
- ✅ **Tamper-proof tests** - impossible to hide bugs by modifying tests
- ✅ **Audit trail** - all validation results logged in PR comments
- ✅ **Consistent enforcement** - same rules apply to everyone

---

**Made with ❤️ for better code quality**

*Powered by intelligent test selection and tamper-proof validation*
