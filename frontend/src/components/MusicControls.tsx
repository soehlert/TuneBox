import { useEffect, useState, useRef } from 'react';
import { Box, Typography } from '@mui/material'; // Import MUI components

const MusicControlsComponent = () => {
  const [currentTrack, setCurrentTrack] = useState<any>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        socketRef.current = new WebSocket("ws://localhost:8000/ws");

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to MusicControlsComponent");
          socketRef.current?.send(JSON.stringify({ message: "get_current_track" }));
        };

        socketRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.message === "Current track update") {
              setCurrentTrack(data.current_track); // Update current track state
            } else if (data.message === "pong") {
              clearTimeout(pongTimeoutRef.current!); // Reset pong timeout
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

        // Heartbeat: Ping the server every 10 seconds
        pingIntervalRef.current = setInterval(() => {
          if (socketRef.current?.readyState === WebSocket.OPEN) {
            socketRef.current?.send(JSON.stringify({ message: "ping" }));

            pongTimeoutRef.current = setTimeout(() => {
              console.error("No pong received, attempting reconnect...");
              socketRef.current?.close();
            }, 5000); // Wait for 5 seconds for the pong
          }
        }, 10000);
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

  return (
    <Box className="music-controls">
      <Box className="track-info">
        <Typography variant="h6" className="track-title">Current Track</Typography>
        {currentTrack ? (
          <Typography variant="body1" className="track-details">
            {currentTrack.title} by {currentTrack.artist} - Remaining: {currentTrack.remaining_percentage.toFixed(2)}%
          </Typography>
        ) : (
          <Typography variant="body2" className="no-track">No track playing...</Typography>
        )}
      </Box>
    </Box>
  );
};

export default MusicControlsComponent;
