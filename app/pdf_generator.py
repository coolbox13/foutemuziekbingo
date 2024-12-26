from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    PageBreak,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO


class BingoCardPDF:
    def __init__(self, cards):
        self.cards = cards
        self.buffer = BytesIO()
        self.page_width, self.page_height = landscape(A4)
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30,
        )
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            "TitleStyle",
            parent=self.styles["Heading1"],
            fontSize=36,
            alignment=TA_CENTER,
            spaceAfter=30,
            spaceBefore=10,
        )
        self.artist_style = ParagraphStyle(
            "ArtistStyle",
            parent=self.styles["Normal"],
            fontSize=11,
            leading=13,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        )
        self.song_style = ParagraphStyle(
            "SongStyle",
            parent=self.styles["Normal"],
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            wordWrap="LTR",
        )

    def create_card_table(self, card_id, card_data):
        header_style = ParagraphStyle(
            "HeaderStyle",
            parent=self.styles["Heading1"],
            fontSize=36,
            alignment=TA_CENTER,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )
        data = [[Paragraph(letter, header_style) for letter in "BINGO"]]
        matches = card_data.get("matches", [])

        col_width = (self.page_width - 60) / 5
        content_row_height = (self.page_height - 200) / 6
        header_height = content_row_height * 1.2

        for row in range(5):
            card_row = []
            for col in range(5):
                idx = row * 5 + col
                track = card_data["tracks"][idx]
                artist = Paragraph(track["artist"], self.artist_style)
                title = Paragraph(track["name"], self.song_style)
                card_row.append([artist, title])
            data.append(card_row)

        table = Table(
            data,
            colWidths=[col_width] * 5,
            rowHeights=[header_height] + [content_row_height] * 5,
        )

        # Update table style with matched cells coloring
        table_style = TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (4, 0), colors.grey),
                # Color matched cells
                *[
                    (
                        "BACKGROUND",
                        (pos % 5, pos // 5 + 1),
                        (pos % 5, pos // 5 + 1),
                        colors.lightgreen,
                    )
                    for pos in matches
                ],
            ]
        )

        table.setStyle(table_style)
        return table

    def generate(self):
        elements = []
        for card_id, card_data in self.cards.items():
            elements.extend(
                [
                    Paragraph("Foute Muziek Bingo", self.title_style),
                    self.create_card_table(card_id, card_data),
                    Paragraph(f"Card ID: {card_id}", self.title_style),
                    PageBreak(),
                ]
            )
        self.doc.build(elements)
        return self.buffer.getvalue()


def generate_pdf(cards):
    pdf_generator = BingoCardPDF(cards)
    return pdf_generator.generate()
