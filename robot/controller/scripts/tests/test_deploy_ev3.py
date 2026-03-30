#!/usr/bin/env python3
"""
Unit tests for EV3 deployment script.

These tests verify the deployment script logic without requiring
an actual EV3 connection.
"""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deploy_ev3 import (
    should_exclude,
    get_files_to_deploy,
    prepare_deployment_package,
    create_launcher_script,
    EXCLUDE_PATTERNS,
)


class TestShouldExclude(unittest.TestCase):
    """Tests for the should_exclude function."""
    
    def test_exclude_git_directory(self):
        """Test that .git directory is excluded."""
        self.assertTrue(should_exclude(".git", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude(".git/config", EXCLUDE_PATTERNS))
    
    def test_exclude_test_files(self):
        """Test that test files are excluded."""
        self.assertTrue(should_exclude("test_main.py", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("main_test.py", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("tests/test_device.py", EXCLUDE_PATTERNS))
    
    def test_exclude_example_files(self):
        """Test that example files are excluded."""
        self.assertTrue(should_exclude("example_usage.py", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("terrain_scanner_example.py", EXCLUDE_PATTERNS))
    
    def test_exclude_documentation(self):
        """Test that documentation files are excluded."""
        self.assertTrue(should_exclude("README.md", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("CONTRIBUTING.md", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("docs/guide.md", EXCLUDE_PATTERNS))
    
    def test_exclude_pycache(self):
        """Test that __pycache__ directories are excluded."""
        self.assertTrue(should_exclude("__pycache__", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("module/__pycache__/file.pyc", EXCLUDE_PATTERNS))
    
    def test_exclude_venv(self):
        """Test that virtual environment directories are excluded."""
        self.assertTrue(should_exclude(".venv", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("venv", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude(".venv/lib/python3.10/site-packages", EXCLUDE_PATTERNS))
    
    def test_include_main_py(self):
        """Test that main.py is included."""
        self.assertFalse(should_exclude("main.py", EXCLUDE_PATTERNS))
    
    def test_include_module_files(self):
        """Test that module files are included."""
        self.assertFalse(should_exclude("ev3_devices/device_manager.py", EXCLUDE_PATTERNS))
        self.assertFalse(should_exclude("robot_controllers/ps4_controller.py", EXCLUDE_PATTERNS))
    
    def test_include_init_files(self):
        """Test that __init__.py files are included."""
        self.assertFalse(should_exclude("__init__.py", EXCLUDE_PATTERNS))
        self.assertFalse(should_exclude("ev3_devices/__init__.py", EXCLUDE_PATTERNS))
    
    def test_exclude_scripts_directory(self):
        """Test that scripts directory is excluded."""
        self.assertTrue(should_exclude("scripts/deploy_ev3.py", EXCLUDE_PATTERNS))
        self.assertTrue(should_exclude("scripts/", EXCLUDE_PATTERNS))


class TestGetFilesToDeploy(unittest.TestCase):
    """Tests for the get_files_to_deploy function."""
    
    def setUp(self):
        """Create a temporary directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Create test directory structure
        dirs = [
            "ev3_devices",
            "robot_controllers",
            "tests",
            "__pycache__",
            ".venv",
            "scripts",
        ]
        for d in dirs:
            os.makedirs(os.path.join(self.temp_dir, d), exist_ok=True)
        
        # Create test files
        files = [
            "main.py",
            "ev3_devices/__init__.py",
            "ev3_devices/device_manager.py",
            "robot_controllers/__init__.py",
            "robot_controllers/ps4_controller.py",
            "tests/test_main.py",
            "tests/__init__.py",
            "__pycache__/main.cpython-310.pyc",
            "README.md",
            "example_usage.py",
            "scripts/deploy_ev3.py",
        ]
        for f in files:
            filepath = os.path.join(self.temp_dir, f)
            with open(filepath, "w") as fp:
                fp.write("# test file")
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)
    
    def test_includes_main_py(self):
        """Test that main.py is included."""
        files = get_files_to_deploy(self.temp_dir)
        self.assertIn("main.py", files)
    
    def test_includes_module_files(self):
        """Test that module files are included."""
        files = get_files_to_deploy(self.temp_dir)
        self.assertIn("ev3_devices/__init__.py", files)
        self.assertIn("ev3_devices/device_manager.py", files)
        self.assertIn("robot_controllers/__init__.py", files)
        self.assertIn("robot_controllers/ps4_controller.py", files)
    
    def test_excludes_test_files(self):
        """Test that test files are excluded."""
        files = get_files_to_deploy(self.temp_dir)
        self.assertNotIn("tests/test_main.py", files)
        # tests/__init__.py should also be excluded since tests/ is excluded
        for f in files:
            self.assertFalse(f.startswith("tests/"))
    
    def test_excludes_pycache(self):
        """Test that __pycache__ is excluded."""
        files = get_files_to_deploy(self.temp_dir)
        for f in files:
            self.assertFalse("__pycache__" in f)
    
    def test_excludes_readme(self):
        """Test that README.md is excluded."""
        files = get_files_to_deploy(self.temp_dir)
        self.assertNotIn("README.md", files)
    
    def test_excludes_examples(self):
        """Test that example files are excluded."""
        files = get_files_to_deploy(self.temp_dir)
        self.assertNotIn("example_usage.py", files)
    
    def test_excludes_scripts(self):
        """Test that scripts directory is excluded."""
        files = get_files_to_deploy(self.temp_dir)
        for f in files:
            self.assertFalse(f.startswith("scripts/"))


class TestCreateLauncherScript(unittest.TestCase):
    """Tests for the create_launcher_script function."""
    
    def test_release_mode_uses_optimization(self):
        """Test that release mode launcher uses -O flag."""
        script = create_launcher_script("release")
        self.assertIn("python3 -O", script)
        self.assertIn("RELEASE MODE", script)
        self.assertIn("__debug__ = False", script)
    
    def test_debug_mode_no_optimization(self):
        """Test that debug mode launcher doesn't use -O flag."""
        script = create_launcher_script("debug")
        self.assertNotIn("python3 -O", script)
        self.assertIn("DEBUG MODE", script)
        self.assertIn("__debug__ = True", script)
    
    def test_launcher_is_executable_script(self):
        """Test that launcher script has proper shebang."""
        for mode in ["release", "debug"]:
            script = create_launcher_script(mode)
            self.assertTrue(script.startswith("#!/bin/bash"))
    
    def test_launcher_runs_main_py(self):
        """Test that launcher runs main.py."""
        for mode in ["release", "debug"]:
            script = create_launcher_script(mode)
            self.assertIn("main.py", script)


class TestPrepareDeploymentPackage(unittest.TestCase):
    """Tests for the prepare_deployment_package function."""
    
    def setUp(self):
        """Create a temporary source directory for testing."""
        self.source_dir = tempfile.mkdtemp()
        
        # Create minimal test structure
        os.makedirs(os.path.join(self.source_dir, "ev3_devices"), exist_ok=True)
        
        files = [
            "main.py",
            "ev3_devices/__init__.py",
            "ev3_devices/device_manager.py",
        ]
        for f in files:
            filepath = os.path.join(self.source_dir, f)
            with open(filepath, "w") as fp:
                fp.write("# test file\nprint('hello')")
    
    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.source_dir)
    
    def test_creates_temp_directory(self):
        """Test that a temp directory is created."""
        temp_dir, files = prepare_deployment_package(self.source_dir, "release")
        try:
            self.assertTrue(os.path.isdir(temp_dir))
        finally:
            shutil.rmtree(temp_dir)
    
    def test_copies_source_files(self):
        """Test that source files are copied."""
        temp_dir, files = prepare_deployment_package(self.source_dir, "release")
        try:
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "main.py")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "ev3_devices/__init__.py")))
        finally:
            shutil.rmtree(temp_dir)
    
    def test_creates_launcher_script(self):
        """Test that run.sh launcher is created."""
        temp_dir, files = prepare_deployment_package(self.source_dir, "release")
        try:
            launcher_path = os.path.join(temp_dir, "run.sh")
            self.assertTrue(os.path.exists(launcher_path))
            self.assertIn("run.sh", files)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_release_mode_launcher_content(self):
        """Test that release mode creates correct launcher."""
        temp_dir, files = prepare_deployment_package(self.source_dir, "release")
        try:
            with open(os.path.join(temp_dir, "run.sh")) as f:
                content = f.read()
            self.assertIn("python3 -O", content)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_debug_mode_launcher_content(self):
        """Test that debug mode creates correct launcher."""
        temp_dir, files = prepare_deployment_package(self.source_dir, "debug")
        try:
            with open(os.path.join(temp_dir, "run.sh")) as f:
                content = f.read()
            self.assertNotIn("python3 -O", content)
        finally:
            shutil.rmtree(temp_dir)


class TestExcludePatterns(unittest.TestCase):
    """Tests for the EXCLUDE_PATTERNS configuration."""
    
    def test_patterns_list_not_empty(self):
        """Test that exclude patterns are defined."""
        self.assertGreater(len(EXCLUDE_PATTERNS), 0)
    
    def test_common_patterns_present(self):
        """Test that common exclude patterns are present."""
        patterns_str = " ".join(EXCLUDE_PATTERNS)
        self.assertIn(".git", patterns_str)
        self.assertIn("tests/", patterns_str)
        self.assertIn("__pycache__", patterns_str)
        self.assertIn(".venv", patterns_str)


if __name__ == "__main__":
    unittest.main()
