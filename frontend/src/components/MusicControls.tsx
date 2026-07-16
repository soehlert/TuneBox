import { useEffect, useState, useRef } from 'react';
import { Box, Typography, LinearProgress, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
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
        <Box className="player-controls-buttons">
          {currentTrack ? (
            <IconButton onClick={handlePlayStop} className="player-play-btn">
              {isPlaying ? <StopIcon style={{ fontSize: "28px" }} /> : <PlayArrowIcon style={{ fontSize: "28px" }} />}
            </IconButton>
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
