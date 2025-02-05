import os
import time
from copy import copy
from openpyxl import load_workbook, Workbook
from openpyxl.comments import Comment
from langdetect import detect, DetectorFactory
from tqdm import tqdm
from functools import lru_cache

# Set seed for reproducibility in language detection
DetectorFactory.seed = 0

# Configuration: input file, output directory, output file name, and how often to yield control.
input_file = 'C:\Script\VELUX master glossary_LB_current upload_03.01.2025.xlsx'
output_dir = 'C:/Script'  # Change this to your desired directory
output_filename = 'translated_output.xlsx'
YIELD_EVERY = 500  # every 500 rows, yield control

# Ensure the output directory exists; if not, create it.
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Build the full output file path
output_file = os.path.join(output_dir, output_filename)


# Create a cached language detection function to avoid redundant processing.
@lru_cache(maxsize=None)
def detect_lang(text: str) -> str:
    try:
        return detect(text)
    except Exception:
        return ""


# Helper function to check if a cell is marked non-translatable.
def is_non_translatable(cell) -> bool:
    if cell.comment and isinstance(cell.comment, Comment):
        if "non-translatable" in cell.comment.text.lower():
            return True
    return False


# Helper function to copy a cell’s value and formatting from source to target.
def copy_cell(src_cell, tgt_cell):
    tgt_cell.value = src_cell.value
    if src_cell.has_style:
        tgt_cell.font = copy(src_cell.font)
        tgt_cell.border = copy(src_cell.border)
        tgt_cell.fill = copy(src_cell.fill)
        tgt_cell.number_format = copy(src_cell.number_format)
        tgt_cell.protection = copy(src_cell.protection)
        tgt_cell.alignment = copy(src_cell.alignment)


print("Loading workbook...")
# Load the entire workbook (normal mode) so that formatting is available.
wb_in = load_workbook(filename=input_file)
wb_out = Workbook()
# Remove the default sheet in the output workbook.
if "Sheet" in wb_out.sheetnames and len(wb_in.sheetnames) > 0:
    std = wb_out["Sheet"]
    wb_out.remove(std)

# Process each sheet in the input workbook.
for sheet_name in wb_in.sheetnames:
    ws_in = wb_in[sheet_name]
    print(f"\nProcessing sheet: '{sheet_name}'")

    # ---- Pass 1: Identify all language codes in this sheet ----
    language_set = set()
    total_rows = ws_in.max_row or 0
    for row in tqdm(ws_in.iter_rows(), total=total_rows, desc="Scanning languages", unit="row"):
        for cell in row:
            if cell.value and isinstance(cell.value, str) and cell.value.strip():
                if not is_non_translatable(cell):
                    lang = detect_lang(cell.value.strip())
                    if lang:
                        language_set.add(lang)
    # Sort languages for consistent column order.
    languages = sorted(language_set)
    print(f"Detected languages on this sheet: {languages}")

    # ---- Prepare the output sheet: copy original columns and add new language columns ----
    ws_out = wb_out.create_sheet(title=sheet_name)

    # Assume that the first row is a header row.
    header = []
    for cell in ws_in[1]:
        header.append(cell.value)
    # Append new headers for each language.
    for lang in languages:
        header.append(f"Translated ({lang})")
    ws_out.append(header)

    # ---- Pass 2: Process each row, copy original cells (with formatting),
    # and extract translatable text into extra columns. ----
    row_index = 1  # already processed header row
    for row in tqdm(ws_in.iter_rows(min_row=2), total=total_rows - 1, desc="Processing rows", unit="row"):
        row_index += 1
        out_row = []
        # Dictionary to aggregate texts for each language in this row.
        row_language_text = {lang: [] for lang in languages}

        for cell in row:
            out_row.append(cell.value)
            if cell.value and isinstance(cell.value, str) and cell.value.strip():
                if not is_non_translatable(cell):
                    lang = detect_lang(cell.value.strip())
                    if lang in row_language_text:
                        row_language_text[lang].append(cell.value.strip())
        # For each language, join texts (if any) with newline separators.
        for lang in languages:
            combined_text = "\n".join(row_language_text[lang]) if row_language_text[lang] else ""
            out_row.append(combined_text)

        ws_out.append(out_row)

        # Yield control periodically to keep the system responsive.
        if row_index % YIELD_EVERY == 0:
            time.sleep(0.001)

print(f"\nSaving output workbook to '{output_file}' ...")
wb_out.save(output_file)
print("Extraction complete.")
