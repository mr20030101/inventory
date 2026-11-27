"""Export tables to CSV, Excel and PDF with the school name, title, filters and generator on printouts."""
from __future__ import annotations

import csv
import html
from datetime import datetime

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from saims.desktop.ui import theme


def ask_path(parent: QWidget, title: str, kind: str) -> str | None:
    ext = {"csv": "CSV files (*.csv)", "xlsx": "Excel workbooks (*.xlsx)", "pdf": "PDF documents (*.pdf)"}[kind]
    name = "".join(c if c.isalnum() or c in "-_ " else "-" for c in title).strip().replace(" ", "-").lower()
    path, _ = QFileDialog.getSaveFileName(parent, f"Export {title}", f"{name}.{kind}", ext)
    if not path:
        return None
    return path if path.lower().endswith(f".{kind}") else f"{path}.{kind}"


def write(kind: str, path: str, title: str, headers: list[str], rows: list[list[str]], meta: dict) -> None:
    if kind == "csv":
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
    elif kind == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = title[:31]
        ws.append([meta.get("school", "")])
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"].font = Font(bold=True)
        ws.append([_meta_line(meta)])
        ws.append([])
        ws.append(headers)
        for cell in ws[5]:
            cell.font = Font(bold=True)
        for r in rows:
            ws.append(r)
        for i, h in enumerate(headers, start=1):
            width = max([len(h)] + [len(str(r[i - 1])) for r in rows[:500]]) + 2
            ws.column_dimensions[ws.cell(row=5, column=i).column_letter].width = min(width, 45)
        wb.save(path)
    else:
        _pdf(path, title, headers, rows, meta)


def _meta_line(meta: dict) -> str:
    parts = [f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}"]
    if meta.get("user"):
        parts.append(f"by {meta['user']}")
    if meta.get("filters"):
        parts.append(f"· {meta['filters']}")
    return " ".join(parts)


def _pdf(path: str, title: str, headers: list[str], rows: list[list[str]], meta: dict) -> None:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    note = f"<p class='note'>{html.escape(meta['note'])}</p>" if meta.get("note") else ""
    doc = QTextDocument()
    # The SAIMS logo in the page header (rendered from the outlined SVG, so no fonts are needed).
    doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("saims-logo"), theme.logo_image(600))
    doc.setHtml(f"""
    <style>
      body {{ font-family: sans-serif; font-size: 8pt; color: #1f3b47; }}
      h1 {{ font-size: 14pt; margin: 0; }} h2 {{ font-size: 11pt; margin: 2px 0 2px 0; color: #2f5d6e; }}
      .meta, .note {{ color: #5e7a86; font-size: 7.5pt; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th {{ background: #2f5d6e; color: white; text-align: left; padding: 4px; }}
      td {{ border-bottom: 1px solid #c5dae2; padding: 3px 4px; }}
    </style>
    <table width='100%' cellspacing='0' cellpadding='0'><tr>
      <td style='border:none; padding:0'><h1>{html.escape(meta.get('school', ''))}</h1>
        <h2>{html.escape(title)}</h2>
        <p class='meta'>{html.escape(_meta_line(meta))} · {len(rows)} rows</p>{note}</td>
      <td style='border:none; padding:0' align='right' valign='top'><img src='saims-logo' width='120'></td>
    </tr></table><p></p>
    <table cellspacing='0'><tr>{head}</tr>{body}</table>""")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    landscape = len(headers) > 6
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                      QPageLayout.Orientation.Landscape if landscape
                                      else QPageLayout.Orientation.Portrait, QMarginsF(12, 12, 12, 12),
                                      QPageLayout.Unit.Millimeter))
    doc.print_(printer)


def export_table(parent: QWidget, kind: str, title: str, headers, rows, meta: dict) -> bool:
    path = ask_path(parent, title, kind)
    if not path:
        return False
    try:
        write(kind, path, title, headers, rows, meta)
    except OSError as exc:
        QMessageBox.critical(parent, "Export failed", str(exc))
        return False
    QMessageBox.information(parent, "Export complete", f"Saved {len(rows)} rows to\n{path}")
    return True
