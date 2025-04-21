#!/usr/bin/env python3
import os
import sys
import subprocess
import importlib.util


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import requests

        print("✓ Required dependencies are installed")
    except ImportError:
        print("Installing required dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        print("✓ Dependencies installed successfully")


def is_valid_url(url):
    """Basic URL validation"""
    return url.startswith(("http://", "https://"))


def main():
    """Main function to run the API tests"""
    print("\n=== Cocktail Database API Tester ===\n")

    # Check if test_api.py exists in the same directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_api_path = os.path.join(script_dir, "test_api.py")

    if not os.path.exists(test_api_path):
        print("Error: test_api.py not found in the same directory.")
        sys.exit(1)

    # Check and install dependencies
    check_dependencies()

    # Get API URL from user
    api_url = input(
        "\nEnter your API Gateway URL (e.g., https://example.execute-api.us-east-1.amazonaws.com/api): "
    ).strip()

    if not api_url:
        print("Error: No API URL provided. Exiting.")
        sys.exit(1)

    if not is_valid_url(api_url):
        print(
            "Warning: The URL doesn't start with http:// or https://. This might not be a valid URL."
        )
        confirm = input("Do you want to continue anyway? (y/n): ").strip().lower()
        if confirm != "y":
            sys.exit(0)

    # Menu for endpoint selection
    print("\nWhich endpoint would you like to test?")
    print("1. All endpoints")
    print("2. Ingredients endpoint")
    print("3. Recipes endpoint")
    print("4. Units endpoint")
    print("5. Config endpoint")

    choice = input("\nEnter your choice (1-5): ").strip()

    endpoints = {
        "1": "all",
        "2": "ingredients",
        "3": "recipes",
        "4": "units",
        "5": "config",
    }

    endpoint = endpoints.get(choice, "all")

    # Run the test script by importing it
    print(f"\nTesting {endpoint} endpoint(s) at {api_url}...\n")

    # We can either import the module and run it programmatically
    # or use subprocess to run it as a separate process
    try:
        # Method 1: Import and run
        spec = importlib.util.spec_from_file_location("test_api", test_api_path)
        test_api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_api)

        # Create an instance of the tester and run the appropriate test
        tester = test_api.CocktailDBApiTester(api_url)

        if endpoint == "all":
            tester.run_all_tests()
        elif endpoint == "ingredients":
            tester.test_ingredients()
        elif endpoint == "recipes":
            tester.test_recipes()
        elif endpoint == "units":
            tester.test_units()
        elif endpoint == "config":
            tester.test_config()

    except Exception as e:
        print(f"Error running tests: {str(e)}")
        # Fallback to method 2 if method 1 fails
        try:
            # Method 2: Use subprocess
            subprocess.run(
                [
                    sys.executable,
                    test_api_path,
                    "--url",
                    api_url,
                    "--endpoint",
                    endpoint,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error running test script: {str(e)}")
            sys.exit(1)

    print("\nTesting complete.")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
