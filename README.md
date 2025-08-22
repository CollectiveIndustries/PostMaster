# SpamVanquisher

SpamVanquisher is a Python-based email classification tool using TensorFlow to detect spam and sort emails into folders. This archive contains all source code, configuration files, and setup instructions.

---

## Dependencies

The following dependencies must be installed for the application to run:

- Python 3.9–3.11
- MySQL client library (`MySQLdb`)
- TensorFlow
- Keras (comes with TensorFlow)
- Other Python libraries (already included in `requirements.txt`):
  - `pickle`
  - `logging`
  - `threading`
  - `os`
  - `typing`

### TensorFlow Installation Options

#### 1. CPU-only (simplest)
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install tensorflow
```

#### 2. GPU-enabled (requires NVIDIA GPU with CUDA & cuDNN)
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install tensorflow[and-cuda]
```

Verify the installation:
```bash
python -c "import tensorflow as tf; print(tf.__version__)"
```

---

## Setup Instructions

1. Clone or extract the archive.
2. Create a virtual environment and activate it:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Ensure MySQL server is running and the database is configured (see `lib/config.py` for database settings).
5. Place training data and logs in the directory specified by `config.TRAINING_DATA_PATH`.

---

## Running the Application

```bash
python main.py
```

- The application will connect to the database, train the email classification model, and process incoming emails.
- To classify emails, ensure the model is trained or loaded first.
