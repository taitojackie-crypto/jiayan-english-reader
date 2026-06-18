import io
import re
import uuid
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import fitz
except Exception:
    fitz = None

try:
    import docx
except Exception:
    docx = None


class MaterialLoader:
    SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    SUPPORTED_DOC = {".pdf", ".docx", ".txt", ".md"}

    def __init__(self, user_agent: str = "JiayanEnglishReader/1.0"):
        self.headers = {"User-Agent": user_agent}

    def load(self, source: Union[str, Path, bytes], source_type: str = "auto") -> str:
        source_type = self._detect_type(source, source_type)

        if source_type == "text":
            return self._from_text(source)
        if source_type == "image":
            return self._from_image(source)
        if source_type == "pdf":
            return self._from_pdf(source)
        if source_type == "docx":
            return self._from_docx(source)
        if source_type == "url":
            return self._from_url(source)

        raise ValueError(f"Unsupported source type: {source_type}")

    def _detect_type(self, source, source_type: str) -> str:
        if source_type != "auto":
            return source_type

        if isinstance(source, str):
            if source.startswith("http://") or source.startswith("https://"):
                return "url"
            return "text"

        if isinstance(source, (str, Path)):
            ext = Path(source).suffix.lower()
            if ext in self.SUPPORTED_IMAGE:
                return "image"
            if ext == ".pdf":
                return "pdf"
            if ext == ".docx":
                return "docx"
            if ext in {".txt", ".md"}:
                return "text"

        raise ValueError("Cannot auto-detect source type")

    def _read_bytes(self, source: Union[str, Path, bytes]) -> bytes:
        if isinstance(source, bytes):
            return source
        with open(source, "rb") as f:
            return f.read()

    def _from_text(self, source: Union[str, bytes, Path]) -> str:
        if isinstance(source, str):
            return source.strip()
        data = self._read_bytes(source)
        for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                return data.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace").strip()

    def _from_image(self, source: Union[str, Path, bytes]) -> str:
        from modules.reading_session import LocalClaudeClient

        client = LocalClaudeClient()

        if isinstance(source, bytes):
            # Claude CLI needs a file path within the workspace. Save bytes to a temp file.
            temp_dir = Path(__file__).parent.parent / "data" / "uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / f"ocr_temp_{uuid.uuid4().hex}.png"
            temp_path.write_bytes(source)
            try:
                return client.ocr_image(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)

        return client.ocr_image(source)

    def _from_pdf(self, source: Union[str, Path, bytes]) -> str:
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is not installed.")

        data = self._read_bytes(source)
        doc = fitz.open(stream=data, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        return "\n\n".join(parts).strip()

    def _from_docx(self, source: Union[str, Path, bytes]) -> str:
        if docx is None:
            raise RuntimeError("python-docx is not installed.")

        data = self._read_bytes(source)
        document = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs).strip()

    def _from_url(self, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http"):
            raise ValueError("URL must start with http:// or https://")

        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        text = "\n\n".join(paragraphs)

        if not text and soup.get_text(strip=True):
            text = soup.get_text(separator="\n\n", strip=True)

        return self._clean_text(text)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
