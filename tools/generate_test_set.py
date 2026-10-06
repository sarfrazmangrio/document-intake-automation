"""Build the Build 1 test set: 20 invoices (copied from invoice-extraction-demo) plus 10 new documents.

New documents, all fictional:
  7 receipts from 2 shops (one phone photo as JPG, one scanned PDF, one duplicate,
  one with the date missing, one with a wrong total) and
  3 certificates of insurance (one expired, one with the policy number missing).

Writes the new files to test_set/documents/ and every document's expected answer
(fields, line items, flags) to test_set/expected.json, so a run can be scored.

Run:   python tools/generate_test_set.py
Needs: reportlab, pillow, pypdfium2
"""
from __future__ import annotations

import io
import json
import random
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "test_set" / "documents"
INVOICE_TRUTH = ROOT / "test_set" / "invoice_ground_truth.json"
EXPECTED = ROOT / "test_set" / "expected.json"

FIELDS = ["doc_type", "issuer", "doc_number", "doc_date", "due_date", "effective_date", "expiry_date",
          "currency", "counterparty", "policy_number", "coverage_limit",
          "subtotal", "tax_rate_percent", "tax_amount", "total"]

# ------------------------------------------------------------------ receipts

SHOPS = {
    "bb": {"name": "BRIGHT BASKET GROCERS", "issuer": "Bright Basket Grocers",
           "address": ["Shop 12, Block 2, PECHS", "Karachi, Pakistan"],
           "currency": "PKR", "tax_label": "GST 18%", "tax_rate": 18.0,
           "date_fmt": lambda d: d.strftime("%d/%m/%Y") + "  18:42", "no_label": "Receipt",
           "money": lambda x: f"{x:,.2f}", "pay": "Paid: Cash"},
    "jl": {"name": "JUNIPER LANE CAFE", "issuer": "Juniper Lane Cafe",
           "address": ["1406 Elm Street", "Austin, TX 78702, USA"],
           "currency": "USD", "tax_label": "Sales tax 8.25%", "tax_rate": 8.25,
           "date_fmt": lambda d: d.strftime("%m/%d/%Y") + "  9:41 AM", "no_label": "Order #",
           "money": lambda x: f"${x:,.2f}", "pay": "Visa ending 4242"},
}

RECEIPTS = [
    # file, shop, number, date (None = blank), lines (description, qty, unit price), form, total misprint, duplicate of
    ("R-01.pdf", "bb", "BB-104233", date(2026, 10, 5),
     [("Basmati rice 5 kg", 1, 1850.00), ("Cooking oil 3 L", 1, 1495.00), ("Eggs, dozen", 2, 380.00),
      ("Milk 1 L", 3, 260.00), ("Green tea, 25 bags", 1, 425.00)], "pdf", 0, None),
    ("R-02.pdf", "jl", "4817", date(2026, 10, 3),
     [("Oat milk latte", 2, 5.25), ("Blueberry muffin", 1, 3.75), ("Cold brew, large", 1, 4.95)], "pdf", 0, None),
    ("R-03.jpg", "bb", "BB-104251", date(2026, 10, 6),
     [("Atta flour 10 kg", 1, 1320.00), ("Sugar 2 kg", 1, 330.00), ("Lentils (masoor) 1 kg", 2, 410.00),
      ("Dish soap 500 ml", 1, 245.00)], "photo", 0, None),
    ("R-04.pdf", "jl", "4817", date(2026, 10, 3),
     [("Oat milk latte", 2, 5.25), ("Blueberry muffin", 1, 3.75), ("Cold brew, large", 1, 4.95)], "pdf", 0, "R-02.pdf"),
    ("R-05.pdf", "jl", "4822", None,
     [("Americano", 1, 3.50), ("Avocado toast", 1, 9.25)], "pdf", 0, None),
    ("R-06.pdf", "bb", "BB-104260", date(2026, 10, 6),
     [("Chicken 1 kg", 2, 780.00), ("Tomatoes 1 kg", 1, 220.00), ("Yogurt 1 kg", 1, 340.00)], "pdf", 100.0, None),
    ("R-07.pdf", "jl", "4830", date(2026, 10, 4),
     [("Cappuccino", 1, 4.75), ("Chai latte", 1, 4.95), ("Croissant", 2, 3.40)], "scan", 0, None),
]

