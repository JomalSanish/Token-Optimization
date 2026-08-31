import os
import sys

# Seed mock environment variables prior to importing src configuration
os.environ["MONGODB_URI"] = "mongodb://mock_connection_string_for_testing"
os.environ["APPLICATION_SECRET"] = "test_shared_app_secret_123"
os.environ["ADMIN_AUTH_SECRET"] = "test_admin_auth_secret_456"
os.environ["CORS_ORIGINS"] = "*"

# Ensure src root is in system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
