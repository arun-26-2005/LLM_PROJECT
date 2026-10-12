"""
retrieval/corpus/generate_corpus.py
------------------------------------
Generates synthetic policy wordings, benefit tables, and IRDAI circular
excerpts for the retrieval pipeline.

This script creates the knowledge base that the FAISS vector store indexes.
All documents are synthetic — no real policyholder data (Guardrail #3).
Every IRDAI reference includes circular number + date (Guardrail #6).

Corpus Structure:
    retrieval/corpus/
    ├── policy_wordings/     → 8 policy wording docs (one per clinical scenario)
    ├── benefit_tables/      → 4 benefit schedule documents
    └── irdai_circulars/     → 3 IRDAI regulatory excerpts

Usage:
    python -m retrieval.corpus.generate_corpus
    # or
    python retrieval/corpus/generate_corpus.py
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

CORPUS_DIR = os.path.join(os.path.dirname(__file__))

# ============================================================================
# Policy Wording Documents
# ============================================================================

POLICY_WORDINGS = {
    "individual_health_standard.txt": """POLICY WORDING: STANDARD INDIVIDUAL HEALTH INSURANCE
Policy Type: Individual
Insurer: Synthetic Insurance Co. Ltd.
Product: HealthGuard Individual Plan
UIN: SYNTH-IND-HLT-001/V1/2024

SECTION 1 — SCOPE OF COVER
1.1 This policy covers the Insured Person against financial loss arising from
hospitalization necessitated by illness or accidental bodily injury during
the policy period, subject to the terms, conditions, and exclusions herein.

1.2 Coverage is available for hospitalization requiring a minimum continuous
period of 24 hours as an inpatient in a hospital, except for Day Care
Procedures listed in Annexure A.

SECTION 2 — SUM INSURED AND LIMITS
2.1 The maximum liability of the Company shall not exceed the Sum Insured
stated in the Policy Schedule for any one policy year.

2.2 Room Rent Sub-Limit: The daily room rent charges payable shall not exceed
1% of the Sum Insured or the amount specified in the Policy Schedule,
whichever is lower.

2.3 ICU Charges: ICU charges shall not exceed 2% of the Sum Insured per day.

2.4 Proportionate Deduction: If the actual room rent exceeds the eligible
room rent limit, all other admissible charges (surgeon fees, anaesthesia
charges, consultation fees, diagnostics, pharmacy) shall be reduced in the
same proportion as the eligible room rent bears to the actual room rent
charged by the hospital.

2.5 Ambulance Charges: Emergency ambulance charges are covered up to a maximum
of Rs. 2,000 per hospitalization.

SECTION 3 — WAITING PERIODS
3.1 Initial Waiting Period: No claim shall be admissible during the first 30
days of the first policy period, except claims arising from an accident.

3.2 Specific Disease Waiting Period: Claims arising from the following diseases
and treatments shall be admissible only after completion of 24 continuous months
(2 years) from the date of commencement of the first policy period:
    a) Cataract (ICD-10: H25, H26)
    b) Hernia of all types (ICD-10: K40-K46)
    c) Benign Prostatic Hypertrophy (ICD-10: N40)
    d) Cholelithiasis / Gallstones (ICD-10: K80)
    e) Kidney Stones / Urolithiasis (ICD-10: N20, N21)
    f) Joint Replacement Surgery (ICD-10: M17)
    g) Sinusitis and related conditions (ICD-10: J34)
    h) Internal Congenital Anomalies
    i) Haemorrhoids / Piles (ICD-10: I84)

3.3 Pre-Existing Disease (PED) Waiting Period: Any condition, ailment, injury
or disease that is diagnosed or for which medical advice or treatment was
recommended or received by the Insured Person prior to inception of the first
policy shall be covered only after completion of 48 continuous months (4 years)
from the date of commencement of the first policy period.

3.4 Moratorium Period: After completion of 8 continuous years under the policy,
no claim shall be contestable on the ground that a disease or condition was
pre-existing at the time of taking the policy, except for proven fraud.

SECTION 4 — CO-PAYMENT
4.1 The Insured Person shall bear a co-payment as a percentage of every
admissible claim, as specified in the Policy Schedule.

