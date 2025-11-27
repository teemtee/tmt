#!/bin/bash
# A simple test that demonstrates Polarion + ReportPortal integration

set -e

echo "Starting Polarion + ReportPortal integration test..."
echo "Testing token authentication for Polarion test run uploads"
echo ""

# Simulate some test activity
echo "Running test steps..."
sleep 1

# Check if we can access basic system info
echo "System: $(uname -s)"
echo "Architecture: $(uname -m)"
echo "Hostname: $(hostname)"
echo ""

# Test some basic functionality
echo "Testing basic assertions..."
if [ "$(echo 'test')" = "test" ]; then
    echo "✓ String comparison: PASS"
else
    echo "✗ String comparison: FAIL"
    exit 1
fi

if [ -d "/tmp" ]; then
    echo "✓ Directory check: PASS"
else
    echo "✗ Directory check: FAIL"
    exit 1
fi

# Create some test output
echo ""
echo "Test completed successfully!"
echo "This output will be included in both ReportPortal and Polarion reports"

# Create test data files in TMT_TEST_DATA directory
if [ -n "$TMT_TEST_DATA" ]; then
    echo ""
    echo "Creating test artifacts in: $TMT_TEST_DATA"
    
    # Create a test report file
    cat > "$TMT_TEST_DATA/test-report.txt" << 'EOF'
Test Report
===========
Test Name: Polarion + ReportPortal Integration
Status: PASSED
Duration: 1 second

Test Steps Executed:
1. String comparison test
2. Directory existence check
3. System information gathering

All tests passed successfully.
EOF
    
    # Create a JSON metadata file
    cat > "$TMT_TEST_DATA/test-metadata.json" << 'EOF'
{
  "test_name": "polarion-reportportal-integration",
  "timestamp": "2024-11-14T14:30:00Z",
  "environment": {
    "os": "Linux",
    "framework": "TMT"
  },
  "results": {
    "passed": 2,
    "failed": 0,
    "skipped": 0
  }
}
EOF
    
    # Create a test log file with some details
    cat > "$TMT_TEST_DATA/detailed-test.log" << EOF
$(date '+%Y-%m-%d %H:%M:%S') - Test started
$(date '+%Y-%m-%d %H:%M:%S') - Running on $(hostname)
$(date '+%Y-%m-%d %H:%M:%S') - System: $(uname -a)
$(date '+%Y-%m-%d %H:%M:%S') - Test assertions passed
$(date '+%Y-%m-%d %H:%M:%S') - Test completed successfully
EOF
    
    # Create a CSV file with test data
    cat > "$TMT_TEST_DATA/test-results.csv" << 'EOF'
TestCase,Status,Duration,Notes
String Comparison,PASSED,0.01s,Basic string equality test
Directory Check,PASSED,0.01s,Verified /tmp directory exists
System Info,PASSED,0.01s,Retrieved system information
EOF
    
    echo "✓ Created test artifacts:"
    ls -lh "$TMT_TEST_DATA/"
else
    echo "⚠ TMT_TEST_DATA not set, skipping artifact creation"
fi

exit 0

