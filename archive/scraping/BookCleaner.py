import os
import re
import json
import logging
from bs4 import BeautifulSoup

# Optional: sentence splitting
try:
    from nltk.tokenize import sent_tokenize
    nltk_available = True
except ImportError:
    nltk_available = False

# ---------------- Logging ----------------
logging.basicConfig(
    filename="BookCleaner.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------- Config ----------------
html_folder = r"D:\dnd5E\Books"
output_folder = r"D:\dnd5E\Cleaned_Books"
os.makedirs(output_folder, exist_ok=True)

skip_headings = ["contents", "preface", "introduction", "life of"]

chunk_size_words = 2000        # for splitting long texts
one_sentence_per_line = True   # if True, split sentences onto new lines
lowercase = True               # normalize case

# Output mode: "jsonl" or "txt"
output_format = "txt"

# ---------------- Helpers ----------------
def clean_text_block(text: str) -> str:
    """Apply regex cleaning & normalization to raw extracted text."""
    text = re.sub(r"\[.*?\]", "", text)                # remove footnotes/annotations
    text = re.sub(r"[^\x00-\x7F]+", " ", text)         # strip non-ASCII
    text = re.sub(r"[ \t]+", " ", text)                # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)             # collapse 3+ newlines
    if lowercase:
        text = text.lower()
    return text.strip()


def extract_metadata(soup) -> dict:
    """Grab metadata (if available) from Gutenberg HTML."""
    metadata = {}
    try:
        title = soup.find("meta", {"name": "dc.title"})
        author = soup.find("meta", {"name": "dc.creator"})
        lang = soup.find("meta", {"name": "dc.language"})
        metadata["title"] = title["content"] if title else "Unknown"
        metadata["author"] = author["content"] if author else "Unknown"
        metadata["language"] = lang["content"] if lang else "Unknown"
    except Exception as e:
        logging.warning(f"Metadata extraction failed: {e}")
    return metadata


def chunk_text(text: str, chunk_size: int = 2000):
    """Split long text into word-based chunks."""
    words = text.split()
    return [
        " ".join(words[i:i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]


# ---------------- Main Cleaning ----------------
jsonl_path = os.path.join(output_folder, "books_dataset.jsonl")
jsonl_file = open(jsonl_path, "w", encoding="utf-8") if output_format == "jsonl" else None

for file in os.listdir(html_folder):
    if not (file.endswith(".htm") or file.endswith(".html")):
        continue

    file_path = os.path.join(html_folder, file)
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "html.parser")
            raw_text = soup.get_text()

        # Extract text between START and END markers
        start = re.search(r"\*\*\* START OF.*\*\*\*", raw_text, re.IGNORECASE)
        end = re.search(r"\*\*\* END OF.*\*\*\*", raw_text, re.IGNORECASE)

        if not (start and end):
            logging.warning(f"Markers missing in {file}, keeping full text.")
            body_text = raw_text
        else:
            body_text = raw_text[start.end():end.start()]

        # Split into sections
        sections = re.split(r"\n\s*\n", body_text)
        clean_sections = []
        for sec in sections:
            if not sec.strip():
                continue
            heading_line = sec.strip().split("\n")[0].lower()
            if any(h in heading_line for h in skip_headings):
                continue
            clean_sections.append(sec.strip())

        clean_text = "\n\n".join(clean_sections)
        clean_text = clean_text_block(clean_text)

        # Sentence splitting (optional)
        if one_sentence_per_line and nltk_available:
            try:
                sentences = sent_tokenize(clean_text)
                clean_text = "\n".join(sentences)
            except Exception as e:
                logging.error(f"Sentence splitting failed for {file}: {e}")

        # Chunking
        chunks = chunk_text(clean_text, chunk_size_words)

        # Metadata
        metadata = extract_metadata(soup)
        base_name = os.path.splitext(file)[0]

        if output_format == "jsonl":
            for i, chunk in enumerate(chunks):
                out_data = {
                    "metadata": metadata,
                    "chunk_index": i,
                    "text": chunk
                }
                jsonl_file.write(json.dumps(out_data, ensure_ascii=False) + "\n")

        elif output_format == "txt":
            for i, chunk in enumerate(chunks):
                out_file = os.path.join(output_folder, f"{base_name}_chunk{i}.txt")
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(chunk)

        logging.info(f"Processed {file} into {len(chunks)} chunks.")

    except Exception as e:
        logging.error(f"Error processing {file}: {e}")

if jsonl_file:
    jsonl_file.close()
