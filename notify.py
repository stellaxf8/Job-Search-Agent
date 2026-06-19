"""
notify.py
---------
Sends a daily email digest with job matches and tailored resume
attachments via SendGrid.

Called by tailor.py — import run() directly, or run standalone.

Requirements:
    pip install sendgrid python-dotenv

Environment variables (set in GitHub Secrets):
    SENDGRID_API_KEY
"""

import os
import json
import glob
import base64
from datetime import datetime
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName,
    FileType, Disposition, To
)

load_dotenv(override=True)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = "stella_fuentes@outlook.com"
TO_EMAIL   = "stella_fuentes@outlook.com"


# ── Email Builder ──────────────────────────────────────────────────────────────

def build_html(results: list[dict], all_jobs: list[dict]) -> str:
    """Builds the HTML email body."""

    today = datetime.now().strftime("%A, %B %d %Y")

    # Split into high matches (tailored) and others worth noting
    high    = [j for j in all_jobs if j.get("match_score", 0) >= 80]
    notable = [j for j in all_jobs if 60 <= j.get("match_score", 0) < 80]

    def score_color(score):
        if score >= 80: return "#1a7f4b"
        if score >= 60: return "#b45309"
        return "#888888"

    def job_row(job):
        score = job.get("match_score", 0)
        link  = job.get("link", "")
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "")
        reason = job.get("match_reason", "")
        missing = ", ".join(job.get("missing_skills", [])) or "None"
        posted = job.get("posted_at", "")

        title_cell = f'<a href="{link}" style="color:#1a56db;text-decoration:none;font-weight:600;">{title}</a>' if link else f'<strong>{title}</strong>'

        return f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
            {title_cell}<br>
            <span style="font-size:13px;color:#555;">{company} &middot; {location}</span>
            {f'<br><span style="font-size:12px;color:#999;">{posted}</span>' if posted else ''}
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;text-align:center;">
            <span style="font-weight:700;color:{score_color(score)};font-size:15px;">{score}%</span>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;font-size:13px;color:#444;">
            {reason}<br>
            <span style="color:#999;">Gaps: {missing}</span>
          </td>
        </tr>"""

    high_rows    = "".join(job_row(j) for j in high)
    notable_rows = "".join(job_row(j) for j in notable)

    tailored_section = ""
    if results:
        tailored_section = """
        <h2 style="font-size:16px;color:#111;margin:32px 0 8px;">Tailored resumes attached</h2>
        <p style="font-size:14px;color:#555;margin:0 0 8px;">A tailored .docx has been generated for each high-match role below:</p>
        <ul style="font-size:14px;color:#333;margin:0;padding-left:20px;">
        """ + "".join(
            f'<li style="margin-bottom:6px;"><strong>{r["title"]}</strong> @ {r["company"]} ({r["match_score"]}%)<br>'
            f'<span style="font-size:13px;color:#555;">{r.get("changes_made","")}</span></li>'
            for r in results
        ) + "</ul>"

    notable_section = ""
    if notable:
        notable_section = f"""
        <h2 style="font-size:16px;color:#111;margin:32px 0 8px;">Worth watching (60–79%)</h2>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
          <thead>
            <tr style="background:#f9fafb;">
              <th style="padding:10px 8px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Role</th>
              <th style="padding:10px 8px;text-align:center;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Match</th>
              <th style="padding:10px 8px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Notes</th>
            </tr>
          </thead>
          <tbody>{notable_rows}</tbody>
        </table>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#111;">

      <p style="font-size:13px;color:#999;margin:0 0 4px;">{today}</p>
      <h1 style="font-size:22px;font-weight:700;margin:0 0 4px;">Job search digest</h1>
      <p style="font-size:14px;color:#555;margin:0 0 24px;">
        {len(all_jobs)} jobs scanned &nbsp;&middot;&nbsp;
        {len(high)} high matches (&ge;80%) &nbsp;&middot;&nbsp;
        {len(notable)} worth watching (60–79%)
      </p>

      <h2 style="font-size:16px;color:#111;margin:0 0 8px;">High matches (&ge;80%)</h2>
      {"<p style='font-size:14px;color:#999;'>No high matches today.</p>" if not high else f'''
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#f9fafb;">
            <th style="padding:10px 8px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Role</th>
            <th style="padding:10px 8px;text-align:center;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Match</th>
            <th style="padding:10px 8px;text-align:left;color:#666;font-weight:600;border-bottom:2px solid #e5e7eb;">Notes</th>
          </tr>
        </thead>
        <tbody>{high_rows}</tbody>
      </table>'''}

      {tailored_section}
      {notable_section}

      <p style="font-size:12px;color:#bbb;margin-top:40px;border-top:1px solid #e5e7eb;padding-top:16px;">
        Sent by your job search agent &middot; GitHub Actions
      </p>

    </body>
    </html>
    """


# ── Attachments ────────────────────────────────────────────────────────────────

def build_attachments(results: list[dict]) -> list[Attachment]:
    """Reads each tailored .docx and encodes it as an email attachment."""
    attachments = []
    for r in results:
        filename = r.get("filename", "")
        if not filename or not os.path.exists(filename):
            print(f"  Warning: file not found — {filename}")
            continue
        with open(filename, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(filename),
            FileType("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            Disposition("attachment")
        )
        attachments.append(attachment)
        print(f"  Attached: {filename}")
    return attachments


# ── Send ───────────────────────────────────────────────────────────────────────

def send_email(results: list[dict], all_jobs: list[dict]):
    """Builds and sends the digest email via SendGrid."""
    today = datetime.now().strftime("%b %d")
    high_count = len([j for j in all_jobs if j.get("match_score", 0) >= 80])

    subject = f"Job digest {today} — {high_count} high match{'es' if high_count != 1 else ''}"
    html    = build_html(results, all_jobs)

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject=subject,
        html_content=html
    )

    for attachment in build_attachments(results):
        message.add_attachment(attachment)

    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    response = sg.send(message)

    if response.status_code in (200, 202):
        print(f"\nEmail sent: {subject}")
    else:
        print(f"\nSendGrid error {response.status_code}: {response.body}")


# ── Main ───────────────────────────────────────────────────────────────────────

def run(results: list[dict], all_jobs: list[dict]):
    """Called directly from tailor.py with results and full job list."""
    print("\n=== Notify: Sending digest email ===")
    send_email(results, all_jobs)


# Standalone usage — loads from latest job_results JSON
if __name__ == "__main__":
    files = sorted(glob.glob("job_results_*.json"), reverse=True)
    if not files:
        print("No job_results JSON found. Run search_agent.py first.")
    else:
        with open(files[0]) as f:
            all_jobs = json.load(f)

        # Look for any .docx files generated today
        docx_files = glob.glob("Stella_Fuentes_*.docx")
        results = [
            {"title": f.replace("Stella_Fuentes_", "").replace(".docx", ""),
             "company": "", "match_score": 0, "filename": f, "changes_made": ""}
            for f in docx_files
        ]

        send_email(results, all_jobs)
