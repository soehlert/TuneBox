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

for idx, artist_name in enumerate(ARTIST_NAMES):
    artist_id = 1001 + idx
    MOCK_ARTISTS.append({"artist_id": artist_id, "name": artist_name})

    albums = ALBUM_NAMES[artist_name]
    MOCK_ALBUMS[artist_id] = []

    for a_idx, album_title in enumerate(albums):
        album_id = 2000 + (idx * 6) + (a_idx + 1)
        MOCK_ALBUMS[artist_id].append(
            {
                "album_id": album_id,
                "artist": artist_name,
                "title": album_title,
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
