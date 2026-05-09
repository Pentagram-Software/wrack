#!/usr/bin/env python3
"""
EV3 Deployment Script

This script handles deployment of the robot controller code to an EV3 brick.
It supports both debug and release (optimized) modes.

Release mode benefits:
- Removes assert statements (faster execution)
- Sets __debug__ to False (skips debug-only code blocks)
- Smaller bytecode files (.pyc)
- Better performance on resource-constrained EV3

Usage:
    python scripts/deploy_ev3.py --host <EV3_IP> [--mode release|debug] [--dry-run]
    
Examples:
    # Deploy release version (recommended for production)
    python scripts/deploy_ev3.py --host 192.168.1.100 --mode release
    
    # Deploy debug version (for development/troubleshooting)
    python scripts/deploy_ev3.py --host 192.168.1.100 --mode debug
    
    # Dry run to see what would be deployed
    python scripts/deploy_ev3.py --host 192.168.1.100 --mode release --dry-run
"""

import argparse
import os
import subprocess
import sys
import tempfile
import shutil
import py_compile
import fnmatch
from pathlib import Path
from typing import List, Optional, Tuple


# Default configuration
DEFAULT_EV3_USER = "robot"
DEFAULT_EV3_PATH = "/home/robot/ev3PS4Controlled"
DEFAULT_SSH_PORT = 22

# Files/directories to always exclude from deployment
EXCLUDE_PATTERNS = [
    # Git
    ".git",
    ".git/",
    ".gitignore",
    
    # Tests
    "tests/",
    "test_*.py",
    "*_test.py",
    "pytest.ini",
    "requirements-test.txt",
    "run_all_tests.py",
    "run_pytest.py",
    ".pytest_cache/",
    "htmlcov/",
    ".coverage",
    "coverage.xml",
    
    # Examples
    "example_*.py",
    "*_example.py",
    "examples/",
    
    # Documentation
    "*.md",
    "README*",
    "docs/",
    
    # Development
    ".vscode/",
    ".cursorignore",
    "deploy.conf",
    ".ev3ignore",
    "AGENTS.md",
    
    # Python cache (we'll generate fresh .pyc files)
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    
    # IDE
    ".idea/",
    "*.swp",
    "*.swo",
    
    # OS
    ".DS_Store",
    "Thumbs.db",
    
    # Virtual environment
    ".venv/",
    "venv/",
    
    # Scripts directory (deployment scripts themselves)
    "scripts/",
    
    # Specific files to exclude
    "main_NetworkClient.py",
    "example_remote_usage.py",
    "example_client.py",
    "example_turret_control.py",
    "test_network_integration.py",
    "REMOTE_CONTROLLER_README.md",
    "PROJECT_DOCUMENTATION.md",
    "CONTRIBUTING.md",
]


def should_exclude(path: str, patterns: List[str]) -> bool:
    """Check if a path should be excluded based on patterns."""
    path_parts = Path(path).parts
    name = os.path.basename(path)
    
    for pattern in patterns:
        # Remove trailing slash for directory patterns
        clean_pattern = pattern.rstrip("/")
        
        # Check if pattern matches the filename
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(name, clean_pattern):
            return True
            
        # Check if pattern matches any part of the path
        for part in path_parts:
            if fnmatch.fnmatch(part, pattern):
                return True
            if fnmatch.fnmatch(part, clean_pattern):
                return True
                
        # Check if the full path ends with the pattern
        if path.endswith(clean_pattern):
            return True
            
        # Check if any path component matches the pattern exactly
        if clean_pattern in path_parts:
            return True
    
    return False


def get_files_to_deploy(source_dir: str) -> List[str]:
    """Get list of files to deploy, excluding unwanted files."""
    files = []
    source_path = Path(source_dir)
    
    for root, dirs, filenames in os.walk(source_dir):
        # Get relative path from source directory
        rel_root = os.path.relpath(root, source_dir)
        if rel_root == ".":
            rel_root = ""
        
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if not should_exclude(
            os.path.join(rel_root, d) if rel_root else d, 
            EXCLUDE_PATTERNS
        )]
        
        for filename in filenames:
            rel_path = os.path.join(rel_root, filename) if rel_root else filename
            
            if not should_exclude(rel_path, EXCLUDE_PATTERNS):
                files.append(rel_path)
    
    return sorted(files)


def compile_python_optimized(source_file: str, dest_file: str, optimize: int = 1) -> bool:
    """
    Compile a Python file to optimized bytecode.
    
    Args:
        source_file: Path to source .py file
        dest_file: Path to destination .pyc file
        optimize: Optimization level (0=none, 1=remove asserts, 2=remove asserts+docstrings)
    
    Returns:
        True if compilation succeeded, False otherwise
    """
    try:
        py_compile.compile(source_file, dest_file, doraise=True, optimize=optimize)
        return True
    except py_compile.PyCompileError as e:
        print(f"Error compiling {source_file}: {e}", file=sys.stderr)
        return False


