import re
import pandas as pd
from datetime import datetime
import streamlit as st
import tempfile
import os

def bengali_to_english_digits(text):
    """Convert Bengali digits to English digits"""
    bengali_digits = '০১২৩৪৫৬৭৮৯'
    english_digits = '0123456789'
    translation_table = str.maketrans(bengali_digits, english_digits)
    return text.translate(translation_table)

def extract_phone_number(line):
    """Extract phone number from a line, handling both English and Bengali digits"""
    # First convert any Bengali digits to English
    english_line = bengali_to_english_digits(line)

    # Look for 11-digit phone numbers (with optional +88 prefix)
    phone_patterns = [
        r'(\d{11})',  # Standard 11-digit number
        r'\+88(\d{11})',  # +88 prefix followed by 11 digits
    ]

    for pattern in phone_patterns:
        match = re.search(pattern, english_line)
        if match:
            return match.group(1)

    return None

def extract_amount(note_text):
    """Extract amount from note text using regex pattern matching"""
    # Convert Bengali digits to English for easier processing
    text = bengali_to_english_digits(note_text)

    # Pattern to match amount (looks for numbers followed by "টাকা" or "Taka")
    amount_pattern = r'(\d+)\s*টাকা|Taka'
    match = re.search(amount_pattern, text)
    if match:
        return match.group(1)

    # Try to find any number in the text as fallback
    number_match = re.search(r'(\d+)', text)
    if number_match:
        return number_match.group(1)

    return None

def extract_customer_blocks(input_text):
    """Split input text into separate customer blocks"""
    # First, normalize the input by replacing various whitespace patterns
    normalized_text = re.sub(r'\r\n', '\n', input_text)  # Convert Windows line endings
    normalized_text = re.sub(r'\r', '\n', normalized_text)  # Convert old Mac line endings
    normalized_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', normalized_text)  # Reduce multiple blank lines
    
    # Split by double newlines (which typically separate customers)
    blocks = re.split(r'\n\s*\n', normalized_text.strip())
    
    # Further process blocks to handle cases where customers aren't properly separated
    customer_blocks = []
    current_block = []
    
    for block in blocks:
        lines = block.split('\n')
        lines = [line.strip() for line in lines if line.strip()]  # Clean up lines
        
        if not lines:
            continue
            
        # Check if this block starts with a customer identifier
        starts_with_name = any(re.match(r'^(নাম|name|nam|আপনার নাম)', line, re.IGNORECASE) for line in lines[:2])
        
        if starts_with_name and current_block:
            # If we have a current block and this looks like a new customer, save the current one
            customer_blocks.append('\n'.join(current_block))
            current_block = lines
        else:
            # Otherwise, add to current block
            if current_block:
                current_block.extend(lines)
            else:
                current_block = lines
    
    # Add the last block if it exists
    if current_block:
        customer_blocks.append('\n'.join(current_block))
    
    # Final validation: if we found no blocks with the above method, treat the whole text as one block
    if not customer_blocks and input_text.strip():
        customer_blocks = [input_text.strip()]
    
    return customer_blocks

def process_customer_block(block_text):
    """Process a single customer block and extract data"""
    lines = block_text.strip().split('\n')

    # Initialize variables
    name = ""
    phone = ""
    address_lines = []
    note = ""
    amount = ""

    # Process each line
    for i, line in enumerate(lines):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Extract name (first non-empty line or line with name)
        if not name and (i == 0 or any(keyword in line for keyword in ['নাম', 'name',  'nam'])):
            name = re.sub(r'^(নাম|আপনার নাম|name|nam)\s*[:：]?\s*', '', line, flags=re.IGNORECASE).strip()

        # Extract phone (look for 11 digits in any format)
        if not phone:
            extracted_phone = extract_phone_number(line)
            if extracted_phone:
                phone = extracted_phone

        # Extract address (lines with address keywords)
        address_keywords = ['জেলা', 'থানা', 'এলাকা', 'ঠিকানা', 'এলাকার নাম', 'address', 'area']
        if any(keyword in line for keyword in address_keywords) and not any(order_keyword in line for order_keyword in ['অর্ডার', 'অডার', 'order']):
            address_lines.append(line)

        # Extract order note
        if 'অর্ডার' in line or 'order' in line or 'অডার' in line:
            # The next non-empty line is the order note
            for j in range(i+1, len(lines)):
                if lines[j].strip():
                    note = lines[j].strip()
                    amount = extract_amount(note)
                    break

    # Combine address lines
    address = '\n'.join(address_lines)

    return {
        'Name': name,
        'Address': address,
        'Phone': phone,
        'Amount': amount,
        'Note': note,
        'Delivery Type': 'Home'
    }

def validate_data(data):
    """Validate extracted data"""
    missing_fields = []

    if not data['Name']:
        missing_fields.append('Name')
    if not data['Phone'] or len(data['Phone']) != 11:
        missing_fields.append('Phone')
    if not data['Address']:
        missing_fields.append('Address')
    if not data['Amount']:
        missing_fields.append('Amount')

    return missing_fields

def main():
    st.title("Bengali Data Extraction to Excel - Multiple Entries")
    st.write("Paste all customer data below (separate entries with blank lines):")
    
    # Text area for input
    user_input = st.text_area("Input:", height=300, placeholder="Paste all customer data here...\n\nExample:\nনাম: Customer 1\nমোবাইল: ০১৭১২৩৪৫৬৭৮\nজেলা: District 1\n...\n\nনাম: Customer 2\nমোবাইল: 01234567891\nজেলা: District 2\n...")
    
    if st.button('Process All Data'):
        if not user_input.strip():
            st.error("No input provided.")
            return

        # Split input into customer blocks
        customer_blocks = extract_customer_blocks(user_input)
        st.write(f"Found {len(customer_blocks)} customer entries")

        all_data = []
        invalid_entries = []

        # Process each customer block
        for i, block in enumerate(customer_blocks, 1):
            data = process_customer_block(block)

            # Validate data
            missing_fields = validate_data(data)

            if missing_fields:
                invalid_entries.append((i, data, missing_fields))
            else:
                all_data.append(data)

        # Handle invalid entries
        if invalid_entries:
            st.warning(f"{len(invalid_entries)} entries have missing data and were skipped:")
            for i, data, missing_fields in invalid_entries:
                st.write(f"Entry {i}: Missing {', '.join(missing_fields)}")

        if not all_data:
            st.error("No valid data to process.")
            return

        # Create DataFrame
        df = pd.DataFrame(all_data)
        
        # Add Invoice column at the beginning with sequential numbers
        df.insert(0, 'Invoice', range(1, len(df) + 1))

        # Generate filename with current date and time
        now = datetime.now()
        filename = now.strftime("%d-%b-%Y(%I:%M%p).xlsx")

        # Save to Excel
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                df.to_excel(tmp.name, index=False, engine='openpyxl')
                tmp.flush()
                
                # Read the file data for download
                with open(tmp.name, "rb") as file:
                    excel_data = file.read()
                
                # Clean up
                os.unlink(tmp.name)
            
            st.success(f"Data successfully processed. Total entries: {len(all_data)}")
            
            # Display the saved data
            st.dataframe(df)
            
            # Download button
            st.download_button(
                label="Download Excel file",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except ImportError:
            st.error("The openpyxl package is required to export to Excel. Please add it to your requirements.txt file.")
        except Exception as e:
            st.error(f"Error saving to Excel: {str(e)}")

if __name__ == "__main__":
    main()
