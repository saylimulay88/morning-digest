import os
import smtplib
import feedparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

FEEDS = {
    "finance": [
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Guardian Business", "https://www.theguardian.com/uk/business/rss"),
        ("Axios", "https://api.axios.com/feed/"),
    ],
    "geopolitics": [
        ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
        ("Foreign Policy", "https://foreignpolicy.com/feed/"),
        ("Deutsche Welle", "https://rss.dw.com/rdf/rss-en-world"),
    ],
    "tech": [
        ("Hacker News", "https://hnrss.org/frontpage"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Wired", "https://www.wired.com/feed/rss"),
    ],
    "philosophy_behavior": [
("Psychology Today", "https://www.psychologytoday.com/us/front-page/feed"),
        ("Greater Good Magazine", "https://greatergood.berkeley.edu/feeds/news"),
        ("Harvard Business Review", "https://hbr.org/feed"),
        ("MIT Sloan Management Review", "https://sloanreview.mit.edu/feed/"),
    ],
}

MAX_ARTICLES_PER_FEED = 5


def fetch_articles(feeds: dict) -> dict:
    all_articles = {}
    for category, sources in feeds.items():
        articles = []
        for source_name, url in sources:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    title = entry.get("title", "No title").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    # Strip basic HTML tags from summary
                    import re
                    summary = re.sub(r"<[^>]+>", "", summary)[:300]
                    articles.append(f"[{source_name}] {title}: {summary}")
            except Exception as e:
                print(f"  Warning: could not fetch {source_name} ({url}): {e}")
        all_articles[category] = articles
    return all_articles


def build_gemini_prompt(articles: dict) -> str:
    sections = {
        "finance": "FINANCE",
        "geopolitics": "GEOPOLITICS",
        "tech": "TECH",
        "philosophy_behavior": "CREATOR ECONOMY",
    }
    prompt_parts = [
        "Act as a sharp, witty friend who actually reads the news — someone who gives you the real deal "
        "with personality, not a boring press release. Based on the articles below, write a daily news digest "
        "with exactly these five sections:\n\n"
        "1. **Money Talk** — Finance and markets (use $ signs, be direct, hint at what it means for regular people)\n"
        "2. **World Lore** — Geopolitics and global affairs (smart but accessible, light sarcasm welcome)\n"
        "3. **Tech Tea** — Tech news (be sharp and opinionated, call out hype when you see it)\n"
        "4. **Mind & Behavior** — Philosophy and human psychology insights (thoughtful, curious tone)\n"
        "5. **Lead & Grow** — Leadership and organizational psychology (practical, insightful tone)\n"
        "6. **Speed Round** — 5–7 one-liner quick takes on anything notable from all categories\n\n"
        "Rules:\n"
        "- Write in second person ('you') where it makes sense\n"
        "- Keep each section to 3–5 punchy bullet points (except Speed Round)\n"
        "- No filler phrases like 'In today's fast-paced world...'\n"
        "- Be specific — reference actual companies, numbers, names from the articles\n"
        "- End each section with one spicy take or prediction\n\n"
        "HERE ARE TODAY'S ARTICLES:\n\n",
    ]

    for category, label in sections.items():
        prompt_parts.append(f"--- {label} ---\n")
        for article in articles.get(category, []):
            prompt_parts.append(f"• {article}\n")
        prompt_parts.append("\n")

    prompt_parts.append(
        "\nNow write the digest. Use markdown-style bold (**text**) for emphasis. "
        "Do not include any preamble — start directly with the first section header."
    )
    return "".join(prompt_parts)


def call_gemini(prompt: str) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text


def markdown_to_html(text: str) -> str:
    """Convert basic markdown (bold, bullets) to HTML."""
    import re
    lines = text.split("\n")
    html_lines = []
    in_ul = False

    for line in lines:
        stripped = line.strip()

        # Bold
        stripped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)

        if stripped.startswith("• ") or stripped.startswith("- "):
            content = stripped[2:]
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"  <li>{content}</li>")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if stripped:
                html_lines.append(f"<p>{stripped}</p>")
            else:
                html_lines.append("")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