def prepare_deployment_package(
    source_dir: str,
    mode: str = "release",
    verbose: bool = False
) -> Tuple[str, List[str]]:
    """
    Prepare a deployment package in a temporary directory.
    
    Args:
        source_dir: Source directory containing the code
        mode: "release" or "debug"
        verbose: Print detailed progress
    
    Returns:
        Tuple of (temp_dir_path, list_of_files)
    """
    temp_dir = tempfile.mkdtemp(prefix="ev3_deploy_")
    files_to_deploy = get_files_to_deploy(source_dir)
    deployed_files = []
    
    if verbose:
        print(f"Preparing {mode} deployment package...")
        print(f"Source: {source_dir}")
        print(f"Temp dir: {temp_dir}")
        print(f"Files to process: {len(files_to_deploy)}")
    
    for rel_path in files_to_deploy:
        source_file = os.path.join(source_dir, rel_path)
        dest_file = os.path.join(temp_dir, rel_path)
        
        # Create destination directory if needed
        os.makedirs(os.path.dirname(dest_file) or temp_dir, exist_ok=True)
        
        if rel_path.endswith(".py"):
            if mode == "release":
                # For release mode, we copy the .py file but also create a launcher
                # that runs with -O flag. The actual optimization happens at runtime.
                shutil.copy2(source_file, dest_file)
                deployed_files.append(rel_path)
                if verbose:
                    print(f"  Copied (release): {rel_path}")
            else:
                # Debug mode: just copy the file
                shutil.copy2(source_file, dest_file)
                deployed_files.append(rel_path)
                if verbose:
                    print(f"  Copied (debug): {rel_path}")
        else:
            # Non-Python files: just copy
            shutil.copy2(source_file, dest_file)
            deployed_files.append(rel_path)
            if verbose:
                print(f"  Copied: {rel_path}")
    
    # Create launcher script based on mode
    launcher_content = create_launcher_script(mode)
    launcher_path = os.path.join(temp_dir, "run.sh")
    with open(launcher_path, "w") as f:
        f.write(launcher_content)
    os.chmod(launcher_path, 0o755)
    deployed_files.append("run.sh")
    
    if verbose:
        print(f"Created launcher script: run.sh (mode: {mode})")
    
    return temp_dir, deployed_files


def create_launcher_script(mode: str) -> str:
    """Create a shell script to launch the robot controller."""
    if mode == "release":
        # Release mode: run with -O flag for optimization
        return '''#!/bin/bash
# EV3 Robot Controller Launcher - RELEASE MODE
# This script runs the robot controller with Python optimization enabled.
# __debug__ will be False, assert statements are removed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting EV3 Robot Controller (RELEASE MODE)..."
echo "Optimization: ENABLED (__debug__ = False)"

# Run with -O flag for optimization (removes asserts, sets __debug__=False)
# Use -OO for additional optimization (also removes docstrings)
exec python3 -O main.py "$@"
'''
    else:
        # Debug mode: run normally
        return '''#!/bin/bash
# EV3 Robot Controller Launcher - DEBUG MODE
# This script runs the robot controller with full debugging enabled.
# __debug__ will be True, all assert statements are active.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting EV3 Robot Controller (DEBUG MODE)..."
echo "Optimization: DISABLED (__debug__ = True)"

# Run without optimization flags for full debugging
exec python3 main.py "$@"
'''


