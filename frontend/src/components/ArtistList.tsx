import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button, Snackbar, Alert } from "@mui/material"; // MUI components
import { FallbackImage } from "./FallbackImage";
import { TuneBoxDialog } from "./TuneBoxDialog";
import axios from "axios";
import { getLocalUsername } from "../utils";
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
  onSelectLetter?: (letter: string) => void;
}

function ArtistList({
  filteredArtists,
  loading,
  searchResults,
  isSearching,
  selectedLetter,
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

  const [visibleCount, setVisibleCount] = useState(() => {
    const saved = sessionStorage.getItem("tunebox_artist_visible_count");
    return saved ? parseInt(saved, 10) : 48;
  });
  const loaderRef = useRef<HTMLDivElement | null>(null);

  const handleArtistClick = (artistId: number, serverId?: string) => {
    sessionStorage.setItem("tunebox_artist_scroll_top", String(window.scrollY || document.querySelector('.main-content')?.scrollTop || 0));
    sessionStorage.setItem("tunebox_artist_visible_count", String(visibleCount));
    const sParam = serverId ? `?server_id=${serverId}` : "";
    navigate(`/artists/${artistId}/albums${sParam}`);
  };

  // Restore scroll position when returning from album/track views
  useEffect(() => {
    const savedScroll = sessionStorage.getItem("tunebox_artist_scroll_top");
    if (savedScroll) {
      sessionStorage.removeItem("tunebox_artist_scroll_top");
      sessionStorage.removeItem("tunebox_artist_visible_count");
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

  const sortedArtists = [...filteredArtists].sort((a, b) => {
    if (sortBy === "plays") {
      const playsA = (a as any).play_count || 0;
      const playsB = (b as any).play_count || 0;
      if (playsB !== playsA) return playsB - playsA;
      return a.name.localeCompare(b.name);
    }
    const cmp = a.name.localeCompare(b.name);
    return sortOrder === "asc" ? cmp : -cmp;
  });

  // Fast-scroll to selected alphabet letter while maintaining full artist grid
  useEffect(() => {
    if (!selectedLetter || isSearching || sortedArtists.length === 0) return;

    const targetIndex = sortedArtists.findIndex((artist) => {
      if (!artist.name) return false;
      const firstChar = artist.name[0];
      if (selectedLetter === "0-9") {
        return /^\d/.test(firstChar);
      }
      return firstChar.toUpperCase() === selectedLetter.toUpperCase();
    });

    if (targetIndex !== -1) {
      if (targetIndex >= visibleCount) {
        setVisibleCount(targetIndex + 36);
      }

      const targetArtist = sortedArtists[targetIndex];
      const attemptScroll = () => {
        const el = document.getElementById(`artist-${targetArtist.artist_id}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
          return true;
        }
        return false;
      };

      if (!attemptScroll()) {
        const timer1 = setTimeout(attemptScroll, 50);
        const timer2 = setTimeout(attemptScroll, 150);
        const timer3 = setTimeout(attemptScroll, 300);
        return () => {
          clearTimeout(timer1);
          clearTimeout(timer2);
          clearTimeout(timer3);
        };
      }
    }
  }, [selectedLetter, sortedArtists, isSearching, visibleCount]);

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
      if (error.response && error.response.status === 400) {
        showSnackbar("This song is already in the queue!", "warning");
      } else {
        showSnackbar("An unexpected error occurred.", "error");
      }
    }
  };

  // Reset display count and scroll to top when list of filtered artists changes
  useEffect(() => {
    const hasSavedScroll = sessionStorage.getItem("tunebox_artist_scroll_top");
    if (!hasSavedScroll && !selectedLetter) {
      setVisibleCount(48);
      const mainContent = document.querySelector(".main-content");
      if (mainContent) {
        mainContent.scrollTop = 0;
      }
    }
  }, [filteredArtists, searchResults, selectedLetter]);

  // Set up intersection observer to detect when user scrolls to bottom
  useEffect(() => {
    if (isSearching) return; // Disable pagination for search results

    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first.isIntersecting) {
          setVisibleCount((prev) => {
            if (prev < filteredArtists.length) {
              return Math.min(prev + 36, filteredArtists.length);
            }
            return prev;
          });
        }
      },
      { threshold: 0.1, rootMargin: "100px" }
    );

    const currentLoader = loaderRef.current;
    if (currentLoader) {
      observer.observe(currentLoader);
    }

    return () => {
      if (currentLoader) {
        observer.unobserve(currentLoader);
      }
    };
  }, [filteredArtists.length, isSearching]);

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
        const targetY = mainRect.top + 120;

        const cards = mainContent.querySelectorAll(".artist-card");
        let topVisibleName: string | null = null;

        for (let i = 0; i < cards.length; i++) {
          const rect = cards[i].getBoundingClientRect();
          if (rect.bottom >= targetY) {
            const nameEl = cards[i].querySelector(".artist-card-name");
            if (nameEl && nameEl.textContent) {
              topVisibleName = nameEl.textContent;
              break;
            }
          }
        }

        if (topVisibleName && onSelectLetter) {
          const firstChar = topVisibleName.trim()[0];
          if (firstChar) {
            let letter = firstChar.toUpperCase();
            if (/^\d/.test(letter)) {
              letter = "0-9";
            }
            if (letter !== selectedLetter) {
              onSelectLetter(letter);
            }
          }
        }
      });
    };

    mainContent.addEventListener("scroll", handleScroll, { passive: true });
    return () => mainContent.removeEventListener("scroll", handleScroll);
  }, [isSearching, filteredArtists, sortBy, selectedLetter, onSelectLetter]);

  const currentArtists = sortedArtists.slice(0, visibleCount);

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
                setSortBy((prev) => (prev === "plays" ? "alphabetical" : "plays"));
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "15px" }}>local_fire_department</span>
              <span>Most Played</span>
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
                    onClick={() => handleArtistClick(artist.artist_id, artist.server_id)}
                  >
                    <FallbackImage
                      src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                      alt={artist.name}
                      type="artist"
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
              <Typography variant="h5" style={{ color: "#f5a623", marginBottom: "16px", fontFamily: "var(--font-title)", fontWeight: 700 }}>
                Tracks
              </Typography>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {searchTracks.map((track) => (
                  <Card
                    key={track.track_id}
                    onClick={() => {
                      if (track.album_id) {
                        const sParam = track.server_id ? `?server_id=${track.server_id}` : "";
                        navigate(`/albums/${track.album_id}/tracks${sParam}`);
                      }
                    }}
                    style={{
                      background: "var(--color-glass-bg)",
                      border: "1px solid var(--color-glass-border)",
                      borderRadius: "12px",
                      padding: "12px 20px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
                      boxSizing: "border-box",
                      width: "100%",
                      cursor: track.album_id ? "pointer" : "default",
                      transition: "transform 0.15s ease, border-color 0.15s ease",
                    }}
                  >
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
                    <div style={{ display: "flex", alignItems: "center", gap: "16px", flexShrink: 0 }}>
                      <Typography style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.85rem", fontFamily: "var(--font-body)" }}>
                        {formatDuration(track.duration)}
                      </Typography>
                      <Button
                        variant="contained"
                        onClick={(e) => {
                          e.stopPropagation();
                          addToQueue(track.track_id, track.server_id, track.server_name);
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
            {currentArtists.map((artist) => (
              <Card
                className="artist-card"
                key={artist.artist_id}
                id={`artist-${artist.artist_id}`}
                onClick={() => handleArtistClick(artist.artist_id)}
              >
                <FallbackImage
                  src={`${apiBase}/api/music/artist-image/${artist.artist_id}`}
                  alt={artist.name}
                  type="artist"
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
            ))}
          </div>

          {/* Infinite Scroll Loader Target */}
          {visibleCount < filteredArtists.length && (
            <div ref={loaderRef} className="infinite-scroll-loader">
              <div className="spinner-glass">
                <span className="spinner-inner"></span>
              </div>
              <Typography className="loader-text">Loading more artists...</Typography>
            </div>
          )}
        </div>
      )}

      {/* Snackbar Alert for Track Queueing */}
      {createPortal(
        <Snackbar
          open={snackbarOpen}
          autoHideDuration={1500}
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
