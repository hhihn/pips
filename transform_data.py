import pandas as pd
from pathlib import Path


def transform_code_column(file_path, output_path):
    """Transform a single Excel file by extracting the last part after '>' in the Code column"""
    try:
        # Read the Excel file
        df = pd.read_excel(file_path)

        # Check if 'Code' column exists
        if "Code" not in df.columns:
            print(f"Warning: 'Code' column not found in {file_path.name}")
            # Save unchanged file
            df.to_excel(output_path, index=False)
            return False

        # Transform the 'Code' column to keep only the last part after '>'
        df["Code"] = df["Code"].apply(
            lambda x: x.split(" > ")[-1] if isinstance(x, str) and " > " in x else x
        )

        # Save the transformed DataFrame to the output path
        df.to_excel(output_path, index=False)
        return True

    except Exception as e:
        print(f"Error processing {file_path.name}: {str(e)}")
        return False


def process_folder(folder_path):
    """Process all Excel files in the given folder"""
    folder_path = Path(folder_path)

    # Check if folder exists
    if not folder_path.exists():
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    # Create transformed subfolder
    transformed_folder = folder_path / "transformed"
    transformed_folder.mkdir(exist_ok=True)

    # Supported Excel file extensions
    excel_extensions = [".xlsx", ".xls"]

    # Get all Excel files in the folder
    excel_files = [
        f
        for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in excel_extensions
    ]

    if not excel_files:
        print(f"No Excel files found in {folder_path}")
        return

    print(f"Found {len(excel_files)} Excel file(s) to process...")

    processed_count = 0
    error_count = 0

    # Process each Excel file
    for file_path in excel_files:
        output_path = transformed_folder / file_path.name
        print(f"Processing: {file_path.name}")

        if transform_code_column(file_path, output_path):
            processed_count += 1
            print(f"  ✓ Saved as: {output_path.name}")
        else:
            error_count += 1

    print("\nProcessing complete!")
    print(f"Successfully processed: {processed_count} files")
    if error_count > 0:
        print(f"Errors encountered: {error_count} files")


# Main execution
if __name__ == "__main__":
    # Specify your folder path here
    folder_path = (
        "./data/interrater_data_raw/"  # Current directory, change this to your desired folder path
    )

    process_folder(folder_path)