4.2 Co-payment shall be calculated on the admissible claim amount after
deduction of any non-payable items and sub-limit capping.

4.3 For Senior Citizen plans (entry age 60+), a mandatory co-payment of
not less than 10% shall apply unless waived by the Company.

SECTION 5 — EXCLUSIONS
5.1 Permanent Exclusions: The following are permanently excluded and shall
not be covered under this policy under any circumstances:
    a) Cosmetic or aesthetic treatment or surgery
    b) Self-inflicted injuries or attempted suicide
    c) Treatment for alcoholism or drug/substance abuse
    d) War, invasion, act of foreign enemy, terrorism
    e) Nuclear contamination or radioactive exposure
    f) Hazardous or adventure sports injuries
    g) Treatments for change of sex / gender reassignment
    h) Vaccination and inoculation (unless post-bite)
    i) Weight management / obesity treatment (unless morbid obesity with BMI > 40)

SECTION 6 — CASHLESS FACILITY
6.1 Cashless facility is available at Network Hospitals empanelled with the
Company's Third Party Administrator (TPA).

6.2 Pre-Authorisation Request: For planned hospitalization, a pre-authorisation
request must be submitted to the TPA at least 48-72 hours prior to admission.
For emergency hospitalization, the request must be submitted within 24 hours
of admission.

6.3 Decision Timeline: As per IRDAI Master Circular on Health Insurance
(IRDAI/HLT/CIR/MISC/116/05/2024, dated 29-May-2024), the initial
pre-authorisation decision shall be communicated within 1 hour of receipt
of the request with all necessary documents. Final authorization upon
discharge shall be communicated within 3 hours.

6.4 Non-Network Hospitals: Treatment at non-network hospitals is covered
on a reimbursement basis only, unless emergency pre-authorisation exception
is granted by the Company.

SECTION 7 — POLICY STATUS
7.1 Active Policy: Claims are admissible only when the policy is in active
status with all due premiums paid.

7.2 Lapsed Policy: If the premium due is not paid within the grace period of
30 days, the policy shall lapse. No claims arising during the lapsed period
shall be admissible.

7.3 Expired Policy: Upon expiry of the policy period, no new claims shall be
admissible unless the policy is renewed within the grace period.
""",

    "family_floater_plan.txt": """POLICY WORDING: FAMILY FLOATER HEALTH INSURANCE
Policy Type: Family Floater
Insurer: Synthetic Insurance Co. Ltd.
Product: HealthGuard Family Floater Plan
UIN: SYNTH-FF-HLT-002/V1/2024

SECTION 1 — FAMILY FLOATER PROVISIONS
1.1 The Sum Insured specified in the Policy Schedule is the combined maximum
liability of the Company for all Insured Persons covered under this policy
during any one policy year. Any claim by one Insured Person reduces the Sum
Insured available for all other Insured Persons.

1.2 The primary policyholder's age determines the premium. The oldest member
of the family is considered the primary insured for underwriting purposes.

SECTION 2 — SUM INSURED TIERS AND ROOM RENT
2.1 Sum Insured options: Rs. 3,00,000 / Rs. 5,00,000 / Rs. 10,00,000 / Rs. 25,00,000
2.2 Room Rent Sub-Limit:
    - Sum Insured up to Rs. 5,00,000: Rs. 5,000 per day (General Ward) or
      1% of SI, whichever is lower.
    - Sum Insured Rs. 5,00,001 to Rs. 10,00,000: Rs. 7,500 per day or
      1% of SI, whichever is lower.
    - Sum Insured above Rs. 10,00,000: No room rent sub-limit (Single AC Room).

2.3 ICU Charges: ICU charges limited to 2x the applicable room rent sub-limit.

2.4 Proportionate Deduction: If actual room rent exceeds the eligible room rent,
proportionate deduction shall apply to surgeon fees, anaesthesia, consultation,
diagnostics, and pharmacy charges in the ratio: (eligible room rent / actual room rent).

SECTION 3 — WAITING PERIODS
3.1 All waiting period provisions follow the Standard Individual Plan
(Reference: SYNTH-IND-HLT-001, Section 3).

