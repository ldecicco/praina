import os
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.proposal import ProjectProposalSection
from app.models.proposal_image import ProposalImage

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))

_IMG_SRC_RE = re.compile(r'(<img\s[^>]*?)src="([^"]*?/proposal-images/([^/]+)/content[^"]*)"', re.IGNORECASE)

_CSS = """
@page {
  size: A4;
  margin: 2.5cm 2cm;
  @bottom-center { content: counter(page); font-size: 9pt; color: #666; }
}
body {
  font-family: "Times New Roman", Times, serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #222;
}
h1 { font-size: 22pt; margin-top: 0; margin-bottom: 0.5em; }
h2 { font-size: 16pt; margin-top: 1.2em; margin-bottom: 0.4em; page-break-after: avoid; }
h3 { font-size: 13pt; margin-top: 1em; margin-bottom: 0.3em; page-break-after: avoid; }
p { margin: 0.4em 0; orphans: 3; widows: 3; }
img { max-width: 100%; }
table { width: 100%; border-collapse: collapse; margin: 0.8em 0; font-size: 10pt; }
th, td { border: 1px solid #999; padding: 4px 8px; text-align: left; }
th { background: #f0f0f0; font-weight: bold; }
pre { background: #f5f5f5; padding: 8px; font-size: 9pt; white-space: pre-wrap; }
code { font-size: 9pt; }
section { page-break-before: always; }
section:first-of-type { page-break-before: avoid; }
"""


class ProposalExportService:
    def __init__(self, db: Session):
        self.db = db

    def generate_pdf(self, project_id) -> bytes:
        import markdown
        from weasyprint import HTML

        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("Project not found")

        sections = (
            self.db.query(ProjectProposalSection)
            .filter(ProjectProposalSection.project_id == project_id)
            .order_by(ProjectProposalSection.position)
            .all()
        )
        sections = [s for s in sections if s.content and s.content.strip()]
        if not sections:
            raise ValueError("No proposal sections with content to export")

        # Build image lookup: image_id -> absolute file path
        images = (
            self.db.query(ProposalImage)
            .filter(ProposalImage.project_id == project_id)
            .all()
        )
        image_path_map: dict[str, str] = {}
        for img in images:
            abs_path = (STORAGE_ROOT / img.storage_path).resolve()
            if abs_path.is_file():
                image_path_map[str(img.id)] = abs_path.as_uri()

        # Build HTML sections
        md_extensions = ["tables", "fenced_code"]
        html_sections: list[str] = []
        for section in sections:
            section_html = markdown.markdown(section.content, extensions=md_extensions)
            section_html = self._rewrite_images(section_html, image_path_map)
            html_sections.append(
                f"<section>\n<h2>{_escape_html(section.title)}</h2>\n{section_html}\n</section>"
            )

        title = f"{project.code} — Proposal" if project.code else project.title
        full_html = (
            "<!DOCTYPE html><html><head>"
            f"<meta charset='utf-8'><title>{_escape_html(title)}</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<h1>{_escape_html(title)}</h1>"
            + "\n".join(html_sections)
            + "</body></html>"
        )

        return HTML(string=full_html).write_pdf()

    def _rewrite_images(self, html: str, image_path_map: dict[str, str]) -> str:
        def _replace(match: re.Match) -> str:
            prefix = match.group(1)
            image_id = match.group(3)
            file_uri = image_path_map.get(image_id)
            if file_uri:
                return f'{prefix}src="{file_uri}"'
            return match.group(0)

        return _IMG_SRC_RE.sub(_replace, html)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
