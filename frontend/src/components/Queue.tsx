import { useEffect, useState, useRef } from 'react';
import { Box, Typography } from '@mui/material';

const QueueComponent = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

  const isDev = window.location.port === "5173";
  const wsHost = isDev ? "localhost:8000" : window.location.host;
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        const webSocketUrl = `${wsProto}//${wsHost}/ws`;
        socketRef.current = new WebSocket(webSocketUrl);

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to QueueComponent");
          socketRef.current?.send(JSON.stringify({
            type: "queue_update",
            message: "get_current_queue"
          }));
          console.log("Asked for queue");
        };

        socketRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.message === "Queue update") {
              setQueue(data.queue);
            } else if (data.message === "pong") {
              clearTimeout(pongTimeoutRef.current!);
            }
          } catch (error) {
            console.error("Error parsing WebSocket message:", error);
          }
        };

        socketRef.current.onerror = (error) => {
          console.error("WebSocket error in QueueComponent:", error);
        };

        socketRef.current.onclose = () => {
          console.log("WebSocket closed in QueueComponent");
          setTimeout(connectWebSocket, 5000); // Attempt reconnection after 5 seconds
        };

        // Heartbeat
        pingIntervalRef.current = window.setInterval(() => {
          if (socketRef.current?.readyState === WebSocket.OPEN) {
            socketRef.current?.send(JSON.stringify({
              type: "heartbeat",
              message: "ping"
            }));
            pongTimeoutRef.current = window.setTimeout(() => {
              console.error("No pong received, attempting reconnect...");
              socketRef.current?.close();
            }, 5000); // Wait for 5 seconds for the pong
          }
        }, 10000);
      }
    };

    // Initial connection
    connectWebSocket();

    // Cleanup on unmount
    return () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
        clearInterval(pingIntervalRef.current as number);
        clearTimeout(pongTimeoutRef.current as number);
        console.log("WebSocket connection closed on component unmount.");
      }
    };
  }, [wsHost]);

  return (
    <Box className="queue-container">
      <Typography variant="h4" color="primary" sx={{ marginBottom: 2.5, fontWeight: 700, fontFamily: 'var(--font-title)' }}>
        Queue
      </Typography>
      <ul className="queue-list">
        {queue.map((track, index) => (
          <li key={index} className="queue-item">
            <Box sx={{ display: 'flex', alignItems: 'center', gap: '12px', width: '100%' }}>
              {track.album_art ? (
                <img
                  src={track.album_art}
                  alt={track.album}
                  className="queue-item-art"
                />
              ) : (
                <Box className="queue-item-art-placeholder">
                  🎵
                </Box>
              )}
              <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minWidth: 0 }}>
                <Typography
                  variant="h6"
                  component="strong"
                  color="primary"
                  className="queue-item-title"
                >
                  {track.title}
                </Typography>
                <Typography variant="body2" className="queue-item-artist">
                  {track.artist}
                </Typography>
              </Box>
            </Box>
          </li>
        ))}
      </ul>
    </Box>
  );
};

export default QueueComponent;