3.2 Additional Maternity Waiting Period: Maternity expenses including normal
delivery, caesarean section, and pre/post-natal expenses are covered only
after completion of 36 continuous months (3 years) from the date of
commencement of the first policy period. Maximum limit: Rs. 50,000 for
normal delivery, Rs. 75,000 for caesarean section.

SECTION 4 — CO-PAYMENT
4.1 No mandatory co-payment for ages below 60 years.
4.2 Mandatory 10% co-payment for members aged 60-70 years.
4.3 Mandatory 20% co-payment for members aged above 70 years.
4.4 Voluntary co-payment options (10%, 20%, 25%) available for premium discount.
""",

    "group_corporate_plan.txt": """POLICY WORDING: GROUP HEALTH INSURANCE (CORPORATE)
Policy Type: Group
Insurer: Synthetic Insurance Co. Ltd.
Product: HealthGuard Corporate Shield
UIN: SYNTH-GRP-HLT-003/V1/2024

SECTION 1 — GROUP POLICY PROVISIONS
1.1 This policy is issued to the Employer (Master Policyholder) for the benefit
of eligible employees and their declared dependents.

1.2 Waiver of Initial Waiting Period: The initial 30-day waiting period
is waived for all covered members from the date of joining the group scheme.

1.3 Waiver of Specific Disease Waiting Period: The 24-month specific disease
waiting period is waived for group policies covering 100 or more lives.

1.4 Pre-Existing Disease: PED waiting period is reduced to 12 months
(from the standard 48 months) for group policies covering 500 or more lives.

SECTION 2 — SUM INSURED AND LIMITS
2.1 Sum Insured: As specified in the Group Policy Schedule, typically
Rs. 3,00,000 / Rs. 5,00,000 per employee per policy year.

2.2 Room Rent: Single occupancy room (no sub-limit) for Sum Insured of
Rs. 5,00,000 and above. For lower Sum Insured, Rs. 5,000/day limit applies.

SECTION 3 — CO-PAYMENT
3.1 No co-payment applicable for network hospital treatment.
3.2 For non-network hospitals, a 20% co-payment applies on the total
admissible claim amount.
""",

    "senior_citizen_plan.txt": """POLICY WORDING: SENIOR CITIZEN HEALTH INSURANCE
Policy Type: Senior Citizen
Insurer: Synthetic Insurance Co. Ltd.
Product: HealthGuard Senior Shield
UIN: SYNTH-SC-HLT-004/V1/2024

SECTION 1 — ELIGIBILITY
1.1 Entry age: 60 years to 80 years. Renewal available lifelong.
1.2 Pre-policy medical screening is mandatory for all applicants.

SECTION 2 — SUM INSURED AND LIMITS
2.1 Sum Insured options: Rs. 2,00,000 / Rs. 3,00,000 / Rs. 5,00,000
2.2 Room Rent: Rs. 4,000/day for SI up to Rs. 3,00,000; Rs. 5,000/day
for SI of Rs. 5,00,000.

SECTION 3 — MANDATORY CO-PAYMENT
3.1 All claims are subject to a mandatory co-payment of 20%.
3.2 This co-payment is non-waivable and applies after sub-limit deductions.

SECTION 4 — DISEASE-SPECIFIC SUB-LIMITS
4.1 Cataract Surgery: Maximum Rs. 40,000 per eye (inclusive of lens, IOL,
surgery charges, pre and post-operative care).
4.2 Knee Replacement: Maximum Rs. 1,50,000 per knee.
4.3 CABG / Cardiac Surgery: Maximum Rs. 3,00,000.
4.4 Dialysis: Maximum Rs. 2,000 per session, limited to 24 sessions per year.
""",

    "top_up_super_top_up.txt": """POLICY WORDING: TOP-UP AND SUPER TOP-UP PLANS
Policy Type: Top-Up / Super Top-Up
Insurer: Synthetic Insurance Co. Ltd.

TOP-UP PLAN (SYNTH-TU-HLT-005/V1/2024):
1.1 A Top-Up plan activates when any single claim in a policy year exceeds
the specified Deductible amount.
1.2 Deductible options: Rs. 3,00,000 / Rs. 5,00,000 / Rs. 10,00,000
1.3 Sum Insured (above deductible): Rs. 10,00,000 / Rs. 25,00,000 / Rs. 50,00,000
1.4 Only the amount exceeding the deductible in a single claim is payable.

