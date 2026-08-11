"""Mock dataset generator for TuneBox offline library simulation."""

ARTIST_NAMES = [
    "Daft Punk",
    "Pink Floyd",
    "The Beatles",
    "Queen",
    "Michael Jackson",
    "Led Zeppelin",
    "Fleetwood Mac",
    "Radiohead",
    "Nirvana",
    "David Bowie",
]

ALBUM_NAMES = {
    "Daft Punk": [
        "Homework",
        "Discovery",
        "Human After All",
        "Random Access Memories",
        "Alive 1997",
        "Alive 2007",
    ],
    "Pink Floyd": [
        "The Dark Side of the Moon",
        "Wish You Were Here",
        "The Wall",
        "Animals",
        "Meddle",
        "A Momentary Lapse of Reason",
    ],
    "The Beatles": [
        "Abbey Road",
        "Revolver",
        "Sgt. Pepper's Lonely Hearts Club Band",
        "Rubber Soul",
        "White Album",
        "Help!",
    ],
    "Queen": [
        "A Night at the Opera",
        "News of the World",
        "Sheer Heart Attack",
        "The Game",
        "Jazz",
        "A Day at the Races",
    ],
    "Michael Jackson": [
        "Thriller",
        "Bad",
        "Off the Wall",
        "Dangerous",
        "HIStory",
        "Invincible",
    ],
    "Led Zeppelin": [
        "Led Zeppelin I",
        "Led Zeppelin II",
        "Led Zeppelin III",
        "Led Zeppelin IV",
        "Houses of the Holy",
        "Physical Graffiti",
    ],
    "Fleetwood Mac": [
        "Rumours",
        "Tusk",
        "Mac",
        "Mirage",
        "Tango in the Night",
        "Say You Will",
    ],
    "Radiohead": [
        "OK Computer",
        "Kid A",
        "In Rainbows",
        "The Bends",
        "A Moon Shaped Pool",
        "Hail to the Thief",
    ],
    "Nirvana": [
        "Nevermind",
        "In Utero",
        "Bleach",
        "MTV Unplugged",
        "Incesticide",
        "Muddy Banks of the Wishkah",
    ],
    "David Bowie": [
        "The Rise and Fall of Ziggy Stardust",
        "Hunky Dory",
        "Heroes",
        "Low",
        "Let's Dance",
        "Space Oddity",
    ],
}

MOCK_ARTISTS = []
MOCK_ALBUMS = {}
MOCK_TRACKS = {}

GENRES = ["Electronic", "Rock", "Pop", "Classic Rock", "Alternative", "Soul", "Disco"]

for idx, artist_name in enumerate(ARTIST_NAMES):
    artist_id = 1001 + idx
    MOCK_ARTISTS.append({"artist_id": artist_id, "name": artist_name, "play_count": (len(ARTIST_NAMES) - idx) * 12})

    albums = ALBUM_NAMES[artist_name]
    MOCK_ALBUMS[artist_id] = []

    for a_idx, album_title in enumerate(albums):
        album_id = 2000 + (idx * 6) + (a_idx + 1)
        year = 1970 + ((idx * 5 + a_idx * 4) % 54)
        genre = GENRES[(idx + a_idx) % len(GENRES)]
        MOCK_ALBUMS[artist_id].append(
            {
                "album_id": album_id,
                "artist": artist_name,
                "artist_id": artist_id,
                "title": album_title,
                "year": year,
                "genre": genre,
                "play_count": (len(albums) - a_idx) * 8 + (idx * 3),
                "thumb": f"/api/music/album-art/{album_id}",
            }
        )

        MOCK_TRACKS[album_id] = []
        for t_idx in range(15):
            track_id = 3000 + ((idx * 6 + a_idx) * 15) + (t_idx + 1)
            MOCK_TRACKS[album_id].append(
                {
                    "track_id": track_id,
                    "artist": artist_name,
                    "album": album_title,
                    "title": f"{album_title} - Track {t_idx + 1}",
                    "duration": 180 + (t_idx * 15),  # 3 mins + offset
                    "url": f"/api/music/stream/{track_id}",
                }
            )


def seed_mock_library_db(db_path: str | None = None):
    """Seed the SQLite library database with mock server, artist, album, and track data."""
    from backend.config import settings
    from backend.services.library import get_db_connection, upsert_server, upsert_artist, upsert_album, upsert_track

    if not db_path:
        # Never seed mock data into real library.db
        return

    mock_server_id = "mock-server-001"
    upsert_server(mock_server_id, "Mock Plex Server", "http://mock-server:32400", is_primary=True, enabled=True, db_path=db_path)

    for a in MOCK_ARTISTS:
        a_db_id = upsert_artist(
            name=a["name"],
            guid=f"mock://artist/{a['artist_id']}",
            thumb=f"/api/music/artist-image/{a['artist_id']}",
            play_count=a["play_count"],
            server_id=mock_server_id,
            server_artist_id=str(19586 + int(a["artist_id"])),
            db_path=db_path,
        )

        albums = MOCK_ALBUMS.get(a["artist_id"], [])
        for alb in albums:
            alb_db_id = upsert_album(
                title=alb["title"],
                artist_name=alb["artist"],
                artist_id=a_db_id,
                year=alb["year"],
                genre=alb["genre"],
                thumb=alb["thumb"],
                play_count=alb["play_count"],
                guid=f"mock://album/{alb['album_id']}",
                server_id=mock_server_id,
                server_album_id=str(28401 + int(alb["album_id"])),
                db_path=db_path,
            )

            tracks = MOCK_TRACKS.get(alb["album_id"], [])
            for trk in tracks:
                upsert_track(
                    album_id=alb_db_id,
                    server_id=mock_server_id,
                    server_track_id=str(34910 + int(trk["track_id"])),
                    artist_name=trk["artist"],
                    album_title=trk["album"],
                    title=trk["title"],
                    duration=trk["duration"],
                    url=trk["url"],
                    thumb=alb["thumb"],
                    play_count=0,
                    db_path=db_path,
                )


# Automatically seed SQLite library in mock environment
try:
    seed_mock_library_db()
except Exception:
    pass
