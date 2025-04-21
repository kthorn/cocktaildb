import requests
import json
import argparse
import sys
import os


class CocktailDBApiTester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        print(f"Testing API at {self.base_url}")

    def test_ingredients(self):
        """Test the ingredients endpoint"""
        print("\n=== Testing Ingredients Endpoint ===")

        # GET all ingredients
        response = self.session.get(f"{self.base_url}/ingredients")
        print(f"GET /ingredients - Status: {response.status_code}")
        self._print_response(response)

        # POST a new ingredient
        new_ingredient = {
            "name": "Test Ingredient",
            "category": "Test Category",
            "abv": 40.0,
        }
        response = self.session.post(
            f"{self.base_url}/ingredients", json=new_ingredient
        )
        print(f"POST /ingredients - Status: {response.status_code}")
        self._print_response(response)

        if response.status_code == 200 or response.status_code == 201:
            # Get the ID from the response
            try:
                ingredient_id = response.json().get("id")
                if ingredient_id:
                    # PUT/update the ingredient
                    updated_ingredient = {
                        "id": ingredient_id,
                        "name": "Updated Test Ingredient",
                        "category": "Test Category",
                        "abv": 42.0,
                    }
                    response = self.session.put(
                        f"{self.base_url}/ingredients", json=updated_ingredient
                    )
                    print(f"PUT /ingredients - Status: {response.status_code}")
                    self._print_response(response)

                    # DELETE the ingredient
                    response = self.session.delete(
                        f"{self.base_url}/ingredients?id={ingredient_id}"
                    )
                    print(f"DELETE /ingredients - Status: {response.status_code}")
                    self._print_response(response)
            except Exception as e:
                print(f"Error processing ingredient ID: {str(e)}")

    def test_recipes(self):
        """Test the recipes endpoint"""
        print("\n=== Testing Recipes Endpoint ===")

        # GET all recipes
        response = self.session.get(f"{self.base_url}/recipes")
        print(f"GET /recipes - Status: {response.status_code}")
        self._print_response(response)

        # POST a new recipe
        new_recipe = {
            "name": "Test Recipe",
            "description": "A test cocktail recipe",
            "instructions": "Mix all ingredients together and serve",
            "ingredients": [{"ingredient_id": 1, "amount": 2.0, "unit_id": 1}],
        }
        response = self.session.post(f"{self.base_url}/recipes", json=new_recipe)
        print(f"POST /recipes - Status: {response.status_code}")
        self._print_response(response)

        if response.status_code == 200 or response.status_code == 201:
            # Get the ID from the response
            try:
                recipe_id = response.json().get("id")
                if recipe_id:
                    # PUT/update the recipe
                    updated_recipe = {
                        "id": recipe_id,
                        "name": "Updated Test Recipe",
                        "description": "An updated test cocktail recipe",
                        "instructions": "Mix all ingredients carefully and serve chilled",
                        "ingredients": [
                            {"ingredient_id": 1, "amount": 2.5, "unit_id": 1}
                        ],
                    }
                    response = self.session.put(
                        f"{self.base_url}/recipes", json=updated_recipe
                    )
                    print(f"PUT /recipes - Status: {response.status_code}")
                    self._print_response(response)

                    # DELETE the recipe
                    response = self.session.delete(
                        f"{self.base_url}/recipes?id={recipe_id}"
                    )
                    print(f"DELETE /recipes - Status: {response.status_code}")
                    self._print_response(response)
            except Exception as e:
                print(f"Error processing recipe ID: {str(e)}")

    def test_units(self):
        """Test the units endpoint"""
        print("\n=== Testing Units Endpoint ===")

        # GET all units
        response = self.session.get(f"{self.base_url}/units")
        print(f"GET /units - Status: {response.status_code}")
        self._print_response(response)

        # POST a new unit
        new_unit = {"name": "Test Unit", "abbreviation": "tu"}
        response = self.session.post(f"{self.base_url}/units", json=new_unit)
        print(f"POST /units - Status: {response.status_code}")
        self._print_response(response)

        if response.status_code == 200 or response.status_code == 201:
            # Get the ID from the response
            try:
                unit_id = response.json().get("id")
                if unit_id:
                    # PUT/update the unit
                    updated_unit = {
                        "id": unit_id,
                        "name": "Updated Test Unit",
                        "abbreviation": "utu",
                    }
                    response = self.session.put(
                        f"{self.base_url}/units", json=updated_unit
                    )
                    print(f"PUT /units - Status: {response.status_code}")
                    self._print_response(response)

                    # DELETE the unit
                    response = self.session.delete(
                        f"{self.base_url}/units?id={unit_id}"
                    )
                    print(f"DELETE /units - Status: {response.status_code}")
                    self._print_response(response)
            except Exception as e:
                print(f"Error processing unit ID: {str(e)}")

    def test_config(self):
        """Test the config endpoint"""
        print("\n=== Testing Config Endpoint ===")

        # GET the config
        response = self.session.get(f"{self.base_url}/config")
        print(f"GET /config - Status: {response.status_code}")
        self._print_response(response)

    def _print_response(self, response):
        """Helper method to print a summarized response"""
        try:
            json_response = response.json()
            print(
                f"Response: {json.dumps(json_response, indent=2)[:200]}{'...' if len(json.dumps(json_response)) > 200 else ''}"
            )
        except ValueError:
            print(
                f"Response text: {response.text[:200]}{'...' if len(response.text) > 200 else ''}"
            )

    def run_all_tests(self):
        """Run all API tests"""
        self.test_config()
        self.test_units()
        self.test_ingredients()
        self.test_recipes()


def main():
    parser = argparse.ArgumentParser(description="Test the Cocktail Database API")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the API (e.g., https://example.execute-api.us-east-1.amazonaws.com/api)",
    )
    parser.add_argument(
        "--endpoint",
        choices=["all", "ingredients", "recipes", "units", "config"],
        default="all",
        help="Specific endpoint to test (default: all)",
    )

    args = parser.parse_args()

    tester = CocktailDBApiTester(args.url)

    if args.endpoint == "all":
        tester.run_all_tests()
    elif args.endpoint == "ingredients":
        tester.test_ingredients()
    elif args.endpoint == "recipes":
        tester.test_recipes()
    elif args.endpoint == "units":
        tester.test_units()
    elif args.endpoint == "config":
        tester.test_config()


if __name__ == "__main__":
    main()