def deploy_to_ev3(
    package_dir: str,
    host: str,
    user: str = DEFAULT_EV3_USER,
    remote_path: str = DEFAULT_EV3_PATH,
    port: int = DEFAULT_SSH_PORT,
    dry_run: bool = False,
    verbose: bool = False
) -> bool:
    """
    Deploy the package to an EV3 brick using rsync over SSH.
    
    Args:
        package_dir: Local directory containing the deployment package
        host: EV3 IP address or hostname
        user: SSH username
        remote_path: Destination path on EV3
        port: SSH port
        dry_run: If True, only show what would be done
        verbose: Print detailed progress
    
    Returns:
        True if deployment succeeded, False otherwise
    """
    rsync_cmd = [
        "rsync",
        "-avz",  # archive, verbose, compress
        "--delete",  # Remove files on destination that don't exist in source
        "-e", f"ssh -p {port}",
        f"{package_dir}/",
        f"{user}@{host}:{remote_path}/"
    ]
    
    if dry_run:
        rsync_cmd.insert(1, "--dry-run")
    
    if verbose:
        print(f"Deploying to {user}@{host}:{remote_path}")
        print(f"Command: {' '.join(rsync_cmd)}")
    
    try:
        result = subprocess.run(
            rsync_cmd,
            check=True,
            capture_output=not verbose,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Deployment failed: {e}", file=sys.stderr)
        if e.stderr:
            print(f"Error output: {e.stderr}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("Error: rsync not found. Please install rsync.", file=sys.stderr)
        return False


def verify_deployment(
    host: str,
    user: str = DEFAULT_EV3_USER,
    remote_path: str = DEFAULT_EV3_PATH,
    port: int = DEFAULT_SSH_PORT,
    verbose: bool = False
) -> bool:
    """
    Verify that the deployment was successful by checking files on EV3.
    
    Returns:
        True if verification passed, False otherwise
    """
    ssh_cmd = [
        "ssh",
        "-p", str(port),
        f"{user}@{host}",
        f"ls -la {remote_path}/main.py {remote_path}/run.sh 2>/dev/null && echo 'VERIFY_OK'"
    ]
    
    if verbose:
        print(f"Verifying deployment on {host}...")
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if "VERIFY_OK" in result.stdout:
            if verbose:
                print("Verification passed: main.py and run.sh found on EV3")
            return True
        else:
            print("Verification failed: Required files not found on EV3", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("Verification timed out", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Verification error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Deploy EV3 robot controller code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Deploy release version (recommended for production):
    %(prog)s --host 192.168.1.100 --mode release
    
  Deploy debug version (for development):
    %(prog)s --host 192.168.1.100 --mode debug
    
  Dry run to preview deployment:
    %(prog)s --host 192.168.1.100 --mode release --dry-run
    
  List files that would be deployed:
    %(prog)s --list-files
"""
    )
    
    parser.add_argument(
        "--host",
        help="EV3 IP address or hostname"
    )
    parser.add_argument(
        "--mode",
        choices=["release", "debug"],
        default="release",
        help="Deployment mode (default: release)"
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_EV3_USER,
        help=f"SSH username (default: {DEFAULT_EV3_USER})"
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_EV3_PATH,
        help=f"Remote path on EV3 (default: {DEFAULT_EV3_PATH})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_SSH_PORT,
        help=f"SSH port (default: {DEFAULT_SSH_PORT})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deployed without actually deploying"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress"
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List files that would be deployed and exit"
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip deployment verification"
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Source directory (default: auto-detect from script location)"
    )
    
    args = parser.parse_args()
    
    # Determine source directory
    if args.source_dir:
        source_dir = args.source_dir
    else:
        # Default to parent of scripts directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        source_dir = os.path.dirname(script_dir)
    
    if not os.path.isdir(source_dir):
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)
    
    # List files mode
    if args.list_files:
        files = get_files_to_deploy(source_dir)
        print(f"Files to deploy from {source_dir}:")
        print(f"Mode: {args.mode}")
        print("-" * 50)
        for f in files:
            print(f"  {f}")
        print("-" * 50)
        print(f"Total: {len(files)} files")
        sys.exit(0)
    
    # Require host for actual deployment
    if not args.host:
        parser.error("--host is required for deployment")
    
    # Prepare deployment package
    try:
        temp_dir, deployed_files = prepare_deployment_package(
            source_dir,
            mode=args.mode,
            verbose=args.verbose
        )
        
        if args.verbose:
            print(f"\nPrepared {len(deployed_files)} files for deployment")
        
        # Deploy
        print(f"\nDeploying {args.mode.upper()} version to {args.host}...")
        success = deploy_to_ev3(
            temp_dir,
            host=args.host,
            user=args.user,
            remote_path=args.path,
            port=args.port,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        
        if not success:
            sys.exit(1)
        
        # Verify (unless dry-run or --no-verify)
        if not args.dry_run and not args.no_verify:
            if not verify_deployment(
                host=args.host,
                user=args.user,
                remote_path=args.path,
                port=args.port,
                verbose=args.verbose
            ):
                print("Error: Deployment verification failed", file=sys.stderr)
                sys.exit(1)
        
        if args.dry_run:
            print("\nDry run complete. No files were actually deployed.")
        else:
            print(f"\n{'='*50}")
            print(f"Deployment complete!")
            print(f"Mode: {args.mode.upper()}")
            print(f"Files deployed: {len(deployed_files)}")
            print(f"Location: {args.user}@{args.host}:{args.path}")
            print(f"\nTo run the robot controller:")
            print(f"  ssh {args.user}@{args.host}")
            print(f"  cd {args.path}")
            print(f"  ./run.sh")
            print(f"{'='*50}")
        
    finally:
        # Cleanup temp directory
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
