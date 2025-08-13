"""
Tests for CSRF protection middleware.
"""

import pytest
import json
from fastapi.testclient import TestClient
from app.fastapi_app import create_app
from app.secure_session import generate_csrf_token


class TestCSRFProtection:
    """Test CSRF middleware functionality."""
    
    def setup_method(self):
        """Set up test client."""
        self.app = create_app()
        self.client = TestClient(self.app)
    
    def test_get_requests_allowed_without_csrf(self):
        """GET requests should be allowed without CSRF tokens."""
        response = self.client.get("/health")
        assert response.status_code == 200
        
        response = self.client.get("/")
        assert response.status_code == 200
    
    def test_post_request_rejected_without_csrf(self):
        """POST requests should be rejected without CSRF tokens."""
        response = self.client.post("/some-endpoint", json={"data": "test"})
        assert response.status_code == 403
        
        response_data = response.json()
        assert response_data["success"] is False
        assert response_data["error"] == "CSRF_ERROR"
        assert "CSRF token missing" in response_data["message"]
    
    def test_exempt_paths_work_without_csrf(self):
        """Exempt paths should work without CSRF tokens."""
        # Test auth login page (exempt)
        response = self.client.get("/auth/login")
        # This might be a 404 if route doesn't exist, but shouldn't be CSRF blocked
        assert response.status_code != 403
        
        # Test health endpoint (exempt)
        response = self.client.post("/health")
        # Health is GET only, but if it were POST, it should be exempt
        # The actual status depends on the endpoint implementation
        assert response.status_code != 403
    
    def test_csrf_token_endpoint(self):
        """Test CSRF token endpoint requires authentication."""
        response = self.client.get("/csrf-token")
        # Should require authentication
        assert response.status_code == 401
    
    def test_post_with_invalid_csrf_rejected(self):
        """POST requests with invalid CSRF tokens should be rejected."""
        headers = {"X-CSRF-Token": "invalid_token"}
        response = self.client.post("/some-endpoint", 
                                   json={"data": "test"}, 
                                   headers=headers)
        assert response.status_code == 403
        
        response_data = response.json()
        assert response_data["success"] is False
        assert response_data["error"] == "CSRF_ERROR"
        assert "Invalid CSRF token" in response_data["message"]
    
    def test_put_request_requires_csrf(self):
        """PUT requests should require CSRF tokens."""
        response = self.client.put("/some-endpoint", json={"data": "test"})
        assert response.status_code == 403
        
        response_data = response.json()
        assert "CSRF token missing" in response_data["message"]
    
    def test_delete_request_requires_csrf(self):
        """DELETE requests should require CSRF tokens."""
        response = self.client.delete("/some-endpoint")
        assert response.status_code == 403
        
        response_data = response.json()
        assert "CSRF token missing" in response_data["message"]
    
    def test_patch_request_requires_csrf(self):
        """PATCH requests should require CSRF tokens."""
        response = self.client.patch("/some-endpoint", json={"data": "test"})
        assert response.status_code == 403
        
        response_data = response.json()
        assert "CSRF token missing" in response_data["message"]
    
    def test_csrf_headers_accepted(self):
        """Test that various CSRF header formats are accepted."""
        # Test X-CSRF-Token header
        headers = {"X-CSRF-Token": "test_token"}
        response = self.client.post("/some-endpoint", 
                                   json={"data": "test"}, 
                                   headers=headers)
        # Should get to token validation (and fail with invalid token)
        assert response.status_code == 403
        assert "Invalid CSRF token" in response.json()["message"]
        
        # Test X-CSRFToken header (Django compatibility)
        headers = {"X-CSRFToken": "test_token"}
        response = self.client.post("/some-endpoint", 
                                   json={"data": "test"}, 
                                   headers=headers)
        assert response.status_code == 403
        assert "Invalid CSRF token" in response.json()["message"]
    
    def test_csrf_error_response_format(self):
        """Test that CSRF error responses have correct format."""
        response = self.client.post("/some-endpoint", json={"data": "test"})
        
        assert response.status_code == 403
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        
        response_data = response.json()
        assert "success" in response_data
        assert "error" in response_data
        assert "message" in response_data
        assert "details" in response_data
        
        assert response_data["success"] is False
        assert response_data["error"] == "CSRF_ERROR"
    
    def test_static_files_exempt(self):
        """Static files should be exempt from CSRF protection."""
        # This test might need actual static files to exist
        # For now, we test that the path would be exempt
        response = self.client.post("/static/some-file.js")
        # Should get 404 or method not allowed, not CSRF error
        assert response.status_code != 403 or "CSRF" not in response.text


if __name__ == "__main__":
    # Simple test runner for development
    import asyncio
    
    def run_tests():
        test_instance = TestCSRFProtection()
        
        print("Testing CSRF protection...")
        
        test_instance.setup_method()
        
        try:
            test_instance.test_get_requests_allowed_without_csrf()
            print("✓ GET requests allowed without CSRF")
            
            test_instance.test_post_request_rejected_without_csrf()
            print("✓ POST requests rejected without CSRF")
            
            test_instance.test_exempt_paths_work_without_csrf()
            print("✓ Exempt paths work without CSRF")
            
            test_instance.test_csrf_token_endpoint()
            print("✓ CSRF token endpoint requires authentication")
            
            test_instance.test_post_with_invalid_csrf_rejected()
            print("✓ Invalid CSRF tokens rejected")
            
            test_instance.test_put_request_requires_csrf()
            print("✓ PUT requests require CSRF")
            
            test_instance.test_delete_request_requires_csrf()
            print("✓ DELETE requests require CSRF")
            
            test_instance.test_patch_request_requires_csrf()
            print("✓ PATCH requests require CSRF")
            
            test_instance.test_csrf_headers_accepted()
            print("✓ CSRF headers accepted")
            
            test_instance.test_csrf_error_response_format()
            print("✓ CSRF error response format correct")
            
            test_instance.test_static_files_exempt()
            print("✓ Static files exempt")
            
            print("\nAll CSRF protection tests passed!")
            
        except Exception as e:
            print(f"Test failed: {e}")
            raise
    
    run_tests()
