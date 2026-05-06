"""Test selection logic for PR validation with integrity checks."""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Set


@dataclass(frozen=True)
class TestIdentifier:
    """Unique identifier for a test case."""
    
    file_path: str  # Relative path from repo root
    test_name: str  # Function/method name
    
    def __str__(self) -> str:
        return f"{self.file_path}::{self.test_name}"
    
    def __hash__(self) -> int:
        return hash((self.file_path, self.test_name))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TestIdentifier):
            return False
        return self.file_path == other.file_path and self.test_name == other.test_name


class TestDiscovery:
    """Discovers test cases from Python test files."""
    
    @staticmethod
    def extract_test_functions(file_path: Path) -> list[str]:
        """Extract test function names from a Python file using AST parsing."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            
            test_names = []
            for node in ast.walk(tree):
                # Find test functions (def test_*)
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    test_names.append(node.name)
                # Find test methods in classes (class Test*)
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                            test_names.append(f"{node.name}::{item.name}")
            
            return test_names
        except Exception:
            # If parsing fails, return empty list (file might not be valid Python)
            return []
    
    @staticmethod
    def discover_tests(test_dir: Path, repo_root: Path) -> Set[TestIdentifier]:
        """Discover all test identifiers in a directory."""
        test_identifiers: Set[TestIdentifier] = set()
        
        if not test_dir.exists():
            return test_identifiers
        
        # Find all test files matching pytest patterns
        test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))
        
        for test_file in test_files:
            # Get relative path from repo root
            try:
                rel_path = test_file.relative_to(repo_root)
            except ValueError:
                # File is outside repo root, skip
                continue
            
            # Extract test functions
            test_functions = TestDiscovery.extract_test_functions(test_file)
            
            # Create identifiers
            for test_func in test_functions:
                test_identifiers.add(TestIdentifier(
                    file_path=str(rel_path),
                    test_name=test_func
                ))
        
        return test_identifiers


class TestSelector:
    """
    Selects which tests to run based on base and PR branch comparison.
    
    Implements intelligent test selection with integrity protection using set theory.
    Prevents PRs from hiding bugs by ensuring base tests always run with their
    original implementation.
    """
    
    def __init__(self, repo_root: Path, test_paths: list[str]):
        """
        Initialize test selector.
        
        Args:
            repo_root: Root directory of the repository
            test_paths: List of test directory paths (e.g., ["tests/", "test/"])
        
        Raises:
            ValueError: If repo_root doesn't exist or test_paths is empty
        """
        if not repo_root.exists():
            raise ValueError(f"Repository root does not exist: {repo_root}")
        if not test_paths:
            raise ValueError("At least one test path must be provided")
        
        self.repo_root = repo_root
        self.test_paths = test_paths
        self.discovery = TestDiscovery()
    
    def get_base_tests(self, base_ref: str) -> Set[TestIdentifier]:
        """
        Get all test identifiers from the base branch (Set A).
        
        This discovers what tests exist in the base branch, which forms the
        foundation of our test integrity system. These tests MUST always run
        using their base branch version to prevent PRs from hiding bugs.
        
        Process:
        1. Temporarily checkout base branch
        2. Discover all test functions/methods
        3. Restore original branch
        4. Return set A (base tests)
        
        Args:
            base_ref: Base branch reference (e.g., "main", "develop")
        
        Returns:
            Set A: All test identifiers from base branch
        """
        all_base_tests: Set[TestIdentifier] = set()
        
        # Save current state to restore later
        current_head = self._get_current_head()
        
        try:
            # Fetch latest base branch and checkout (detached HEAD)
            self._run_git(["fetch", "origin", base_ref])
            self._run_git(["checkout", f"origin/{base_ref}", "--detach"])
            
            # Discover tests in each configured test path
            for test_path in self.test_paths:
                test_dir = self.repo_root / test_path.rstrip("/")
                tests = self.discovery.discover_tests(test_dir, self.repo_root)
                all_base_tests.update(tests)
        
        finally:
            # CRITICAL: Always restore original state, even if discovery fails
            self._run_git(["checkout", current_head])
        
        return all_base_tests
    
    def get_pr_tests(self) -> Set[TestIdentifier]:
        """
        Get all test identifiers from the current PR branch (Set B).
        
        This discovers what tests exist in the PR branch. By comparing with
        base tests (Set A), we can identify:
        - New tests: N = B - A (tests added in PR)
        - Modified tests: B ∩ A (tests that exist in both but may be changed)
        - Deleted tests: A - B (tests removed in PR)
        
        Returns:
            Set B: All test identifiers from PR branch
        """
        all_pr_tests: Set[TestIdentifier] = set()
        
        # Discover tests in each configured test path (from current working directory)
        for test_path in self.test_paths:
            test_dir = self.repo_root / test_path.rstrip("/")
            tests = self.discovery.discover_tests(test_dir, self.repo_root)
            all_pr_tests.update(tests)
        
        return all_pr_tests
    
    def compute_new_tests(
        self,
        base_tests: Set[TestIdentifier],
        pr_tests: Set[TestIdentifier]
    ) -> Set[TestIdentifier]:
        """
        Compute new tests introduced in the PR (Set N).
        
        Set Theory: N = B - A
        - Tests that exist in PR (B) but not in base (A)
        - These are genuinely new tests added by the PR
        - We'll use the PR version of these test files
        
        Note: This does NOT include modified tests. Modified tests are in B ∩ A,
        and we'll use the BASE version of those files for integrity.
        
        Edge Cases Handled:
        - Empty base_tests: All PR tests are new (N = B)
        - Empty pr_tests: No new tests (N = ∅)
        - Renamed tests: Treated as delete + add (old in A-B, new in B-A)
        
        Args:
            base_tests: Test identifiers from base branch (Set A)
            pr_tests: Test identifiers from PR branch (Set B)
        
        Returns:
            Set N: New tests (B - A)
        """
        return pr_tests - base_tests
    
    def build_final_test_set(
        self,
        base_tests: Set[TestIdentifier],
        new_tests: Set[TestIdentifier]
    ) -> Set[TestIdentifier]:
        """
        Build the final set of tests to run (A ∪ N).
        
        Set Theory Logic:
        - A = base branch tests (ALWAYS included for integrity)
        - N = new tests in PR (B - A)
        - Final = A ∪ N
        
        Special Cases:
        1. If N is empty (no new tests) → run only A
           - PR only modifies code or existing tests
           - Base tests ensure no regressions
        
        2. If N is non-empty → run A ∪ N
           - Run all base tests (A) for integrity
           - Run new tests (N) to validate new functionality
        
        3. If A is empty (no base tests) → run only N
           - New repository or first tests being added
           - Nothing to protect, just run new tests
        
        Why always include A:
        - Prevents PRs from hiding bugs by deleting/modifying tests
        - Ensures all existing functionality still works
        - Even if PR deletes tests, we still run them from base
        
        Edge Cases Handled:
        - Empty A and empty N: Returns empty set (no tests to run)
        - Empty A, non-empty N: Returns N (new repo scenario)
        - Non-empty A, empty N: Returns A (code-only changes)
        - Non-empty A and N: Returns A ∪ N (normal case)
        
        Args:
            base_tests: Test identifiers from base branch (Set A)
            new_tests: New test identifiers from PR (Set N = B - A)
        
        Returns:
            Final set of tests to execute (A ∪ N)
        """
        # Edge case: No base tests (new repository or first tests)
        if not base_tests:
            return new_tests
        
        # Edge case: No new tests (code-only or test modification)
        if not new_tests:
            return base_tests
        
        # Normal case: Union of base and new tests
        return base_tests | new_tests
    
    def prepare_test_environment(
        self,
        base_ref: str,
        final_tests: Set[TestIdentifier],
        base_tests: Set[TestIdentifier]
    ) -> Path:
        """
        Prepare a test directory with the correct test files.
        
        CRITICAL LOGIC - Test Integrity Protection:
        ============================================
        This method implements the core security feature: preventing PRs from
        hiding bugs by modifying both code AND tests.
        
        Strategy (Set Theory: A ∪ N):
        - A = base branch tests (always use base version of test file)
        - N = new tests in PR (use PR version of test file)
        - Final = A ∪ N
        
        File-Level Granularity:
        - If a test file contains ANY test from set A → use BASE version of entire file
        - If a test file contains ONLY tests from set N → use PR version of entire file
        - This means: adding new tests to existing files will NOT include them
          (limitation of file-level granularity, but ensures integrity)
        
        Why git show instead of git checkout:
        - Avoids modifying working directory (no side effects)
        - No need to restore files afterward (no race conditions)
        - Safer and more reliable
        
        Args:
            base_ref: Base branch reference (e.g., "main")
            final_tests: Final set of tests to run (A ∪ N)
            base_tests: Set of base branch tests (set A)
        
        Returns:
            Path to the prepared test directory
        """
        import sys
        import tempfile
        
        # Create temporary directory for isolated test execution
        temp_dir = Path(tempfile.mkdtemp(prefix="pr_validation_tests_"))
        print(f"\nPreparing test environment in: {temp_dir}", file=sys.stderr)
        
        # Group tests by file for efficient processing
        tests_by_file: dict[str, list[str]] = {}
        for test in final_tests:
            if test.file_path not in tests_by_file:
                tests_by_file[test.file_path] = []
            tests_by_file[test.file_path].append(test.test_name)
        
        # Process each test file
        for file_path, test_names in tests_by_file.items():
            # CRITICAL DECISION: Which version of the file to use?
            # If ANY test in this file is from base (set A) → use BASE version
            # This ensures test integrity: can't modify tests to hide bugs
            has_base_test = any(
                TestIdentifier(file_path, name) in base_tests
                for name in test_names
            )
            
            dest_file = temp_dir / file_path
            
            # Create parent directories
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            if has_base_test:
                # Use BASE version of the file (from base branch)
                # This is the KEY security feature: PR cannot modify these tests
                print(f"  Using BASE version: {file_path} (contains {len([n for n in test_names if TestIdentifier(file_path, n) in base_tests])} base test(s))", file=sys.stderr)
                
                # Use 'git show' to read file content without modifying working directory
                # Format: git show <ref>:<path>
                result = self._run_git(["show", f"origin/{base_ref}:{file_path}"])
                
                if result.returncode == 0:
                    # Successfully retrieved base version
                    try:
                        dest_file.write_text(result.stdout, encoding="utf-8")
                        print(f"  ✓ Copied base version of {file_path} ({len(result.stdout)} bytes)", file=sys.stderr)
                        
                        # Debug: Show first few lines to verify content
                        try:
                            lines = result.stdout.split('\n')[:5]
                            print(f"  DEBUG: First 5 lines of base version:", file=sys.stderr)
                            for i, line in enumerate(lines, 1):
                                print(f"    {i}: {line}", file=sys.stderr)
                        except Exception:
                            pass
                    except Exception as write_error:
                        print(f"  ⚠️  Error writing base version to {dest_file}: {write_error}", file=sys.stderr)
                        raise
                else:
                    # File doesn't exist in base branch
                    # This can happen if:
                    # 1. Test file was renamed (old name in base, new name in PR)
                    # 2. Git history issue
                    # 3. File path mismatch
                    print(f"  ⚠️  Warning: Could not retrieve base version of {file_path}", file=sys.stderr)
                    print(f"  Git error: {result.stderr}", file=sys.stderr)
                    
                    # Edge case handling: Fall back to PR version as last resort
                    # This is not ideal but prevents complete failure
                    source_file = self.repo_root / file_path
                    if source_file.exists():
                        import shutil
                        try:
                            shutil.copy2(source_file, dest_file)
                            print(f"  ⚠️  Falling back to PR version (integrity may be compromised)", file=sys.stderr)
                        except Exception as copy_error:
                            print(f"  ⚠️  Error copying PR version: {copy_error}", file=sys.stderr)
                            raise
                    else:
                        # File doesn't exist in either branch - this is a critical error
                        error_msg = f"Test file {file_path} not found in base or PR branch"
                        print(f"  ❌ {error_msg}", file=sys.stderr)
                        raise FileNotFoundError(error_msg)
            else:
                # Use PR version (new test file, only contains tests from set N)
                print(f"  Using PR version: {file_path} (new test file with {len(test_names)} new test(s))", file=sys.stderr)
                source_file = self.repo_root / file_path
                if source_file.exists():
                    import shutil
                    try:
                        shutil.copy2(source_file, dest_file)
                        print(f"  ✓ Copied PR version of {file_path}", file=sys.stderr)
                    except Exception as copy_error:
                        print(f"  ⚠️  Error copying PR file: {copy_error}", file=sys.stderr)
                        raise
                else:
                    # New test file doesn't exist - this shouldn't happen
                    error_msg = f"New test file {file_path} not found in PR branch"
                    print(f"  ❌ {error_msg}", file=sys.stderr)
                    raise FileNotFoundError(error_msg)
        
        print(f"\n✓ Test environment prepared with {len(tests_by_file)} test file(s)", file=sys.stderr)
        
        # Verify at least one file was copied
        copied_files = list(temp_dir.rglob("*.py"))
        if not copied_files:
            error_msg = "No test files were copied to temp directory"
            print(f"❌ {error_msg}", file=sys.stderr)
            raise RuntimeError(error_msg)
        
        print(f"✓ Verified: {len(copied_files)} Python file(s) in temp directory", file=sys.stderr)
        return temp_dir
    
    def _get_current_head(self) -> str:
        """Get current HEAD commit SHA."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    
    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git"] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False
        )

# Made with Bob
