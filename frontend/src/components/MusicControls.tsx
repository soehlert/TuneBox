import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Typography, LinearProgress, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import DevicesIcon from '@mui/icons-material/Devices';
import { FallbackImage } from './FallbackImage';
import TuneBoxDialog from './TuneBoxDialog';
import "./MusicControls.css";

const MusicControlsComponent = ({
  instanceName,
  onOpenMobileQueue,
  primaryServerName: _primaryServerName,
  onOpenServerModal: _onOpenServerModal,
}: {
  instanceName?: string;
  onOpenMobileQueue?: () => void;
  primaryServerName?: string;
  onOpenServerModal?: () => void;
}) => {
  const navigate = useNavigate();
  const [currentTrack, setCurrentTrack] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [elapsedTime, setElapsedTime] = useState<string>('00:00');
  const [duration, setDuration] = useState<string>('00:00');
  const [skipVotes, setSkipVotes] = useState<number>(0);
  const [skipTotal, setSkipTotal] = useState<number>(0);
  const [hasVoted, setHasVoted] = useState<boolean>(false);
  const [dialogConfig, setDialogConfig] = useState<{ open: boolean; title?: string; message: string }>({
    open: false,
    message: '',
  });
  const socketRef = useRef<WebSocket | null>(null);
  const transitionTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);
  const syncTimeRef = useRef<number>(0);
  const baseElapsedRef = useRef<number>(0);
  const totalTimeRef = useRef<number>(0);

  const clearTransitionTimer = () => {
    if (transitionTimeoutRef.current) {
      clearTimeout(transitionTimeoutRef.current);
      transitionTimeoutRef.current = null;
    }
  };

  useEffect(() => {
    if (!isPlaying || !currentTrack) return;

    const interval = setInterval(() => {
      if (totalTimeRef.current > 0) {
        const elapsedSinceSync = Math.max((performance.now() - syncTimeRef.current) / 1000, 0);
        const currentElapsed = Math.min(baseElapsedRef.current + elapsedSinceSync, totalTimeRef.current);
        const minutesElapsed = Math.floor(currentElapsed / 60);
        const secondsElapsed = Math.floor(currentElapsed % 60);
        setElapsedTime(`${minutesElapsed}:${secondsElapsed < 10 ? '0' : ''}${secondsElapsed}`);
        setProgress((currentElapsed / totalTimeRef.current) * 100);
      }
    }, 250);

    return () => clearInterval(interval);
  }, [isPlaying, currentTrack]);

  const apiBase = window.location.origin;
  const wsHost = window.location.host;
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        const webSocketUrl = `${wsProto}//${wsHost}/ws`;
        socketRef.current = new WebSocket(webSocketUrl);

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to MusicControlsComponent");
          socketRef.current?.send(JSON.stringify({
            type: "music_control",
            message: "get_current_track"
          }));
        };

        socketRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.message === "Current track update") {
              const currentTrackData = data.current_track;
              if (currentTrackData) {
                clearTransitionTimer();
                setCurrentTrack(currentTrackData);
                const stateLower = String(currentTrackData.track_state || '').toLowerCase();
                const playingNow = stateLower === 'playing';
                setIsPlaying(playingNow);

                const totalTime = currentTrackData.total_time || 0;
                const elapsed = currentTrackData.elapsed_time !== undefined
                  ? currentTrackData.elapsed_time
                  : Math.max(totalTime - currentTrackData.remaining_time, 0);

                syncTimeRef.current = performance.now();
                baseElapsedRef.current = elapsed;
                totalTimeRef.current = totalTime;

                const minutesElapsed = Math.floor(elapsed / 60);
                const secondsElapsed = Math.floor(elapsed % 60);
                setElapsedTime(`${minutesElapsed}:${secondsElapsed < 10 ? '0' : ''}${secondsElapsed}`);

                const minutes = Math.floor(totalTime / 60);
                const seconds = Math.floor(totalTime % 60);
                setDuration(`${minutes}:${seconds < 10 ? '0' : ''}${seconds}`);

                setProgress(totalTime > 0 ? (elapsed / totalTime) * 100 : 0);
              } else if (data.stopped || data.queue_empty) {
                // Instant stop (0ms delay) when queue ends or stopped explicitly
                clearTransitionTimer();
                setCurrentTrack(null);
                setIsPlaying(false);
                setProgress(0);
                setElapsedTime('00:00');
                setDuration('00:00');
              } else {
                // Track transition hold: keep previous track metadata & timer intact during 2s grace period to prevent flash
                if (!transitionTimeoutRef.current) {
                  transitionTimeoutRef.current = window.setTimeout(() => {
                    setCurrentTrack(null);
                    setIsPlaying(false);
                    setProgress(0);
                    setElapsedTime('00:00');
                    setDuration('00:00');
                    transitionTimeoutRef.current = null;
                  }, 2000);
                }
              }
            } else if (data.type === "skip_vote_update") {
              const status = data.status;
              setSkipVotes(status.votes);
              setSkipTotal(status.total);
              const cid = localStorage.getItem("tunebox_client_id") || "";
              setHasVoted(status.voted_ids.includes(cid));
            } else if (data.type === "skip_vote_reset") {
              setSkipVotes(0);
              setSkipTotal(data.status ? data.status.total : 0);
              setHasVoted(false);
            } else if (data.message === "pong") {
              if (pongTimeoutRef.current) {
                clearTimeout(pongTimeoutRef.current);
                pongTimeoutRef.current = null;
              }
            }
          } catch (error) {
            console.error("Error parsing WebSocket message:", error);
          }
        };

        socketRef.current.onerror = (error) => {
          console.error("WebSocket error in MusicControlsComponent:", error);
        };

        socketRef.current.onclose = () => {
          console.log("WebSocket closed in MusicControlsComponent");
          if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
          if (pongTimeoutRef.current) clearTimeout(pongTimeoutRef.current);
          socketRef.current = null;
          setTimeout(connectWebSocket, 3000);
        };

        pingIntervalRef.current = window.setInterval(() => {
          if (socketRef.current?.readyState === WebSocket.OPEN) {
            socketRef.current.send(JSON.stringify({ type: "heartbeat", message: "ping" }));
            pongTimeoutRef.current = window.setTimeout(() => {
              console.warn("MusicControls WS ping timeout, closing and reconnecting");
              socketRef.current?.close();
            }, 4000);
          }
        }, 10000);
      }
    };

    connectWebSocket();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
          console.log("Tab became visible, reconnecting MusicControls WS...");
          connectWebSocket();
        } else {
          socketRef.current.send(JSON.stringify({ type: "music_control", message: "get_current_track" }));
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearTransitionTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (pongTimeoutRef.current) clearTimeout(pongTimeoutRef.current);
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
      }
    };
  }, []);

  const handlePlayStop = async () => {
    try {
      const endpoint = "/api/music/pause";
      const response = await fetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        setIsPlaying(!isPlaying);
      }
    } catch (error) {
      console.error('Error toggling playback:', error);
    }
  };

  const handleStartQueue = async () => {
    try {
      const apiURL = `${apiBase}/api/music/play-queue`;
      const response = await fetch(apiURL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        setIsPlaying(true);
      } else {
        const errorData = await response.json();
        setDialogConfig({
          open: true,
          title: "Playback Player Warning",
          message: errorData.detail || "No Plex playback player selected. Please select an active player in Settings.",
        });
      }
    } catch (error) {
      console.error('Error starting queue playback:', error);
    }
  };

  const adminToken = localStorage.getItem("tunebox_admin_token") || "";

  const handleForceSkip = async () => {
    try {
      await fetch(`${apiBase}/api/music/skip`, {
        method: "POST",
        headers: {
          "X-Admin-Token": adminToken,
        },
      });
    } catch (error) {
      console.error("Error force skipping track:", error);
    }
  };

  const handleCastSkipVote = () => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const cid = localStorage.getItem("tunebox_client_id") || "";
      socketRef.current.send(JSON.stringify({
        type: "cast_skip_vote",
        client_id: cid,
        vote: !hasVoted
      }));
    }
  };

  const targetAlbumId = currentTrack ? currentTrack.album_id : "";
  const sParam = currentTrack && currentTrack.server_id ? `?server_id=${currentTrack.server_id}` : "";

  let artSrc = "";
  if (currentTrack) {
    if (currentTrack.album_art && currentTrack.album_art.startsWith("/api/music/")) {
      const sep = currentTrack.album_art.includes("?") ? "&" : "?";
      artSrc = `${apiBase}${currentTrack.album_art}${sParam ? sParam.replace("?", sep) : ""}`;
    } else if (currentTrack.album_art) {
      artSrc = currentTrack.album_art;
    } else if (currentTrack.album_id) {
      artSrc = `${apiBase}/api/music/album-art/${currentTrack.album_id}${sParam}`;
    } else if (currentTrack.item_id) {
      artSrc = `${apiBase}/api/music/track-art/${currentTrack.item_id}${sParam}`;
    }
  }

  return (
    <Box className="player-inner-container">
      {/* Top Row: Track info (Left), Play/Skip (Center), Queue/Settings (Right) */}
      <Box className="player-controls-row">
        {/* Left Section: Track Info */}
        <Box
          className="player-left-section"
          onClick={() => {
            if (currentTrack && targetAlbumId) {
              const trackId = currentTrack.track_id || currentTrack.item_id || currentTrack.server_track_id || currentTrack.rating_key;
              const serverQuery = currentTrack.server_id ? `server_id=${currentTrack.server_id}` : "";
              const trackQuery = trackId ? `highlight_track_id=${trackId}` : "";
              const combinedQuery = [trackQuery, serverQuery].filter(Boolean).join("&");
              const finalQuery = combinedQuery ? `?${combinedQuery}` : "";
              navigate(`/albums/${targetAlbumId}/tracks${finalQuery}`);
            }
          }}
          style={{
            cursor: currentTrack && targetAlbumId ? "pointer" : "default",
          }}
          title={currentTrack && targetAlbumId ? "View Album" : ""}
        >
          {currentTrack ? (
            <>
              <FallbackImage
                src={artSrc}
                alt={currentTrack.title}
                type="album"
                className="player-album-art"
              />
              <Box className="player-song-details">
                <Typography className="player-song-title">
                  {currentTrack.title}
                </Typography>
                <Typography className="player-song-artist">
                  {currentTrack.artist}
                </Typography>
              </Box>
            </>
          ) : (
            <Box className="player-song-details">
              <Typography className="player-song-title" style={{ color: 'rgba(255,255,255,0.4)' }}>
                No track playing
              </Typography>
            </Box>
          )}
        </Box>

        {/* Center Section: Playback buttons */}
        <Box className="player-center-section">
          <Box className="player-controls-buttons" style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            {currentTrack ? (
              <>
                <IconButton onClick={handlePlayStop} className="player-play-btn">
                  {isPlaying ? <PauseIcon style={{ fontSize: "28px" }} /> : <PlayArrowIcon style={{ fontSize: "28px" }} />}
                </IconButton>

                <button
                  onClick={handleCastSkipVote}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    background: hasVoted ? "rgba(245, 166, 35, 0.18)" : "rgba(255,255,255,0.05)",
                    border: hasVoted ? "1px solid #f5a623" : "1px solid rgba(255,255,255,0.15)",
                    color: hasVoted ? "#f5a623" : "#fff",
                    borderRadius: "20px",
                    padding: "6px 12px",
                    fontSize: "12px",
                    fontWeight: "bold",
                    cursor: "pointer",
                    transition: "all 0.2s",
                    fontFamily: "var(--font-body)",
                    boxSizing: "border-box",
                    whiteSpace: "nowrap"
                  }}
                  onMouseOver={(e) => {
                    if (!hasVoted) {
                      e.currentTarget.style.borderColor = "#f5a623";
                      e.currentTarget.style.color = "#f5a623";
                      e.currentTarget.style.backgroundColor = "rgba(245, 166, 35, 0.08)";
                    }
                  }}
                  onMouseOut={(e) => {
                    if (!hasVoted) {
                      e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)";
                      e.currentTarget.style.color = "#fff";
                      e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
                    }
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>skip_next</span>
                  <span>Skip ({skipVotes}/{skipTotal})</span>
                </button>

                {adminToken && (
                  <button
                    onClick={handleForceSkip}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      background: "rgba(51, 117, 173, 0.15)",
                      border: "1px solid #3376ad",
                      color: "#9bd0ff",
                      borderRadius: "20px",
                      padding: "6px 12px",
                      fontSize: "12px",
                      fontWeight: "bold",
                      cursor: "pointer",
                      transition: "all 0.2s",
                      fontFamily: "var(--font-body)",
                      whiteSpace: "nowrap",
                      flexShrink: 0
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.backgroundColor = "rgba(51, 117, 173, 0.28)";
                      e.currentTarget.style.borderColor = "#4895d9";
                      e.currentTarget.style.color = "#ffffff";
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.backgroundColor = "rgba(51, 117, 173, 0.15)";
                      e.currentTarget.style.borderColor = "#3376ad";
                      e.currentTarget.style.color = "#9bd0ff";
                    }}
                    title="Force Skip Track (Admin)"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>skip_next</span>
                    <span>Force Skip</span>
                  </button>
                )}
              </>
            ) : (
              <button onClick={handleStartQueue} className="player-start-queue-btn">
                Start TuneBox
              </button>
            )}
          </Box>
        </Box>

        {/* Right Section: Device indicators & Settings / Queue */}
        <Box className="player-right-section">
          <Box className="player-device-group">
            <DevicesIcon className="player-utility-icon" />
            <Typography className="player-device-text">{instanceName || "TuneBox"}</Typography>
          </Box>
          {onOpenMobileQueue && (
            <button
              onClick={onOpenMobileQueue}
              className="player-queue-btn"
              title="Queue"
              style={{
                background: "transparent",
                border: "none",
                color: "rgba(255, 255, 255, 0.6)",
                padding: "6px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                transition: "color 0.2s",
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.color = "var(--color-primary)";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.color = "rgba(255, 255, 255, 0.6)";
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "22px" }}>queue_music</span>
            </button>
          )}
        </Box>
      </Box>

      {/* Bottom Row: Full-width Progress Bar */}
      {currentTrack && (
        <Box className="player-progress-row">
          <Typography className="player-time-text">{elapsedTime}</Typography>
          <LinearProgress
            variant="determinate"
            value={progress}
            className="player-progress-bar"
            sx={{
              '& .MuiLinearProgress-bar': {
                transition: 'transform 0.25s linear',
              },
            }}
          />
          <Typography className="player-time-text">{duration}</Typography>
        </Box>
      )}

      <TuneBoxDialog
        open={dialogConfig.open}
        title={dialogConfig.title}
        message={dialogConfig.message}
        onConfirm={() => setDialogConfig((prev) => ({ ...prev, open: false }))}
      />
    </Box>
  );
};

export default MusicControlsComponent;
