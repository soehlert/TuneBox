import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Button, Card, Typography, Snackbar, Alert } from "@mui/material";
import { FallbackImage } from "./FallbackImage";
import { getLocalUsername } from "../utils";
import "./TrackList.css";

interface Track {
  track_id: number;
  title: string;
  duration: string;
  track_number?: number;
  disc_number?: number;
  user_rating?: number;
  is_primary?: boolean;
}

interface AlbumData {
  album_title: string;
  artist_id?: number;
  artist_name?: string;
  thumb: string | null;
  server_name?: string;
  sources?: { server_id: string; server_name: string }[];
  tracks: Track[];
}

const StarRating = ({
  rating,
  onRate,
  readOnly = false,
}: {
  rating: number;
  onRate?: (newRating: number) => void;
  readOnly?: boolean;
}) => {
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const activeRating = !readOnly && hoverRating !== null ? hoverRating : rating;

  if (readOnly && !rating) {
    return null;
  }

  return (
    <div
      style={{ display: "inline-flex", alignItems: "center", gap: "2px", cursor: readOnly ? "default" : "pointer" }}
      onMouseLeave={() => !readOnly && setHoverRating(null)}
      title={rating ? `Rating: ${rating} / 5 stars` : "Rate song (1-5 stars)"}
    >
      {[1, 2, 3, 4, 5].map((starIdx) => {
        const fullStarValue = starIdx;
        const halfStarValue = starIdx - 0.5;

        const isFilled = activeRating >= fullStarValue;
        const isHalf = !isFilled && activeRating >= halfStarValue;
        const iconName = isHalf ? "star_half" : "star";

        return (
          <span
            key={starIdx}
            className="material-symbols-outlined"
            style={{
              fontSize: "18px",
              color: (isFilled || isHalf) ? "#f5a623" : "rgba(255,255,255,0.25)",
              fontVariationSettings: (isFilled || isHalf) ? "'FILL' 1" : "'FILL' 0",
              userSelect: "none",
              transition: "color 0.1s ease, transform 0.1s ease",
            }}
            onMouseMove={(e) => {
              if (readOnly) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const isLeftHalf = e.clientX - rect.left < rect.width / 2;
              setHoverRating(isLeftHalf ? halfStarValue : fullStarValue);
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (readOnly || !onRate) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const isLeftHalf = e.clientX - rect.left < rect.width / 2;
              const selectedValue = isLeftHalf ? halfStarValue : fullStarValue;
              const newRating = rating === selectedValue ? 0 : selectedValue;
              onRate(newRating);
            }}
          >
            {iconName}
          </span>
        );
      })}
    </div>
  );
};