# -------------------------------------------------------------- certificates

INSURER = "Northstar Mutual Insurance Co."
HOLDER = "Crescent Foods"
CERTS = [
    # file, certificate number, issue date, insured, insured address, policy number (None = blank), limit, effective, expiry
    ("C-01.pdf", "NM-COI-2026-0418", date(2026, 3, 12), "Harbor Line Freight",
     "2200 Port Road, Building 4, Long Beach, CA 90802, USA", "GL-77310245", 1_000_000, date(2026, 4, 1), date(2027, 3, 31)),
    ("C-02.pdf", "NM-COI-2025-0977", date(2025, 8, 20), "Kestrel Packaging Ltd.",
     "Plot 27, Sector 12-C, Korangi Industrial Area, Karachi 74900, Pakistan", "GL-66120873", 500_000,
     date(2025, 9, 1), date(2026, 8, 31)),
    ("C-03.pdf", "NM-COI-2026-0533", date(2026, 5, 7), "Saffron Print Studio",
     "14-B Main Boulevard, Gulberg III, Lahore 54660, Pakistan", None, 1_000_000, date(2026, 5, 15), date(2027, 5, 14)),
]
CHECK_DATE = date(2026, 10, 6)  # certificates are judged as of this date in the expected answers


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# ------------------------------------------------------------------ drawing

def receipt_pdf(path: Path, shop: dict, number: str, day: date | None, lines, total_shift: float) -> dict:
    """Draw an 80 mm till receipt; return its true values."""
    items = [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2)} for d, q, p in lines]
    subtotal = round(sum(i["amount"] for i in items), 2)
    tax = round(subtotal * shop["tax_rate"] / 100, 2)
    total_true = round(subtotal + tax, 2)
    total_printed = round(total_true + total_shift, 2)

    W = 80 * mm
    H = (118 + 26 * len(items) + 110)
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setTitle(f"{shop['issuer']} {number}")
    y = H - 22
    c.setFont("Courier-Bold", 10.5)
    c.drawCentredString(W / 2, y, shop["name"])
    c.setFont("Courier", 8)
    for line in shop["address"]:
        y -= 11
        c.drawCentredString(W / 2, y, line)
    y -= 16
    c.drawString(10, y, f"{shop['no_label']}: {number}" if shop["no_label"] != "Order #" else f"Order #{number}")
    y -= 11
    c.drawString(10, y, "Date: " + (shop["date_fmt"](day) if day else ""))
    y -= 8
    c.line(10, y, W - 10, y)
    m = shop["money"]
    for it in items:
        y -= 12
        c.drawString(10, y, it["description"])
        y -= 11
        c.drawString(18, y, f"{it['quantity']} x {m(it['unit_price'])}")
        c.drawRightString(W - 10, y, m(it["amount"]))
    y -= 8
    c.line(10, y, W - 10, y)
    for label, val, bold in (("Subtotal", subtotal, False), (shop["tax_label"], tax, False), ("TOTAL", total_printed, True)):
        y -= 13
        c.setFont("Courier-Bold" if bold else "Courier", 9 if bold else 8)
        c.drawString(10, y, label)
        c.drawRightString(W - 10, y, m(val))
    c.setFont("Courier", 8)
    y -= 16
    c.drawString(10, y, shop["pay"])
    y -= 16
    c.drawCentredString(W / 2, y, "Thank you for shopping with us")
    c.showPage()
    c.save()
    return {"items": items, "subtotal": subtotal, "tax": tax, "total": total_printed}


