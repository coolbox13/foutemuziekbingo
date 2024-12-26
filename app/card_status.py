def summarize_card_statuses(cards, played_tracks):
    """Summarize the status of bingo cards, indicating rows, columns, or cards with results."""
    card_summaries = {}
    for card_id, card in cards.items():
        matches = card.get("matches", [])
        status = "No results"

        if len(matches) >= 25:  # Full card
            status = "Full card bingo"
        elif any(
            all(pos in matches for pos in range(row * 5, row * 5 + 5))
            for row in range(5)
        ):
            status = "Row bingo"
        elif any(
            all(pos in matches for pos in range(col, col + 21, 5)) for col in range(5)
        ):
            status = "Column bingo"

        card_summaries[card_id] = status

    return card_summaries


def validate_card(card_id, cards, played_tracks):
    """Validate a card against played tracks to check for bingo."""
    if card_id not in cards:
        return {"error": "Invalid card ID"}

    card = cards[card_id]
    matches = card.get("matches", [])
    if not matches:
        return {"card_id": card_id, "status": "No matches"}

    has_bingo = False
    if len(matches) >= 25:
        has_bingo = True
    elif any(
        all(pos in matches for pos in range(row * 5, row * 5 + 5)) for row in range(5)
    ):
        has_bingo = True
    elif any(
        all(pos in matches for pos in range(col, col + 21, 5)) for col in range(5)
    ):
        has_bingo = True

    return {
        "card_id": card_id,
        "matches": matches,
        "has_bingo": has_bingo,
        "status": "BINGO!" if has_bingo else "No bingo",
    }