function TrackList() {
  const { albumId } = useParams();
  const [searchParams] = useSearchParams();
  const serverId = searchParams.get("server_id");
  const navigate = useNavigate();
  const [albumData, setAlbumData] = useState<AlbumData | null>(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [severity, setSeverity] = useState<"success" | "warning" | "error">("success");
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  const adminToken = localStorage.getItem("tunebox_admin_token") || "";
  const isAdmin = Boolean(adminToken);

  useEffect(() => {
    const fetchTracks = async () => {
      try {
        const sParam = serverId ? `?server_id=${serverId}` : "";
        const albumUrl = `${apiBase}/api/music/albums/${albumId}/tracks${sParam}`;
        const response = await axios.get(albumUrl);
        setAlbumData(response.data);
      } catch (error) {
        console.error("Error fetching album tracks:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchTracks();
  }, [albumId, serverId, apiBase]);

  const formatDuration = (duration: any) => {
    if (!duration) return "0:00";
    if (typeof duration === "string" && duration.includes(":")) return duration;
    const seconds = parseInt(duration, 10);
    if (isNaN(seconds)) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const showSnackbar = (message: string, severity: "success" | "warning" | "error") => {
    setSnackbarMessage(message);
    setSeverity(severity);
    setSnackbarOpen(true);
  };

  const handleRateTrack = async (trackId: number, rating: number) => {
    try {
      // Optimistically update state
      setAlbumData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          tracks: prev.tracks.map((t) =>
            t.track_id === trackId ? { ...t, user_rating: rating } : t
          ),
        };
      });

      await axios.post(
        `${apiBase}/api/music/tracks/${trackId}/rate`,
        { rating },
        { headers: { "x-admin-token": adminToken } }
      );
      if (rating > 0) {
        showSnackbar(`Rated ${rating} ${rating === 1 ? "Star" : "Stars"}!`, "success");
      } else {
        showSnackbar("Rating cleared.", "warning");
      }
    } catch (err: any) {
      console.error("Failed to update track rating:", err);
      const errMsg = err?.response?.data?.detail || "Failed to update rating.";
      showSnackbar(errMsg, "error");
    }
  };

  const addToQueue = async (trackId: number) => {
    try {
      const queueUrl = `${apiBase}/api/music/queue/${trackId}`;
      await axios.post(queueUrl, {
        server_id: serverId,
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

  const addAlbumToQueue = async () => {
    try {
      const queueUrl = `${apiBase}/api/music/albums/${albumId}/add-to-queue`;
      const response = await axios.post(
        queueUrl,
        {},
        {
          params: {
            server_id: serverId || undefined,
            username: getLocalUsername() || undefined,
          },
        }
      );
      showSnackbar(`Added ${response.data.added_count || 'all'} tracks from album to queue!`, "success");
    } catch (error: any) {
      console.error("Error adding album to queue:", error);
      showSnackbar("Failed to add album to queue.", "error");
    }
  };

  const hasMultipleDiscs = albumData?.tracks.some((t, idx, arr) => {
    if (idx === 0) return false;
    const prev = arr[idx - 1];
    return (
      (t.disc_number && prev.disc_number && t.disc_number !== prev.disc_number) ||
      (t.track_number === 1 && prev.track_number && prev.track_number > 1)
    );
  });

  let runningDisc = 1;

  return (
    <div className="track-list-page">
      <div className="track-list-container">
        <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap", alignItems: "center" }}>
          <button
            className="back-button"
            style={{ marginBottom: 0 }}
            onClick={() =>
              navigate(
                `/artists/${albumData?.artist_id || ""}/albums${
                  serverId ? `?server_id=${serverId}` : ""
                }`
              )
            }
          >
            <span className="material-symbols-outlined">library_music</span>
            Back to Albums
          </button>

          {(() => {
            if (!albumData) return null;
            const rawSources = albumData.sources || [];
            const uniqueSourcesMap = new Map<string, string>();
            rawSources.forEach((s) => {
              if (s.server_name) {
                uniqueSourcesMap.set(s.server_id || s.server_name, s.server_name);
              }
            });
            const uniqueNames = Array.from(uniqueSourcesMap.values());
            const namesStr = uniqueNames.join(" • ");

            if (uniqueNames.length > 1) {
              return (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "12px",
                    background: "rgba(191, 9, 94, 0.15)",
                    border: "1px solid rgba(191, 9, 94, 0.35)",
                    color: "#ff4d94",
                    padding: "6px 14px",
                    borderRadius: "14px",
                    fontWeight: 600,
                  }}
                  title={`Available on: ${namesStr}`}
                >
                  🌐 {uniqueNames.length} Connected Libraries ({namesStr})
                </span>
              );
            }
            const displayServer = uniqueNames[0] || albumData.server_name;
            if (displayServer) {
              return (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "12px",
                    background: "rgba(191, 9, 94, 0.15)",
                    border: "1px solid rgba(191, 9, 94, 0.35)",
                    color: "#ff4d94",
                    padding: "4px 12px",
                    borderRadius: "14px",
                    fontWeight: 600,
                  }}
                >
                  📍 {displayServer}
                </span>
              );
            }
            return null;
          })()}
        </div>
        {loading ? (
          <Typography variant="h6">Loading...</Typography>
        ) : albumData ? (
          <>
            <header className="page-header" style={{ marginBottom: "16px" }}>
              <Typography variant="h1" className="gradient-text">{albumData.album_title || "Unknown Album"}</Typography>
            </header>
              {(
                <FallbackImage
                  src={`${apiBase}/api/music/album-art/${albumId}${serverId ? `?server_id=${serverId}` : ""}`}
                  alt={albumData.album_title || "Album Art"}
                  type="album"
                  className="album-banner"
                />
              )}

              <div style={{ marginTop: "16px", marginBottom: "20px" }}>
                <Button
                  variant="contained"
                  className="add-album-btn"
                  onClick={addAlbumToQueue}
                  style={{
                    background: "linear-gradient(135deg, #0077b6 0%, #bf095e 100%)",
                    color: "#fff",
                    fontWeight: "bold",
                    borderRadius: "20px",
                    padding: "8px 20px",
                    textTransform: "none"
                  }}
                >
                  <span className="material-symbols-outlined" style={{ marginRight: "6px", fontSize: "20px" }}>playlist_add</span>
                  Add Entire Album to Queue
                </Button>
              </div>

              <div className="track-list">
                {albumData.tracks.map((track, idx, tracks) => {
                  let showDiscHeader = false;
                  if (idx === 0) {
                    if (hasMultipleDiscs) {
                      runningDisc = track.disc_number || 1;
                      showDiscHeader = true;
                    }
                  } else {
                    const prev = tracks[idx - 1];
                    if (track.disc_number && prev.disc_number && track.disc_number !== prev.disc_number) {
                      runningDisc = track.disc_number;
                      showDiscHeader = true;
                    } else if (track.track_number === 1 && prev.track_number && prev.track_number > 1) {
                      runningDisc = (runningDisc || 1) + 1;
                      showDiscHeader = true;
                    }
                  }

                  return (
                    <div key={track.track_id} style={{ display: "contents" }}>
                      {showDiscHeader && (
                        <div
                          className="disc-header"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            marginTop: idx === 0 ? "16px" : "32px",
                            marginBottom: "12px",
                            paddingBottom: "8px",
                            borderBottom: "1px solid rgba(255, 255, 255, 0.15)",
                            width: "100%",
                          }}
                        >
                          <span className="material-symbols-outlined" style={{ color: "#f5a623", fontSize: "20px" }}>album</span>
                          <Typography variant="h6" style={{ fontWeight: 800, color: "#f5a623", letterSpacing: "0.5px" }}>
                            Disc {runningDisc}
                          </Typography>
                        </div>
                      )}
                      <Card className="track-card">
                        <div className="track-card-left">
                          <Typography className="track-number" style={{ opacity: 0.6, fontWeight: "bold", minWidth: "28px", flexShrink: 0 }}>
                            {track.track_number ?? (idx + 1)}.
                          </Typography>
                          <Typography className="album-track-title">{track.title || `Track ${track.track_number ?? (idx + 1)}`}</Typography>
                        </div>
                        <div className="track-card-right">
                          <div className="star-rating-cell">
                            <StarRating
                              rating={track.user_rating || 0}
                              readOnly={!isAdmin || !(track.is_primary ?? true)}
                              onRate={(newRating) => handleRateTrack(track.track_id, newRating)}
                            />
                          </div>
                          <Typography className="track-duration">
                            {formatDuration(track.duration)}
                          </Typography>
                          <Button
                            variant="contained"
                            onClick={() => addToQueue(track.track_id)}
                          >
                            Add to Queue
                          </Button>
                        </div>
                      </Card>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <Typography variant="h6">No tracks found.</Typography>
          )}
      </div>
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
    </div>
  );
}

export default TrackList;
