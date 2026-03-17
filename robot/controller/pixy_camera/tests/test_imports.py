#!/usr/bin/env python3

"""
Test that pixy_camera library is properly structured for EV3 deployment
"""

import pytest
import os
import sys

class TestPixyCameraLibrary:
    
    def test_library_structure(self):
        """Test that library has proper file structure"""
        base_path = os.path.dirname(os.path.dirname(__file__))
        
        # Check main library files exist
        assert os.path.exists(os.path.join(base_path, "__init__.py"))
        assert os.path.exists(os.path.join(base_path, "pixy2_camera.py"))
        assert os.path.exists(os.path.join(base_path, "README.md"))
        assert os.path.exists(os.path.join(base_path, "setup.py"))
        
        # Check pixycamev3 directory exists
        assert os.path.exists(os.path.join(base_path, "pixycamev3"))
        assert os.path.exists(os.path.join(base_path, "pixycamev3", "pixy2.py"))
    
    def test_import_fails_gracefully_on_non_ev3(self):
        """Test that import fails gracefully on non-EV3 platform"""
        # This is expected behavior - the library should only work on EV3
        # We test this by trying to import in a subprocess to avoid crashing pytest
        import subprocess
        import sys
        
        result = subprocess.run([
            sys.executable, "-c", 
            "try:\n    from pixy_camera import Pixy2Camera\n    print('UNEXPECTED_SUCCESS')\nexcept Exception as e:\n    print(f'EXPECTED_ERROR:{type(e).__name__}')"
        ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))
        
        # Should fail with platform error
        assert "EXPECTED_ERROR" in result.stdout
        assert "UNEXPECTED_SUCCESS" not in result.stdout
    
    def test_pixycamev3_module_exists(self):
        """Test that pixycamev3 module files exist"""
        base_path = os.path.dirname(os.path.dirname(__file__))
        pixycamev3_path = os.path.join(base_path, "pixycamev3")
        
        assert os.path.isdir(pixycamev3_path)
        assert os.path.exists(os.path.join(pixycamev3_path, "pixy2.py"))
    
    def test_pixy2_camera_file_content(self):
        """Test that pixy2_camera.py has expected class definition"""
        base_path = os.path.dirname(os.path.dirname(__file__))
        camera_file = os.path.join(base_path, "pixy2_camera.py")
        
        with open(camera_file, 'r') as f:
            content = f.read()
        
        # Check for key components
        assert "class Pixy2Camera" in content
        assert "EventHandler" in content
        assert "threading.Thread" in content
        assert "def onBlockDetected" in content
        assert "def light" in content
        assert "def run" in content
    
    def test_init_file_exports(self):
        """Test that __init__.py has proper exports"""
        base_path = os.path.dirname(os.path.dirname(__file__))
        init_file = os.path.join(base_path, "__init__.py")
        
        with open(init_file, 'r') as f:
            content = f.read()
        
        assert "Pixy2Camera" in content
        assert "__all__" in content
        assert "from .pixy2_camera import Pixy2Camera" in content

# Note: Full functional testing requires EV3 hardware
# These tests verify the library structure and deployment readiness