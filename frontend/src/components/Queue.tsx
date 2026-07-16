import { useEffect, useState, useRef } from 'react';
import { Box, Typography } from '@mui/material';
import "./Queue.css";

const QueueComponent = () => {
  const [queue, setQueue] = useState<any[]>([]);

  const formatDuration = (ms: number | string) => {
    const totalSeconds = Math.floor(Number(ms) / 1000);
    if (isNaN(totalSeconds) || totalSeconds <= 0) return "0:00";
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;
  };
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

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
          console.log("WebSocket connected to QueueComponent");
          socketRef.current?.send(JSON.stringify({
            type: "queue_update",
            message: "get_current_queue"
          }));
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
          setTimeout(connectWebSocket, 5000);
        };

        pingIntervalRef.current = window.setInterval(() => {
          if (socketRef.current?.readyState === WebSocket.OPEN) {
            socketRef.current?.send(JSON.stringify({
              type: "heartbeat",
              message: "ping"
            }));
            pongTimeoutRef.current = window.setTimeout(() => {
              console.error("No pong received, attempting reconnect...");
              socketRef.current?.close();
            }, 5000);
          }
        }, 10000);
      }
    };

    connectWebSocket();

    return () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
        clearInterval(pingIntervalRef.current as number);
        clearTimeout(pongTimeoutRef.current as number);
      }
    };
  }, [wsHost]);

  return (
    <Box className="queue-wrapper">
      <Box className="queue-header">
        <Typography className="queue-title">Up Next</Typography>
      </Box>
      <ul className="queue-list">
        {queue.map((track, index) => {
          const isActive = index === 0;
          return (
            <li key={index} className={`queue-item ${isActive ? 'active' : ''}`}>
              <Box className="queue-item-left">
                {track.item_id ? (
                  <img
                    src={`${apiBase}/api/music/track-art/${track.item_id}`}
                    alt={track.title}
                    className="queue-item-art"
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                      const sibling = e.currentTarget.nextElementSibling as HTMLElement;
                      if (sibling) sibling.style.display = "flex";
                    }}
                  />
                ) : null}
                <Box className="queue-item-art-placeholder" style={{ display: track.item_id ? "none" : "flex" }}>🎵</Box>
                <Box className="queue-item-meta">
                  <Typography className="queue-item-title">
                    {track.title}
                  </Typography>
                  <Typography className="queue-item-artist">
                    {track.artist}
                  </Typography>
                </Box>
              </Box>
              {isActive ? (
                <span className="material-symbols-outlined queue-equalizer animate-pulse">equalizer</span>
              ) : (
                <Typography className="queue-item-time">{formatDuration(track.duration)}</Typography>
              )}
            </li>
          );
        })}
      </ul>
    </Box>
  );
};

export default QueueComponent;
