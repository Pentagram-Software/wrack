#!/usr/bin/env python3

"""
Modern pytest runner for EV3 PS4 Controlled Robot tests with coverage
"""

import subprocess
import sys
import os
from pathlib import Path

def run_pytest_with_coverage():
    """Run pytest with coverage reporting and nice output"""
    
    print("🧪 EV3 PS4 Controlled Robot - Pytest Test Suite")
    print("=" * 60)
    
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Basic pytest command with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "--verbose",
        "--tb=short",
        "--cov=.",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-fail-under=50"
    ]
    
    try:
        # Run pytest
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        print("\n" + "=" * 60)
        if result.returncode == 0:
            print("🎉 ALL TESTS PASSED!")
            print("📊 Coverage report generated in htmlcov/index.html")
            print("🚀 Code is ready for deployment!")
        else:
            print("❌ SOME TESTS FAILED")
            print("📋 Please review the output above and fix failing tests")
        
        print("=" * 60)
        return result.returncode == 0
        
    except FileNotFoundError:
        print("❌ ERROR: pytest not installed")
        print("📦 Install with: pip install -r requirements-test.txt")
        return False
    except Exception as e:
        print(f"❌ ERROR running tests: {e}")
        return False

def run_specific_test(test_pattern):
    """Run specific test(s) matching the pattern"""
    
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    cmd = [
        sys.executable, "-m", "pytest",
        "--verbose",
        "--tb=short",
        test_pattern
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ ERROR running specific test: {e}")
        return False

def run_with_watch():
    """Run tests with file watching (requires pytest-xdist)"""
    
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "--verbose",
        "--tb=short",
        "--cov=.",
        "--cov-report=term-missing",
        "-f"  # Watch for file changes
    ]
    
    try:
        print("👀 Running tests with file watching...")
        print("   Press Ctrl+C to stop")
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n👋 Test watching stopped")
        return True
    except Exception as e:
        print(f"❌ ERROR running watch mode: {e}")
        return False

def check_dependencies():
    """Check if required dependencies are installed"""
    
    required_packages = ['pytest', 'pytest-cov', 'pytest-mock']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Install with: pip install -r requirements-test.txt")
        return False
    
    return True

if __name__ == '__main__':
    if not check_dependencies():
        sys.exit(1)
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == "--watch":
            success = run_with_watch()
        elif arg.startswith("--"):
            print("Usage:")
            print("  python run_pytest.py              # Run all tests")
            print("  python run_pytest.py test_turret  # Run specific test")
            print("  python run_pytest.py --watch      # Run with file watching")
            sys.exit(0)
        else:
            # Run specific test
            success = run_specific_test(f"tests/*{arg}*")
    else:
        # Run all tests
        success = run_pytest_with_coverage()
    
    sys.exit(0 if success else 1) 