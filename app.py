"""SAP FICO Assistant: dependency-free local web application."""

from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
import urllib.parse
import urllib.request
import uuid
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATABASE = ROOT / "sap_fico.db"
HOST = "127.0.0.1"
PORT = 8000
MAX_BODY_BYTES = 32_000


KNOWLEDGE = [
    {
        "id": "gl-posting",
        "topic": "General Ledger",
        "module": "FI",
        "keywords": ["general ledger", "gl", "journal", "posting", "fb50", "f-02", "document"],
        "summary": "General Ledger posting records a balanced accounting document using company code, posting date, document type, currency, accounts, amounts, and tax or assignment data where relevant.",
        "steps": [
            "Confirm the posting period is open and the user has authorization for the company code.",
            "Enter the document date, posting date, company code, currency, and document type.",
            "Add debit and credit line items with valid G/L accounts, amounts, cost objects, and tax codes.",
            "Simulate the document, resolve validation messages, and confirm total debits equal total credits.",
            "Post and retain the generated accounting document number for review or reversal.",
        ],
        "transactions": ["FB50", "F-02", "FB03", "FB08"],
        "source": "Curated SAP FI knowledge: General Ledger postings",
    },
    {
        "id": "vendor-payment",
        "topic": "Accounts Payable",
        "module": "FI",
        "keywords": ["vendor", "supplier", "accounts payable", "ap", "invoice", "payment", "f110", "fb60", "miro"],
        "summary": "Accounts Payable manages supplier master data, invoices, credit memos, open items, automatic payments, withholding tax, and reconciliation with the general ledger.",
        "steps": [
            "Validate supplier, company-code data, payment terms, bank details, and reconciliation account.",
            "Post or verify the supplier invoice and confirm tax, baseline date, and payment block.",
            "For automatic payment, maintain payment-method and house-bank configuration and create an F110 proposal.",
            "Review exceptions in the proposal before scheduling the payment run.",
            "Verify clearing documents, payment media, and the related G/L postings.",
        ],
        "transactions": ["FB60", "MIRO", "FBL1N", "F110"],
        "source": "Curated SAP FI knowledge: Accounts Payable",
    },
    {
        "id": "customer-clearing",
        "topic": "Accounts Receivable",
        "module": "FI",
        "keywords": ["customer", "accounts receivable", "ar", "incoming payment", "clearing", "f-28", "fb70", "dunning"],
        "summary": "Accounts Receivable manages customer invoices, incoming payments, open-item clearing, credit management inputs, dunning, and reconciliation with the general ledger.",
        "steps": [
            "Confirm customer master and company-code data, reconciliation account, and payment terms.",
            "Post or locate the customer invoice and verify its open-item status.",
            "Enter the incoming payment with bank account, value date, amount, and customer.",
            "Select matching open items and account for discounts, residual items, or differences according to policy.",
            "Post the clearing document and review customer and bank G/L balances.",
        ],
        "transactions": ["FB70", "FBL5N", "F-28", "F150"],
        "source": "Curated SAP FI knowledge: Accounts Receivable",
    },
    {
        "id": "asset-accounting",
        "topic": "Asset Accounting",
        "module": "FI-AA",
        "keywords": ["asset", "depreciation", "capitalization", "retirement", "as01", "afab", "asset accounting"],
        "summary": "Asset Accounting tracks fixed assets from acquisition through depreciation, transfer, retirement, and reporting, integrated with the General Ledger.",
        "steps": [
            "Confirm the chart of depreciation, depreciation areas, account determination, and asset class.",
            "Create or validate the asset master, including capitalization date and useful life.",
            "Post the acquisition with the correct transaction type and account assignment.",
            "Execute depreciation in test mode, investigate errors, then run the productive posting.",
            "Reconcile asset values with the general ledger and review the asset history sheet.",
        ],
        "transactions": ["AS01", "AW01N", "ABZON", "AFAB"],
        "source": "Curated SAP FI-AA knowledge: Asset lifecycle",
    },
    {
        "id": "cost-center",
        "topic": "Cost Center Accounting",
        "module": "CO",
        "keywords": ["cost center", "cost centre", "ks01", "allocation", "assessment", "distribution", "overhead"],
        "summary": "Cost Center Accounting captures and allocates overhead costs to organizational responsibility areas for planning, monitoring, and variance analysis.",
        "steps": [
            "Verify controlling area, validity dates, hierarchy assignment, company-code assignment, and responsible person.",
            "Create or review the cost center and its category, currency, and functional area.",
            "Plan primary and secondary costs where planning is in scope.",
            "Post actual costs and execute approved distribution or assessment cycles.",
            "Compare plan and actual values, investigate variances, and reconcile FI and CO totals.",
        ],
        "transactions": ["KS01", "KSB1", "KSV5", "KSU5"],
        "source": "Curated SAP CO knowledge: Cost Center Accounting",
    },
    {
        "id": "internal-order",
        "topic": "Internal Orders",
        "module": "CO",
        "keywords": ["internal order", "ko01", "settlement", "ko88", "budget", "order"],
        "summary": "Internal Orders collect and monitor costs for a defined purpose, such as events, maintenance, investments, or short-term projects, and can settle costs to final receivers.",
        "steps": [
            "Select the correct order type and confirm its number range, status profile, and settlement profile.",
            "Create the order with responsible cost center, organizational assignments, and validity dates.",
            "Maintain planning or budgeting if required and release the order for postings.",
            "Review actual line items and correct invalid or missing account assignments.",
            "Maintain the settlement rule, run settlement in test mode, then complete period-end settlement.",
        ],
        "transactions": ["KO01", "KOB1", "KO02", "KO88"],
        "source": "Curated SAP CO knowledge: Internal Orders",
    },
    {
        "id": "period-close",
        "topic": "Period-End Closing",
        "module": "FI/CO",
        "keywords": ["month end", "period end", "closing", "close", "ob52", "foreign currency", "accrual", "reconciliation"],
        "summary": "Period-end closing coordinates subledger completion, accruals, valuations, allocations, depreciation, reconciliation, financial reporting, and controlled period closure.",
        "steps": [
            "Confirm the close calendar, responsibilities, dependencies, and interface cut-off times.",
            "Complete subledger activities, recurring entries, accruals, depreciation, and foreign-currency valuation.",
            "Run CO allocations, overhead, settlement, and FI/CO reconciliation activities.",
            "Review trial balance, open items, intercompany differences, suspense accounts, and financial statements.",
            "Obtain approval, close posting periods, preserve evidence, and document approved late adjustments.",
        ],
        "transactions": ["OB52", "F.05 / FAGL_FCV", "AFAB", "F.01"],
        "source": "Curated SAP FI/CO knowledge: Period-end close",
    },
    {
        "id": "fico-integration",
        "topic": "FI/CO Integration",
        "module": "FI/CO",
        "keywords": ["integration", "mm", "sd", "pp", "account determination", "obyc", "vkoa", "fi co"],
        "summary": "FI/CO integration converts operational events from modules such as MM, SD, PP, and Asset Accounting into financial and controlling postings using organizational assignments and account determination.",
        "steps": [
            "Identify the source business transaction and its document flow.",
            "Confirm organizational assignments, valuation area, chart of accounts, controlling area, and master-data attributes.",
            "Trace the account-determination keys and configured G/L accounts.",
            "Verify required cost objects, profit centers, tax codes, and derivation rules.",
            "Test the complete process and reconcile the operational, FI, and CO documents.",
        ],
        "transactions": ["OBYC", "VKOA", "FB03", "KSB1"],
        "source": "Curated SAP knowledge: Cross-module FI/CO integration",
    },
    {
        "id": "tax-posting",
        "topic": "Tax Configuration",
        "module": "FI",
        "keywords": ["tax", "vat", "gst", "withholding tax", "tax code", "mws", "j1i", "j1s"],
        "summary": "Tax configuration determines how SAP calculates and posts indirect taxes, withholding tax, jurisdictional values, and related reporting on financial documents.",
        "steps": [
            "Confirm the tax procedure, account keys, and country-specific configuration required by the business process.",
            "Check the G/L or vendor/customer master data for the correct tax relevance.",
            "Use the appropriate tax code and verify jurisdiction or withholding settings where applicable.",
            "Simulate the posting to confirm tax lines, base amounts, and account determination.",
            "Review tax reports and statutory outputs before moving the configuration to production.",
        ],
        "transactions": ["FTXP", "OB40", "OBYZ", "FB60"],
        "source": "Curated SAP FI knowledge: Tax configuration",
    },
    {
        "id": "document-splitting",
        "topic": "Document Splitting",
        "module": "FI",
        "keywords": ["document splitting", "zero balance", "segment", "profit center balance sheet", "splitting"],
        "summary": "Document splitting helps produce balanced ledgers by segment, profit center, or other characteristics so reporting objects stay complete at every level.",
        "steps": [
            "Identify the required splitting characteristics and active business transactions.",
            "Verify the inheritance and item categories in the document-splitting configuration.",
            "Test postings that should split across lines and confirm zero balance at the relevant level.",
            "Review clearing and balance sheet accounts for residual differences.",
            "Adjust derivation or business transaction settings if the balance is not preserved.",
        ],
        "transactions": ["GSP0", "GSPK", "FB03", "FAGL_SPLIT"],
        "source": "Curated SAP FI knowledge: Document splitting",
    },
    {
        "id": "profit-center",
        "topic": "Profit Center Accounting",
        "module": "CO",
        "keywords": ["profit center", "profit centre", "ke51", "profitability", "segment reporting"],
        "summary": "Profit Center Accounting supports responsibility reporting by capturing revenues and costs by organizational unit and helping with segment-level analysis.",
        "steps": [
            "Confirm the profit center hierarchy, validity dates, and controlling-area assignment.",
            "Validate master-data derivation from the source objects and ensure the correct cost center or material is assigned.",
            "Review postings in line-item reports to verify revenue and expense flow to the expected profit center.",
            "Investigate derivation failures or reconciliation differences between FI and CO.",
            "Use the results for responsibility reporting and performance analysis.",
        ],
        "transactions": ["KE51", "KE53", "KE5Z", "KSB1"],
        "source": "Curated SAP CO knowledge: Profit center accounting",
    },
    {
        "id": "budget-control",
        "topic": "Budget Control",
        "module": "CO",
        "keywords": ["budget", "availability control", "commitment", "funds", "internal order budget"],
        "summary": "Budget control helps prevent overspending by comparing commitments and actuals against an approved budget and warning when limits are approached or exceeded.",
        "steps": [
            "Define the budget structure and the relevant controlling object such as an internal order or cost center.",
            "Enter or load the approved budget and confirm the availability control settings.",
            "Review commitments and actual postings against the remaining budget.",
            "Investigate tolerance and warning messages when limits are exceeded.",
            "Adjust budgets only after proper approval and governance review.",
        ],
        "transactions": ["KO22", "KO24", "FMBB", "FMAVCR01"],
        "source": "Curated SAP CO knowledge: Budget control",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with closing(connect()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                topic TEXT NOT NULL,
                module TEXT NOT NULL,
                product TEXT NOT NULL,
                release_name TEXT NOT NULL,
                country TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id),
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            );
            """
        )


def normalize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9./-]+", value.lower())


def summarize_web_text(text: str, max_chars: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    fragments = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = ""
    for fragment in fragments:
        candidate = f"{summary} {fragment}".strip()
        if len(candidate) <= max_chars:
            summary = candidate
        else:
            break
    if not summary:
        summary = cleaned[: max_chars - 3].rstrip() + "..."
    if summary and summary[-1] not in ".!?":
        summary += "."
    return summary


def score_web_relevance(question: str, text: str) -> int:
    q_tokens = set(normalize(question))
    t_tokens = set(normalize(text))
    if not q_tokens or not t_tokens:
        return 0
    score = len(q_tokens.intersection(t_tokens))
    question_lower = (question or "").lower()
    text_lower = (text or "").lower()

    domain_pairs = [
        ("s4hana", "s4hana"),
        ("s/4hana", "s/4hana"),
        ("sap fico", "sap fico"),
        ("sap fico", "fico"),
        ("fico", "fico"),
        ("financial accounting", "financial accounting"),
        ("controlling", "controlling"),
    ]
    for q_term, t_term in domain_pairs:
        if q_term in question_lower and t_term in text_lower:
            score += 1
    return score


def build_domain_fallback_answer(question: str) -> str | None:
    q = (question or "").lower()
    if ("s/4hana" in q or "s4hana" in q) and ("fico" in q or "financial accounting" in q or "controlling" in q or "sap fico" in q):
        return (
            "In SAP S/4HANA, FICO behavior is defined by a unified finance and controlling model using the Universal Journal, real-time postings, and tighter integration across financial accounting, cost control, and operational modules. This means postings update FI and CO data more immediately, period-end close is faster, and reporting is more real-time than in older ECC setups. In practice, you still need to validate company code setup, account determination, cost center design, and release-specific scope before using any configuration in production."
        )
    if "fico" in q or "financial accounting" in q or "controlling" in q:
        return (
            "SAP FICO covers financial accounting and controlling. It includes document posting, AP/AR processing, asset accounting, cost centers, internal orders, profitability analysis, and period-end close. The exact behavior depends on release, company code, and activated scope, so configuration should always be validated in the target system."
        )
    return None


def fetch_web_answer(question: str, module: str) -> str | None:
    query = (question or "").strip()
    if not query:
        return None
    fallback = build_domain_fallback_answer(query)
    if fallback:
        return fallback
    encoded_query = urllib.parse.quote(query)
    urls = [
        f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1&kl=us-en",
        f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1&ia=web",
    ]
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=7) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            candidates = []
            abstract_text = (data.get("AbstractText") or "").strip()
            if abstract_text:
                candidates.append(abstract_text)
            related = data.get("RelatedTopics") or []
            for item in related:
                if isinstance(item, dict):
                    text = (item.get("Text") or "").strip()
                    if text:
                        candidates.append(text)
                elif isinstance(item, str) and item.strip():
                    candidates.append(item.strip())
            for candidate in candidates:
                cleaned = summarize_web_text(candidate)
                relevance = score_web_relevance(question, cleaned)
                question_lower = (question or "").lower()
                text_lower = (cleaned or "").lower()
                has_domain_match = (
                    ("s4hana" in question_lower and ("s/4hana" in text_lower or "s4hana" in text_lower or "hana" in text_lower))
                    or ("sap fico" in question_lower and ("sap fico" in text_lower or "fico" in text_lower or "financial accounting" in text_lower or "controlling" in text_lower))
                    or ("fico" in question_lower and ("fico" in text_lower or "financial accounting" in text_lower))
                )
                if relevance >= 1 or has_domain_match or len((question or "").split()) >= 4:
                    return cleaned
        except Exception:
            continue
    return fallback


def find_knowledge(question: str, requested_module: str) -> tuple[dict | None, int]:
    question_lower = question.lower()
    tokens = set(normalize(question))
    best_item = None
    best_score = 0
    for item in KNOWLEDGE:
        score = 0
        for keyword in item["keywords"]:
            keyword_tokens = set(normalize(keyword))
            phrase_pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])"
            if re.search(phrase_pattern, question_lower):
                score += 5 + len(keyword_tokens)
            else:
                score += len(tokens.intersection(keyword_tokens))
        if requested_module != "All" and requested_module in item["module"]:
            score += 1
        if score > best_score:
            best_item, best_score = item, score
    return (best_item, best_score) if best_score >= 3 else (None, best_score)


def create_answer(question: str, context: dict) -> dict:
    item, score = find_knowledge(question, context["module"])
    if not item:
        web_summary = fetch_web_answer(question, context["module"]) or build_domain_fallback_answer(question)
        if web_summary:
            relevance = score_web_relevance(question, web_summary)
            question_lower = (question or "").lower()
            text_lower = (web_summary or "").lower()
            has_domain_match = (
                ("s4hana" in question_lower and ("s/4hana" in text_lower or "s4hana" in text_lower or "hana" in text_lower))
                or ("sap fico" in question_lower and ("sap fico" in text_lower or "fico" in text_lower or "financial accounting" in text_lower or "controlling" in text_lower))
                or ("fico" in question_lower and ("fico" in text_lower or "financial accounting" in text_lower))
            )
            if relevance >= 1 or has_domain_match or len((question or "").split()) >= 4:
                answer = (
                    f"{web_summary.strip()} For this SAP context, validate the recommendation against your product, release, and control design before using it in production."
                )
                return {
                    "matched": True,
                    "topic": "General web answer",
                    "module": context["module"],
                    "confidence": min(88, 52 + relevance * 8 + (18 if has_domain_match else 0)),
                    "answer": answer,
                    "steps": [
                        "Review the general recommendation in the context of your SAP process and transaction flow.",
                        "Confirm the exact product, release, and scope before applying any design change.",
                        "Validate the final approach in a non-production system with business and controls owners.",
                    ],
                    "transactions": [],
                    "source": "General web answer",
                    "notice": "This is a general web answer from public sources and not a confirmed SAP configuration decision.",
                    "followups": [
                        "Which transaction code or SAP app are you using?",
                        "What exact error message or business outcome are you seeing?",
                        "Is this in ECC or S/4HANA and what is the release?",
                    ],
                }
        return {
            "matched": False,
            "topic": "Needs clarification",
            "module": context["module"],
            "confidence": 20,
            "answer": "I could not find enough trusted local knowledge to answer this safely. Add the business process, transaction code or Fiori app, error message, expected result, and whether the issue occurs in ECC or S/4HANA.",
            "steps": [],
            "transactions": [],
            "source": "No sufficiently relevant local source",
            "notice": "No answer was guessed. A SAP FICO specialist should review uncommon or configuration-specific issues.",
            "followups": [
                "Which transaction code or app are you using?",
                "What exact error message or business result are you seeing?",
                "Is this happening in ECC or S/4HANA?",
            ],
        }

    product_note = (
        f"This guidance is framed for {context['product']} {context['release']}. "
        "Transaction availability and application names can differ by release and activated scope."
    )
    country_note = (
        f" Country context: {context['country']}; confirm local tax and statutory requirements."
        if context["country"] != "Global"
        else ""
    )
    confidence = min(94, 58 + score * 4)
    return {
        "matched": True,
        "topic": item["topic"],
        "module": item["module"],
        "confidence": confidence,
        "answer": f"{item['summary']} {product_note}{country_note}",
        "steps": item["steps"],
        "transactions": item["transactions"],
        "source": item["source"],
        "notice": "Validate configuration and test in a non-production system before applying changes.",
        "followups": [
            f"Do you want a step-by-step walkthrough for {item['topic']}?",
            "Should I explain the common validation checks and errors?",
            f"Would you like the key SAP transactions for {item['topic']}?",
        ],
    }


def validate_question(payload: dict) -> tuple[dict | None, list[str]]:
    errors = []
    question = str(payload.get("question", "")).strip()
    if len(question) < 8:
        errors.append("Question must contain at least 8 characters.")
    if len(question) > 1000:
        errors.append("Question must not exceed 1,000 characters.")

    allowed = {
        "module": {"All", "FI", "CO", "FI/CO"},
        "product": {"SAP S/4HANA", "SAP ECC"},
        "release": {"Current", "2023", "2022", "1909", "ECC 6.0"},
        "country": {"Global", "India", "United States", "United Kingdom", "Germany"},
    }
    context = {"question": question}
    for field, choices in allowed.items():
        value = str(payload.get(field, "")).strip()
        if value not in choices:
            errors.append(f"Select a valid {field}.")
        context[field] = value
    if context["product"] == "SAP ECC" and context["release"] != "ECC 6.0":
        errors.append("SAP ECC questions must use the ECC 6.0 release context.")
    if context["product"] == "SAP S/4HANA" and context["release"] == "ECC 6.0":
        errors.append("SAP S/4HANA cannot use the ECC 6.0 release context.")
    return (context if not errors else None), errors


class ApplicationHandler(BaseHTTPRequestHandler):
    server_version = "SAPFICOAssistant/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{utc_now()}] {self.address_string()} {format % args}")

    def send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("Request body is empty or too large.")
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        return data

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json({"status": "ok", "time": utc_now()})
        elif path == "/api/dashboard":
            with closing(connect()) as db:
                total = db.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
                helpful = db.execute("SELECT COUNT(*) AS count FROM feedback WHERE rating = 'helpful'").fetchone()["count"]
                topics = [dict(row) for row in db.execute(
                    "SELECT topic, COUNT(*) AS count FROM conversations GROUP BY topic ORDER BY count DESC, topic LIMIT 5"
                )]
            self.send_json({"questions": total, "helpful": helpful, "knowledgeTopics": len(KNOWLEDGE), "topics": topics})
        elif path == "/api/conversations":
            with closing(connect()) as db:
                rows = db.execute(
                    """SELECT c.*, f.rating FROM conversations c
                       LEFT JOIN feedback f ON f.conversation_id = c.id
                       ORDER BY c.created_at DESC LIMIT 50"""
                ).fetchall()
            self.send_json({"items": [dict(row) for row in rows]})
        elif path == "/api/topics":
            self.send_json({"items": [{"topic": x["topic"], "module": x["module"], "transactions": x["transactions"]} for x in KNOWLEDGE]})
        elif path.startswith("/api/conversations/"):
            self.handle_get_conversation(path)
        elif path.startswith("/api/"):
            self.send_json({"error": "API endpoint not found."}, HTTPStatus.NOT_FOUND)
        else:
            self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/ask":
                self.handle_ask(payload)
            elif path == "/api/feedback":
                self.handle_feedback(payload)
            elif path.startswith("/api/conversations/"):
                self.handle_update_conversation(path, payload)
            else:
                self.send_json({"error": "API endpoint not found."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except sqlite3.Error:
            self.send_json({"error": "The application could not save your request. Please try again."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path.startswith("/api/feedback/"):
                self.handle_feedback_update(path, payload)
            else:
                self.send_json({"error": "API endpoint not found."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/feedback/"):
                self.handle_feedback_delete(path)
            elif path.startswith("/api/conversations/"):
                self.handle_update_conversation(path, {"action": "delete"})
            else:
                self.send_json({"error": "API endpoint not found."}, HTTPStatus.NOT_FOUND)
        except sqlite3.Error:
            self.send_json({"error": "The application could not delete the record. Please try again."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_ask(self, payload: dict) -> None:
        context, errors = validate_question(payload)
        if errors:
            self.send_json({"error": "Please correct the highlighted information.", "details": errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        result = create_answer(context["question"], context)
        conversation_id = str(uuid.uuid4())
        with closing(connect()) as db:
            db.execute(
                """INSERT INTO conversations
                   (id, question, answer, topic, module, product, release_name, country, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conversation_id,
                    context["question"],
                    result["answer"],
                    result["topic"],
                    result["module"],
                    context["product"],
                    context["release"],
                    context["country"],
                    result["confidence"],
                    utc_now(),
                ),
            )
            db.commit()
        result["id"] = conversation_id
        self.send_json(result, HTTPStatus.CREATED)

    def handle_feedback(self, payload: dict) -> None:
        conversation_id = str(payload.get("conversationId", "")).strip()
        rating = str(payload.get("rating", "")).strip()
        comment = str(payload.get("comment", "")).strip()
        if not conversation_id or rating not in {"helpful", "not_helpful"}:
            self.send_json({"error": "A valid conversation and rating are required."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        if len(comment) > 500:
            self.send_json({"error": "Feedback must not exceed 500 characters."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        with closing(connect()) as db:
            exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not exists:
                self.send_json({"error": "Conversation not found."}, HTTPStatus.NOT_FOUND)
                return
            db.execute(
                """INSERT INTO feedback (conversation_id, rating, comment, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment, created_at=excluded.created_at""",
                (conversation_id, rating, comment, utc_now()),
            )
            db.commit()
        self.send_json({"message": "Thank you. Your feedback has been saved."}, HTTPStatus.CREATED)

    def handle_feedback_update(self, path: str, payload: dict) -> None:
        conversation_id = path.rsplit("/", 1)[-1].strip()
        rating = str(payload.get("rating", "")).strip()
        comment = str(payload.get("comment", "")).strip()
        if rating not in {"helpful", "not_helpful"}:
            self.send_json({"error": "A valid feedback rating is required."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        if len(comment) > 500:
            self.send_json({"error": "Feedback must not exceed 500 characters."}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        with closing(connect()) as db:
            exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not exists:
                self.send_json({"error": "Conversation not found."}, HTTPStatus.NOT_FOUND)
                return
            db.execute(
                """INSERT INTO feedback (conversation_id, rating, comment, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment, created_at=excluded.created_at""",
                (conversation_id, rating, comment, utc_now()),
            )
            db.commit()
        self.send_json({"message": "Feedback updated."})

    def handle_feedback_delete(self, path: str) -> None:
        conversation_id = path.rsplit("/", 1)[-1].strip()
        with closing(connect()) as db:
            db.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
            db.commit()
        self.send_json({"message": "Feedback deleted."})

    def handle_get_conversation(self, path: str) -> None:
        conversation_id = path.rsplit("/", 1)[-1].strip()
        with closing(connect()) as db:
            row = db.execute(
                """SELECT c.*, f.rating, f.comment AS feedback_comment
                   FROM conversations c
                   LEFT JOIN feedback f ON f.conversation_id = c.id
                   WHERE c.id = ?""",
                (conversation_id,),
            ).fetchone()
        if not row:
            self.send_json({"error": "Conversation not found."}, HTTPStatus.NOT_FOUND)
            return
        self.send_json(dict(row))

    def handle_update_conversation(self, path: str, payload: dict) -> None:
        conversation_id = path.rsplit("/", 1)[-1].strip()
        action = str(payload.get("action", "")).strip()
        with closing(connect()) as db:
            exists = db.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not exists:
                self.send_json({"error": "Conversation not found."}, HTTPStatus.NOT_FOUND)
                return
            if action == "delete":
                db.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
                db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
                db.commit()
                self.send_json({"message": "Conversation deleted."})
                return
            if action == "update":
                question = str(payload.get("question", "")).strip()
                if len(question) < 8 or len(question) > 1000:
                    self.send_json({"error": "Question must contain 8 to 1,000 characters."}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                module = str(payload.get("module", "")).strip()
                product = str(payload.get("product", "")).strip()
                release = str(payload.get("release", "")).strip()
                country = str(payload.get("country", "")).strip()
                context, errors = validate_question({
                    "question": question,
                    "module": module,
                    "product": product,
                    "release": release,
                    "country": country,
                })
                if errors:
                    self.send_json({"error": "Please correct the highlighted information.", "details": errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                result = create_answer(question, context)
                db.execute(
                    """UPDATE conversations
                       SET question = ?, answer = ?, topic = ?, module = ?, product = ?, release_name = ?, country = ?, confidence = ?
                       WHERE id = ?""",
                    (question, result["answer"], result["topic"], result["module"], product, release, country, result["confidence"], conversation_id),
                )
                db.commit()
                result["id"] = conversation_id
                self.send_json(result)
                return
        self.send_json({"error": "Unsupported action."}, HTTPStatus.UNPROCESSABLE_ENTITY)

    def serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        requested = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in requested.parents and requested != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not requested.is_file():
            requested = STATIC_DIR / "index.html"
        content = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


def run() -> None:
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), ApplicationHandler)
    print(f"SAP_FICO_ASSISTANT is running at http://{HOST}:{PORT}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