SECTION_CONFIG = {
    "Money Talk": {
        "emoji": "💰",
        "color": "#10b981",
        "bg": "#064e3b",
        "border": "#059669",
    },
    "World Lore": {
        "emoji": "🌍",
        "color": "#60a5fa",
        "bg": "#1e3a5f",
        "border": "#3b82f6",
    },
    "Tech Tea": {
        "emoji": "⚡",
        "color": "#a78bfa",
        "bg": "#2d1b69",
        "border": "#7c3aed",
    },
    "Mind & Behavior": {
        "emoji": "🎨",
        "color": "#fb923c",
        "bg": "#431407",
        "border": "#ea580c",
    },
    "Speed Round": {
        "emoji": "🔥",
        "color": "#fbbf24",
        "bg": "#451a03",
        "border": "#d97706",
    },
}


def build_html_email(digest_text: str, date_str: str) -> str:
    import re

    section_names = list(SECTION_CONFIG.keys())
    # Split digest into sections
    pattern = r"(?=(?:" + "|".join(re.escape(s) for s in section_names) + r"))"
    raw_sections = re.split(pattern, digest_text, flags=re.IGNORECASE)

    sections_html = []
    for chunk in raw_sections:
        chunk = chunk.strip()
        if not chunk:
            continue
        matched_name = None
        for name in section_names:
            if chunk.lower().startswith(name.lower()):
                matched_name = name
                break
        if matched_name:
            cfg = SECTION_CONFIG[matched_name]
            body = chunk[len(matched_name):].lstrip(":— \n")
            body_html = markdown_to_html(body)
            sections_html.append(f"""
        <div style="margin: 24px 0; border-radius: 12px; overflow: hidden;
                    border: 1px solid {cfg['border']}; background: {cfg['bg']};">
          <div style="padding: 14px 20px; background: {cfg['border']}20;">
            <h2 style="margin: 0; font-size: 18px; font-weight: 700;
                       color: {cfg['color']}; letter-spacing: 0.5px;">
              {cfg['emoji']}&nbsp; {matched_name}
            </h2>
          </div>
          <div style="padding: 16px 20px; color: #e2e8f0; font-size: 15px;
                      line-height: 1.7;">
            {body_html}
          </div>
        </div>""")
        else:
            # Unmatched text — render as plain paragraph
            sections_html.append(
                f'<p style="color:#94a3b8;font-size:14px;">{chunk}</p>'
            )

    sections_joined = "\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily Digest — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0"
               style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
                       border-radius:16px 16px 0 0;padding:36px 32px 28px;
                       border-bottom:2px solid #334155;">
              <p style="margin:0 0 6px;font-size:12px;font-weight:600;
                        letter-spacing:2px;color:#64748b;text-transform:uppercase;">
                Your Daily Briefing
              </p>
              <h1 style="margin:0;font-size:32px;font-weight:800;
                         background:linear-gradient(90deg,#f8fafc,#94a3b8);
                         -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                         background-clip:text;">
                The Digest
              </h1>
              <p style="margin:10px 0 0;font-size:14px;color:#475569;">
               {date_str} &nbsp;·&nbsp; Finance · Geopolitics · Tech · Mind & Behavior · Lead & Grow
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:#1e293b;padding:24px 28px 8px;
                       border-left:1px solid #1e293b;border-right:1px solid #1e293b;">
              {sections_joined}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0f172a;border-radius:0 0 16px 16px;
                       padding:20px 28px;border-top:1px solid #1e293b;
                       text-align:center;">
              <p style="margin:0;font-size:12px;color:#475569;">
                Generated by your AI news friend &nbsp;·&nbsp; {date_str}
              </p>
              <p style="margin:6px 0 0;font-size:11px;color:#334155;">
                Powered by Google Gemini · RSS · Python
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(html_body: str, date_str: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"The Digest — {date_str}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL

    plain_fallback = "Your daily digest is ready. Open this email in an HTML-capable client to read it."
    msg.attach(MIMEText(plain_fallback, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())


def main():
    date_str = datetime.now().strftime("%B %d, %Y")
    print(f"[digest] Starting — {date_str}")

    print("[digest] Fetching RSS feeds...")
    articles = fetch_articles(FEEDS)
    total = sum(len(v) for v in articles.values())
    print(f"[digest] Fetched {total} articles across {len(articles)} categories")

    print("[digest] Calling Gemini...")
    prompt = build_gemini_prompt(articles)
    digest_text = call_gemini(prompt)
    print("[digest] Digest generated")

    print("[digest] Building HTML email...")
    html = build_html_email(digest_text, date_str)

    print("[digest] Sending email...")
    send_email(html, date_str)
    print(f"[digest] Done! Email sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