SUPER TOP-UP PLAN (SYNTH-STU-HLT-006/V1/2024):
2.1 A Super Top-Up plan activates when the aggregate of all claims in a
policy year exceeds the specified Deductible amount.
2.2 Unlike Top-Up, multiple smaller claims can aggregate to breach the deductible.
2.3 Deductible options: Rs. 3,00,000 / Rs. 5,00,000
2.4 Sum Insured: Rs. 15,00,000 / Rs. 25,00,000 / Rs. 50,00,000
""",

    "critical_illness_plan.txt": """POLICY WORDING: CRITICAL ILLNESS BENEFIT PLAN
Policy Type: Critical Illness
Insurer: Synthetic Insurance Co. Ltd.
Product: HealthGuard Critical Care
UIN: SYNTH-CI-HLT-007/V1/2024

SECTION 1 — BENEFIT STRUCTURE
1.1 This is a fixed-benefit plan. Upon first diagnosis of a covered Critical
Illness, the entire Sum Insured is payable as a lump sum, irrespective of
actual treatment cost.

1.2 Covered Critical Illnesses (37 conditions):
    - STEMI / Myocardial Infarction (ICD-10: I21)
    - Stroke (ICD-10: I63, I64)
    - Cancer (ICD-10: C00-C97)
    - End-Stage Renal Disease (ICD-10: N18.5, N18.6)
    - Major Organ Transplant
    - Coronary Artery Bypass Graft (CABG)
    - Open Heart Surgery / Valve Replacement

1.3 Survival Period: The insured must survive for at least 30 days after
the date of first diagnosis of the Critical Illness.

SECTION 2 — WAITING PERIODS
2.1 Initial waiting period: 90 days from the date of commencement.
2.2 No specific disease waiting period applicable.
2.3 PED exclusion: Any Critical Illness that is a direct consequence of
a pre-existing disease diagnosed before policy inception is excluded
for the first 48 months.
""",

    "cataract_procedure_guidelines.txt": """PROCEDURE GUIDELINES: CATARACT SURGERY (ICD-10: H25, H26)
Applicable to all plan types under Synthetic Insurance Co. Ltd.

1. COVERAGE CRITERIA
1.1 Cataract surgery is covered under Day Care Procedures (Annexure A, Item 17).
1.2 Both phacoemulsification with IOL implantation and manual SICS are covered.
1.3 Coverage includes pre-operative investigations, surgical procedure, IOL
cost, post-operative medications for up to 6 weeks.

2. SUB-LIMITS
2.1 Individual and Family Floater Plans: Maximum Rs. 40,000 per eye.
2.2 Senior Citizen Plans: Maximum Rs. 40,000 per eye.
2.3 Group Plans: No sub-limit (covered under overall Sum Insured).

3. WAITING PERIOD
3.1 Subject to 24-month specific disease waiting period from first policy inception.
3.2 Waived for Group policies with 100+ lives.

4. SPECIAL CONDITIONS
4.1 Both eyes cannot be operated in the same sitting. A minimum gap of
15 days between surgeries for the two eyes is required.
4.2 IOL (Intraocular Lens) cost: Standard monofocal IOL is fully covered.
Premium multifocal/toric IOL: covered up to Rs. 20,000 per eye, balance
borne by the insured.

5. NON-PAYABLE ITEMS FOR CATARACT SURGERY
5.1 Eye pads, eye shields, and sunglasses post-surgery — non-payable.
5.2 Lubricant eye drops beyond the prescribed post-operative period — non-payable.
""",

    "cardiac_stemi_guidelines.txt": """PROCEDURE GUIDELINES: CARDIAC — STEMI / MYOCARDIAL INFARCTION (ICD-10: I21)
Applicable to all plan types under Synthetic Insurance Co. Ltd.

1. COVERAGE CRITERIA
1.1 Acute ST-Elevation Myocardial Infarction (STEMI) is covered as Emergency
hospitalization. Pre-authorisation request must be submitted within 24 hours.
1.2 Procedures covered: Primary PCI (percutaneous coronary intervention),
thrombolysis, CABG (coronary artery bypass graft).

