#!/bin/bash
# Test runner script for Transcode Flow
# Usage: ./tests/run_tests.sh [unit|integration|load|security|all]

set -e

TEST_TYPE="${1:-all}"
COVERAGE_THRESHOLD=80

echo "=========================================="
echo "  TRANSCODE FLOW TEST SUITE"
echo "=========================================="
echo "  Test Type: $TEST_TYPE"
echo "  Coverage Threshold: ${COVERAGE_THRESHOLD}%"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

run_unit_tests() {
    echo "Running unit tests..."
    pytest tests/unit/ \
        -v \
        --cov=app \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-fail-under=$COVERAGE_THRESHOLD \
        -m unit \
        || { echo -e "${RED}Unit tests failed${NC}"; exit 1; }
    echo -e "${GREEN}Unit tests passed${NC}"
}

run_integration_tests() {
    echo "Running integration tests..."
    pytest tests/integration/ \
        -v \
        -m integration \
        || { echo -e "${RED}Integration tests failed${NC}"; exit 1; }
    echo -e "${GREEN}Integration tests passed${NC}"
}

run_security_tests() {
    echo "Running security tests..."
    pytest tests/test_security.py \
        -v \
        -m security \
        || { echo -e "${RED}Security tests failed${NC}"; exit 1; }
    echo -e "${GREEN}Security tests passed${NC}"
}

run_load_tests() {
    echo "Running load tests with Locust..."
    echo -e "${YELLOW}Load tests require manual execution:${NC}"
    echo "  locust -f tests/load/locustfile.py --host=http://localhost:18000"
    echo "  Then open http://localhost:8089 in your browser"
}

case $TEST_TYPE in
    unit)
        run_unit_tests
        ;;
    integration)
        run_integration_tests
        ;;
    security)
        run_security_tests
        ;;
    load)
        run_load_tests
        ;;
    all)
        run_unit_tests
        echo ""
        run_integration_tests
        echo ""
        run_security_tests
        echo ""
        echo "=========================================="
        echo -e "${GREEN}All automated tests passed!${NC}"
        echo "=========================================="
        echo ""
        run_load_tests
        ;;
    *)
        echo -e "${RED}Invalid test type: $TEST_TYPE${NC}"
        echo "Usage: $0 [unit|integration|load|security|all]"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "  Test Coverage Report"
echo "=========================================="
echo "  HTML Report: htmlcov/index.html"
echo "=========================================="
