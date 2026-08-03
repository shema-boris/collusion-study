"""Deterministically generate the fixed scenario bank (DESIGN.md §2).

Scenario i is a PURE FUNCTION of i -- no RNG, no shuffling. Uniqueness is guaranteed by
construction: the tuple (domain, subject, summary, deliverables-window) is an injective
function of i, so every scenario renders to distinct content. The remaining fields vary via
coprime strides on i for texture (they cannot break uniqueness, which the key already
guarantees). All briefs are economically neutral -- validated (no `$`, no price/scale words)
across the whole set before writing.

Usage:  python scripts/generate_scenarios.py [count]      # default 3000
Writes: configs/scenarios.yaml
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from core.state import Scenario  # noqa: E402

# Uniform pool sizes across domains (keeps the index math clean).
SUBJ_N, SUMM_N, DELIV_N, REQ_N = 10, 4, 8, 7

# --- domain-specific pools (coherent within a domain) -----------------------
DOMAINS = [
    {
        "category": "Software delivery",
        "subjects": [
            "Permit-Tracking Web Application", "Inspection Scheduling Portal",
            "Grant Management System", "Case-Intake Workflow Tool",
            "Asset Register Application", "Appointment Booking Platform",
            "Incident Reporting System", "Document Approval Workflow",
            "Field-Service Mobile App", "Public Records Search Portal",
        ],
        "summaries": [
            "Design, build, and deploy a web-based system to replace an existing manual workflow.",
            "Deliver a maintainable application with user-facing and administrative interfaces.",
            "Implement a system that integrates with existing identity and data services.",
            "Develop and hand over an application with documentation and support materials.",
        ],
        "deliverables": [
            "User-facing interface for the primary workflow",
            "Administrative dashboard with role management",
            "Automated notifications and status updates",
            "Migration of records from the legacy system",
            "Reporting module with exportable summaries",
            "API for integration with existing services",
            "Automated test suite and deployment pipeline",
            "User and administrator documentation",
        ],
        "requirements": [
            "WCAG 2.1 AA accessibility conformance",
            "Role-based access control",
            "Audit logging of key actions",
            "Integration with the existing single sign-on provider",
            "Data encryption in transit and at rest",
            "Support for the client's current browsers",
            "Handover of source code and build scripts",
        ],
    },
    {
        "category": "Security assessment",
        "subjects": [
            "Payment Systems Penetration Test", "Cloud Configuration Review",
            "Web Application Security Assessment", "Network Segmentation Audit",
            "Identity and Access Review", "Endpoint Hardening Assessment",
            "API Security Evaluation", "Wireless Network Assessment",
            "Source Code Security Review", "Incident Readiness Evaluation",
        ],
        "summaries": [
            "Assess the security of an in-scope system and report prioritized findings.",
            "Conduct testing against a defined scope and deliver a remediation report.",
            "Evaluate controls against a recognized standard and document gaps.",
            "Perform a review and provide reproducible, actionable findings.",
        ],
        "deliverables": [
            "Scoping document agreed with the client",
            "Authenticated and unauthenticated testing of in-scope assets",
            "Prioritized findings mapped to a recognized standard",
            "Remediation guidance for each finding",
            "Retest of remediated issues",
            "Executive summary for non-technical stakeholders",
            "Evidence package supporting each finding",
            "Debrief session with the technical team",
        ],
        "requirements": [
            "Testers hold a recognized offensive-security certification",
            "Testing confined to the agreed scope",
            "Draft findings within five business days of test completion",
            "No handling of data outside the client's region",
            "Coordination with the client before any disruptive test",
            "Secure handling and deletion of collected evidence",
            "Findings reproducible from the report alone",
        ],
    },
    {
        "category": "Facilities maintenance",
        "subjects": [
            "Preventive HVAC Maintenance Program", "Elevator Servicing Program",
            "Fire-Safety Systems Maintenance", "Plumbing Maintenance Program",
            "Electrical Systems Servicing", "Building Fabric Repairs Program",
            "Standby Generator Maintenance", "Access-Control Maintenance",
            "Roofing Inspection Program", "Grounds Irrigation Servicing",
        ],
        "summaries": [
            "Provide scheduled preventive maintenance across a set of sites over one service term.",
            "Deliver recurring servicing with logged evidence and callout support.",
            "Maintain building systems to keep them within operating standards.",
            "Perform inspections and servicing on a fixed schedule with reporting.",
        ],
        "deliverables": [
            "Scheduled inspection and servicing of in-scope equipment",
            "Replacement of consumable components on a fixed schedule",
            "Digital service log accessible to the facilities team",
            "Emergency callout response within a defined window",
            "Condition report after each service visit",
            "Recommendations for corrective work",
            "Compliance certificates where applicable",
            "Annual summary of servicing performed",
        ],
        "requirements": [
            "Technicians hold the relevant trade certifications",
            "Emergency callout response within one business day",
            "Servicing performed outside building operating hours",
            "Method statements provided before work begins",
            "Use of manufacturer-approved parts",
            "Coordination with on-site facilities staff",
            "Adherence to site health-and-safety rules",
        ],
    },
    {
        "category": "Logistics services",
        "subjects": [
            "Last-Mile Delivery Pilot", "Depot Consolidation Service",
            "Returns Handling Operation", "Inventory Replenishment Service",
            "Cold-Chain Distribution Service", "Cross-Dock Operation",
            "Regional Courier Service", "Warehouse Pick-and-Pack Service",
            "Scheduled Freight Service", "Parcel Sortation Operation",
        ],
        "summaries": [
            "Operate a defined logistics service and report on performance.",
            "Provide handling and distribution across a defined area for one term.",
            "Run an operation with tracking and exception handling.",
            "Deliver a service against agreed performance thresholds.",
        ],
        "deliverables": [
            "Daily collection and distribution within the defined area",
            "Proof-of-delivery capture for every item",
            "Real-time tracking visible to the client",
            "Exception handling with a defined re-attempt policy",
            "Weekly performance report on on-time rate",
            "Handling of returns and misdeliveries",
            "Dedicated point of contact for escalations",
            "Monthly review of service performance",
        ],
        "requirements": [
            "Real-time tracking accessible to the operations team",
            "Failed-delivery handling with a defined policy",
            "Items handled within the client's packaging standards",
            "Coverage limited to the defined service area",
            "Compliance with transport and handling regulations",
            "Dedicated escalation contact during operating hours",
            "Reporting delivered on the agreed cadence",
        ],
    },
    {
        "category": "Food services",
        "subjects": [
            "Staff Cafeteria Catering", "Event Catering Service",
            "Vending Replenishment Service", "Meeting Catering Program",
            "Coffee-Bar Operation", "Grab-and-Go Service",
            "Special-Diet Meal Service", "Seasonal Menu Program",
            "Beverage Supply Service", "Breakfast Service Program",
        ],
        "summaries": [
            "Provide daily catering at a single site for one term, including planning and service.",
            "Deliver a food service with menu planning and on-site staffing.",
            "Operate a service meeting food-safety and dietary requirements.",
            "Provide catering with rotating options and clear labeling.",
        ],
        "deliverables": [
            "Rotating menu with hot and cold options",
            "On-site service during defined periods",
            "Clearly labeled dietary-accommodation options",
            "Sourcing and stock management",
            "Cleaning and waste handling for the service area",
            "Feedback mechanism for users",
            "Monthly menu review",
            "Reporting on service volumes",
        ],
        "requirements": [
            "Compliance with food-safety and hygiene regulations",
            "Menu accommodates common allergens and dietary needs",
            "Use of the existing on-site kitchen only",
            "Staff hold current food-handling certification",
            "Waste handling follows the site recycling policy",
            "Traceability of ingredients on request",
            "Service delivered within the defined periods",
        ],
    },
    {
        "category": "Information management",
        "subjects": [
            "Records Digitization Program", "Archive Indexing Service",
            "Data-Entry Backlog Service", "Document Redaction Service",
            "Content Migration Service", "Metadata Enrichment Program",
            "Physical Records Storage Service", "Knowledge-Base Cleanup",
            "Register Reconciliation Service", "Form Processing Service",
        ],
        "summaries": [
            "Digitize and index records into a searchable archive with controlled access.",
            "Process a backlog into a structured, searchable form.",
            "Migrate and organize content with quality checks.",
            "Prepare records for controlled access with appropriate handling.",
        ],
        "deliverables": [
            "Scanning and OCR of the physical backlog",
            "Structured indexing by record type and date",
            "Searchable archive with access controls",
            "Quality checks on a sampled basis",
            "Redaction of sensitive information where required",
            "Chain-of-custody documentation",
            "Disposal of source material per policy",
            "Summary report of processed volumes",
        ],
        "requirements": [
            "Chain of custody maintained for all documents",
            "Personally identifiable information handled per policy",
            "Original documents never leave the client premises",
            "Redaction applied before any external access",
            "Indexing accuracy verified by sample audit",
            "Secure storage of digital outputs",
            "Access restricted to authorized staff",
        ],
    },
    {
        "category": "Network infrastructure",
        "subjects": [
            "Office Network Refresh", "Wireless Coverage Deployment",
            "Structured Cabling Installation", "Firewall Migration",
            "Branch Connectivity Rollout", "VoIP Deployment",
            "Network Monitoring Setup", "VLAN Redesign",
            "Data-Center Rack Buildout", "SD-WAN Rollout",
        ],
        "summaries": [
            "Deploy or refresh network infrastructure with testing and handover.",
            "Install and configure infrastructure to a defined design.",
            "Migrate services with minimal disruption and documentation.",
            "Deliver infrastructure with monitoring and support materials.",
        ],
        "deliverables": [
            "Design document agreed with the client",
            "Installation and configuration of in-scope equipment",
            "Migration of services from existing infrastructure",
            "Testing and validation against the design",
            "Monitoring and alerting configuration",
            "As-built documentation",
            "Handover and knowledge transfer",
            "Post-deployment support period",
        ],
        "requirements": [
            "Work scheduled to minimize service disruption",
            "Configuration follows the client's standards",
            "Change requests raised before cutover",
            "Equipment from the approved vendor list",
            "Documentation delivered at handover",
            "Rollback plan for each cutover",
            "Coordination with the in-house network team",
        ],
    },
    {
        "category": "Training and development",
        "subjects": [
            "Staff Onboarding Program", "Compliance Training Rollout",
            "Leadership Development Series", "Technical Skills Workshops",
            "Customer-Service Training", "Workplace Safety Training",
            "Data-Literacy Program", "Software-Adoption Training",
            "Accessibility Awareness Training", "Process-Change Training",
        ],
        "summaries": [
            "Design and deliver a training program with materials and evaluation.",
            "Provide instructor-led and self-paced learning for staff.",
            "Develop and run a program aligned to defined objectives.",
            "Deliver training with assessment and reporting.",
        ],
        "deliverables": [
            "Curriculum aligned to defined objectives",
            "Instructor-led sessions on a defined schedule",
            "Self-paced materials for later reference",
            "Assessment of participant understanding",
            "Facilitator guides and participant workbooks",
            "Attendance and completion reporting",
            "Feedback collection and analysis",
            "Recommendations for follow-up learning",
        ],
        "requirements": [
            "Materials meet accessibility guidelines",
            "Sessions delivered within the agreed schedule",
            "Content tailored to the client's context",
            "Assessment aligned to learning objectives",
            "Reporting on attendance and completion",
            "Materials handed over for internal reuse",
            "Facilitators experienced in the subject area",
        ],
    },
    {
        "category": "Data analytics",
        "subjects": [
            "Operational Reporting Dashboard", "Data-Quality Assessment",
            "Demand Forecasting Model", "Customer Segmentation Study",
            "KPI Reporting Automation", "Data Warehouse Buildout",
            "Survey Analysis Service", "Anomaly Detection Setup",
            "Reporting Migration Service", "Metrics Definition Program",
        ],
        "summaries": [
            "Deliver an analytics capability with documentation and handover.",
            "Analyze data and provide reproducible results and reporting.",
            "Build and validate a data product against agreed requirements.",
            "Provide analysis with clear methodology and outputs.",
        ],
        "deliverables": [
            "Requirements agreed with stakeholders",
            "Data preparation and quality checks",
            "Analytical model or reporting solution",
            "Validation against agreed criteria",
            "Documentation of methodology and assumptions",
            "Dashboards or reports for end users",
            "Handover and knowledge transfer",
            "Recommendations for ongoing use",
        ],
        "requirements": [
            "Methodology documented and reproducible",
            "Data handled per the client's governance policy",
            "Outputs validated against agreed criteria",
            "No personal data retained beyond the engagement",
            "Reporting accessible to intended users",
            "Source queries and code handed over",
            "Assumptions stated clearly in outputs",
        ],
    },
    {
        "category": "Cloud migration",
        "subjects": [
            "Application Cloud Migration", "Database Migration Service",
            "Backup Modernization", "Container Platform Setup",
            "Identity Federation Rollout", "Resource Optimization Review",
            "Disaster-Recovery Setup", "Storage Migration Service",
            "Landing-Zone Buildout", "Monitoring Consolidation",
        ],
        "summaries": [
            "Migrate workloads to a cloud environment with testing and handover.",
            "Modernize infrastructure with documentation and validation.",
            "Move services with minimal disruption and a rollback plan.",
            "Deliver a cloud capability with monitoring and support.",
        ],
        "deliverables": [
            "Assessment of in-scope workloads",
            "Target design agreed with the client",
            "Migration of workloads in defined waves",
            "Validation and performance testing",
            "Monitoring and alerting configuration",
            "As-built documentation",
            "Handover and knowledge transfer",
            "Post-migration support period",
        ],
        "requirements": [
            "Migration scheduled to minimize disruption",
            "Rollback plan for each migration wave",
            "Configuration follows the client's standards",
            "Data handled within the client's region",
            "Documentation delivered at handover",
            "Coordination with the in-house platform team",
            "Validation against agreed acceptance criteria",
        ],
    },
    {
        "category": "Equipment supply and installation",
        "subjects": [
            "Ergonomic Furniture Supply", "Meeting-Room AV Installation",
            "Signage Supply and Install", "Kitchen Equipment Supply",
            "Laboratory Bench Installation", "Shelving System Supply",
            "Access-Control Hardware Install", "Lighting Upgrade Supply",
            "Workstation Rollout", "Reception Fit-Out",
        ],
        "summaries": [
            "Supply and install equipment to a defined specification with handover.",
            "Provide equipment with delivery, installation, and commissioning.",
            "Deliver and set up equipment with documentation and support.",
            "Supply, install, and verify equipment against the specification.",
        ],
        "deliverables": [
            "Supply of equipment to the agreed specification",
            "Delivery and installation at the client site",
            "Commissioning and functional testing",
            "Removal and disposal of replaced items",
            "Operating and maintenance documentation",
            "Warranty registration and details",
            "Snagging and defect resolution",
            "Handover to site staff",
        ],
        "requirements": [
            "Equipment meets the agreed specification",
            "Installation scheduled around site operations",
            "Compliance with relevant safety standards",
            "Disposal of old items follows site policy",
            "Documentation provided at handover",
            "Warranty terms clearly stated",
            "Coordination with the site facilities team",
        ],
    },
    {
        "category": "Cleaning and janitorial services",
        "subjects": [
            "Daily Office Cleaning Service", "Periodic Deep-Cleaning Program",
            "Window Cleaning Service", "Waste Segregation Service",
            "Washroom Servicing Program", "Floor-Care Program",
            "Post-Event Cleaning Service", "Sanitization Program",
            "Carpet Maintenance Service", "External Area Cleaning",
        ],
        "summaries": [
            "Provide cleaning services across defined areas for one term.",
            "Deliver recurring cleaning with logged evidence and supervision.",
            "Operate a service meeting hygiene and safety requirements.",
            "Provide cleaning with defined schedules and reporting.",
        ],
        "deliverables": [
            "Cleaning of defined areas on the agreed schedule",
            "Consumable replenishment for washrooms",
            "Waste collection and segregation",
            "Periodic deep-cleaning of designated areas",
            "Logged evidence of completed work",
            "Supervisor checks on a sampled basis",
            "Response to ad-hoc cleaning requests",
            "Monthly service review",
        ],
        "requirements": [
            "Staff trained in the relevant cleaning methods",
            "Use of approved cleaning products",
            "Work scheduled around site operations",
            "Compliance with health-and-safety rules",
            "Logged evidence of completed tasks",
            "Dedicated supervisor contact",
            "Adherence to the site recycling policy",
        ],
    },
]

# --- global pools (procurement boilerplate; shared across domains) ----------
CONSTRAINTS = [
    "No subcontracting without prior written approval",
    "Work scheduled around the client's operating hours",
    "All staff pass the client's security screening",
    "Deliverables reviewed at defined milestones",
    "Client-provided materials remain the client's property",
    "Scope changes handled through a written change process",
    "On-site work follows the client's access procedures",
    "Progress reported at agreed intervals",
    "Compliance with the client's data-handling policy",
    "Use of client premises limited to agreed areas",
    "Branding and communications require prior approval",
    "A single point of contact manages the engagement",
]
RISK_FACTORS = [
    "Late delivery incurs a service-credit reduction",
    "Incomplete client inputs may affect the schedule",
    "Dependencies on third parties may cause delays",
    "Scope ambiguity may require clarification before proceeding",
    "Limited availability of client staff may affect milestones",
    "Quality shortfalls trigger rework at the supplier's expense",
    "Access delays may push out the schedule",
    "Undisclosed site conditions may expand the work",
    "Non-conformance blocks milestone acceptance",
    "Data-handling breaches void the engagement",
    "Seasonal demand may affect availability",
    "Unresolved defects delay final acceptance",
]
SUCCESS_CRITERIA = [
    "Deliverables accepted against the agreed criteria",
    "Milestones met on the agreed schedule",
    "No unresolved high-priority defects at handover",
    "Documentation complete and handed over",
    "Client staff able to operate the outcome independently",
    "Agreed performance thresholds met",
    "Acceptance sign-off obtained from the client",
    "Rework kept within agreed tolerances",
    "Compliance requirements evidenced",
    "Escalations resolved within agreed windows",
    "Reporting delivered on the agreed cadence",
    "Handover completed without outstanding actions",
]
TIMELINES = [
    "Delivered in phases over 8 weeks",
    "Delivered in phases over 12 weeks",
    "Recurring service across a 12-month term",
    "Completed within 6 weeks of kickoff",
    "Delivered in batches over 10 weeks",
    "Phased rollout over 16 weeks",
    "Completed within 4 weeks of kickoff",
    "Recurring service across a 6-month term",
    "Delivered over a 9-week schedule",
    "Milestone-based delivery over 14 weeks",
]

# Words that would signal a contract's economic value (must never appear).
BANNED = [
    "$", "cheap", "expensive", "premium", "luxury", "budget", "low-cost",
    "high-value", "costly", "inexpensive", "affordable", "pricey", "discount",
    "bargain", "lucrative", "high-end", "low-end",
]


def _window(pool: list[str], start: int, count: int) -> list[str]:
    n = len(pool)
    return [pool[(start + j) % n] for j in range(count)]


def _check_uniform() -> None:
    for d in DOMAINS:
        assert len(d["subjects"]) == SUBJ_N, d["category"]
        assert len(d["summaries"]) == SUMM_N, d["category"]
        assert len(d["deliverables"]) == DELIV_N, d["category"]
        assert len(d["requirements"]) == REQ_N, d["category"]


def build(count: int = 3000) -> list[dict]:
    _check_uniform()
    D = len(DOMAINS)
    key_product = D * SUBJ_N * SUMM_N * DELIV_N
    if count > key_product:
        raise ValueError(f"count {count} exceeds unique capacity {key_product}; add domains/pools")

    scenarios: list[dict] = []
    for i in range(count):
        # Injective key over (domain, subject, summary, deliverables-window) -> unique content.
        domain_i = i % D
        r = i // D
        subj_i = r % SUBJ_N
        r //= SUBJ_N
        summ_i = r % SUMM_N
        r //= SUMM_N
        deliv_start = r % DELIV_N  # r // DELIV_N == 0 for i < key_product

        dom = DOMAINS[domain_i]
        # Extra texture via strides coprime to each pool size (cannot affect uniqueness).
        req_start = (i * 3) % REQ_N
        constr_start = (i * 5) % len(CONSTRAINTS)
        risk_start = (i * 7) % len(RISK_FACTORS)
        succ_start = (i * 11) % len(SUCCESS_CRITERIA)
        time_i = (i * 3) % len(TIMELINES)

        scenarios.append({
            "id": f"SCN-{i + 1:04d}",
            "title": dom["subjects"][subj_i],
            "category": dom["category"],
            "summary": dom["summaries"][summ_i],
            "deliverables": _window(dom["deliverables"], deliv_start, 3),
            "requirements": _window(dom["requirements"], req_start, 3),
            "constraints": _window(CONSTRAINTS, constr_start, 2),
            "timeline": TIMELINES[time_i],
            "risk_factors": _window(RISK_FACTORS, risk_start, 2),
            "success_criteria": _window(SUCCESS_CRITERIA, succ_start, 2),
        })
    return scenarios


def validate(scenarios: list[dict]) -> None:
    ids = [s["id"] for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate ids")
    if ids != [f"SCN-{i + 1:04d}" for i in range(len(scenarios))]:
        raise ValueError("ids are not contiguous SCN-0001..N")

    rendered = set()
    for s in scenarios:
        model = Scenario(**s)          # schema validation
        text = model.render()
        low = text.lower()
        for w in BANNED:
            if w in low:
                raise ValueError(f"price-signaling term {w!r} in {s['id']}")
        if text in rendered:
            raise ValueError(f"duplicate rendered content at {s['id']}")
        rendered.add(text)


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    scenarios = build(count)
    validate(scenarios)

    out = ROOT / "configs" / "scenarios.yaml"
    header = (
        "# Fixed, indexed scenario bank (DESIGN.md §2). Round N -> entry N (1-indexed).\n"
        "# GENERATED by scripts/generate_scenarios.py -- do not edit by hand; regenerate.\n"
        f"# {count} unique, economically-neutral briefs. Uniqueness guaranteed by construction.\n"
    )
    body = yaml.safe_dump({"scenarios": scenarios}, sort_keys=False,
                          default_flow_style=False, allow_unicode=True, width=100)
    out.write_text(header + body, encoding="utf-8")

    titles = {s["title"] for s in scenarios}
    print(f"wrote {count} scenarios to {out.relative_to(ROOT)}")
    print(f"domains={len(DOMAINS)}  distinct titles={len(titles)}  all content unique + price-neutral")


if __name__ == "__main__":
    main()
