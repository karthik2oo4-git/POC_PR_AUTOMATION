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
    """Selects which tests to run based on base and PR branch comparison."""
    
    def __init__(self, repo_root: Path, test_paths: list[str]):
        """
        Initialize test selector.
        
        Args:
            repo_root: Root directory of the repository
            test_paths: List of test directory paths (e.g., ["tests/", "test/"])
        """
        self.repo_root = repo_root
        self.test_paths = test_paths
        self.discovery = TestDiscovery()
    
    def get_base_tests(self, base_ref: str) -> Set[TestIdentifier]:
        """
        Get all test identifiers from the base branch.
        
        Args:
            base_ref: Base branch reference (e.g., "main")
        
        Returns:
            Set of test identifiers from base branch
        """
        all_base_tests: Set[TestIdentifier] = set()
        
        # Save current state
        current_head = self._get_current_head()
        
        try:
            # Fetch and checkout base branch
            self._run_git(["fetch", "origin", base_ref])
            self._run_git(["checkout", f"origin/{base_ref}", "--detach"])
            
            # Discover tests in each test path
            for test_path in self.test_paths:
                test_dir = self.repo_root / test_path.rstrip("/")
                tests = self.discovery.discover_tests(test_dir, self.repo_root)
                all_base_tests.update(tests)
        
        finally:
            # Restore original state
            self._run_git(["checkout", current_head])
        
        return all_base_tests
    
    def get_pr_tests(self) -> Set[TestIdentifier]:
        """
        Get all test identifiers from the current PR branch.
        
        Returns:
            Set of test identifiers from PR branch
        """
        all_pr_tests: Set[TestIdentifier] = set()
        
        # Discover tests in each test path
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
        Compute new tests introduced in the PR.
        
        Args:
            base_tests: Test identifiers from base branch (set A)
            pr_tests: Test identifiers from PR branch (set B)
        
        Returns:
            New tests (N = B - A)
        """
        return pr_tests - base_tests
    
    def build_final_test_set(
        self,
        base_tests: Set[TestIdentifier],
        new_tests: Set[TestIdentifier]
    ) -> Set[TestIdentifier]:
        """
        Build the final set of tests to run.
        
        Logic:
        - If N is empty → run only A
        - If N is non-empty → run A ∪ N
        
        Args:
            base_tests: Test identifiers from base branch (set A)
            new_tests: New test identifiers from PR (set N)
        
        Returns:
            Final set of tests to execute
        """
        if not new_tests:
            return base_tests
        return base_tests | new_tests
    
    def prepare_test_environment(
        self,
        base_ref: str,
        final_tests: Set[TestIdentifier],
        base_tests: Set[TestIdentifier]
    ) -> Path:
        """
        Prepare a test directory with the correct test files.
        
        Strategy:
        1. Create temp directory for final tests
        2. Copy base test files for base tests
        3. Copy PR test files for new tests only
        
        Args:
            base_ref: Base branch reference
            final_tests: Final set of tests to run
            base_tests: Set of base branch tests (for efficiency)
        
        Returns:
            Path to the prepared test directory
        """
        import shutil
        import sys
        import tempfile
        
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix="pr_validation_tests_"))
        
        # Group tests by file
        tests_by_file: dict[str, list[str]] = {}
        for test in final_tests:
            if test.file_path not in tests_by_file:
                tests_by_file[test.file_path] = []
            tests_by_file[test.file_path].append(test.test_name)
        
        # Process each test file
        for file_path, test_names in tests_by_file.items():
            # Check if any test in this file is from base
            has_base_test = any(
                TestIdentifier(file_path, name) in base_tests
                for name in test_names
            )
            
            source_file = self.repo_root / file_path
            dest_file = temp_dir / file_path
            
            # Create parent directories
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            if has_base_test:
                # Use base version of the file
                print(f"  Using BASE version: {file_path}", file=sys.stderr)
                current_head = self._get_current_head()
                try:
                    # Checkout base version
                    result = self._run_git(["checkout", f"origin/{base_ref}", "--", file_path])
                    if result.returncode != 0:
                        print(f"  Warning: Could not checkout base version of {file_path}", file=sys.stderr)
                        print(f"  Git output: {result.stderr}", file=sys.stderr)
                    
                    if source_file.exists():
                        # Debug: Show first few lines of the file being copied
                        try:
                            with open(source_file, 'r') as f:
                                lines = f.readlines()[:5]
                                print(f"  DEBUG: First 5 lines of {file_path}:", file=sys.stderr)
                                for i, line in enumerate(lines, 1):
                                    print(f"    {i}: {line.rstrip()}", file=sys.stderr)
                        except Exception:
                            pass
                        
                        shutil.copy2(source_file, dest_file)
                        print(f"  ✓ Copied base version of {file_path}", file=sys.stderr)
                        
                        # Debug: Verify the copied file
                        if dest_file.exists():
                            print(f"  ✓ Verified: {dest_file} exists", file=sys.stderr)
                    else:
                        print(f"  Warning: Base file {file_path} does not exist after checkout", file=sys.stderr)
                finally:
                    # Restore PR version in working directory
                    self._run_git(["checkout", current_head, "--", file_path])
            else:
                # Use PR version (new test file)
                print(f"  Using PR version: {file_path} (new test file)", file=sys.stderr)
                if source_file.exists():
                    shutil.copy2(source_file, dest_file)
                    print(f"  ✓ Copied PR version of {file_path}", file=sys.stderr)
                else:
                    print(f"  Warning: PR file {file_path} does not exist", file=sys.stderr)
        
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
