import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button } from "@mui/material";
import axios from "axios";
import { FallbackImage } from "./FallbackImage";
import { getLocalUsername } from "../utils";

interface Album {
  album_id: number;
  title: string;
  artist?: string;
  artist_id?: number;
  year?: number;
  genre?: string;
  thumb?: string | null;
  server_id?: string;
}

interface Genre {
  genre: string;
  album_count: number;
}

interface Decade {
  decade: string;
  year_start: number;
  year_end: number;
  album_count: number;
}

export type ViewMode = "artists" | "albums" | "genres" | "decades";

interface BrowseTabsProps {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export const BrowseTabs: React.FC<BrowseTabsProps> = ({ currentMode, onModeChange }) => {
  const tabs: { id: ViewMode; label: string; icon: string }[] = [
    { id: "artists", label: "Artists", icon: "mic" },
    { id: "albums", label: "Albums", icon: "album" },
    { id: "genres", label: "Genres", icon: "music_note" },
    { id: "decades", label: "Decades", icon: "calendar_clock" },
  ];

  return (
    <div className="browse-tabs-container">
      {tabs.map((tab) => {
        const isActive = currentMode === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onModeChange(tab.id)}
            className={`browse-tab-btn ${isActive ? "active" : ""}`}
          >
            <span className="material-symbols-outlined">{tab.icon}</span>
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};

export const AlbumsGridView: React.FC<{ apiBase: string; selectedLetter?: string }> = ({ apiBase, selectedLetter }) => {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"alphabetical" | "plays">("alphabetical");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const navigate = useNavigate();

  useEffect(() => {
    axios
      .get(`${apiBase}/api/music/all-albums`)
      .then((res) => setAlbums(res.data))
      .catch((err) => console.error("Error fetching all albums:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const sortedAlbums = [...albums].sort((a, b) => {
    if (sortBy === "plays") {
      const playsA = (a as any).play_count || 0;
      const playsB = (b as any).play_count || 0;
      if (playsB !== playsA) return playsB - playsA;
      return a.title.localeCompare(b.title);
    }
    const cmp = a.title.localeCompare(b.title);
    return sortOrder === "asc" ? cmp : -cmp;
  });

  useEffect(() => {
    if (!selectedLetter || sortedAlbums.length === 0) return;

    const targetIndex = sortedAlbums.findIndex((alb) => {
      if (!alb.title) return false;
      const firstChar = alb.title.trim()[0];
      if (selectedLetter === "0-9") {
        return /^\d/.test(firstChar);
      }
      return firstChar.toUpperCase() === selectedLetter.toUpperCase();
    });

    if (targetIndex !== -1) {
      const targetAlb = sortedAlbums[targetIndex];
      setTimeout(() => {
        const el = document.getElementById(`album-${targetAlb.album_id}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 50);
    }
  }, [selectedLetter, sortedAlbums]);

  const handleAddAlbum = async (e: React.MouseEvent, albumId: number, serverId?: string) => {
    e.stopPropagation();
    try {
      await axios.post(
        `${apiBase}/api/music/albums/${albumId}/add-to-queue`,
        {},
        { params: { server_id: serverId, username: getLocalUsername() } }
      );
    } catch (err) {
      console.error("Failed to add album to queue:", err);
    }
  };

  if (loading) return <div style={{ color: "#aaa", padding: "40px", textAlign: "center" }}>Loading Albums...</div>;

  return (
    <div style={{ width: "100%" }}>
      <div className="view-sort-bar">
        <span className="view-count-badge">
          {albums.length} {albums.length === 1 ? "Album" : "Albums"}
        </span>
        <div className="view-sort-actions">
          <button
            className={`sort-pill-btn ${sortBy === "alphabetical" ? "active" : ""}`}
            onClick={() => {
              if (sortBy === "alphabetical") {
                setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
              } else {
                setSortBy("alphabetical");
                setSortOrder("asc");
              }
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>swap_vert</span>
            <span>{sortBy === "alphabetical" ? (sortOrder === "asc" ? "A-Z" : "Z-A") : "A-Z"}</span>
          </button>
          <button
            className={`sort-pill-btn ${sortBy === "plays" ? "active" : ""}`}
            onClick={() => {
              setSortBy((prev) => (prev === "plays" ? "alphabetical" : "plays"));
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>local_fire_department</span>
            <span>Most Played</span>
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px", width: "100%" }}>
        {sortedAlbums.map((alb) => (
        <Card
          key={alb.album_id}
          id={`album-${alb.album_id}`}
          onClick={() => navigate(`/albums/${alb.album_id}/tracks${alb.server_id ? `?server_id=${alb.server_id}` : ""}`)}
          style={{
            background: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "16px",
            padding: "12px",
            cursor: "pointer",
            transition: "transform 0.2s ease, border-color 0.2s ease",
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "rgba(0, 119, 182, 0.6)")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)")}
        >
          <FallbackImage
            src={`${apiBase}/api/music/album-art/${alb.album_id}${alb.server_id ? `?server_id=${alb.server_id}` : ""}`}
            alt={alb.title}
            type="album"
            style={{ width: "100%", aspectRatio: "1/1", borderRadius: "12px", objectFit: "cover" }}
          />
          <div>
            <Typography style={{ color: "#fff", fontWeight: 700, fontSize: "14px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {alb.title}
            </Typography>
            <Typography style={{ color: "rgba(255,255,255,0.6)", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {alb.artist || "Unknown Artist"} {alb.year ? `• ${alb.year}` : ""}
            </Typography>
          </div>
          <Button
            size="small"
            onClick={(e) => handleAddAlbum(e, alb.album_id, alb.server_id)}
            style={{
              marginTop: "auto",
              background: "rgba(255, 255, 255, 0.06)",
              color: "#fff",
              fontSize: "11px",
              fontWeight: 700,
              borderRadius: "12px",
              textTransform: "none",
              border: "1px solid rgba(255, 255, 255, 0.1)",
            }}
          >
            + Add Album
          </Button>
        </Card>
      ))}
      </div>
    </div>
  );
};

export const GenresGridView: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const [genres, setGenres] = useState<Genre[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<string | null>(null);
  const [genreAlbums, setGenreAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    axios
      .get(`${apiBase}/api/music/genres`)
      .then((res) => setGenres(res.data))
      .catch((err) => console.error("Error fetching genres:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const handleSelectGenre = (genreName: string) => {
    setSelectedGenre(genreName);
    setLoading(true);
    axios
      .get(`${apiBase}/api/music/genres/${encodeURIComponent(genreName)}/albums`)
      .then((res) => setGenreAlbums(res.data))
      .catch((err) => console.error("Error fetching genre albums:", err))
      .finally(() => setLoading(false));
  };

  if (loading && !selectedGenre) return <div style={{ color: "#aaa", padding: "40px", textAlign: "center" }}>Loading Genres...</div>;

  if (selectedGenre) {
    return (
      <div>
        <button
          onClick={() => setSelectedGenre(null)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            background: "rgba(255, 255, 255, 0.05)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            color: "#fff",
            padding: "8px 16px",
            borderRadius: "20px",
            fontSize: "13px",
            fontWeight: 700,
            cursor: "pointer",
            marginBottom: "20px",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>arrow_back</span>
          Back to Genres
        </button>
        <Typography variant="h5" style={{ color: "#fff", fontWeight: 800, marginBottom: "20px" }}>
          🎷 {selectedGenre} ({genreAlbums.length} Albums)
        </Typography>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px" }}>
          {genreAlbums.map((alb) => (
            <Card
              key={alb.album_id}
              onClick={() => navigate(`/albums/${alb.album_id}/tracks`)}
              style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "16px", padding: "12px", cursor: "pointer" }}
            >
              <FallbackImage src={`${apiBase}/api/music/album-art/${alb.album_id}`} alt={alb.title} type="album" style={{ width: "100%", aspectRatio: "1/1", borderRadius: "12px" }} />
              <Typography style={{ color: "#fff", fontWeight: 700, fontSize: "14px", marginTop: "8px" }}>{alb.title}</Typography>
              <Typography style={{ color: "rgba(255,255,255,0.6)", fontSize: "12px" }}>{alb.artist}</Typography>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "20px" }}>
      {genres.map((g) => (
        <Card
          key={g.genre}
          onClick={() => handleSelectGenre(g.genre)}
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "20px",
            padding: "24px",
            cursor: "pointer",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            gap: "16px",
            transition: "transform 0.2s ease, border-color 0.2s ease",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#bf095e")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)")}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="material-symbols-outlined" style={{ fontSize: "32px", color: "#bf095e" }}>music_note</span>
            <span style={{ background: "rgba(191, 9, 94, 0.2)", color: "#ff4d94", fontSize: "12px", fontWeight: 800, padding: "4px 10px", borderRadius: "12px" }}>
              {g.album_count} Albums
            </span>
          </div>
          <Typography variant="h6" style={{ color: "#fff", fontWeight: 800 }}>
            {g.genre}
          </Typography>
        </Card>
      ))}
    </div>
  );
};

export const DecadesGridView: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const [decades, setDecades] = useState<Decade[]>([]);
  const [selectedDecade, setSelectedDecade] = useState<Decade | null>(null);
  const [decadeAlbums, setDecadeAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    axios
      .get(`${apiBase}/api/music/decades`)
      .then((res) => setDecades(res.data))
      .catch((err) => console.error("Error fetching decades:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const handleSelectDecade = (d: Decade) => {
    setSelectedDecade(d);
    setLoading(true);
    axios
      .get(`${apiBase}/api/music/decades/${d.year_start}/${d.year_end}/albums`)
      .then((res) => setDecadeAlbums(res.data))
      .catch((err) => console.error("Error fetching decade albums:", err))
      .finally(() => setLoading(false));
  };

  if (loading && !selectedDecade) return <div style={{ color: "#aaa", padding: "40px", textAlign: "center" }}>Loading Decades...</div>;

  if (selectedDecade) {
    return (
      <div>
        <button
          onClick={() => setSelectedDecade(null)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            background: "rgba(255, 255, 255, 0.05)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            color: "#fff",
            padding: "8px 16px",
            borderRadius: "20px",
            fontSize: "13px",
            fontWeight: 700,
            cursor: "pointer",
            marginBottom: "20px",
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>arrow_back</span>
          Back to Decades
        </button>
        <Typography variant="h5" style={{ color: "#fff", fontWeight: 800, marginBottom: "20px" }}>
          📅 {selectedDecade.decade} ({decadeAlbums.length} Albums)
        </Typography>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px" }}>
          {decadeAlbums.map((alb) => (
            <Card
              key={alb.album_id}
              onClick={() => navigate(`/albums/${alb.album_id}/tracks`)}
              style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "16px", padding: "12px", cursor: "pointer" }}
            >
              <FallbackImage src={`${apiBase}/api/music/album-art/${alb.album_id}`} alt={alb.title} type="album" style={{ width: "100%", aspectRatio: "1/1", borderRadius: "12px" }} />
              <Typography style={{ color: "#fff", fontWeight: 700, fontSize: "14px", marginTop: "8px" }}>{alb.title}</Typography>
              <Typography style={{ color: "rgba(255,255,255,0.6)", fontSize: "12px" }}>{alb.artist} {alb.year ? `(${alb.year})` : ""}</Typography>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "20px" }}>
      {decades.map((d) => (
        <Card
          key={d.decade}
          onClick={() => handleSelectDecade(d)}
          style={{
            background: "linear-gradient(135deg, rgba(0,119,182,0.15) 0%, rgba(191,9,94,0.1) 100%)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "20px",
            padding: "24px",
            cursor: "pointer",
            display: "flex",
            flexDirection: "column",
            gap: "16px",
            transition: "transform 0.2s ease, border-color 0.2s ease",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#0077b6")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)")}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="material-symbols-outlined" style={{ fontSize: "32px", color: "#0077b6" }}>calendar_clock</span>
            <span style={{ background: "rgba(0, 119, 182, 0.2)", color: "#38b6ff", fontSize: "12px", fontWeight: 800, padding: "4px 10px", borderRadius: "12px" }}>
              {d.album_count} Albums
            </span>
          </div>
          <Typography variant="h5" style={{ color: "#fff", fontWeight: 800 }}>
            {d.decade}
          </Typography>
        </Card>
      ))}
    </div>
  );
};
