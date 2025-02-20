import pandas as pd
import argparse
from tqdm import tqdm
from collections import defaultdict
import warnings
import json

def detect_columns(df, source_lang, target_langs):
    """
    Dynamically identify source and target language columns based on user-defined mappings.
    Returns a tuple of (source_col, target_cols) or (None, None) if no valid columns are found.
    """
    source_col = None
    target_cols = {}
    target_counts = defaultdict(int)  # Track duplicate target columns

    for col in df.columns:
        col_lower = col.lower()  # Case-insensitive matching
        # Check if the column matches the source language
        if source_lang.lower() in col_lower:
            source_col = col
        # Check if the column matches any target language
        for lang in target_langs:
            if lang.lower() in col_lower:
                target_counts[lang] += 1
                suffix = f"_{target_counts[lang]}" if target_counts[lang] > 1 else ""
                target_cols[col] = f"{lang}{suffix}"

    if not source_col or not target_cols:
        return None, None

    return source_col, target_cols

def convert_to_multilingual_excel(input_path, output_path, source_lang, target_langs, metadata_fields):
    """
    Convert an Excel file to a multilingual format for Phrase TMS.
    Processes all sheets dynamically and handles errors gracefully.
    """
    try:
        # Load the Excel file
        xls = pd.ExcelFile(input_path)

        # Dictionary to store processed data from all sheets
        processed_sheets = {}

        # Process each sheet in the file
        for sheet_name in tqdm(xls.sheet_names, desc="Processing sheets"):
            df = xls.parse(sheet_name=sheet_name)

            # Detect source and target columns dynamically
            source_col, target_cols = detect_columns(df, source_lang, target_langs)
            if not source_col or not target_cols:
                warnings.warn(f"Skipping sheet '{sheet_name}': No valid source or target columns found.")
                continue

            # Select relevant columns (metadata + source + target columns)
            existing_metadata = [col for col in metadata_fields if col in df.columns]
            selected_columns = existing_metadata + [source_col] + list(target_cols.keys())

            if not selected_columns:
                warnings.warn(f"Skipping sheet '{sheet_name}': No valid columns selected.")
                continue

            df_multilingual = df[selected_columns]

            # Rename columns for Phrase TMS compatibility
            df_multilingual = df_multilingual.rename(columns={source_col: source_lang, **target_cols})

            # Store processed sheet
            processed_sheets[sheet_name] = df_multilingual

        # Save the processed file with multiple sheets
        with pd.ExcelWriter(output_path) as writer:
            for sheet, df in processed_sheets.items():
                df.to_excel(writer, sheet_name=sheet, index=False)

        print(f"Multilingual Excel file with multiple sheets saved to: {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Convert Excel file to Phrase TMS multilingual format with multiple sheets dynamically.")
    parser.add_argument("input", help="Path to the input Excel file")
    parser.add_argument("output", help="Path to the output Excel file")
    parser.add_argument("--source", required=True, help="Source language (e.g., 'de' for German)")
    parser.add_argument("--targets", required=True, help="Comma-separated list of target languages (e.g., 'en,pl,cs')")
    parser.add_argument("--metadata", required=True, help="Comma-separated list of metadata fields (e.g., 'Teaserart,Überschrift,Reitername')")
    parser.add_argument("--config", help="Path to a JSON config file (optional)")

    args = parser.parse_args()

    # Load configuration from JSON file if provided
    if args.config:
        with open(args.config, "r") as f:
            config = json.load(f)
        source_lang = config.get("source_lang", args.source)
        target_langs = config.get("target_langs", args.targets.split(","))
        metadata_fields = config.get("metadata_fields", args.metadata.split(","))
    else:
        source_lang = args.source
        target_langs = args.targets.split(",")
        metadata_fields = args.metadata.split(",")

    # Warn about processing untrusted files
    warnings.warn("Ensure the input file is from a trusted source to avoid security risks.")

    # Convert the Excel file
    convert_to_multilingual_excel(args.input, args.output, source_lang, target_langs, metadata_fields)