#!/usr/bin/env python3
"""Generate the small Stage-2 document fixtures (reproducible, synthetic).

Writes into data/documents/:
    synthetic_fir.txt     - a short synthetic FIR (plain text)
    synthetic_fir.pdf     - the same FIR as a PDF (reportlab)
    synthetic_calls.csv   - a synthetic CDR extract

Every file is labelled SYNTHETIC DEMONSTRATION DATA. The names, numbers,
vehicles and accounts are fictional and intentionally echo entities that
already exist in the seeded case CASE-2026-001 so the match-suggestion path
is exercised as well as the new-entity path.
"""

from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Note: the rule extractor works line-by-line for plain text, so every
# sentence that must yield a relationship is kept on ONE line.
FIR_TEXT = """SYNTHETIC DEMONSTRATION DATA - NEXUS stage 2 fixture. Not a real complaint.
Any resemblance to real persons, cases or numbers is coincidental.

IN THE OFFICE OF THE POLICE STATION, SHIVAJI NAGAR
First Information Report No. 214/2026, reference CASE-2026-001.

03/05/2026 - The complainant noticed suspicious activity near the warehouse yard in Shivaji Nagar in the early morning.

1. The complainant, Mr. Vikram Rao, stated that a white Maruti Swift bearing registration MH01GH9876 had been seen loitering near the gate.
The suspect was named Suresh Kulkarni.
The vehicle MH01GH9876 owned by Suresh Kulkarni was reportedly parked there since the previous night.

2. Vikram Rao called 9822044117 to inform his neighbour of the incident.

3. Ms. Neha Patil arrived in vehicle MH12AB1234 and assisted the complainant in documenting the scene.

4. A transfer of Rs. 20000 was later made from AXIS501104 to SBI123456, which are linked to the accused per the bank records.

5. The complainant also spoke with V. Rao, a relative who stayed at the same address during the month of May.

2026-05-03 14:10 - CCTV footage was retrieved from the gate camera and attached as an annexure.

End of report. - SYNTHETIC DEMONSTRATION DATA
"""

CALLS_CSV = """call_id,timestamp,caller,caller_name,callee,callee_name,duration_s,cell_tower,case_ref
CDR-001,03/05/2026 08:41:12,9822044117,Vikram Rao,9000000001,Suresh Kulkarni,124,Kurla Tower 4,CASE-2026-001
CDR-002,03/05/2026 09:15:47,9000000001,Suresh Kulkarni,9812345678,Deepak Menon,302,Kurla Tower 4,
CDR-003,04/05/2026 11:02:33,9812345678,Deepak Menon,9000000002,Ramesh Gupta,95,Dadar Tower 9,
CDR-004,04/05/2026 18:20:05,9000000002,Ramesh Gupta,9822044117,Vikram Rao,41,Dadar Tower 9,
"""


def write_txt(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_csv(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def write_pdf(path: str, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas

    c = pdf_canvas.Canvas(path, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 10)
    y = height - 60
    for line in text.splitlines():
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 60
        c.drawString(60, y, line)
        y -= 14
    c.save()


def main() -> None:
    txt = os.path.join(HERE, "synthetic_fir.txt")
    csv_path = os.path.join(HERE, "synthetic_calls.csv")
    pdf = os.path.join(HERE, "synthetic_fir.pdf")
    write_txt(txt, FIR_TEXT)
    write_csv(csv_path, CALLS_CSV)
    write_pdf(pdf, FIR_TEXT)
    print("fixtures written:")
    for p in (txt, csv_path, pdf):
        print(" ", p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
