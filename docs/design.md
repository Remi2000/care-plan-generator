# Care Plan Generator — Design Document

## 1. Overview

### 1.1 Background
A specialty pharmacy (CVS) needs to automatically generate care plans based on patient clinical records. Currently, pharmacists spend 20–40 minutes per patient manually creating these care plans. The pharmacy is short-staffed and backlogged, while care plans are required for Medicare reimbursement and pharma compliance.

### 1.2 Users
- **CVS medical staff** (pharmacists, medical assistants) — the sole users of this system
- Patients do **not** interact with the system; care plans are printed and handed to them

### 1.3 Core Value Proposition
Reduce care plan creation time from 20–40 min to < 5 min by using an LLM to generate structured care plans from patient data entered via a validated web form.

---

## 2. Functional Requirements

### 2.1 Data Input (Web Form)
The system must accept the following inputs with validation:

| Field | Type | Validation |
|---|---|---|
| Patient First Name | string | Required, non-empty |
| Patient Last Name | string | Required, non-empty |
| Referring Provider | string | Required, non-empty |
| Referring Provider NPI | 10-digit number | Required, exactly 10 digits |
| Patient MRN | 6-digit number | Required, unique, exactly 6 digits |
| Primary Diagnosis | ICD-10 code | Required, format validation |
| Medication Name | string | Required, non-empty |
| Additional Diagnoses | list of ICD-10 codes | Optional |
| Medication History | list of strings | Optional |
| Patient Records | string or PDF | Required, free-text or file upload |

### 2.2 Care Plan Generation
- One care plan corresponds to **one order** (one medication)
- LLM generates a structured care plan containing:
  - **Problem list** / Drug therapy problems (DTPs)
  - **Goals** (SMART format)
  - **Pharmacist interventions / plan**
  - **Monitoring plan & lab schedule**
- Output is downloadable as a text file

### 2.3 Duplicate Detection Rules

| Scenario | Action | Reason |
|---|---|---|
| Same patient + same medication + same day | ❌ ERROR — block submission | Definite duplicate |
| Same patient + same medication + different day | ⚠️ WARNING — allow with confirmation | Could be a refill |
| Same MRN + name or DOB mismatch | ⚠️ WARNING — allow with confirmation | Possible data entry error |
| Same name + DOB + different MRN | ⚠️ WARNING — allow with confirmation | Possibly the same person |
| Same NPI + different provider name | ❌ ERROR — must correct | NPI is a unique identifier |

### 2.4 Provider Management
- Providers are identified uniquely by NPI
- A provider only needs to be entered once in the system
- Subsequent orders can reference an existing provider by NPI

### 2.5 Export & Reporting
- Care plan download as text file (for printing / uploading to their system)
- Export functionality for pharma reporting (e.g., CSV with order summaries)

### 2.6 Feature Priority

| Feature | Priority | Notes |
|---|---|---|
| Patient / order duplicate detection | ✅ Must-have | Cannot disrupt existing workflow |
| Care Plan generation (LLM) | ✅ Must-have | Core value |
| Provider duplicate detection | ✅ Must-have | Affects pharma reporting accuracy |
| Export for reporting | ✅ Must-have | Required for pharma reporting |
| Care Plan download | ✅ Must-have | Users need to upload to their system |

---

## 3. Data Model

### 3.1 Core Entities

**Provider**
- `id` (PK)
- `name` (string)
- `npi` (string, unique, 10 digits)

**Patient**
- `id` (PK)
- `first_name` (string)
- `last_name` (string)
- `mrn` (string, unique, 6 digits)
- `date_of_birth` (date, optional)
- `primary_diagnosis` (string, ICD-10)
- `additional_diagnoses` (list of ICD-10 codes)
- `medication_history` (list of strings)
- `patient_records` (text)

**Order**
- `id` (PK)
- `patient_id` (FK → Patient)
- `provider_id` (FK → Provider)
- `medication_name` (string)
- `created_at` (datetime)

**CarePlan**
- `id` (PK)
- `order_id` (FK → Order, one-to-one)
- `content` (text — LLM-generated output)
- `created_at` (datetime)

### 3.2 Entity Relationships
```
Provider 1 ──── * Order
Patient  1 ──── * Order
Order    1 ──── 1 CarePlan
```

---

## 4. Technical Architecture

### 4.1 Tech Stack (Proposed)
- **Frontend**: React (web form + validation UI)
- **Backend**: Python (FastAPI)
- **Database**: PostgreSQL
- **LLM**: Anthropic Claude API (or OpenAI — TBD)
- **Export**: CSV generation for pharma reporting

### 4.2 High-Level Architecture
```
[Browser - React App]
        │
        ▼
[FastAPI Backend]
   ├── Validation & Duplicate Detection
   ├── CRUD (Patient, Provider, Order)
   ├── LLM Service (Care Plan Generation)
   └── Export Service (CSV)
        │
        ▼
  [PostgreSQL DB]
```

### 4.3 API Endpoints (Draft)
- `POST /api/providers` — Create or lookup provider
- `GET /api/providers?npi=` — Search provider by NPI
- `POST /api/patients` — Create or lookup patient
- `POST /api/orders` — Create order (with duplicate checks)
- `POST /api/orders/{id}/generate-care-plan` — Trigger LLM generation
- `GET /api/orders/{id}/care-plan/download` — Download care plan as text
- `GET /api/export/orders` — Export orders for pharma reporting (CSV)

---

## 5. Production-Ready Requirements

- **Validation**: Every input field is validated on both frontend and backend
- **Data Integrity**: Duplicate detection rules enforced at the API layer and DB constraints
- **Error Handling**: Errors are safe, clear, and contained — no stack traces to users
- **Modularity**: Code is organized into clear modules (routes, services, models, schemas)
- **Testing**: Critical logic (validation, duplicate detection, LLM prompt) covered by automated tests
- **Runnable**: Project runs end-to-end out of the box with a single command

---

## 6. Open Questions / Future Scope

- PDF upload and text extraction (V2)
- User authentication and role-based access (V2)
- ICD-10 code validation against an official registry
- Care plan template customization
- Audit logging for compliance