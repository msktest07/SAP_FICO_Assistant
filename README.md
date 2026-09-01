# SAP_FICO_ASSISTANT

Project Name
------------

SAP_FICO_ASSISTANT (SAP FICO Assistant)

Project Description
-------------------

SAP_FICO_ASSISTANT is a small, dependency-free local web application that provides curated SAP FI (Financial Accounting) and CO (Controlling) guidance. It answers common questions using an internal knowledge base, stores conversation history, accepts feedback, and includes a simple dashboard and topic explorer.

Features
--------

- Natural-language question entry with context selectors (module, product, release, country)
- Structured answers with recommended steps, transactions, and follow-up prompts
- Persistent conversation history stored in SQLite
- Feedback collection (helpful / not helpful) per conversation
- Topic explorer and a basic quality dashboard
- Static frontend (HTML/CSS/JS) served by a lightweight Python HTTP server

Technology Used
---------------

- Python 3.10+ (standard library only)
- SQLite for local persistence
- Vanilla HTML, CSS, and JavaScript for the frontend

How to Install
--------------

1. Clone the repository:

```bash
git clone https://github.com/msktest07/SAP_FICO_Assistant.git
cd SAP_FICO_Assistant
```

2. (Optional) Create a virtual environment and activate it:

```bash
python -m venv .venv
# PowerShell
.\.venv\Scripts\Activate.ps1
# or on cmd.exe
.\.venv\Scripts\activate.bat
```

How to Run Locally
-------------------

Run the application with Python 3.10 or newer:

```powershell
python app.py
```

Open the app in your browser at: http://127.0.0.1:8000/

Notes
-----

- The SQLite database `sap_fico.db` will be created automatically on first run and is included in `.gitignore`.
- This project is a local prototype and does not call external language models or production SAP systems. Use it for exploration and offline guidance only.

Testing
-------

Run the unit tests:

```powershell
python -m unittest discover -s tests -v
```

GitHub Repository
-----------------

https://github.com/msktest07/SAP_FICO_Assistant

Live Application URL
--------------------

The application runs locally. After starting the server, open:

http://127.0.0.1:8000/

If you want, I can update other docs, add a `requirements.txt` entry, or push this README to the remote repo for you.
