import { useEffect, useState, useRef } from 'react';
import { Box, Typography, LinearProgress, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import DevicesIcon from '@mui/icons-material/Devices';
import "./MusicControls.css";

const MusicControlsComponent = ({
  instanceName,
  isAdmin,
  onOpenSettings,
}: {
  instanceName?: string;
  isAdmin?: boolean;
  onOpenSettings?: () => void;
}) => {
  const [currentTrack, setCurrentTrack] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [elapsedTime, setElapsedTime] = useState<string>('00:00');
  const [duration, setDuration] = useState<string>('00:00');
  const [skipVotes, setSkipVotes] = useState<number>(0);
  const [skipTotal, setSkipTotal] = useState<number>(0);
  const [hasVoted, setHasVoted] = useState<boolean>(false);
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<any>(null);
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;
  const wsHost = isDev ? `${window.location.hostname}:8000` : window.location.host;
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
              setCurrentTrack(currentTrackData);
              if (currentTrackData) {
                setIsPlaying(currentTrackData.track_state === 'playing');

                const remainingTime = currentTrackData.remaining_time;
                const totalTime = currentTrackData.total_time;
                const elapsed = totalTime - remainingTime;

                const minutesElapsed = Math.floor(elapsed / 60);
                const secondsElapsed = Math.floor(elapsed % 60);
                setElapsedTime(`${minutesElapsed}:${secondsElapsed < 10 ? '0' : ''}${secondsElapsed}`);

                const totalTimeInSeconds = currentTrackData.total_time;
                const minutes = Math.floor(totalTimeInSeconds / 60);
                const seconds = Math.floor(totalTimeInSeconds % 60);
                setDuration(`${minutes}:${seconds < 10 ? '0' : ''}${seconds}`);

                setProgress(100 - currentTrackData.remaining_percentage);
              } else {
                setIsPlaying(false);
                setProgress(0);
                setElapsedTime('00:00');
                setDuration('00:00');
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
          setTimeout(connectWebSocket, 5000);
        };
      }
    };

    connectWebSocket();

    return () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
        if (timerRef.current) {
          clearInterval(timerRef.current);
        }
      }
    };
  }, []);

  const handlePlayStop = async () => {
    try {
      const endpoint = isPlaying ? "/api/music/stop-queue" : "/api/music/play-queue";
      const response = await fetch(`${apiBase}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        setIsPlaying(!isPlaying);
        if (isPlaying) {
          setProgress(0);
          setElapsedTime('0:00');
        }
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
      }
    } catch (error) {
      console.error('Error starting queue playback:', error);
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

  return (
    <Box className="player-inner-container">
      {/* Left Section: Cover & Metadata */}
      <Box className="player-left-section">
        {currentTrack ? (
          <>
            {currentTrack.item_id ? (
              <img
                src={`${apiBase}/api/music/track-art/${currentTrack.item_id}`}
                alt={currentTrack.title}
                className="player-album-art"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                  const sibling = e.currentTarget.nextElementSibling as HTMLElement;
                  if (sibling) sibling.style.display = "flex";
                }}
              />
            ) : null}
            <Box className="player-album-art-placeholder" style={{ display: currentTrack.item_id ? "none" : "flex" }}>🎵</Box>
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

      {/* Center Section: Playback buttons & Progress bar */}
      <Box className="player-center-section">
        <Box className="player-controls-buttons" style={{ display: "flex", alignItems: "center", gap: "16px" }}>
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
                  gap: "6px",
                  background: hasVoted ? "rgba(245, 166, 35, 0.18)" : "rgba(255,255,255,0.05)",
                  border: hasVoted ? "1px solid #f5a623" : "1px solid rgba(255,255,255,0.15)",
                  color: hasVoted ? "#f5a623" : "#fff",
                  borderRadius: "20px",
                  padding: "6px 14px",
                  fontSize: "12px",
                  fontWeight: "bold",
                  cursor: "pointer",
                  transition: "all 0.2s",
                  fontFamily: "var(--font-body)",
                  boxSizing: "border-box"
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
            </>
          ) : (
            <button onClick={handleStartQueue} className="player-start-queue-btn">
              Start Jukebox
            </button>
          )}
        </Box>
        
        {currentTrack && (
          <Box className="player-progress-row">
            <Typography className="player-time-text">{elapsedTime}</Typography>
            <LinearProgress
              variant="determinate"
              value={progress}
              className="player-progress-bar"
            />
            <Typography className="player-time-text">{duration}</Typography>
          </Box>
        )}
      </Box>

      {/* Right Section: Device indicators & Settings */}
      <Box className="player-right-section" style={{ justifyContent: "flex-end", alignItems: "center" }}>
        <Box className="player-device-group">
          <DevicesIcon className="player-utility-icon" />
          <Typography className="player-device-text">{instanceName || "TuneBox Jukebox"}</Typography>
        </Box>
        {isAdmin && onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="player-settings-btn"
            title="Settings"
            style={{
              background: "transparent",
              border: "none",
              color: "rgba(255, 255, 255, 0.4)",
              marginLeft: "12px",
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
              e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)";
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>settings</span>
          </button>
        )}
      </Box>
    </Box>
  );
};

export default MusicControlsComponent;
