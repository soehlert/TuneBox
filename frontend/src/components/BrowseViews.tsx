import React, { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button } from "@mui/material";
import axios from "axios";
import { FallbackImage } from "./FallbackImage";
import { getLocalUsername, getSortKey, triggerQueueToast } from "../utils";

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
  top_album_id?: number | null;
}



export const GenresGridView: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const [genres, setGenres] = useState<Genre[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<string | null>(null);
  const [genreAlbums, setGenreAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"alphabetical" | "albums">("albums");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
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

  const sortedGenres = useMemo(() => {
    return [...genres].sort((a, b) => {
      if (sortBy === "alphabetical") {
        return sortOrder === "asc"
          ? a.genre.localeCompare(b.genre)
          : b.genre.localeCompare(a.genre);
      }
      const diff = sortOrder === "desc"
        ? b.album_count - a.album_count
        : a.album_count - b.album_count;
      return diff || a.genre.localeCompare(b.genre);
    });
  }, [genres, sortBy, sortOrder]);

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
          {selectedGenre} ({genreAlbums.length} {genreAlbums.length === 1 ? "Album" : "Albums"})
        </Typography>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px" }}>
          {genreAlbums.map((alb) => (
            <Card
              key={alb.album_id}
              onClick={() => navigate(`/albums/${alb.album_id}/tracks`)}
              style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "16px", padding: "12px", cursor: "pointer" }}
            >
              <FallbackImage src={`${apiBase}/api/music/album-art/${alb.album_id}`} alt={alb.title} type="album" loading="lazy" style={{ width: "100%", aspectRatio: "1/1", borderRadius: "12px" }} />
              <Typography style={{ color: "#fff", fontWeight: 700, fontSize: "14px", marginTop: "8px" }}>{alb.title}</Typography>
              <Typography style={{ color: "rgba(255,255,255,0.6)", fontSize: "12px" }}>{alb.artist}</Typography>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Header bar with count and dual sort pills */}
      <div className="view-sort-bar">
        <span className="view-count-badge">
          {genres.length} {genres.length === 1 ? "Genre" : "Genres"}
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
            className={`sort-pill-btn ${sortBy === "albums" ? "active" : ""}`}
            onClick={() => {
              if (sortBy === "albums") {
                setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
              } else {
                setSortBy("albums");
                setSortOrder("desc");
              }
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>library_music</span>
            <span>{sortBy === "albums" ? (sortOrder === "desc" ? "Most Albums" : "Least Albums") : "Most Albums"}</span>
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "20px" }}>
        {sortedGenres.map((g) => (
          <Card
            key={g.genre}
            onClick={() => handleSelectGenre(g.genre)}
            style={{
              background: "linear-gradient(135deg, rgba(0,119,182,0.15) 0%, rgba(191,9,94,0.1) 100%)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              borderRadius: "20px",
              padding: "16px",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              gap: "12px",
              transition: "transform 0.2s ease, border-color 0.2s ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#0077b6")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)")}
          >
            {g.top_album_id ? (
              <div style={{ width: "100%", height: "140px", borderRadius: "14px", overflow: "hidden", position: "relative" }}>
                <FallbackImage
                  src={`${apiBase}/api/music/album-art/${g.top_album_id}`}
                  alt={g.genre}
                  type="album"
                  loading="lazy"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, transparent 40%, rgba(0, 0, 0, 0.8) 100%)" }} />
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span className="material-symbols-outlined" style={{ fontSize: "32px", color: "#0077b6" }}>music_note</span>
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
              <Typography variant="h6" style={{ color: "#fff", fontWeight: 800, fontSize: "16px" }}>
                {g.genre}
              </Typography>
              <span style={{ background: "rgba(0, 119, 182, 0.2)", color: "#38b6ff", fontSize: "12px", fontWeight: 800, padding: "4px 10px", borderRadius: "12px", whiteSpace: "nowrap" }}>
                {g.album_count} {g.album_count === 1 ? "Album" : "Albums"}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};

interface Decade {
  decade: string;
  year_start: number;
  year_end: number;
  album_count: number;
  top_album_id?: number | null;
}

export type ViewMode = "recently_added" | "top_played" | "artists" | "albums" | "genres" | "decades";

interface BrowseTabsProps {
  currentMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export const BrowseTabs: React.FC<BrowseTabsProps> = ({ currentMode, onModeChange }) => {
  const tabs: { id: ViewMode; label: string; icon: string }[] = [
    { id: "artists", label: "Artists", icon: "mic" },
    { id: "albums", label: "Albums", icon: "album" },
    { id: "recently_added", label: "Recently Added", icon: "auto_awesome" },
    { id: "genres", label: "Genres", icon: "music_note" },
    { id: "decades", label: "Decades", icon: "calendar_clock" },
    { id: "top_played", label: "Top Played", icon: "leaderboard" },
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

interface Album {
  album_id: number;
  title: string;
  artist?: string;
  artist_id?: number;
  year?: number;
  genre?: string;
  thumb?: string | null;
  play_count?: number;
}

export const AlbumsGridView: React.FC<{
  apiBase: string;
  selectedLetter?: string;
  scrollTargetLetter?: { letter: string; timestamp: number } | null;
  onSelectLetter?: (letter: string) => void;
}> = ({ apiBase, selectedLetter, scrollTargetLetter, onSelectLetter }) => {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"alphabetical" | "plays">("alphabetical");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const navigate = useNavigate();

  const fetchAlbums = useCallback(() => {
    axios
      .get(`${apiBase}/api/music/all-albums`)
      .then((res) => setAlbums(res.data))
      .catch((err) => console.error("Error fetching all albums:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  useEffect(() => {
    fetchAlbums();
    const handleRefresh = () => fetchAlbums();
    window.addEventListener("tunebox_refresh_albums", handleRefresh);
    return () => window.removeEventListener("tunebox_refresh_albums", handleRefresh);
  }, [fetchAlbums]);

  const sortedAlbums = useMemo(() => {
    return [...albums].sort((a, b) => {
      const keyA = getSortKey(a.title);
      const keyB = getSortKey(b.title);
      if (sortBy === "plays") {
        const playsA = (a as any).play_count || 0;
        const playsB = (b as any).play_count || 0;
        if (playsB !== playsA) {
          return sortOrder === "desc" ? playsB - playsA : playsA - playsB;
        }
        return keyA.localeCompare(keyB);
      }
      const cmp = keyA.localeCompare(keyB);
      return sortOrder === "asc" ? cmp : -cmp;
    });
  }, [albums, sortBy, sortOrder]);

  const lastProcessedTargetRef = useRef<number | null>(null);

  // Fast-scroll to target album ONLY when a letter button on the rail is clicked
  useEffect(() => {
    if (!scrollTargetLetter || !scrollTargetLetter.letter || sortedAlbums.length === 0) return;
    if (lastProcessedTargetRef.current === scrollTargetLetter.timestamp) return;
    lastProcessedTargetRef.current = scrollTargetLetter.timestamp;

    const targetChar = scrollTargetLetter.letter;
    const targetIndex = sortedAlbums.findIndex((alb) => {
      if (!alb.title) return false;
      const sortKey = getSortKey(alb.title);
      const firstChar = sortKey[0] || "";
      if (targetChar === "0-9") {
        return !/^[A-Z]/i.test(firstChar);
      }
      return firstChar.toUpperCase() === targetChar.toUpperCase();
    });

    if (targetIndex !== -1) {
      const targetAlb = sortedAlbums[targetIndex];
      const attemptScroll = () => {
        const el = document.getElementById(`album-${targetAlb.album_id}`);
        const mainContent = document.querySelector(".main-content");
        if (el && mainContent) {
          const sortBar = mainContent.querySelector(".view-sort-bar");
          const headerOffset = sortBar ? sortBar.getBoundingClientRect().height : 0;
          const containerRect = mainContent.getBoundingClientRect();
          const elRect = el.getBoundingClientRect();
          const targetScrollTop = mainContent.scrollTop + (elRect.top - containerRect.top) - headerOffset;
          mainContent.scrollTo({
            top: Math.max(0, targetScrollTop),
            behavior: "smooth",
          });
          return true;
        }
        return false;
      };

      if (!attemptScroll()) {
        const timer1 = setTimeout(attemptScroll, 50);
        const timer2 = setTimeout(attemptScroll, 150);
        return () => {
          clearTimeout(timer1);
          clearTimeout(timer2);
        };
      }
    }
  }, [scrollTargetLetter, sortedAlbums]);

  // Scroll listener to update active letter rail highlight as user scrolls manually through albums
  useEffect(() => {
    if (sortedAlbums.length === 0 || sortBy !== "alphabetical") return;

    const mainContent = document.querySelector(".main-content");
    if (!mainContent) return;

    let ticking = false;

    const handleScroll = () => {
      if (ticking) return;
      ticking = true;

      requestAnimationFrame(() => {
        ticking = false;
        const mainRect = mainContent.getBoundingClientRect();
        const sortBar = mainContent.querySelector(".view-sort-bar");
        const headerOffset = sortBar ? sortBar.getBoundingClientRect().height : 0;
        const targetY = mainRect.top + headerOffset + 15;

        const cards = mainContent.querySelectorAll("[id^='album-']");
        const letterCounts: Record<string, number> = {};
        let firstLetter: string | null = null;

        for (let i = 0; i < cards.length; i++) {
          const rect = cards[i].getBoundingClientRect();
          if (rect.bottom >= targetY && rect.top <= targetY + 250) {
            const albIdStr = cards[i].id.replace("album-", "");
            const albId = parseInt(albIdStr, 10);
            const foundAlb = sortedAlbums.find((a) => a.album_id === albId);
            if (foundAlb && foundAlb.title) {
              const sortKey = getSortKey(foundAlb.title);
              const firstChar = sortKey[0];
              if (firstChar) {
                let letter = firstChar.toUpperCase();
                if (!/^[A-Z]/.test(letter)) letter = "0-9";
                if (!firstLetter) firstLetter = letter;
                letterCounts[letter] = (letterCounts[letter] || 0) + 1;
              }
            }
          }
        }

        let bestLetter = firstLetter;
        let maxCount = 0;
        for (const [letter, count] of Object.entries(letterCounts)) {
          if (count > maxCount) {
            maxCount = count;
            bestLetter = letter;
          }
        }

        if (bestLetter && bestLetter !== selectedLetter && onSelectLetter) {
          onSelectLetter(bestLetter);
        }
      });
    };

    mainContent.addEventListener("scroll", handleScroll, { passive: true });
    return () => mainContent.removeEventListener("scroll", handleScroll);
  }, [sortedAlbums, sortBy, selectedLetter, onSelectLetter]);

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
              if (sortBy === "plays") {
                setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
              } else {
                setSortBy("plays");
                setSortOrder("desc");
              }
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>local_fire_department</span>
            <span>{sortBy === "plays" ? (sortOrder === "desc" ? "Most Played" : "Least Played") : "Most Played"}</span>
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px", width: "100%" }}>
        {sortedAlbums.map((alb) => {
          const targetChar = scrollTargetLetter?.letter?.toUpperCase();
          const firstChar = alb.title ? alb.title.trim()[0].toUpperCase() : "";
          const firstArtistChar = alb.artist ? alb.artist.trim()[0].toUpperCase() : "";
          const isTarget = Boolean(
            targetChar && (
              targetChar === "0-9"
                ? (/^\d/.test(firstChar) || /^\d/.test(firstArtistChar))
                : (firstChar === targetChar || firstArtistChar === targetChar)
            )
          );
          return (
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
                loading={isTarget ? "eager" : "lazy"}
                fetchPriority={isTarget ? "high" : "auto"}
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
      );
    })}
      </div>
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
    <div style={{ width: "100%" }}>
      <div className="view-sort-bar">
        <span className="view-count-badge">
          {decades.length} Decades
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "20px" }}>
        {decades.map((d) => (
          <Card
            key={d.decade}
            onClick={() => handleSelectDecade(d)}
            style={{
              background: "linear-gradient(135deg, rgba(0,119,182,0.15) 0%, rgba(191,9,94,0.1) 100%)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              borderRadius: "20px",
              padding: "16px",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              gap: "12px",
              transition: "transform 0.2s ease, border-color 0.2s ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#0077b6")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)")}
          >
            {d.top_album_id ? (
              <div style={{ width: "100%", height: "140px", borderRadius: "14px", overflow: "hidden", position: "relative" }}>
                <FallbackImage
                  src={`${apiBase}/api/music/album-art/${d.top_album_id}`}
                  alt={d.decade}
                  type="album"
                  loading="lazy"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, transparent 40%, rgba(0, 0, 0, 0.8) 100%)" }} />
              </div>
            ) : (
              <div style={{ width: "100%", height: "140px", borderRadius: "14px", background: "rgba(255, 255, 255, 0.05)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span className="material-symbols-outlined" style={{ fontSize: "48px", color: "#0077b6" }}>calendar_clock</span>
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "4px" }}>
              <Typography variant="h6" style={{ color: "#fff", fontWeight: 800, fontSize: "16px" }}>
                {d.decade}
              </Typography>
              <span style={{ background: "rgba(0, 119, 182, 0.2)", color: "#38b6ff", fontSize: "12px", fontWeight: 800, padding: "4px 10px", borderRadius: "12px", whiteSpace: "nowrap" }}>
                {d.album_count} {d.album_count === 1 ? "Album" : "Albums"}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};

interface RecentlyAddedAlbum {
  album_id: number;
  artist_id?: number;
  artist?: string;
  title: string;
  year?: number;
  genre?: string;
  thumb?: string | null;
  play_count?: number;
  updated_at?: number;
  server_names?: string;
  server_count?: number;
}

export const RecentlyAddedGridView: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const [albums, setAlbums] = useState<RecentlyAddedAlbum[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    axios
      .get(`${apiBase}/api/music/albums/recently-added`)
      .then((res) => setAlbums(res.data))
      .catch((err) => console.error("Error fetching recently added albums:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const formatAddedTime = (updatedAt?: number) => {
    if (!updatedAt) return "Recently";
    const now = Math.floor(Date.now() / 1000);
    const diff = now - updatedAt;
    if (diff < 3600) return "Just added";
    if (diff < 86400) {
      const hours = Math.floor(diff / 3600);
      return `${hours}h ago`;
    }
    const days = Math.floor(diff / 86400);
    if (days === 1) return "Yesterday";
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    return `${months}m ago`;
  };

  if (loading) {
    return <div style={{ color: "#aaa", padding: "40px", textAlign: "center" }}>Loading Recently Added...</div>;
  }

  return (
    <div style={{ width: "100%" }}>
      {albums.length === 0 ? (
        <div style={{ color: "rgba(255,255,255,0.5)", textAlign: "center", padding: "60px 20px" }}>
          No recently added items found.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "20px" }}>
          {albums.map((alb) => (
            <Card
              key={alb.album_id}
              onClick={() => navigate(`/albums/${alb.album_id}/tracks`)}
              style={{
                background: "var(--color-glass-bg)",
                border: "1px solid var(--color-glass-border)",
                borderRadius: "16px",
                padding: "12px",
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                position: "relative",
                transition: "transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--color-primary)";
                e.currentTarget.style.transform = "translateY(-4px)";
                e.currentTarget.style.boxShadow = "0 8px 24px rgba(229, 149, 0, 0.2)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--color-glass-border)";
                e.currentTarget.style.transform = "none";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              <div style={{ position: "relative", width: "100%", aspectRatio: "1/1", borderRadius: "12px", overflow: "hidden" }}>
                <FallbackImage
                  src={`${apiBase}/api/music/album-art/${alb.album_id}`}
                  alt={alb.title}
                  type="album"
                  loading="lazy"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <span
                  style={{
                    position: "absolute",
                    top: "8px",
                    right: "8px",
                    background: "rgba(0, 0, 0, 0.75)",
                    backdropFilter: "blur(6px)",
                    color: "#f5a623",
                    fontSize: "11px",
                    fontWeight: 800,
                    padding: "3px 8px",
                    borderRadius: "10px",
                    border: "1px solid rgba(245, 166, 35, 0.4)",
                  }}
                >
                  {formatAddedTime(alb.updated_at)}
                </span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <Typography style={{ color: "#fff", fontWeight: 700, fontSize: "14px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {alb.title}
                </Typography>
                <Typography style={{ color: "rgba(255,255,255,0.6)", fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {alb.artist || "Unknown Artist"} {alb.year ? `(${alb.year})` : ""}
                </Typography>

                {alb.server_names && (
                  <span
                    style={{
                      display: "inline-block",
                      marginTop: "6px",
                      fontSize: "10px",
                      fontWeight: 700,
                      color: "#ff4d94",
                      background: "rgba(191, 9, 94, 0.15)",
                      border: "1px solid rgba(191, 9, 94, 0.3)",
                      padding: "2px 8px",
                      borderRadius: "10px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={`Source: ${alb.server_names}`}
                  >
                    📍 {alb.server_names}
                  </span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};


interface TopPlayedTrack {
  track_id: number;
  album_id?: number;
  server_id?: string;
  artist: string;
  album: string;
  title: string;
  duration: number;
  thumb?: string | null;
  play_count: number;
  last_played_at?: number;
}

export const TopPlayedTracksGridView: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const [tracks, setTracks] = useState<TopPlayedTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    axios
      .get(`${apiBase}/api/music/tracks/top-played`)
      .then((res) => setTracks(res.data))
      .catch((err) => console.error("Error fetching top played tracks:", err))
      .finally(() => setLoading(false));
  }, [apiBase]);

  const showSnackbar = (msg: string, sev: "success" | "error" | "warning" = "success") => {
    triggerQueueToast(msg, sev);
  };

  const handleQueueTrack = async (track: TopPlayedTrack, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await axios.post(`${apiBase}/api/music/queue/${track.track_id}`, {
        server_id: track.server_id,
        username: getLocalUsername(),
      });
      const etaMin = res?.data?.estimated_wait_minutes;
      const etaStr = etaMin && etaMin > 0 ? ` (Estimated play in ~${etaMin} min)` : "";
      showSnackbar(`"${track.title}" added to queue!${etaStr}`, "success");
    } catch (error: any) {
      const errorMsg = error?.response?.data?.detail || error?.response?.data?.message;
      if (error.response && error.response.status === 400) {
        showSnackbar(errorMsg || "This song is already in the queue!", "warning");
      } else if (error.response && error.response.status === 403) {
        showSnackbar(errorMsg || "🍸 Last Call active! Queue is closed to new guest requests.", "warning");
      } else {
        showSnackbar(errorMsg || "An unexpected error occurred.", "error");
      }
    }
  };

  if (loading) {
    return <div style={{ color: "#aaa", padding: "40px", textAlign: "center" }}>Loading Top Played Tracks...</div>;
  }

  return (
    <div style={{ width: "100%" }}>
      {tracks.length === 0 ? (
        <div style={{ color: "rgba(255,255,255,0.5)", textAlign: "center", padding: "60px 20px" }}>
          No TuneBox play history yet. Start playing songs to see your party's top tracks!
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: "12px" }}>
          {tracks.map((track, idx) => {
            const rank = idx + 1;
            const rankBadgeStyle = rank === 1
              ? { background: "linear-gradient(135deg, #ffd700 0%, #ffa500 100%)", color: "#111" }
              : rank === 2
              ? { background: "linear-gradient(135deg, #e0e0e0 0%, #9e9e9e 100%)", color: "#111" }
              : rank === 3
              ? { background: "linear-gradient(135deg, #cd7f32 0%, #8b4513 100%)", color: "#fff" }
              : { background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.7)" };

            return (
              <div
                key={`${track.track_id}-${idx}`}
                onClick={() => {
                  if (track.album_id) {
                    const trackParam = track.track_id ? `highlight_track_id=${track.track_id}` : "";
                    const serverParam = track.server_id ? `server_id=${track.server_id}` : "";
                    const query = [trackParam, serverParam].filter(Boolean).join("&");
                    navigate(`/albums/${track.album_id}/tracks${query ? `?${query}` : ""}`);
                  }
                }}
                style={{
                  background: "var(--color-glass-bg)",
                  border: "1px solid var(--color-glass-border)",
                  borderRadius: "14px",
                  padding: "10px 14px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  cursor: track.album_id ? "pointer" : "default",
                  transition: "background-color 0.2s, transform 0.2s, border-color 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-primary)";
                  e.currentTarget.style.transform = "translateX(4px)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-glass-border)";
                  e.currentTarget.style.transform = "none";
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0, flex: 1 }}>
                  {/* Rank Badge */}
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 800,
                      fontSize: "13px",
                      flexShrink: 0,
                      ...rankBadgeStyle
                    }}
                  >
                    #{rank}
                  </div>

                  {/* Album Artwork */}
                  <div style={{ width: "48px", height: "48px", borderRadius: "8px", overflow: "hidden", flexShrink: 0 }}>
                    <FallbackImage
                      src={`${apiBase}/api/music/track-art/${track.track_id}`}
                      alt={track.title}
                      type="album"
                      loading="lazy"
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  </div>

                  {/* Track Info (Title, Artist • Album, Play count subheader) */}
                  <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1, overflow: "hidden" }}>
                    <span style={{ fontWeight: 700, fontSize: "14px", color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {track.title}
                    </span>
                    <span style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {track.artist} {track.album ? `• ${track.album}` : ""}
                    </span>
                    <span style={{ fontSize: "11px", fontWeight: 600, color: "#ff9500", marginTop: "2px" }}>
                      {track.play_count} {track.play_count === 1 ? "play" : "plays"}
                    </span>
                  </div>
                </div>

                {/* Far Right: Queue Button */}
                <button
                  onClick={(e) => handleQueueTrack(track, e)}
                  style={{
                    background: "rgba(51, 117, 173, 0.2)",
                    border: "1px solid #3376ad",
                    color: "#9bd0ff",
                    borderRadius: "20px",
                    padding: "6px 14px",
                    fontSize: "12px",
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    flexShrink: 0,
                    transition: "background-color 0.2s, transform 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "rgba(51, 117, 173, 0.4)";
                    e.currentTarget.style.transform = "scale(1.05)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "rgba(51, 117, 173, 0.2)";
                    e.currentTarget.style.transform = "none";
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>add</span>
                  Queue
                </button>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
};
