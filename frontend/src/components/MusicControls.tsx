import { useEffect, useState, useRef } from 'react';
import { Box, Typography, LinearProgress, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';

const MusicControlsComponent = () => {
  const [currentTrack, setCurrentTrack] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0); // Track progress for the smooth bar
  const [elapsedTime, setElapsedTime] = useState<string>('00:00'); // To store the current elapsed time in mm:ss format
  const [duration, setDuration] = useState<string>('00:00'); // To store the song's total duration in mm:ss format
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

  const lastUpdateRef = useRef<number>(0); // Timestamp of the last update
  const lastElapsedTimeRef = useRef<number>(0); // Last known elapsed time
  const targetProgressRef = useRef<number>(0); // Target progress based on the latest WebSocket message

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
          console.log("Asked for now playing")
        };

        socketRef.current.onmessage = (event) => {
          console.log("Message received:", event.data);  // Debug message
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

              // Update progress based on the remaining percentage
              targetProgressRef.current = 100 - currentTrackData.remaining_percentage;

              // Smoothly update progress between updates
              smoothUpdateProgress(elapsed);
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
        clearInterval(pingIntervalRef.current!);
        clearTimeout(pongTimeoutRef.current!);
        console.log("WebSocket connection closed on component unmount.");
      }
    };
  }, []); // Runs only once when component mounts

  // Function to smooth the progress update based on elapsed time
  const smoothUpdateProgress = (elapsed: number) => {
    // If there's no last update, just set it
    if (lastUpdateRef.current === 0) {
      lastUpdateRef.current = Date.now();
      lastElapsedTimeRef.current = elapsed;
      return;
    }

    const timeDiff = (Date.now() - lastUpdateRef.current) / 1000; // Time difference in seconds
    const progressDiff = (elapsed - lastElapsedTimeRef.current) / (currentTrack?.total_time || 1);
    const newProgress = progress + progressDiff * timeDiff; // Update progress

    // Set the progress to the new smooth value
    setProgress(newProgress);

    // Update the last known values
    lastUpdateRef.current = Date.now();
    lastElapsedTimeRef.current = elapsed;
  };

  // Function to handle play/pause and trigger the play-queue API endpoint
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
            <Typography variant="body1" className="track-details">
              {currentTrack.title} by {currentTrack.artist}
            </Typography>
            <Typography variant="body2" className="track-details">
              {elapsedTime}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={progress} // Use the smooth progress value
              sx={{ marginBottom: 2 }}
            />
            <Typography variant="body2" className="track-details">
              Total Duration: {duration}
            </Typography>
            <IconButton onClick={handlePlayPause}>
              {isPlaying ? <PauseIcon /> : <PlayArrowIcon />}
            </IconButton>
          </>
        ) : (
          <Typography variant="body2" className="no-track">No track playing...</Typography>
        )}
      </Box>
    </Box>
  );
};

export default MusicControlsComponent;
