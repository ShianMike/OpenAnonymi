"""Self-contained transactional email, with no remote images or tracking."""

from html import escape


def email_html(subject: str, body: str, *, code: str | None = None) -> str:
    paragraphs = []
    for paragraph in body.split("\n\n"):
        if code is not None and paragraph == code:
            paragraphs.append(
                '<div style="margin:24px 0;padding:20px 16px;background:#edf3ed;'
                'border:1px solid #ccdad0;border-radius:12px">'
                '<p style="margin:0 0 12px;color:#52665b;font-size:12px;'
                'font-weight:700;letter-spacing:1px">YOUR ONE-TIME CODE</p>'
                '<div style="font-family:Consolas,monospace;font-size:18px;'
                'line-height:1.7;color:#173e30;overflow-wrap:anywhere;word-break:break-all">'
                f'{escape(code)}</div></div>'
            )
        else:
            content = escape(paragraph).replace("\n", "<br>")
            paragraphs.append(f'<p style="margin:0 0 16px;line-height:1.7">{content}</p>')
    code_help = (
        '<p style="margin:4px 0 0;font-size:13px;color:#52665b;line-height:1.7">'
        'Copy the whole code and paste it into the tab where you requested it. '
        'Keep that tab open. Never share your code, including with support.</p>'
        if code is not None else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#f4f5ef;color:#243b31;font-family:Arial,Helvetica,sans-serif">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{escape(subject)}. Continue securely in OpenAnonymi.</div>
<table role="presentation" style="width:100%;border-collapse:collapse" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" style="width:100%;max-width:560px;border-collapse:separate;background:#ffffff;border:1px solid #dbe3d9;border-radius:16px" cellpadding="0" cellspacing="0">
<tr><td style="padding:26px 28px;border-bottom:1px solid #e4e9e1">
<a href="https://openanonymi.com" style="font-size:21px;font-weight:700;color:#173e30;text-decoration:none">OpenAnonymi<span style="color:#55866d">.</span></a>
</td></tr>
<tr><td style="padding:28px">
<h1 style="margin:0 0 20px;font-size:24px;line-height:1.35;color:#173e30">{escape(subject)}</h1>
{''.join(paragraphs)}{code_help}
</td></tr>
<tr><td style="padding:20px 28px;border-top:1px solid #e4e9e1;font-size:12px;line-height:1.8;color:#52665b">
Need help? <a href="mailto:support@openanonymi.com" style="color:#2c654b">support@openanonymi.com</a><br>
<a href="https://openanonymi.com" style="color:#52665b;text-decoration:none">openanonymi.com</a>
</td></tr></table>
</td></tr></table></body></html>"""
