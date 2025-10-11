.PHONY: build-DataScienceLayer

build-DataScienceLayer:
	mkdir -p "$(ARTIFACTS_DIR)/python"
	python3.12 -m pip install -r requirements.txt -t "$(ARTIFACTS_DIR)/python"
	# Remove tests and docs to reduce size
	find "$(ARTIFACTS_DIR)/python" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -name "*.pyc" -delete 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -name "*.pyo" -delete 2>/dev/null || true
	# Remove documentation
	find "$(ARTIFACTS_DIR)/python" -type d -name "doc" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -type d -name "docs" -exec rm -rf {} + 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -name "*.md" -delete 2>/dev/null || true
	find "$(ARTIFACTS_DIR)/python" -name "*.rst" -delete 2>/dev/null || true
	# Remove example files
	find "$(ARTIFACTS_DIR)/python" -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
	# Strip binaries (optional, but can save space)
	find "$(ARTIFACTS_DIR)/python" -name "*.so" -exec strip {} \; 2>/dev/null || true
