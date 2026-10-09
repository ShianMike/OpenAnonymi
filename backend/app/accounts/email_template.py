"""Self-contained transactional email, with no remote images or tracking."""

from html import escape


def email_html(subject: str, body: str, *, contact: str, code: str | None = None) -> str:
    title = {
        "OpenAnonymi sign-up code": "Finish signing up",
        "Verify your OpenAnonymi email": "Verify your email",
        "OpenAnonymi account recovery code": "Recover your account",
        "OpenAnonymi workspace invitation": "Your workspace invitation",
    }.get(subject, subject)
    paragraphs = []
    for paragraph in body.split("\n\n"):
        if code is not None and paragraph == code:
            paragraphs.append(
                '<table role="presentation" style="width:100%;margin:24px 0;'
                'border-collapse:separate;background:#edf4ed;border:1px solid #ccdbce;'
                'border-radius:12px" cellpadding="0" cellspacing="0"><tr><td style="padding:22px">'
                '<p style="margin:0 0 12px;color:#48624f;font-size:11px;'
                'font-weight:700;letter-spacing:1.4px">YOUR ONE-TIME CODE</p>'
                '<div style="font-family:Consolas,Menlo,monospace;font-size:22px;font-weight:700;'
                'line-height:1.6;color:#173e30;overflow-wrap:anywhere;word-break:break-all">'
                f'{escape(code)}</div>'
                '<p style="margin:14px 0 0;color:#48624f;font-size:13px;line-height:1.5">'
                'Select and copy the entire code.</p></td></tr></table>'
            )
        else:
            content = escape(paragraph).replace("\n", "<br>")
            paragraphs.append(f'<p style="margin:0 0 16px;line-height:1.7">{content}</p>')
    code_help = (
        '<table role="presentation" style="width:100%;margin-top:24px;border-top:1px solid #e1e7df"'
        ' cellpadding="0" cellspacing="0"><tr><td style="padding-top:20px">'
        '<p style="margin:0 0 8px;font-size:14px;font-weight:700;color:#173e30">Back to your tab</p>'
        '<p style="margin:0;font-size:14px;color:#52665b;line-height:1.7">'
        'Paste the code where you requested it. Keep that tab open until you finish.</p>'
        '</td></tr></table>'
        if code is not None else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#f3f4ef;color:#243b31;font-family:Arial,Helvetica,sans-serif;font-size:16px">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{escape(title)}. Continue securely in OpenAnonymi.</div>
<table role="presentation" style="width:100%;border-collapse:collapse" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" style="width:100%;max-width:560px;border-collapse:separate;background:#ffffff;border:1px solid #dbe3d9;border-radius:16px" cellpadding="0" cellspacing="0">
<tr><td style="padding:24px;background:#173e30;border-radius:15px 15px 0 0">
<span style="font-size:22px;font-weight:700;color:#ffffff">OpenAnonymi<span style="color:#b4e5cb">.</span></span>
<p style="margin:8px 0 0;font-size:11px;letter-spacing:1.5px;color:#c5ddcd">YOUR PRIVACY WORKSPACE</p>
</td></tr>
<tr><td style="padding:28px 24px">
<h1 style="margin:0 0 16px;font-size:30px;line-height:1.2;color:#173e30">{escape(title)}</h1>
{''.join(paragraphs)}{code_help}
</td></tr>
<tr><td style="padding:20px 24px;border-top:1px solid #e1e7df;background:#f9faf6;border-radius:0 0 15px 15px">
<p style="margin:0 0 8px;font-size:13px;line-height:1.7;color:#52665b">Need a hand? <a href="mailto:{escape(contact)}" style="color:#24573e;font-weight:700">Contact support</a></p>
<p style="margin:0;font-size:12px;line-height:1.7;color:#52665b">Never share your code, including with support.</p>
</td></tr></table>
</td></tr></table></body></html>"""
