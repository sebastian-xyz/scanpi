import argparse
import subprocess
import os
import shutil
import re
import tempfile
import tomllib
import requests

# scanpi - A simple command-line tool to scan documents using a remote scanner
# This tool connects to a remote scanner via SSH, scans documents, and optionally uploads them to
# Paperless-ng for document management.
__version__ = "1.0.0"
__author__ = "sebastian-xyz"
__license__ = "MIT"

parser = argparse.ArgumentParser(description="Scan documents using a remote scanner via SSH.")
parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}", help="Show the version of scanpi.")
parser.add_argument("-c", "--config", type=str, help="Path to the configuration file.", default=os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "scanpi", "config"))
parser.add_argument("-f", "--format", type=str, choices=["a4", "a5", "a6", "letter", "legal"], default="a4", help="Document format to use for scanning. Default is A4.")
parser.add_argument("-r", "--resolution", type=int, default=400, help="Resolution for scanning in DPI. Default is 400 DPI.")

args = parser.parse_args()

# Set up document formats and their dimensions
# Dimensions are in millimeters (mm) for the specified formats.

DOCUMENT_FORMATS = {
    "a4": {"width": 210, "height": 297},  # A4 size in mm
    "a5": {"width": 148, "height": 210},  # A5 size in mm
    "a6": {"width": 105, "height": 148},  # A6 size in mm
    "letter": {"width": 216, "height": 279},  # Letter size in mm
    "legal": {"width": 216, "height": 356},  # Legal size in mm
}

# Validate and set up configuration
CONFIG_FILE = args.config
FORMAT = args.format.lower()
RESOLUTION = args.resolution
if RESOLUTION not in [200,400, 600]:
    print(f"Invalid resolution '{RESOLUTION}'. Supported resolutions are: 200, 400, 600 DPI.")
    exit(1)

if FORMAT not in DOCUMENT_FORMATS:
    print(f"Invalid format '{FORMAT}'. Supported formats are: {', '.join(DOCUMENT_FORMATS.keys())}.")
    exit(1)

if not os.path.exists(CONFIG_FILE):
    print(f"Configuration file not found at {CONFIG_FILE}. Please create it.")
    exit(1)

with open(os.path.join(CONFIG_FILE), "rb") as f:
    config = tomllib.load(f)

WITH_PAPERLESS = config.get("paperless", False)
print(f"Paperless integration is {'enabled' if WITH_PAPERLESS else 'disabled'}.")

BATCH_DIR = config.get("batch_dir", "batch_scans")
if BATCH_DIR.lower() == "tmp":
    # Use a temporary directory if "tmp" is specified
    BATCH_DIR = f"/tmp/{os.urandom(15).hex()}"
    
if WITH_PAPERLESS:
    PAPERLESS_URL = config["paperless"].get("base_url", None)
    if not PAPERLESS_URL:
        print("Paperless URL not configured. Please set it in the config file.")
        exit(1)
    PAPERLESS_URL = PAPERLESS_URL.rstrip("/")  # Ensure no trailing slash

    PAPERLESS_API_KEY = config["paperless"].get("api_key", None)
    if not PAPERLESS_API_KEY:
        print("Paperless API key not configured. Please set it in the config file.")
        exit(1)

SSH_ARGS = config.get("ssh_args", None)
if not SSH_ARGS:
    print("SSH arguments not configured. Please set them in the config file.")
    exit(1)

# Validate SSH arguments format
def validate_ssh_args(ssh_args):
    # Matches 'user@host:port', 'user@host', or 'host'
    pattern = r"^([a-zA-Z0-9_\-]+@)?[a-zA-Z0-9_\-]+(\:[0-9]+)?$"
    return re.match(pattern, ssh_args) is not None

# Check if SSH_ARGS is in the correct format
if not validate_ssh_args(SSH_ARGS):
    print("Invalid SSH arguments format. Please check your config file. It should be in the format 'user@host:port', 'user@host', or 'host'")
    exit(1)


SSH_CMD = ["ssh", SSH_ARGS]

SCAN_CMD = SSH_CMD + ["scanimage", "--format=pdf", f"--resolution={RESOLUTION}", f"-x {DOCUMENT_FORMATS[FORMAT]['width']}", f"-y {DOCUMENT_FORMATS[FORMAT]['height']}", "--output-file out.pdf"]
CPY_SCAN_CMD = SSH_CMD + ["cp", "out.pdf"]
CREATE_BATCH_DIR_CMD = SSH_CMD + ["mkdir", "-p", BATCH_DIR]
CPY_CMD = ["scp", f"{SSH_ARGS}:out.pdf"]
CPY_BATCH_CMD = ["scp", f"{SSH_ARGS}:{BATCH_DIR}/scan.pdf"]
MERGE_CMD = SSH_CMD + ["gs", "-q", f"-sPAPERSIZE={FORMAT}", "-dNOPAUSE", "-dBATCH", "-dCompressFonts=true", "-r150" ,"-sDEVICE=pdfwrite", f"-sOutputFile={BATCH_DIR}/scan.pdf"]

