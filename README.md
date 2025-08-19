# Scanpi

Scanpi is a simple command-line tool to scan documents using a remote scanner over SSH. It can optionally upload scanned documents to a Paperless-ng instance for document management.

## Features

- Scan single or multi-page documents via a remote scanner.
- Supports multiple paper sizes and resolutions.
- Secure SSH connection to the scanner host.
- Optional integration with **Paperless-ngx** for automatic document upload.

## Requirements

- Python 3.11+
- Dependencies: `requests`

## Installation

1. Clone this repository:
   ```sh
   git clone https://github.com/yourusername/scanpi.git
   ```
2. Install dependencies:
   ```sh
   pip install requests
   ```

## Configuration

Scanpi requires a configuration file in TOML format. By default, it looks for:

```
~/.config/scanpi/config
```

You can specify a different config file with the `-c` option.

### Example config file

```toml
ssh_args = "user@scanpi-host"
batch_dir = "/home/user/batch_scans"

[paperless]
base_url = "http://your-paperless-ngx-instance"
api_key = "your-paperless-api-key"
```

#### Config options

- `ssh_args` (required): SSH connection string (`user@host` or `host`).
- `batch_dir` (optional): Directory on the remote scanner for batch scans. Use `"tmp"` to create a temporary directory.
- `[paperless]` (optional): Section for Paperless-ng integration.
  - `base_url`: URL of your Paperless-ng instance.
  - `api_key`: API token for Paperless-ng.

## Usage

```sh
python main.py [options]
```

### Options

- `-c`, `--config`   Path to config file (default: `~/.config/scanpi/config`)
- `-f`, `--format`   Document format: `a4`, `a5`, `a6`, `letter`, `legal` (default: `a4`)
- `-r`, `--resolution`  Scan resolution: `200`, `400`, or `600` DPI (default: `400`)
- `-v`, `--version`  Show version

### Example

```sh
python main.py -f letter -r 600
```

## Workflow

1. The tool checks SSH connectivity and scanner status.
2. Enter the number of pages to scan.
3. For each page, follow the prompts to scan.
4. The scanned PDFs are merged (if multi-page).
5. Choose a name for the output PDF.
6. Optionally upload to Paperless-ngx.

## Paperless-ng Integration

If the `[paperless]` section is present in your config, Scanpi can upload the final PDF to your Paperless-ng instance. You will be prompted after scanning.

## Troubleshooting

- Ensure your SSH connection string is correct and the remote scanner is reachable.
- The config file must exist and be readable.
- For Paperless integration, ensure the API key and URL are correct.
