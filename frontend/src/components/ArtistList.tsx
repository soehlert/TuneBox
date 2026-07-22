import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button, Snackbar, Alert } from "@mui/material"; // MUI components
import { FallbackImage } from "./FallbackImage";
import axios from "axios";
import "../App.css";
import "./ArtistList.css";

interface Artist {
  artist_id: number;
  name: string;
  thumb?: string;
}

interface ArtistListProps {
  filteredArtists: Artist[];
  loading: boolean;
  searchResults: any[];
  isSearching: boolean;
  selectedLetter?: string;
}

function ArtistList({
  filteredArtists,
  loading,
  searchResults,
  isSearching,
  selectedLetter,
}: ArtistListProps) {
  const navigate = useNavigate();
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  const [visibleCount, setVisibleCount] = useState(() => {
    const saved = sessionStorage.getItem("tunebox_artist_visible_count");
    return saved ? parseInt(saved, 10) : 48;
  });
  const isRestoringScroll = useRef(Boolean(sessionStorage.getItem("tunebox_artist_scroll_top")));
  const loaderRef = useRef<HTMLDivElement | null>(null);

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

  // Fast-scroll to selected alphabet letter while maintaining full artist grid
  // and pre-loading images for target + surrounding letters
  useEffect(() => {
    if (!selectedLetter || isSearching || filteredArtists.length === 0) return;
    if (isRestoringScroll.current) {
      isRestoringScroll.current = false;
      return;
    }

    // Determine target letter and adjacent letters (e.g. L, M, N for M)
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const letterIdx = alphabet.indexOf(selectedLetter.toUpperCase());
    const adjacentBucketLetters = new Set<string>([selectedLetter.toUpperCase()]);
    if (letterIdx > 0) adjacentBucketLetters.add(alphabet[letterIdx - 1]);
    if (letterIdx >= 0 && letterIdx < alphabet.length - 1) adjacentBucketLetters.add(alphabet[letterIdx + 1]);

    // Prefetch images for target and adjacent letters immediately
    const prefetchArtists = filteredArtists.filter((artist) => {
      if (!artist.name) return false;
      const char = artist.name[0].toUpperCase();
      if (selectedLetter === "0-9") return /^\d/.test(char);
      return adjacentBucketLetters.has(char);
    });

    prefetchArtists.slice(0, 60).forEach((artist) => {
      const img = new Image();
      img.src = `${apiBase}/api/music/artist-image/${artist.artist_id}`;
    });

    const targetIndex = filteredArtists.findIndex((artist) => {
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
      const targetArtist = filteredArtists[targetIndex];
      setTimeout(() => {
        const el = document.getElementById(`artist-${targetArtist.artist_id}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 100);
    }
  }, [selectedLetter, filteredArtists, isSearching, apiBase]);

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
      await axios.post(queueUrl, { server_id: serverId, server_name: serverName });
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

  // Function to handle card click and navigate to artist's album page
  const handleArtistClick = (artistId: number) => {
    navigate(`/artists/${artistId}/albums`);
  };

  const currentArtists = filteredArtists.slice(0, visibleCount);

  // Group search results
  const searchArtists = searchResults.filter((item) => item.type === "artist");
  const searchAlbums = searchResults.filter((item) => item.type === "album");
  const searchTracks = searchResults.filter((item) => item.type === "track");

  return (
    <div className="artist-list-wrapper">
      <header className="page-header">
        <Typography variant="h1" className="gradient-text">
          {isSearching ? "Search Results" : "Artists"}
        </Typography>
      </header>

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
                {searchAlbums.map((album) => (
                  <Card
                    className="artist-card"
                    key={album.album_id}
                    onClick={() => navigate(`/albums/${album.album_id}/tracks`)}
                    style={{
                      position: "relative",
                      aspectRatio: "1/1",
                      cursor: "pointer",
                      overflow: "hidden"
                    }}
                  >
                    <FallbackImage
                      src={`${apiBase}/api/music/album-art/${album.album_id}`}
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
                      height: "50%",
                      background: "linear-gradient(to top, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0.3) 65%, transparent 100%)",
                      display: "flex",
                      alignItems: "flex-end",
                      justifyContent: "center",
                      padding: "12px",
                      boxSizing: "border-box"
                    }}>
                      <Typography style={{
                        fontFamily: "var(--font-title)",
                        fontSize: "0.9rem",
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
                    </div>
                  </Card>
                ))}
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
                      width: "100%"
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, textAlign: "left" }}>
                      <Typography style={{ color: "white", fontFamily: "var(--font-title)", fontWeight: 700, fontSize: "0.95rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "flex", alignItems: "center", gap: "8px" }}>
                        {track.title}
                        {track.server_name && (
                          <span style={{
                            fontSize: "10px",
                            background: "rgba(245, 166, 35, 0.15)",
                            border: "1px solid rgba(245, 166, 35, 0.4)",
                            color: "#f5a623",
                            padding: "2px 6px",
                            borderRadius: "10px",
                            fontWeight: 600,
                          }}>
                            {track.server_name}
                          </span>
                        )}
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
                        onClick={() => addToQueue(track.track_id, track.server_id, track.server_name)}
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
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
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
            border: "1px solid rgba(255,255,255,0.1)"
          }}
        >
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </div>
  );
}

export default ArtistList;