2. SUB-LIMITS
2.1 Stent Cost: Drug-eluting stent (DES) covered up to NPPA ceiling price.
    - As per NPPA notification (effective 2017): DES ceiling price Rs. 30,000.
    - Bare metal stent (BMS): Rs. 7,000.
2.2 CABG: No specific sub-limit — covered under overall Sum Insured.
2.3 ICU charges: Maximum 2% of Sum Insured per day.

3. WAITING PERIOD
3.1 No specific disease waiting period for cardiac emergencies.
3.2 PED waiting period applies if patient has documented history of
ischaemic heart disease prior to policy inception (4-year exclusion).

4. NON-PAYABLE ITEMS
4.1 External cardiac monitoring devices post-discharge — non-payable.
4.2 Cardiac rehabilitation program fees — non-payable under standard plans.
""",
}

# ============================================================================
# Benefit Tables
# ============================================================================

BENEFIT_TABLES = {
    "room_rent_schedule.txt": """BENEFIT SCHEDULE: ROOM RENT AND ICU SUB-LIMITS
Effective from: 01-April-2024
Insurer: Synthetic Insurance Co. Ltd.

Room Rent Sub-Limits by Sum Insured:
+------------------+---------------------+-------------------+
| Sum Insured (SI) | Room Rent Limit/Day | ICU Limit/Day     |
+------------------+---------------------+-------------------+
| Up to Rs. 2L     | Rs. 2,000           | Rs. 4,000         |
| Rs. 2L - Rs. 3L  | Rs. 3,000           | Rs. 6,000         |
| Rs. 3L - Rs. 5L  | Rs. 5,000           | Rs. 10,000        |
| Rs. 5L - Rs. 10L | Rs. 7,500           | Rs. 15,000        |
| Rs. 10L - Rs. 25L| Rs. 10,000          | Rs. 20,000        |
| Above Rs. 25L    | No Sub-Limit        | No Sub-Limit      |
+------------------+---------------------+-------------------+

Proportionate Deduction Formula:
When actual room rent exceeds the eligible limit:
  Eligible Proportion = (Room Rent Limit) / (Actual Room Rent Charged)
  Proportionate Deduction applies to:
    - Surgeon Fee
    - Anaesthesia Fee
    - Consultation Fee
    - Diagnostic Charges
    - Pharmacy Charges

Example:
  Policy SI: Rs. 5,00,000 → Room Rent Limit: Rs. 5,000/day
  Hospital charges Rs. 8,000/day room rent.
  Eligible Proportion = 5000/8000 = 0.625 (62.5%)
  Surgeon Fee Rs. 50,000 → Eligible: Rs. 50,000 × 0.625 = Rs. 31,250
  Deducted: Rs. 50,000 - Rs. 31,250 = Rs. 18,750
""",

    "disease_sublimits_schedule.txt": """BENEFIT SCHEDULE: DISEASE-SPECIFIC AND PROCEDURE SUB-LIMITS
Effective from: 01-April-2024
Insurer: Synthetic Insurance Co. Ltd.

+-----------------------------+-------------------+--------------+
| Procedure / Disease         | Sub-Limit (Max)   | Plan Types   |
+-----------------------------+-------------------+--------------+
| Cataract (per eye)          | Rs. 40,000        | Indiv, FF, SC|
| Knee Replacement (per knee) | Rs. 1,50,000      | Indiv, FF, SC|
| CABG / Open Heart Surgery   | Rs. 3,00,000      | SC only      |
| Dialysis (per session)      | Rs. 2,000         | All plans    |
| Dialysis (annual sessions)  | 24 sessions/year  | All plans    |
| Maternity - Normal Delivery | Rs. 50,000        | FF only      |
| Maternity - Caesarean        | Rs. 75,000        | FF only      |
| Ambulance Charges           | Rs. 2,000/event   | All plans    |
| Dental (accident only)      | Rs. 25,000        | All plans    |
+-----------------------------+-------------------+--------------+

Notes:
1. Sub-limits apply independently of the overall Sum Insured.
2. For Group Plans with 100+ lives, disease-specific sub-limits may be waived.
3. Sub-limits are applied BEFORE co-payment calculation.
""",

    "copay_schedule.txt": """BENEFIT SCHEDULE: CO-PAYMENT STRUCTURE
