import json

# Load the JSON data from the file
with open('../templates.json', 'r') as file:
    data = json.load(file)

# Create or open the TSV file for output
with open('output.tsv', 'w') as outfile:
    # Write the headers
    outfile.write("Camera Name\tURL\tNotes\n")
    
    # Iterate through each camera and extract details
    for camera, details in data.items():
        camera_name = camera
        url = details.get('url', 'No URL provided')
        notes = details.get('notes', 'No notes provided').replace('\n', ' ')  # Remove newlines to avoid format issues
        outfile.write(f"{camera_name}\t{url}\t{notes}\n")

print("Data has been successfully written to output.tsv")