def certificate_pdf(path: Path, number, issued, insured, insured_addr, policy, limit, eff, exp) -> None:
    W, H = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Certificate of insurance {number}")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, H - 70, "CERTIFICATE OF INSURANCE")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawString(50, H - 104, "This certificate is issued as a matter of information only and confers no rights upon the holder.")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(W - 50, H - 70, f"Certificate No.: {number}")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 50, H - 84, f"Date issued: {long_date(issued)}")

    def box(x, y, w, h, title, rows):
        c.setStrokeColor(colors.HexColor("#555555"))
        c.rect(x, y - h, w, h)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 8, y - 14, title)
        c.setFont("Helvetica", 10)
        yy = y - 30
        for r in rows:
            c.drawString(x + 8, yy, r)
            yy -= 14

    top = H - 120
    box(50, top, 240, 90, "INSURER", [INSURER, "88 Commerce Plaza", "Hartford, CT 06103, USA"])
    addr = insured_addr.split(", ")
    half = (len(addr) + 1) // 2
    box(305, top, 240, 90, "INSURED", [insured, ", ".join(addr[:half]), ", ".join(addr[half:])])
    top -= 110
    box(50, top, 495, 150, "COVERAGE", [
        "Type of insurance: Commercial General Liability",
        f"Policy No.: {policy or ''}",
        f"Policy effective: {long_date(eff)}",
        f"Policy expires: {long_date(exp)}",
        f"Each occurrence limit: USD {limit:,}",
        f"General aggregate limit: USD {2 * limit:,}",
    ])
    top -= 170
    box(50, top, 495, 80, "CERTIFICATE HOLDER", [HOLDER, "Suite 9, Plot 3, Shahrah-e-Faisal, Karachi, Pakistan"])
    c.setFont("Helvetica", 9)
    c.drawString(50, top - 120, "Authorized representative: J. Alvarez")
    c.line(50, top - 100, 220, top - 100)
    c.showPage()
    c.save()


def rasterize(pdf_path: Path, scale: float) -> Image.Image:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    img = pdf[0].render(scale=scale).to_pil().convert("RGB")
    pdf.close()
    return img


def make_scan(src_pdf: Path, dst_pdf: Path, seed: int) -> None:
    """Image-only PDF with scan artefacts (no text layer)."""
    rnd = random.Random(seed)
    img = rasterize(src_pdf, 150 / 72).convert("L")
    img = img.rotate(rnd.uniform(0.7, 1.3), resample=Image.BICUBIC, expand=True, fillcolor=255)
    noise = Image.effect_noise(img.size, 18).convert("L")
    img = Image.blend(img, noise, 0.06).filter(ImageFilter.GaussianBlur(0.5))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=55)
    Image.open(buf).convert("RGB").save(dst_pdf, "PDF", resolution=150)


