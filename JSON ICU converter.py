import json
import re


def transform_plural_keys(input_file, output_file):
    # Read the input JSON file
    with open(input_file, 'r', encoding='utf-8') as file:
        data = json.load(file)

    def process_value(value):
        """
        Detect and transform ICU plural syntax into nested structure.
        """
        plural_pattern = re.compile(r"{[^}]+, plural, (.+)}")
        match = plural_pattern.search(value)
        if match:
            plural_cases = match.group(1)
            cases = {}
            for case in re.finditer(r"(\w+) {([^}]*)}", plural_cases):
                key, text = case.groups()
                cases[key] = text.strip()
            return cases
        return value  # Return unchanged if no plural detected

    # Recursively process all keys in the JSON structure
    def transform(data):
        if isinstance(data, dict):
            return {key: transform(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [transform(item) for item in data]
        elif isinstance(data, str):
            return process_value(data)
        else:
            return data

    transformed_data = transform(data)

    # Write the transformed data to the output JSON file
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(transformed_data, file, ensure_ascii=False, indent=2)

    print(f"Transformed file saved to {output_file}")


# Input and output file paths
input_file = 'lokalise_export.json'  # Replace with your Lokalise-exported JSON file
output_file = 'transformed_output.json'

# Transform the file
transform_plural_keys(input_file, output_file)
