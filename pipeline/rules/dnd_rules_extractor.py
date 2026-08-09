

def extract_pdf_text(path: str, page_from: int = 1, page_to: int | None = None) -> tuple[str, int, int]:
    text = ""
    used_from = page_from
    used_to = page_from
    # Try PyPDF2
    try:
        import PyPDF2
        with open(path, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            n = len(pdf.pages)
            start = max(1, page_from)
            end = min(n, page_to or n)
            used_from, used_to = start, end
            for i in range(start-1, end):
                try:
                    page = pdf.pages[i]
                    t = page.extract_text() or ""
                    text += t + "\n"
                except Exception:
                    continue
        if text.strip():
            return text, used_from, used_to
    except Exception:
        pass
    # Fallback to pdfminer.six if present
    try:
        from pdfminer.high_level import extract_text as pm_extract_text
        text = pm_extract_text(path)
        return text, page_from, page_to or page_from
    except Exception:
        return "", page_from, page_to or page_from

def extract_html_text(path: str) -> str:
    from html.parser import HTMLParser
    class Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.data = []
        def handle_data(self, d):
            self.data.append(d)
    s = Stripper()
    with open(path, encoding='utf-8', errors='ignore') as f:
        html = f.read()
    s.feed(html)
    return '\n'.join(s.data)