def generate_cpy_cmd(idx, dir):
    idx_string = str(idx).zfill(2)  # Zero-pad the index to 2 digits
    return CPY_CMD + [os.path.join(dir, f"out{idx_string}.pdf")]

def check_connection():
    try:
        subprocess.run(SSH_CMD + ["exit"], check=True, capture_output=True)
        print("Connection to scanpi is successful.")
    except subprocess.CalledProcessError:
        print("Failed to connect to scanpi. Please check your SSH connection.")
        exit(1)

def upload_to_paperless(output_name):
    RESTAPI_URL = f"{PAPERLESS_URL}/api/documents/post_document/"
    headers = {
        "Authorization": f"Token {PAPERLESS_API_KEY}",
    }
    if not output_name.endswith(".pdf"):
        output_name += ".pdf"
    with open(os.path.join(os.getcwd(), output_name), "rb") as file:
        pdf = file.read()
        response = requests.post(RESTAPI_URL, headers=headers, files={
            "document": pdf,
        }, data={"title": output_name[:-4],  # Remove .pdf extension for title
                })
    if response.status_code == requests.codes.ok:
        print("PDF uploaded successfully to Paperless.")
    else:
        print(f"Failed to upload PDF to Paperless. Status code: {response.status_code}")
        print("Response:", response.text)
        exit(1)
    

def check_scanner_status():
    try:
        result = subprocess.run(SSH_CMD + ["scanimage", "-L"], capture_output=True, text=True, check=True)
        if "device" in result.stdout:
            print("Scanner is available.")
        else:
            print("No scanner found. Please check the scanner connection.")
            exit(1)
    except subprocess.CalledProcessError:
        print("Error checking scanner status. Please ensure the scanner is connected and configured correctly.")
        exit(1)

def cleanup_scanpi(batch_dir=None):
    try:
        subprocess.run(SSH_CMD + [ "rm", "out.pdf"], check=True)
        print("Temporary files on scanpi cleaned up.")
        if batch_dir:
            subprocess.run(["ssh", "scanpi", "rm", "-rf", batch_dir], check=True)
            print(f"Batch directory {batch_dir} cleaned up on scanpi.")
    except subprocess.CalledProcessError:
        print("Failed to clean up temporary files on scanpi. Please check the connection and permissions.")

def merge_pdfs(num_files):
    current_merge_cmd = MERGE_CMD + [f"{BATCH_DIR}/out{i:02d}.pdf" for i in range(num_files)]
    subprocess.run(current_merge_cmd, check=True)
    print("PDF files merged successfully.")
    return
    


def main():
    print("Hello from scanpi!")
    # Check SSH connection
    check_connection()
    # Check scanner status
    check_scanner_status()
    num_scans = int(input("How many pages do you want to scan? "))
    if num_scans <= 0:
        print("Invalid number of scans. Please enter a positive integer.")
        exit(1)
    print(f"Scanning {num_scans} pages...")
    with tempfile.TemporaryDirectory() as tmpdirname:
        if num_scans > 1:
            # Create a batch directory on scanpi
            print("Creating batch directory on scanpi...")
            subprocess.run(CREATE_BATCH_DIR_CMD, check=True)
            for i in range(num_scans):
                print(f"Scanning page {i + 1}...")
                input(f"Press Enter to scan page {i + 1}...")
                # Execute the scan command
                subprocess.run(SCAN_CMD, check=True)
                subprocess.run(CPY_SCAN_CMD + [f"{BATCH_DIR}/out{i:02d}.pdf"], check=True)
                print("Scanning complete. Check the output PDF file.")
                # Copy the scanned file
            print(f"All {num_scans} pages scanned and copied to {BATCH_DIR}.")
            print("Done scanning all pages.")

            merge_pdfs(num_scans)

            subprocess.run(CPY_BATCH_CMD + [os.path.join(tmpdirname, "scan.pdf")], check=True)
        
            # Cleanup scanpi temporary files
            cleanup_scanpi(BATCH_DIR)
        else:
            print("Scanning a single page...")
            input("Press Enter to scan the page...")
            # Execute the scan command
            subprocess.run(SCAN_CMD, check=True)
            print("Scanning complete. Check the output PDF file.")
            print("Copying the scanned file to the temporary directory...")
            subprocess.run(CPY_CMD + [os.path.join(tmpdirname, "scan.pdf")], check=True)
            cleanup_scanpi()  # Clean up temporary files on scanpi
            # Copy the scanned file to the temporary directory

        output_name = input("Enter the name for the merged PDF file (without extension): ")
        # copy the merged PDF to the output path: ~/Temp
        if not output_name:
            output_name = "scan"
        if not output_name.endswith(".pdf"):
            output_name += ".pdf"
        shutil.copy(os.path.join(tmpdirname, "scan.pdf"), os.path.join(os.getcwd(), output_name))

        if WITH_PAPERLESS:
            upload_ask = input("Do you want to upload the scanned PDF to Paperless? (y/n): ").strip().lower()
            if upload_ask == 'y':
                upload_to_paperless(output_name)
            else:
                print("Upload skipped. You can upload the PDF manually later.")


if __name__ == "__main__":
    main()
