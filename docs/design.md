# Care Plan Generation System – Design Document

## 1. Background & Goals

### 1.1 Business Context
This system is designed for **CVS medical staff** (pharmacists and medical assistants).  
Patients do **not** directly interact with the system.

Medical staff need to generate a **Care Plan** when prescribing a medication.  
The generated Care Plan will be **printed and handed to the patient**, and is also required for:
- Compliance
- Reimbursement by Medicare and pharmaceutical partners (pharma)

### 1.2 Problem Statement
Currently, pharmacists spend **20–40 minutes per patient** manually reviewing patient records and drafting Care Plans.  
Due to staffing shortages, this task is backlogged and creates operational risk.

### 1.3 Objective
Build a **production-ready system** that:
- Automatically generates Care Plans from structured clinical input
- Prevents accidental duplicate submissions
- Enforces data integrity rules
- Integrates safely with LLMs
- Supports reporting needs for pharma partners

---

## 2. Users & Personas

### 2.1 Primary Users
- CVS pharmacists
- CVS medical assistants

### 2.2 Non-Users
- Patients do **not** interact with the system directly

---

## 3. Core Domain Concepts

### 3.1 Care Plan
- **One Care Plan corresponds to exactly one order**
- **One order corresponds to one medication**
- A patient may have multiple Care Plans (for different medications or dates)

### 3.2 Required Care Plan Sections
Every generated Care Plan **must include**:
- Problem List
- Goals
- Pharmacist Interventions
- Monitoring Plan

---

## 4. Functional Requirements

| Feature | Required | Notes |
|------|------|------|
| Patient & Order Duplicate Detection | Yes | Must not disrupt existing workflows |
| Care Plan Generation (LLM) | Yes | Core system value |
| Provider Duplicate Detection | Yes | Impacts pharma reporting accuracy |
| Care Plan Download | Yes | Used for printing and external systems |
| Report Export (CSV) | Yes | Required by pharma partners |

---

## 5. Input Data Requirements

### 5.1 Patient Information
- First Name (string)
- Last Name (string)
- MRN (unique identifier, numeric string, may contain leading zeros)
- DOB
- Sex
- Weight
- Allergies

### 5.2 Provider Information
- Provider Name (string)
- **NPI (10-digit numeric identifier, canonical unique key)**

### 5.3 Clinical Information
- Primary Diagnosis (ICD-10)
- Additional Diagnoses (list of ICD-10 codes)
- Medication Name (the medication for this order)
- Medication History (list of strings)
- Patient Records (free-text or uploaded PDF)

---

## 6. Data Integrity & Validation Rules

### 6.1 Hard Validation Errors (Block Submission)
- Invalid NPI format (must be 10 digits)
- Missing required fields
- Malformed ICD-10 codes
- Provider NPI conflicts that require correction

### 6.2 Soft Validation (Warnings)
- Potential duplicate patients
- Potential duplicate orders
- Provider name mismatch for an existing NPI
- MRN/name/DOB inconsistencies

Warnings require **explicit user confirmation** to proceed.

---

## 7. Duplicate Detection Rules

### 7.1 Order-Level Duplicate Detection

| Scenario | Handling | Rationale |
|------|------|------|
| Same patient + same medication + same day | ❌ ERROR (Block) | Definitive duplicate submission |
| Same patient + same medication + different day | ⚠️ WARNING (Confirm to proceed) | Likely continuation of therapy |

### 7.2 Patient-Level Duplicate Detection

| Scenario | Handling | Rationale |
|------|------|------|
| Same MRN + different name or DOB | ⚠️ WARNING | Possible data entry error |
| Same name + DOB + different MRN | ⚠️ WARNING | Possible same patient with inconsistent MRN |

Patient duplicates **do not automatically merge records**.  
They surface warnings and rely on user confirmation.

### 7.3 Provider-Level Duplicate Detection

| Scenario | Handling | Rationale |
|------|------|------|
| Same NPI + different provider name | ❌ ERROR (Must correct) | NPI is the canonical identifier |

- Provider entities are uniquely identified by **NPI**
- Names are treated as attributes, not identifiers
- The system must never create multiple providers for the same NPI

---

## 8. LLM-Based Care Plan Generation

### 8.1 Role of the LLM
The LLM is used for **clinical documentation synthesis**, not diagnosis or prescribing.

- Inputs are structured clinical facts
- Output is a drafted Care Plan document
- Final responsibility remains with the pharmacist

### 8.2 Reliability Requirements
- LLM calls are handled asynchronously
- Timeouts and retries are enforced
- Failures result in a recoverable state (e.g. `needs_review`)
- Fallback templates may be used if generation fails

---

## 9. Output & File Handling

- Care Plans are generated as downloadable files (initially text/markdown; PDF/DOCX optional)
- Files must be printable and uploadable into external systems
- Each Care Plan is versioned and linked to its originating order

---

## 10. Reporting & Export

- Users can export structured data for pharma reporting
- Export format: CSV
- Typical fields include:
  - Provider NPI
  - Medication
  - Primary Diagnosis
  - Care Plan generation date
  - Status

---

## 11. Non-Functional Requirements

### 11.1 Safety & Clarity
- Errors must be clear, safe, and user-facing
- Internal errors must not leak system details or PHI

### 11.2 Modularity
- Validation, duplicate detection, LLM generation, rendering, and export must be modular

### 11.3 Testability
- Critical logic (validation, duplicate detection, state transitions) must be covered by automated tests

### 11.4 Out-of-the-Box Execution
- The project must run end-to-end without manual setup steps