Effective from: 01-April-2024
Insurer: Synthetic Insurance Co. Ltd.

Co-Payment Rules:
1. Co-payment is calculated on the ADMISSIBLE claim amount AFTER:
   - Deduction of non-payable items (IRDAI Lists I-IV)
   - Application of sub-limit capping
   - Application of proportionate deductions (if any)

2. Co-payment by Plan Type and Age:
   +---------------------+--------+--------+--------+
   | Plan Type           | <60 yr | 60-70  | >70 yr |
   +---------------------+--------+--------+--------+
   | Individual          | 0%     | 10%    | 20%    |
   | Family Floater      | 0%     | 10%    | 20%    |
   | Group               | 0%     | 0%     | 0%     |
   | Senior Citizen      | 20%    | 20%    | 20%    |
   +---------------------+--------+--------+--------+

3. Voluntary Co-payment Options (premium discount):
   - 10% voluntary co-pay → 10% premium discount
   - 20% voluntary co-pay → 20% premium discount
   - 25% voluntary co-pay → 25% premium discount

4. Non-Network Hospital Co-payment:
   Additional 20% co-payment applies for treatment at non-network hospitals
   (added to any existing mandatory/voluntary co-payment).

5. Deductible (Top-Up / Super Top-Up):
   Applied BEFORE co-payment. The deductible amount is the insured's
   self-retention and is not eligible for co-payment calculation.
""",

    "waiting_period_matrix.txt": """BENEFIT SCHEDULE: WAITING PERIOD MATRIX
Effective from: 01-April-2024
Insurer: Synthetic Insurance Co. Ltd.

Waiting Period by Type and Plan:
+-----------------------------+-----------+----------+---------+----------+
| Waiting Period Type         | Indiv/FF  | Group    | SC      | CI       |
+-----------------------------+-----------+----------+---------+----------+
| Initial (all illnesses)     | 30 days   | Waived   | 30 days | 90 days  |
| Specific Disease (listed)   | 24 months | Waived*  | 24 mo   | N/A      |
| Pre-Existing Disease (PED)  | 48 months | 12 mo**  | 48 mo   | 48 mo    |
| Maternity                   | 36 months | 12 mo    | N/A     | N/A      |
| Moratorium (all diseases)   | 8 years   | 8 years  | 8 years | 8 years  |
+-----------------------------+-----------+----------+---------+----------+

* Waived for groups with 100+ lives.
** Reduced to 12 months for groups with 500+ lives.

Specific Disease List (24-month waiting period):
ICD-10  | Disease
--------|--------------------------------------------------
H25-H26 | Cataract
K40-K46 | Hernia (all types)
N40     | Benign Prostatic Hypertrophy (BPH)
K80     | Cholelithiasis (Gallstones)
N20-N21 | Urolithiasis (Kidney / Ureter Stones)
M17     | Gonarthrosis (Knee Osteoarthritis)
J34     | Nasal Septum Deviation / Chronic Sinusitis
I84     | Haemorrhoids / Piles
H40     | Glaucoma

Waiting Period Calculation:
- Start date: Date of commencement of FIRST policy period (not renewal).
- Continuous coverage required — any break resets waiting periods.
- Portability: Waiting period credit given for prior continuous coverage
  with another insurer, as per IRDAI Portability Guidelines.
""",
}

# ============================================================================
# IRDAI Regulatory Circulars
# ============================================================================

IRDAI_CIRCULARS = {
    "irdai_master_circular_health_2024.txt": """IRDAI MASTER CIRCULAR ON HEALTH INSURANCE BUSINESS
Circular No.: IRDAI/HLT/CIR/MISC/116/05/2024
Date: 29-May-2024
Source: Insurance Regulatory and Development Authority of India (IRDAI)
URL: https://www.irdai.gov.in/admincms/cms/frmGeneral_Layout.aspx?page=PageNo5659

CHAPTER VI — CASHLESS FACILITY AND CLAIMS SETTLEMENT

Section 36 — Cashless Authorization Timelines:
36.1 Pre-Authorization Decision: The insurer or its TPA shall communicate the
pre-authorization decision within ONE HOUR of receipt of the pre-authorization
request along with all necessary documents from the network provider.

