#!/usr/bin/env python3

"""
Test runner for all EV3 PS4 Controlled Robot unit tests
"""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_all_tests():
    """Run all unit tests and display results"""
    
    print("="*60)
    print("EV3 PS4 Controlled Robot - Unit Test Suite")
    print("="*60)
    
    # Discover and run all tests in the tests directory
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    success_count = total_tests - failures - errors
    
    print(f"Total Tests Run: {total_tests}")
    print(f"Successful: {success_count}")
    print(f"Failures: {failures}")
    print(f"Errors: {errors}")
    
    if result.failures:
        print(f"\nFAILURES ({len(result.failures)}):")
        for test, traceback in result.failures:
            print(f"  - {test}")
    
    if result.errors:
        print(f"\nERRORS ({len(result.errors)}):")
        for test, traceback in result.errors:
            print(f"  - {test}")
    
    if result.wasSuccessful():
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("The robot code is ready for deployment to EV3!")
    else:
        print(f"\n❌ {failures + errors} TEST(S) FAILED")
        print("Please fix the issues before deploying to EV3.")
    
    print("="*60)
    
    return result.wasSuccessful()

def run_specific_test(test_module):
    """Run a specific test module"""
    
    print(f"Running tests for: {test_module}")
    print("-" * 40)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(test_module)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run specific test module
        test_module = sys.argv[1]
        success = run_specific_test(test_module)
    else:
        # Run all tests
        success = run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1) 