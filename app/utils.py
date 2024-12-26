def generate_bingo_cards(tracks, num_cards):
    """Generate Bingo cards with tracks."""
    cards = []
    for _ in range(num_cards):
        cards.append(
            {
                "tracks": tracks[:25],  # Example logic: take the first 25 tracks
                "bingo_status": "Not checked",
            }
        )
    return cards


def check_bingo_status(card, played_tracks):
    """Check if a bingo card has a bingo based on played tracks."""
    for row in card["rows"]:
        if all(track in played_tracks for track in row):
            return True
    return False
