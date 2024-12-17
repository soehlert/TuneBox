import { useEffect, useState, useRef } from 'react';
import { Box, Typography } from '@mui/material';


const QueueComponent = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

  const backendUrl = import.meta.env.VITE_TUNEBOX_URL;

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        const webSocketUrl = `ws://${backendUrl}:8000/ws`;
        socketRef.current = new WebSocket(webSocketUrl);

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to QueueComponent");
          socketRef.current?.send(JSON.stringify({
            type: "queue_update",
            message: "get_current_queue" }));
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
  }, [backendUrl]);

  return (
    <Box className="queue-container" sx={{ padding: 2 }}>
      <Typography variant="h4" color="primary" sx={{ marginBottom: 2 }}>
        Queue
      </Typography>
      <ul className="queue-list">
        {queue.map((track, index) => (
          <li key={index} className="queue-item">
            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
              <Typography
                variant="h6"
                component="strong"
                color="primary"
                sx={{ fontSize: '1.25rem', marginBottom: 1 }}
              >
                {track.title}
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ fontSize: '1rem' }}>
                {track.artist}
              </Typography>
            </Box>
          </li>
        ))}
      </ul>
    </Box>
  );
};

export default QueueComponent;
