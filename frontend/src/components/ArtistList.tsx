import { useEffect, useState, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button, Snackbar, Alert } from "@mui/material"; // MUI components
import { FallbackImage } from "./FallbackImage";
import { TuneBoxDialog } from "./TuneBoxDialog";
import axios from "axios";
import { getLocalUsername, getSortKey } from "../utils";
import "../App.css";
import "./ArtistList.css";

interface Artist {
  artist_id: number;
  name: string;
  thumb?: string;
  source_count?: number;
  server_names?: string[];
}

interface ArtistListProps {
  filteredArtists: Artist[];
  loading: boolean;
  searchResults: any[];
  isSearching: boolean;
  selectedLetter?: string;
  scrollTargetLetter?: { letter: string; timestamp: number } | null;
  onSelectLetter?: (letter: string) => void;
}

function ArtistList({
  filteredArtists,
  loading,
  searchResults,
  isSearching,
  selectedLetter,
  scrollTargetLetter,
  onSelectLetter,
}: ArtistListProps) {
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  const [dialogState, setDialogState] = useState<{ open: boolean; title: string; message: string }>({
    open: false,
    title: "",
    message: "",
  });

  const [visibleTrackLimit, setVisibleTrackLimit] = useState(15);
  const trackSentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setVisibleTrackLimit(15);
  }, [searchResults]);

  useEffect(() => {
    const sentinel = trackSentinelRef.current;
    if (!sentinel) return;

    const totalTracks = searchResults.filter((i) => i.type === "track").length;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleTrackLimit((prev) => Math.min(prev + 15, totalTracks));
        }
      },
      { rootMargin: "250px" }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [searchResults]);

  const handleArtistClick = (artistId: number, artistName?: string, serverId?: string) => {
    sessionStorage.setItem("tunebox_artist_scroll_top", String(window.scrollY || document.querySelector('.main-content')?.scrollTop || 0));
    const sParam = serverId ? `?server_id=${serverId}` : "";
    navigate(`/artists/${artistId}/albums${sParam}`, { state: { artistName } });
  };

  // Restore scroll position when returning from album/track views
  useEffect(() => {
    const savedScroll = sessionStorage.getItem("tunebox_artist_scroll_top");
    if (savedScroll) {
      sessionStorage.removeItem("tunebox_artist_scroll_top");
      const targetScroll = parseInt(savedScroll, 10);
      setTimeout(() => {
        const mainContent = document.querySelector(".main-content");
        if (mainContent) {
          mainContent.scrollTop = targetScroll;
        }
      }, 50);
    }
  }, []);

  const [sortBy, setSortBy] = useState<"alphabetical" | "plays">("alphabetical");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  const sortedArtists = useMemo(() => {
    return [...filteredArtists].sort((a, b) => {
      const keyA = getSortKey(a.name);
      const keyB = getSortKey(b.name);
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
  }, [filteredArtists, sortBy, sortOrder]);

  const lastProcessedTargetRef = useRef<number | null>(null);

  // Fast-scroll to selected alphabet letter ONLY when a letter button on the rail is clicked
  useEffect(() => {
    if (!scrollTargetLetter || !scrollTargetLetter.letter || isSearching || sortedArtists.length === 0) return;
    if (lastProcessedTargetRef.current === scrollTargetLetter.timestamp) return;
    lastProcessedTargetRef.current = scrollTargetLetter.timestamp;

    const targetChar = scrollTargetLetter.letter;
    const targetIndex = sortedArtists.findIndex((artist) => {
      if (!artist.name) return false;
      const sortKey = getSortKey(artist.name);
      const firstChar = sortKey[0] || "";
      if (targetChar === "0-9") {
        return !/^[A-Z]/i.test(firstChar);
      }
      return firstChar.toUpperCase() === targetChar.toUpperCase();
    });

    if (targetIndex !== -1) {
      const targetArtist = sortedArtists[targetIndex];
      const attemptScroll = () => {
        const el = document.getElementById(`artist-${targetArtist.artist_id}`);
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
  }, [scrollTargetLetter, sortedArtists, isSearching]);

  // Snackbar alerts
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [severity, setSeverity] = useState<"success" | "warning" | "error">("success");

  const showSnackbar = (message: string, type: "success" | "warning" | "error") => {
    setSnackbarMessage(message);
    setSeverity(type);
    setSnackbarOpen(true);
  };

  const formatDuration = (secondsStr: string | number) => {
    const secs = typeof secondsStr === "string" ? parseFloat(secondsStr) : secondsStr;
    if (isNaN(secs)) return "0:00";
    const mins = Math.floor(secs / 60);
    const remainingSecs = Math.floor(secs % 60);
    return `${mins}:${remainingSecs < 10 ? "0" : ""}${remainingSecs}`;
  };

  const addToQueue = async (trackId: number, serverId?: string, serverName?: string) => {
    try {
      const queueUrl = `${apiBase}/api/music/queue/${trackId}`;
      await axios.post(queueUrl, {
        server_id: serverId,
        server_name: serverName,
        username: getLocalUsername(),
      });
      showSnackbar("Track added to queue!", "success");
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

  // Scroll listener to update active letter rail highlight as user scrolls manually
  useEffect(() => {
    if (isSearching || filteredArtists.length === 0 || sortBy !== "alphabetical") return;

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

        const cards = mainContent.querySelectorAll(".artist-card");
        const letterCounts: Record<string, number> = {};
        let firstLetter: string | null = null;

        for (let i = 0; i < cards.length; i++) {
          const rect = cards[i].getBoundingClientRect();
          if (rect.bottom >= targetY && rect.top <= targetY + 250) {
            const nameEl = cards[i].querySelector(".artist-card-name");
            if (nameEl && nameEl.textContent) {
              const sortKey = getSortKey(nameEl.textContent);
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
  }, [isSearching, filteredArtists, sortBy, selectedLetter, onSelectLetter]);

  const currentArtists = sortedArtists;

  // Group search results
  const searchArtists = searchResults.filter((item) => item.type === "artist");
  const searchAlbums = searchResults.filter((item) => item.type === "album");
  const searchTracks = searchResults.filter((item) => item.type === "track");

  return (
    <div className="artist-list-wrapper">
      {isSearching && (
        <header className="page-header">
          <Typography variant="h1" className="gradient-text">
            Search Results
          </Typography>
        </header>
      )}

      {!isSearching && (
        <div className="view-sort-bar">
          <span className="view-count-badge">
            {filteredArtists.length} {filteredArtists.length === 1 ? "Artist" : "Artists"}
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
      )}

      {loading ? (
        <Typography variant="h6">Loading...</Typography>
      ) : isSearching ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "32px", width: "100%" }}>
          {/* 1. Artists Section */}
          {searchArtists.length > 0 && (
            <div>
              <Typography variant="h5" style={{ color: "#f5a623", marginBottom: "16px", fontFamily: "var(--font-title)", fontWeight: 700 }}>
                Artists
              </Typography>
              <div className="artist-grid">
                {searchArtists.map((artist) => (
                  <Card
                    className="artist-card"
                    key={artist.artist_id}
                    id={`artist-${artist.artist_id}`}
                    onClick={() => handleArtistClick(artist.artist_id, artist.name, artist.server_id)}
                  >
                    <FallbackImage
                      src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                      alt={artist.name}
                      type="artist"
                      loading="eager"
                      fetchPriority="high"
                      className="artist-photo"
                    />
                    <div className="artist-card-overlay" style={{ flexDirection: "column", gap: "4px", padding: "12px 8px" }}>
                      <Typography className="artist-card-name">{artist.name}</Typography>
                      {(() => {
                        const sources = artist.sources || [];
                        if (sources.length > 1) {
                          const names = sources.map((s: any) => s.server_name).filter(Boolean).join(" • ");
                          return (
                            <span
                              style={{
                                fontSize: "10px",
                                background: "rgba(46, 204, 113, 0.2)",
                                border: "1px solid rgba(46, 204, 113, 0.5)",
                                color: "#2ecc71",
                                padding: "1px 7px",
                                borderRadius: "10px",
                                fontWeight: 700,
                                lineHeight: 1.2,
                                cursor: "pointer",
                              }}
                              title={`Found on ${sources.length} servers: ${names}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                const listStr = sources.map((s: any) => `• ${s.server_name || "Unknown Library"}`).join("\n");
                                setDialogState({
                                  open: true,
                                  title: `Multi-Library Artist`,
                                  message: `"${artist.name}" is available across ${sources.length} connected libraries:\n\n${listStr}`,
                                });
                              }}
                            >
                              🌐 {sources.length} libraries
                            </span>
                          );
                        }
                        const sName = artist.server_name || (sources.length === 1 ? sources[0].server_name : null);
                        if (!sName) return null;
                        const sLower = sName.toLowerCase();
                        if (sLower === "plex-so" || sLower === "home server" || sLower === "primary server") return null;

                        return (
                          <span
                            style={{
                              fontSize: "10px",
                              background: "rgba(245, 166, 35, 0.2)",
                              border: "1px solid rgba(245, 166, 35, 0.4)",
                              color: "#f5a623",
                              padding: "1px 6px",
                              borderRadius: "10px",
                              fontWeight: 600,
                              lineHeight: 1.2,
                            }}
                          >
                            {sName}
                          </span>
                        );
                      })()}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* 2. Albums Section */}
          {searchAlbums.length > 0 && (
            <div>
              <Typography variant="h5" style={{ color: "#f5a623", marginBottom: "16px", fontFamily: "var(--font-title)", fontWeight: 700 }}>
                Albums
              </Typography>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
                gap: "16px",
                width: "100%"
              }}>
                {searchAlbums.map((album) => {
                  const sParam = album.server_id ? `?server_id=${album.server_id}` : "";
                  return (
                    <Card
                      className="artist-card"
                      key={album.album_id}
                      onClick={() => {
                        navigate(`/albums/${album.album_id}/tracks${sParam}`);
                      }}
                      style={{
                        position: "relative",
                        aspectRatio: "1/1",
                        cursor: "pointer",
                        overflow: "hidden"
                      }}
                    >
                      <FallbackImage
                        src={`${apiBase}/api/music/album-art/${album.album_id}${sParam}`}
                      alt={album.title}
                      type="album"
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover"
                      }}
                    />
                    <div className="artist-card-overlay" style={{
                      position: "absolute",
                      bottom: 0,
                      left: 0,
                      right: 0,
                      height: "55%",
                      background: "linear-gradient(to top, rgba(0, 0, 0, 0.9) 0%, rgba(0, 0, 0, 0.35) 70%, transparent 100%)",
                      display: "flex",
                      alignItems: "flex-end",
                      justifyContent: "center",
                      padding: "10px 8px",
                      boxSizing: "border-box"
                    }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: "100%", gap: "2px" }}>
                        <Typography style={{
                          fontFamily: "var(--font-title)",
                          fontSize: "0.85rem",
                          color: "white",
                          fontWeight: 700,
                          textAlign: "center",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textShadow: "0 0 10px rgba(0,0,0,0.5)",
                          textOverflow: "ellipsis",
                          width: "100%"
                        }}>
                          {album.title}
                        </Typography>
                        {(() => {
                          const sources = album.sources || [];
                          if (sources.length > 1) {
                            const names = sources.map((s: any) => s.server_name).filter(Boolean).join(" • ");
                            return (
                              <span
                                style={{
                                  fontSize: "9px",
                                  background: "rgba(46, 204, 113, 0.2)",
                                  border: "1px solid rgba(46, 204, 113, 0.5)",
                                  color: "#2ecc71",
                                  padding: "1px 5px",
                                  borderRadius: "8px",
                                  fontWeight: 700,
                                  lineHeight: 1.2,
                                  cursor: "pointer",
                                }}
                                title={`Found on ${sources.length} servers: ${names}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const listStr = sources.map((s: any) => `• ${s.server_name || "Unknown Library"}`).join("\n");
                                  setDialogState({
                                    open: true,
                                    title: `Multi-Library Album`,
                                    message: `"${album.title}" is available across ${sources.length} connected libraries:\n\n${listStr}`,
                                  });
                                }}
                              >
                                🌐 {sources.length} libraries
                              </span>
                            );
                          }
                          const sName = album.server_name || (sources.length === 1 ? sources[0].server_name : null);
                          if (!sName) return null;
                          const sLower = sName.toLowerCase();
                          if (sLower === "plex-so" || sLower === "home server" || sLower === "primary server") return null;

                          return (
                            <span
                              style={{
                                fontSize: "9px",
                                background: "rgba(245, 166, 35, 0.2)",
                                border: "1px solid rgba(245, 166, 35, 0.4)",
                                color: "#f5a623",
                                padding: "1px 5px",
                                borderRadius: "8px",
                                fontWeight: 600,
                                lineHeight: 1.2,
                              }}
                            >
                              {sName}
                            </span>
                          );
                        })()}
                      </div>
                    </div>
                  </Card>
                );
              })}
              </div>
            </div>
          )}

          {/* 3. Tracks Section */}
          {searchTracks.length > 0 && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
                <Typography variant="h5" style={{ color: "#f5a623", fontFamily: "var(--font-title)", fontWeight: 700 }}>
                  Tracks
                </Typography>
                <span style={{ fontSize: "12px", color: "rgba(255,255,255,0.5)", fontWeight: 600 }}>
                  Showing {Math.min(visibleTrackLimit, searchTracks.length)} of {searchTracks.length} tracks
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {searchTracks.slice(0, visibleTrackLimit).map((track) => (
                  <Card
                    key={track.track_id}
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
                      borderRadius: "12px",
                      padding: "10px 16px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
                      boxSizing: "border-box",
                      width: "100%",
                      cursor: "pointer",
                      transition: "transform 0.15s ease, border-color 0.15s ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--color-primary)")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--color-glass-border)")}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "14px", minWidth: 0 }}>
                      <FallbackImage
                        src={`${apiBase}/api/music/album-art/${track.album_id || track.track_id}${track.server_id ? `?server_id=${track.server_id}` : ""}`}
                        alt={track.album || track.title}
                        type="album"
                        loading="eager"
                        fetchPriority="high"
                        style={{ width: "48px", height: "48px", borderRadius: "8px", objectFit: "cover", flexShrink: 0 }}
                      />
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, textAlign: "left" }}>
                        <Typography style={{ color: "white", fontFamily: "var(--font-title)", fontWeight: 700, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{track.title}</span>
                        {(() => {
                          const sources = track.sources || [];
                          if (sources.length > 1) {
                            const names = sources.map((s: any) => s.server_name).filter(Boolean).join(" • ");
                            return (
                              <span
                                style={{
                                  fontSize: "10px",
                                  background: "rgba(46, 204, 113, 0.15)",
                                  border: "1px solid rgba(46, 204, 113, 0.5)",
                                  color: "#2ecc71",
                                  padding: "2px 6px",
                                  borderRadius: "10px",
                                  fontWeight: 700,
                                  cursor: "pointer",
                                }}
                                title={`Found on ${sources.length} servers: ${names}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const listStr = sources.map((s: any) => `• ${s.server_name || "Unknown Library"}`).join("\n");
                                  setDialogState({
                                    open: true,
                                    title: `Multi-Library Track`,
                                    message: `"${track.title}" is available across ${sources.length} connected libraries:\n\n${listStr}`,
                                  });
                                }}
                              >
                                🌐 {sources.length} libraries
                              </span>
                            );
                          }
                          const sName = track.server_name || (sources.length === 1 ? sources[0].server_name : null);
                          if (!sName) return null;
                          const sLower = sName.toLowerCase();
                          if (sLower === "plex-so" || sLower === "home server" || sLower === "primary server") return null;

                          return (
                            <span style={{
                              fontSize: "10px",
                              background: "rgba(245, 166, 35, 0.15)",
                              border: "1px solid rgba(245, 166, 35, 0.4)",
                              color: "#f5a623",
                              padding: "2px 6px",
                              borderRadius: "10px",
                              fontWeight: 600,
                              maxWidth: "120px",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}>
                              {sName}
                            </span>
                          );
                        })()}
                      </Typography>
                      <Typography style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "0.75rem", fontFamily: "var(--font-body)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {track.artist} • {track.album}
                      </Typography>
                    </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "16px", flexShrink: 0 }}>
                      <Typography style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.85rem", fontFamily: "var(--font-body)" }}>
                        {formatDuration(track.duration)}
                      </Typography>
                      <Button
                        variant="contained"
                        onClick={(e) => {
                          e.stopPropagation();
                          addToQueue(track.track_id || track.item_id || track.server_track_id, track.server_id, track.server_name);
                        }}
                        style={{
                          background: "var(--color-primary)",
                          color: "#0e0e0f",
                          fontWeight: 700,
                          textTransform: "none",
                          borderRadius: "20px",
                          padding: "6px 16px",
                          fontFamily: "var(--font-body)",
                          fontSize: "12px"
                        }}
                      >
                        Add to Queue
                      </Button>
                    </div>
                  </Card>
                ))}
              </div>
              {/* Scroll Sentinel for Auto Infinite Scroll */}
              {visibleTrackLimit < searchTracks.length && (
                <div ref={trackSentinelRef} style={{ height: "40px", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.5)", fontSize: "13px", marginTop: "12px" }}>
                  Loading more tracks...
                </div>
              )}
            </div>
          )}

          {searchArtists.length === 0 && searchAlbums.length === 0 && searchTracks.length === 0 && (
            <Typography variant="h6">No results found.</Typography>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px", width: "100%" }}>
          {/* Artist grid */}
          <div className="artist-grid">
            {currentArtists.map((artist: any) => {
            const targetChar = scrollTargetLetter?.letter?.toUpperCase();
            const cleanName = artist.name
              ? artist.name.replace(/^[:?="'"()\s]+/, "").replace(/^(the|a|an)\s+/i, "").trim()
              : "";
            const firstChar = cleanName ? cleanName[0].toUpperCase() : (artist.name ? artist.name.trim()[0].toUpperCase() : "");
            const rawFirst = artist.name ? artist.name.trim()[0].toUpperCase() : "";
            const isTarget = Boolean(
              targetChar && (
                targetChar === "0-9"
                  ? (/^\d/.test(firstChar) || /^\d/.test(rawFirst))
                  : (firstChar === targetChar || rawFirst === targetChar)
              )
            );
            return (
              <Card
                className="artist-card"
                key={artist.artist_id}
                id={`artist-${artist.artist_id}`}
                onClick={() => handleArtistClick(artist.artist_id, artist.name)}
              >
                <FallbackImage
                  src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                  alt={artist.name}
                  type="artist"
                  loading={isTarget ? "eager" : "lazy"}
                  fetchPriority={isTarget ? "high" : "auto"}
                  className="artist-photo"
                />
                <div className="artist-card-overlay">
                  <Typography className="artist-card-name">{artist.name}</Typography>
                  {Boolean(artist.source_count && artist.source_count > 1) && (
                    <span
                      style={{
                        fontSize: "10px",
                        background: "rgba(51, 117, 173, 0.25)",
                        border: "1px solid #3375A8",
                        color: "#9bd0ff",
                        padding: "2px 6px",
                        borderRadius: "10px",
                        fontWeight: "bold",
                        marginTop: "4px",
                      }}
                      title={`Sourced from: ${artist.server_names?.join(", ") || "Multiple Servers"}`}
                    >
                      ⚡ {artist.source_count} Sources
                    </span>
                  )}
                </div>
              </Card>
            );
          })}
          </div>
        </div>
      )}

      {/* Snackbar Alert for Track Queueing */}
      {createPortal(
        <Snackbar
          open={snackbarOpen}
          autoHideDuration={4000}
          onClose={() => setSnackbarOpen(false)}
          className="queue-toast-snackbar"
        >
          <Alert
            onClose={() => setSnackbarOpen(false)}
            severity={severity}
            sx={{
              width: "100%",
              background: severity === "success" ? "#1e4620" : severity === "warning" ? "#663c00" : "#5f2120",
              color: "white",
              fontWeight: "bold",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.2)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.8)"
            }}
          >
            {snackbarMessage}
          </Alert>
        </Snackbar>,
        document.body
      )}

      <TuneBoxDialog
        open={dialogState.open}
        title={dialogState.title}
        message={dialogState.message}
        type="info"
        icon="dns"
        confirmText="Got It"
        onConfirm={() => setDialogState({ ...dialogState, open: false })}
      />
    </div>
  );
}

export default ArtistList;