36.2 Enhancement / Final Authorization: Upon discharge of the insured from the
hospital, the insurer or TPA shall communicate the final authorization within
THREE HOURS of receipt of the final bill and discharge summary.

36.3 If the insurer fails to communicate within the stipulated time, the claim
shall be deemed to be approved for the amount requested, subject to policy
terms and conditions.

Section 37 — Query Communication:
37.1 If additional information is required, the insurer shall raise a query
in a single communication and not in multiple rounds. Multiple rounds of
queries for the same claim constitute poor claims servicing.

37.2 The insured shall be given a reasonable time of not less than 15 days
to respond to any query.

Section 38 — Claim Settlement:
38.1 Claims shall be settled within 30 days of receipt of the last necessary
document from the insured or the hospital.

38.2 In case of delay beyond 30 days, interest at the rate of 2% above the
bank rate shall be payable from the date of receipt of last document to the
date of payment.

CHAPTER VII — STANDARDIZATION AND REFORM

Section 42 — National Health Claims Exchange (NHCX):
42.1 All insurers shall mandatorily onboard the National Health Claims Exchange
platform operated by the National Health Authority (NHA).

42.2 Claims data exchange shall follow the FHIR (Fast Healthcare Interoperability
Resources) standard as specified by NHA.

Section 43 — Pre-Existing Disease Definition:
43.1 Pre-Existing Disease (PED) means any condition, ailment, injury or disease:
    a) That is/are diagnosed by a physician within 48 months prior to the
       effective date of the policy issued by the insurer, OR
    b) For which medical advice or treatment was recommended by, or received
       from, a physician within 48 months prior to the effective date of the
       policy issued by the insurer.

43.2 The standard moratorium period of 8 continuous years applies, after which
no claim shall be contestable for pre-existing disease, except in cases of
proven fraud or moral hazard.
""",

    "irdai_non_payables_schedule.txt": """IRDAI GUIDELINES ON NON-PAYABLE ITEMS IN HEALTH INSURANCE
Reference: IRDAI/HLT/REG/CIR/XXX/10/2019 (as updated by Master Circular 2024)
Circular No.: IRDAI/HLT/CIR/MISC/116/05/2024, Chapter IX, Section 52
Date: 29-May-2024
Source: Insurance Regulatory and Development Authority of India (IRDAI)

LIST I — ITEMS THAT ARE NOT PART OF TREATMENT (ALWAYS NON-PAYABLE)
1. Toiletries: Toilet paper, tissues, sanitary pads, diapers
2. Personal comfort items: Telephone charges, TV charges, guest bed charges
3. Administrative charges: Registration charges, admission charges, filing charges
4. Documentation charges: Medico-legal case documentation, birth/death certificate
5. Service charges: Attendant charges, extra diet charges beyond therapeutic diet
6. Laundry charges
7. Mineral water and beverages

LIST II — ITEMS RELATED TO ROOM AND BOARDING (SUBJECT TO ROOM RENT LIMIT)
1. Extra bed charges beyond entitled category
2. Charges for upgrades in room category
3. Mini-bar charges, special menu charges

LIST III — ITEMS RELATED TO CONSUMABLES / DISPOSABLES
Items not directly related to treatment and are for provider's convenience:
1. Surgical gloves, surgical masks, caps, shoe covers, gowns
2. PPE kits (Personal Protective Equipment)
3. Hand sanitizers, disinfectants for room cleaning
4. Linen savers and under-pads
5. Nebulizer masks and tubing (single-use disposable types)

Note: Items in List III that are integral to surgical procedures (e.g., sterile
drapes used during operation) may be admissible at the insurer's discretion.

LIST IV — ITEMS THAT REQUIRE SPECIFIC CONSIDERATION
1. External durable medical equipment: Wheelchair, walker, crutches
   (may be covered under specific plans if prescribed for post-surgical recovery)
2. Spectacles, contact lenses, hearing aids — generally non-payable
3. Dentures — covered only if required due to accidental injury

NPPA PRICE CAPS ON MEDICAL DEVICES:
As per National Pharmaceutical Pricing Authority (NPPA) orders:
- Drug-eluting coronary stent (DES): Ceiling price Rs. 30,000
- Bare metal stent (BMS): Ceiling price Rs. 7,000
- Knee implant: Ceiling price Rs. 54,720 (total knee replacement)
- Hip implant: Ceiling price Rs. 45,350

