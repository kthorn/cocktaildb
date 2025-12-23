"""Tests for analytics API endpoints

NOTE: These tests are currently disabled because they require S3 storage configuration
(ANALYTICS_BUCKET environment variable) which is not available in the test environment.

The analytics endpoints rely on pre-computed data stored in S3 and retrieved via
AnalyticsStorage. To re-enable these tests, you would need to either:
1. Mock the AnalyticsStorage class to return test data
2. Set up a test S3 bucket or use moto to mock S3
3. Update the analytics routes to have a fallback for test environments
"""
import pytest
import sys
import os

# Add api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))


# Tests disabled - require S3 storage configuration
# See file docstring for details
