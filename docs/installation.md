# Installation

## Installation from Binaries

Download the latest release from the [Film-Scan-Converter Latest Release](https://github.com/kaimonmok/Film-Scan-Converter/releases/latest).

If no binary exists for your platform yet, please use the manual installation.

## Manual Installation

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).

2. Download the source files from the repository using one of the following methods:
    - Download ZIP:
      Click the "Code" button on the repository page and select "Download ZIP". Extract the downloaded archive.
    - Clone with Git:
      Run the following command in your terminal: `git clone https://github.com/kaimonmok/Film-Scan-Converter.git`

3. Open the `source` folder in the terminal.

4. Install the required libraries by running the following command in the terminal:

    ```bash
    pip install -r requirements.txt
    ```

5. Run the application by executing the following command in the terminal:

    ```bash
    python "Film Scan Converter.pyw"
    ```

## Manual Installation in Python venv

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).

2. Download the source files from the repository using one of the following methods:
    - Download ZIP:
      Click the "Code" button on the repository page and select "Download ZIP". Extract the downloaded archive.
    - Clone with Git:
      Run the following command in your terminal: `git clone https://github.com/kaimonmok/Film-Scan-Converter.git`

3. Open the `source` folder in the terminal.

4. Create and activate a virtual environment:

    ```bash
    python -m venv venv
    # On macOS/Linux:
    source venv/bin/activate
    # On Windows:
    venv\Scripts\activate
    ```

5. Install the required libraries:

    ```bash
    pip install -r requirements.txt
    ```

6. Run the application:

```bash
python "Film Scan Converter.pyw"
```

## Note on tkinter

The application requires `tkinter` for the GUI. On some platforms this may not installable in a venv or through pip.

- On **macOS**, install it with Homebrew:

    ```bash
    brew install python-tk
    ```

- On **Linux** (Debian/Ubuntu):

    ```bash
    sudo apt-get install python3-tk
    ```

- On **Windows**, `tkinter` is usually included with the standard Python installer. If you encounter issues, ensure you installed Python from [python.org](https://www.python.org/downloads/).
