import re

# Input and output file paths
input_file = 'C:\Script\de.dict.xliff.xml'
output_file = 'C:\Script\corrected.xml'

# Read the input file
with open(input_file, 'r', encoding='utf-8') as file:
    content = file.read()

# Replace xml:lang="de" with xml:lang="it"
updated_content = re.sub(r'(<target xml:lang=")de(">)', r'\1it\2', content)

# Write the updated content to the output file
with open(output_file, 'w', encoding='utf-8') as file:
    file.write(updated_content)

print("The file has been updated and saved as:", output_file)