def make_photo(src_pdf: Path, dst_jpg: Path, seed: int) -> None:
    """Phone-photo look: receipt on a table, tilted, uneven light, slight blur, JPEG."""
    rnd = random.Random(seed)
    rec = rasterize(src_pdf, 3.0)
    bg = Image.new("RGB", (int(rec.width * 1.6), int(rec.height * 1.25)), (118, 96, 74))
    bg.paste(rec, ((bg.width - rec.width) // 2, (bg.height - rec.height) // 2))
    bg = bg.rotate(rnd.uniform(4, 6), resample=Image.BICUBIC, fillcolor=(118, 96, 74))
    w, h = bg.size
    shade = Image.new("L", (w, h))
    d = ImageDraw.Draw(shade)
    for x in range(w):
        d.line([(x, 0), (x, h)], fill=int(60 * x / w))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    bg = Image.composite(dark, bg, shade)
    noise = Image.effect_noise(bg.size, 22).convert("RGB")
    bg = Image.blend(bg, noise, 0.05).filter(ImageFilter.GaussianBlur(1.1))
    bg.save(dst_jpg, "JPEG", quality=70)


# ------------------------------------------------------------------ expected answers

def blank_fields(doc_type: str) -> dict:
    f = {k: None for k in FIELDS}
    f["doc_type"] = doc_type
    return f


def invoice_expectations() -> list[dict]:
    truth = json.loads(INVOICE_TRUTH.read_text(encoding="utf-8"))
    out = []
    for file, inv in truth.items():
        f = blank_fields("invoice")
        f.update(issuer=inv["vendor_name"], doc_number=inv["invoice_number"], doc_date=inv["invoice_date"],
                 due_date=inv["due_date"], currency=inv["currency"], counterparty=inv["customer_name"],
                 subtotal=inv["subtotal"], tax_rate_percent=inv["tax_rate_percent"], tax_amount=inv["tax_amount"],
                 total=inv["total"])
        flags = ["duplicate_document" if x == "duplicate_invoice" else x for x in inv["expected_issues"]]
        out.append({"file": file, "fields": f, "lines": inv["line_items"], "expected_flags": flags,
                    "notes": inv.get("case") or ""})
    return out


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    expected = invoice_expectations()

    for i, (file, key, number, day, lines, form, shift, dup_of) in enumerate(RECEIPTS, start=1):
        shop = SHOPS[key]
        target = DOCS / file
        tmp = DOCS / f"_tmp_{i}.pdf"
        vals = receipt_pdf(tmp if form != "pdf" else target, shop, number, day, lines, shift)
        if form == "scan":
            make_scan(tmp, target, seed=100 + i)
        elif form == "photo":
            make_photo(tmp, target, seed=100 + i)
        if tmp.exists():
            tmp.unlink()
        f = blank_fields("receipt")
        f.update(issuer=shop["issuer"], doc_number=number, doc_date=day.isoformat() if day else None,
                 currency=shop["currency"], subtotal=vals["subtotal"], tax_rate_percent=shop["tax_rate"],
                 tax_amount=vals["tax"], total=vals["total"])
        flags = []
        if day is None:
            flags.append("missing_required_field")
        if shift:
            flags.append("total_equals_subtotal_plus_tax")
        if dup_of:
            flags.append("duplicate_document")
        notes = {"photo": "phone photo (JPG)", "scan": "scanned, no text layer"}.get(form, "")
        if dup_of:
            notes = f"duplicate of {dup_of}"
        if day is None:
            notes = "date left blank"
        if shift:
            notes = f"total printed {shift:,.0f} too high"
        expected.append({"file": file, "fields": f, "lines": vals["items"], "expected_flags": flags, "notes": notes})

    for number_, (file, number, issued, insured, addr, policy, limit, eff, exp) in enumerate(CERTS, start=1):
        certificate_pdf(DOCS / file, number, issued, insured, addr, policy, limit, eff, exp)
        f = blank_fields("certificate")
        f.update(issuer=INSURER, doc_number=number, doc_date=issued.isoformat(), effective_date=eff.isoformat(),
                 expiry_date=exp.isoformat(), currency="USD", counterparty=insured, policy_number=policy,
                 coverage_limit=float(limit))
        flags = []
        if policy is None:
            flags.append("missing_required_field")
        if exp < CHECK_DATE:
            flags.append("certificate_expired")
        notes = "expired before 6 Oct 2026" if exp < CHECK_DATE else ("policy number left blank" if policy is None else "")
        expected.append({"file": file, "fields": f, "lines": [], "expected_flags": flags, "notes": notes})

    EXPECTED.write_text(json.dumps({
        "about": ("Expected answers for the Build 1 test set. Fields not printed on a document are null. "
                  "Documents are processed in file-name order, so a duplicate is flagged on the later file. "
                  f"Certificates are judged as of {CHECK_DATE.isoformat()}."),
        "check_date": CHECK_DATE.isoformat(),
        "fields": FIELDS,
        "documents": expected,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    n_flags = sum(len(d["expected_flags"]) for d in expected)
    print(f"{len(expected)} documents, {n_flags} expected flags -> {EXPECTED}")


if __name__ == "__main__":
    main()
