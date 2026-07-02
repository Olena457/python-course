from pypdf import PdfReader

def load_resume_text(path: str) -> str:
    """Завантажує PDF-файл та повертає весь текст суцільним рядком."""
    reader = PdfReader(path)
    # Збираємо текст з усіх сторінок і склеюємо його через перенесення рядка.
    # ЧОМУ САМЕ ТАК: pypdf може губити пробіли при склеюванні колонок, 
    # але для LLM це не критично, головне — зберегти ключові слова.
    return "\n".join(page.extract_text() or "" for page in reader.pages)
