import { useEffect, useState, useRef } from 'react';
import { Box, Typography, LinearProgress, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import "./MusicControls.css";

const MusicControlsComponent = () => {
  const [currentTrack, setCurrentTrack] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0); // Track progress for the smooth bar
  const [elapsedTime, setElapsedTime] = useState<string>('00:00'); // To store the current elapsed time in mm:ss format
  const [duration, setDuration] = useState<string>('00:00'); // To store the song's total duration in mm:ss format
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<any>(null); // Timer reference for interval updates
  const startTimeRef = useRef<number>(0); // Start time for progress calculation

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        socketRef.current = new WebSocket("ws://localhost:8000/ws");

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to MusicControlsComponent");
          socketRef.current?.send(JSON.stringify({
            type: "music_control",
            message: "get_current_track"
          }));
          console.log("Asked for now playing");
        };

        socketRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.message === "Current track update") {
              const currentTrackData = data.current_track;
              setCurrentTrack(currentTrackData);
              setIsPlaying(currentTrackData.track_state === 'playing');

              // Calculate elapsed time
              const remainingTime = currentTrackData.remaining_time;
              const totalTime = currentTrackData.total_time;
              const elapsed = totalTime - remainingTime;

              // Update elapsed time and song duration in mm:ss format
              const minutesElapsed = Math.floor(elapsed / 60);
              const secondsElapsed = Math.floor(elapsed % 60);
              setElapsedTime(`${minutesElapsed}:${secondsElapsed < 10 ? '0' : ''}${secondsElapsed}`);

              // Update the song duration in mm:ss format
              const totalTimeInSeconds = currentTrackData.total_time;
              const minutes = Math.floor(totalTimeInSeconds / 60);
              const seconds = Math.floor(totalTimeInSeconds % 60);
              setDuration(`${minutes}:${seconds < 10 ? '0' : ''}${seconds}`);

              // Initialize progress and start time
              startTimeRef.current = Date.now();
              setProgress(100 - currentTrackData.remaining_percentage);

              // Clear any previous interval
              if (timerRef.current) {
                clearInterval(timerRef.current);
              }

              // Update progress every second
              timerRef.current = setInterval(() => {
                updateProgress();
              }, 1000);
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
          setTimeout(connectWebSocket, 5000); // Reconnect after 5 seconds
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
        console.log("WebSocket connection closed on component unmount.");
      }
    };
  }, []); // Runs only once when component mounts

  const updateProgress = () => {
    if (currentTrack) {
      const elapsed = (Date.now() - startTimeRef.current) / 1000; // Calculate elapsed time in seconds
      const totalDuration = currentTrack.total_time;
      const remainingPercentage = 100 - currentTrack.remaining_percentage;

      // Update progress based on elapsed time and remaining percentage
      const newProgress = Math.min(remainingPercentage + (elapsed / totalDuration) * 100, 100);
      setProgress(newProgress);
    }
  };

  const handlePlayPause = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/music/play-queue', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        console.log('Playback started:', data.message);
        setIsPlaying(true);
      } else {
        console.error('Failed to start playback');
      }
    } catch (error) {
      console.error('Error starting playback:', error);
    }
  };

  return (
    <Box className="music-controls">
      <Box className="track-info">
        {currentTrack ? (
          <>
            <Typography variant="h4" className="track-title">
              {currentTrack.title}
            </Typography>
            <Typography variant="body1" className="track-artist">
              {currentTrack.artist}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={progress} // Use the smooth progress value
              sx={{ marginBottom: 2 }}
            />
            <Typography variant="body2" className="track-time">
              {elapsedTime} / {duration}
            </Typography>
            <Box className="playback-controls">
              <IconButton onClick={handlePlayPause}>
                {isPlaying ? <PauseIcon /> : <PlayArrowIcon />}
              </IconButton>
            </Box>
          </>
        ) : (
          <Typography variant="body2" className="no-track">No track playing...</Typography>
        )}
      </Box>
    </Box>
  );
};

export default MusicControlsComponent;
