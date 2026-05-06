# PR Validation Agent - Implementation Guide

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Complete Code Flow](#complete-code-flow)
4. [Key Components Explained](#key-components-explained)
5. [Configuration Guide](#configuration-guide)
6. [How It Works - Step by Step](#how-it-works---step-by-step)
7. [Common Scenarios](#common-scenarios)
8. [Troubleshooting](#troubleshooting)

---

## Project Overview

### What Does This Do?
This is an automated PR validation system that runs on GitHub Actions. When someone creates a pull request, it automatically:
- Copies test files from the base branch (prevents test tampering)
- Runs tests on the PR code
- Checks for merge conflicts
- Posts results as comments on the PR
- Blocks or allows merge based on results

### Why Is This Important?
- **Prevents bad code from being merged** - Tests must pass before merge
- **Prevents test tampering** - Developers can't modify tests to hide bugs
- **Automated quality control** - No manual review needed for basic checks
- **Fast feedback** - Developers know immediately if their code works

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Pull Request                       │
│                  (Developer creates PR)                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions Workflow Triggered               │
│           (.github/workflows/pr-validation.yml)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 Composite Action (action.yml)                │
│  - Installs uv (Python package manager)                     │
│  - Installs Python 3.11                                      │
│  - Syncs dependencies                                        │
│  - Runs pr-validation-ci command                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         Python Validation Runner (runner.py)                 │
│                                                              │
│  1. Load configuration                                       │
│  2. Get PR context from GitHub                              │
│  3. Set status to "pending"                                 │
│  4. Copy tests from base branch                             │
│  5. Run setup commands                                      │
│  6. Run tests                                               │
│  7. Check for merge conflicts                               │
│  8. Post results comment                                    │
│  9. Set final status (success/failure)                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub API Updates                        │
│  - Commit status (✅ or ❌)                                  │
│  - PR comment (detailed results)                            │
│  - Labels (test-failed, ready-for-review, etc.)             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Branch Protection Decision                      │
│  - If status = success → Enable merge button                │
│  - If status = failure → Block merge button                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Complete Code Flow

### Phase 1: Initialization

**File: `src/pr_validation_agent/ci/runner.py`**

```python
def validate() -> ValidationResult:
    # Step 1: Get current working directory
    cwd = Path.cwd()
    
    # Step 2: Load configuration from YAML file
    config = AppConfig.load(os.getenv("PR_VALIDATION_CONFIG", ".github/pr-validation.yml"))
    
    # Step 3: Create GitHub API client
    github = GitHubClient.from_env()
    
    # Step 4: Load PR context (PR number, author, branches, etc.)
    pr = github.load_pr_context_from_event(_load_event())
    
    # Step 5: Set initial status to "pending"
    github.set_status(pr, ValidationState.PENDING, "PR validation started", config)
```

**What Happens:**
1. Reads environment variables (`GITHUB_TOKEN`, `GITHUB_EVENT_PATH`, etc.)
2. Loads YAML configuration file
3. Extracts PR metadata (author, branch names, SHA, etc.)
4. Posts "pending" status to GitHub (shows yellow circle on PR)

---

### Phase 2: Test Integrity (Copy Tests from Base)

**File: `src/pr_validation_agent/ci/runner.py`**

```python
def copy_tests_from_base(cwd: Path, pr: PullRequestContext, config: AppConfig):
    # Step 1: Configure git
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git config user.name "github-actions[bot]"
    
    # Step 2: Fetch base branch
    git fetch origin main
    
    # Step 3: Extract test directory from config
    # Example: "pytest tests/" → test_paths = ["tests/"]
    
    # Step 4: Copy test files from base branch
    git checkout origin/main -- tests/
    
    # Step 5: Reset git index (keep files, unstage changes)
    git reset HEAD
```

**Why This Matters:**
```
Scenario: Developer tries to hide a bug

Base branch (main):
├── calculator.py: def add(a, b): return a + b
└── test_calculator.py: assert add(2, 3) == 5  ✅

PR branch (malicious):
├── calculator.py: def add(a, b): return a * b  ❌ BUG!
└── test_calculator.py: assert add(2, 3) == 6  ❌ Modified test!

Without test copy:
- PR tests run: assert add(2, 3) == 6
- PR code: 2 * 3 = 6
- Result: PASS ✅ (but code is wrong!)

With test copy:
- Base tests run: assert add(2, 3) == 5
- PR code: 2 * 3 = 6
- Result: FAIL ❌ (bug caught!)
```

---

### Phase 3: Setup Commands

**File: `src/pr_validation_agent/ci/runner.py`**

```python
def run_setup(config: AppConfig, cwd: Path) -> TestRunResult | None:
    # Example setup commands from config:
    # - "uv sync --frozen"
    # - "npm install"
    # - "pip install -r requirements.txt"
    
    for command in config.setup.commands:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            timeout=config.setup.timeout_seconds
        )
        
        if result.returncode != 0:
            # Setup failed! Return failure result
            return TestRunResult(
                command=command,
                exit_code=result.returncode,
                passed=False,
                stdout=result.stdout,
                stderr=result.stderr
            )
    
    # All setup commands passed
    return TestRunResult(passed=True, ...)
```

**What This Does:**
- Installs dependencies
- Sets up the environment
- Prepares for test execution
- If any setup command fails, validation stops immediately

---

### Phase 4: Run Tests

**File: `src/pr_validation_agent/ci/runner.py`**

```python
def run_tests(config: AppConfig, cwd: Path) -> TestRunResult:
    # Run test command from config
    # Example: "pytest -q --maxfail=1"
    
    result = subprocess.run(
        config.tests.command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        timeout=config.tests.timeout_seconds
    )
    
    # Capture output
    stdout = result.stdout
    stderr = result.stderr
    
    # Truncate if too large
    stdout, stderr = _truncate_log(stdout, stderr, config.tests.log_max_bytes)
    
    # Save to log file
    log_path = cwd / ".pr-validation-test.log"
    log_path.write_text(f"{stdout}\n{stderr}")
    
    return TestRunResult(
        command=config.tests.command,
        exit_code=result.returncode,
        passed=(result.returncode == 0),
        stdout=stdout,
        stderr=stderr,
        log_path=str(log_path)
    )
```

**Test Execution Flow:**
```
1. Execute: pytest -q --maxfail=1
2. Capture output:
   ├── stdout: Test results
   └── stderr: Error messages
3. Check exit code:
   ├── 0 = All tests passed ✅
   └── Non-zero = Tests failed ❌
4. Save logs to file
5. Return result
```

---

### Phase 5: Merge Conflict Check

**File: `src/pr_validation_agent/ci/runner.py`**

```python
def merge_base_into_head(cwd: Path, pr: PullRequestContext):
    # Only runs if tests passed!
    
    # Step 1: Configure git
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git config user.name "github-actions[bot]"
    
    # Step 2: Fetch latest base branch
    git fetch origin main
    
    # Step 3: Try to merge base into current branch
    git merge --no-edit --no-ff origin/main
    
    # Step 4: Check result
    if merge_failed:
        return (False, merge_output)  # Conflict detected
    else:
        return (True, merge_output)   # Clean merge
```

**Merge Conflict Scenarios:**

```
Scenario 1: Clean Merge
Base:    A---B---C (main)
PR:           \---D---E (feature)
Merge:   A---B---C---M (merged successfully)
Result: ✅ No conflicts

Scenario 2: Conflict
Base:    A---B---C (main, modified calculator.py)
PR:           \---D (feature, also modified calculator.py)
Merge:   CONFLICT in calculator.py
Result: ❌ Merge conflict detected
```

---

### Phase 6: Result Handling

**File: `src/pr_validation_agent/ci/runner.py`**

```python
# If setup fails:
if setup_result is not None and not setup_result.passed:
    body = render_test_failure_comment(
        marker=config.comments.marker,
        author=pr.author,
        test_result=setup_result,
        phase="setup"
    )
    github.upsert_comment(pr, config.comments.marker, body)
    github.set_status(pr, ValidationState.FAILURE, "Repository setup failed", config)
    return ValidationResult(state=FAILURE, reason="Repository setup failed")

# If tests fail:
if not test_result.passed:
    body = render_test_failure_comment(...)
    github.upsert_comment(pr, config.comments.marker, body)
    github.set_status(pr, ValidationState.FAILURE, "Tests failed", config)
    return ValidationResult(state=FAILURE, reason="Tests failed")

# If merge conflicts:
if not merged:
    body = render_merge_conflict_comment(...)
    github.upsert_comment(pr, config.comments.marker, body)
    github.set_status(pr, ValidationState.FAILURE, "Base branch merge failed", config)
    return ValidationResult(state=FAILURE, reason="Merge conflict")

# If everything passes:
body = render_success_comment(marker=config.comments.marker)
github.upsert_comment(pr, config.comments.marker, body)
github.set_status(pr, ValidationState.SUCCESS, "All checks passed", config)
return ValidationResult(state=SUCCESS)
```

---

## Key Components Explained

### 1. Configuration System

**File: `src/pr_validation_agent/config.py`**

```python
class AppConfig(BaseModel):
    status: StatusConfig          # Commit status settings
    setup: SetupConfig           # Setup commands
    tests: TestsConfig           # Test command and timeout
    labels: LabelsConfig         # PR labels
    comments: CommentsConfig     # Comment settings
    auto_merge: AutoMergeConfig  # Auto-merge settings
```

**Example Configuration:**
```yaml
version: 1

status:
  context: "pr-unit-test-validation"  # Status check name

tests:
  command: "pytest -q --maxfail=1"    # Test command
  timeout_seconds: 900                # 15 minutes max

setup:
  commands:
    - "uv sync --frozen"              # Install dependencies

labels:
  enabled: true
  test_failed: "test-failed"
  ready_for_review: "ready-for-review"
  merge_conflict: "merge-conflict"
```

---

### 2. GitHub API Integration

**File: `src/pr_validation_agent/github.py`**

```python
class GitHubClient:
    def set_status(self, pr, state, description, config):
        """Posts commit status to GitHub"""
        POST /repos/{owner}/{repo}/statuses/{sha}
        {
            "state": "success" | "failure" | "pending",
            "context": "pr-unit-test-validation",
            "description": "All checks passed"
        }
    
    def upsert_comment(self, pr, marker, body):
        """Updates or creates PR comment"""
        # Find existing bot comment with marker
        # If found: UPDATE comment
        # If not found: CREATE new comment
    
    def apply_outcome_label(self, pr, config, label):
        """Manages PR labels"""
        # Remove stale labels (test-failed, merge-conflict)
        # Add new label (ready-for-review)
```

---

### 3. Comment Rendering

**File: `src/pr_validation_agent/comments.py`**

**Success Comment:**
```markdown
<!-- pr-validation-agent:summary -->
✅ All configured setup and unit-test checks passed.

GitHub can now allow merge when this workflow is marked as a required status check in branch protection.
```

**Failure Comment:**
```markdown
<!-- pr-validation-agent:summary -->
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

---

## How It Works - Step by Step

### Complete Example: PR with Bug

**Initial State:**
```
Repository: calculator-app
Base branch: main
PR branch: feature/new-calculation
Author: john-doe
```

**Step 1: PR Created**
```
John creates PR: feature/new-calculation → main
GitHub triggers workflow
```

**Step 2: Workflow Starts**
```yaml
# .github/workflows/pr-validation.yml runs
- Checkout PR branch (feature/new-calculation)
- Install uv, Python, dependencies
- Run pr-validation-ci command
```

**Step 3: Validation Begins**
```
✓ Load config from .github/pr-validation.yml
✓ Get PR context (number: 42, author: john-doe)
✓ Set status: PENDING "PR validation started"
```

**Step 4: Copy Tests**
```
✓ Fetch origin/main
✓ Copy tests/ from main branch
✓ Reset git index
Result: Tests from main are now in working directory
```

**Step 5: Run Setup**
```
$ uv sync --frozen
Installing dependencies...
✓ Setup completed in 15.3s
```

**Step 6: Run Tests**
```
$ pytest -q --maxfail=1
F
FAILED tests/test_calculator.py::test_add - AssertionError: assert 6 == 5
Exit code: 1
```

**Step 7: Handle Failure**
```
✓ Post comment to PR #42
✓ Add label: test-failed
✓ Set status: FAILURE "Tests failed"
✓ Merge button: DISABLED ❌
```

**Step 8: Developer Fixes**
```
John fixes the bug: a*b → a+b
John pushes fix
Workflow runs again automatically
```

**Step 9: Validation Passes**
```
$ pytest -q --maxfail=1
.
1 passed in 0.05s
Exit code: 0

✓ Tests passed
✓ Check merge conflicts
✓ No conflicts found
✓ Post success comment
✓ Add label: ready-for-review
✓ Set status: SUCCESS
✓ Merge button: ENABLED ✅
```

---

## Common Scenarios

### Scenario 1: Test Failure

**What Happens:**
1. Tests run and fail
2. Comment posted with error details
3. Label "test-failed" added
4. Status set to FAILURE
5. Merge button disabled

**Developer Action:**
- Fix the failing test
- Push changes
- Validation runs automatically

---

### Scenario 2: Merge Conflict

**What Happens:**
1. Tests pass ✅
2. Try to merge base branch
3. Conflict detected in file
4. Comment posted with conflict details
5. Label "merge-conflict" added
6. Status set to FAILURE
7. Merge button disabled

**Developer Action:**
- Pull latest main branch locally
- Resolve conflicts
- Push resolved changes
- Validation runs automatically

---

### Scenario 3: Setup Failure

**What Happens:**
1. Setup command fails (e.g., dependency error)
2. Comment posted with setup error
3. Tests are NOT run (no point)
4. Status set to FAILURE
5. Merge button disabled

**Developer Action:**
- Fix dependency issue
- Update requirements/package.json
- Push changes
- Validation runs automatically

---

### Scenario 4: Test Tampering Attempt

**What Happens:**
```
Developer modifies test to hide bug:
- Changes: assert add(2,3) == 5 → assert add(2,3) == 6
- Implements: def add(a,b): return a*b (wrong!)

Validation process:
1. Copy tests from base (original test restored)
2. Run base test: assert add(2,3) == 5
3. PR code: 2*3 = 6
4. Test fails! ❌
5. Bug caught despite tampering attempt
```

---

## Troubleshooting

### Issue: Tests pass locally but fail in CI

**Possible Causes:**
1. Different Python version
2. Missing dependencies
3. Environment variables not set
4. Different test data

**Solution:**
- Check Python version in action.yml
- Verify all dependencies in pyproject.toml
- Add required env vars to workflow
- Ensure test data is committed

---

### Issue: Merge conflicts not detected

**Possible Causes:**
1. Git index not reset after test copy
2. Merge check skipped

**Solution:**
- Ensure `git reset HEAD` runs after test copy
- Check PR_VALIDATION_SKIP_MERGE is not set

---

### Issue: Status check not appearing

**Possible Causes:**
1. Wrong status context name
2. Workflow not triggered
3. Permissions issue

**Solution:**
- Verify status.context in config matches branch protection
- Check workflow triggers in .github/workflows/
- Ensure GITHUB_TOKEN has correct permissions

---

## Summary

This PR validation system provides:
- ✅ Automated quality control
- ✅ Test integrity (prevents tampering)
- ✅ Merge conflict detection
- ✅ Fast feedback to developers
- ✅ GitHub-native integration
- ✅ Configurable and extensible

**Key Innovation:**
Tests are copied from the base branch before running, ensuring developers cannot modify tests to hide bugs in their PRs.