Any charge by hospital exceeding the NPPA ceiling price for capped devices
is non-payable and shall be deducted from the admissible claim amount.
""",

    "irdai_cashless_timeline_enforcement.txt": """IRDAI ENFORCEMENT GUIDANCE: CASHLESS PRE-AUTHORISATION TIMELINES
Reference: IRDAI/HLT/CIR/MISC/116/05/2024, Chapter VI, Sections 36-38
Date: 29-May-2024
Source: Insurance Regulatory and Development Authority of India (IRDAI)

REGULATORY COMPLIANCE REQUIREMENTS:

1. ONE-HOUR CLOCK:
   The pre-authorisation decision must be communicated to the network
   provider within 60 minutes of receipt of the request with all
   necessary supporting documents. This is a hard compliance obligation,
   not a service-level aspiration.

2. THREE-HOUR CLOCK:
   Final discharge authorization must be communicated within 3 hours of
   receipt of the final bill and discharge summary.

3. CONSEQUENCES OF NON-COMPLIANCE:
   3.1 Deemed approval: If the insurer fails to communicate within the
   stipulated time, the claim is deemed approved.
   3.2 Regulatory action: Persistent non-compliance may attract regulatory
   action under Section 102 of the Insurance Act, 1938.

4. SINGLE-QUERY RULE:
   All queries must be raised in a single communication. Serial queries
   on the same claim are treated as poor claims practice and are subject
   to penalty.

5. DOCUMENT REQUIREMENTS:
   The following documents are considered "necessary" for pre-auth decision:
   a) Duly filled pre-authorization form
   b) Doctor's prescription / case sheet recommending hospitalization
   c) Photo ID proof of insured person
   d) Health card / policy number
   e) Investigation reports supporting the diagnosis

6. RECOMMEND-ONLY AUTOMATED SYSTEMS:
   Any automated system assisting in pre-authorisation decisions must
   operate in a "recommend-only" mode. The final decision authority
   rests with the insurer's authorized medical officer or claims
   team. Automated systems shall not auto-approve or auto-deny claims.
""",
}


def generate_corpus() -> dict[str, int]:
    """Generate the complete synthetic corpus.

    Creates all policy wording, benefit table, and IRDAI circular documents
    in the appropriate subdirectories under retrieval/corpus/.

    Returns:
        Dict with counts: {"policy_wordings": N, "benefit_tables": N, "irdai_circulars": N}
    """
    counts = {}

    # Policy Wordings
    wording_dir = os.path.join(CORPUS_DIR, "policy_wordings")
    os.makedirs(wording_dir, exist_ok=True)
    for filename, content in POLICY_WORDINGS.items():
        filepath = os.path.join(wording_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
    counts["policy_wordings"] = len(POLICY_WORDINGS)
    logger.info("Generated %d policy wording documents.", counts["policy_wordings"])

    # Benefit Tables
    benefit_dir = os.path.join(CORPUS_DIR, "benefit_tables")
    os.makedirs(benefit_dir, exist_ok=True)
    for filename, content in BENEFIT_TABLES.items():
        filepath = os.path.join(benefit_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
    counts["benefit_tables"] = len(BENEFIT_TABLES)
    logger.info("Generated %d benefit table documents.", counts["benefit_tables"])

    # IRDAI Circulars
    irdai_dir = os.path.join(CORPUS_DIR, "irdai_circulars")
    os.makedirs(irdai_dir, exist_ok=True)
    for filename, content in IRDAI_CIRCULARS.items():
        filepath = os.path.join(irdai_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
    counts["irdai_circulars"] = len(IRDAI_CIRCULARS)
    logger.info("Generated %d IRDAI circular documents.", counts["irdai_circulars"])

    total = sum(counts.values())
    logger.info("Corpus generation complete: %d total documents.", total)

    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = generate_corpus()
    print(f"\n✅ Corpus generated successfully!")
    print(f"   Policy wordings: {result['policy_wordings']}")
    print(f"   Benefit tables:  {result['benefit_tables']}")
    print(f"   IRDAI circulars: {result['irdai_circulars']}")
    print(f"   Total documents: {sum(result.values())}")
