import { useEffect, useState, useRef } from 'react';
import { Box, Typography } from '@mui/material';
import "./Queue.css";

const QueueComponent = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const [vibes, setVibes] = useState<string[]>([]);
  const adminToken = localStorage.getItem("tunebox_admin_token") || "";

  const handleDeleteTrack = async (itemId: number | string) => {
    try {
      const response = await fetch(`${apiBase}/api/music/queue/${itemId}`, {
        method: "DELETE",
        headers: {
          "X-Admin-Token": adminToken,
        },
      });
      if (!response.ok) {
        throw new Error(`Failed to delete track: ${response.statusText}`);
      }
    } catch (error) {
      console.error("Error deleting track from queue:", error);
    }
  };

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
              setVibes(data.vibes || []);
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
      
      {vibes && vibes.length > 0 && (
        <Box 
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "6px",
            padding: "0 12px 12px 12px",
            marginTop: "-4px"
          }}
        >
          {vibes.map((vibe, idx) => (
            <span
              key={idx}
              style={{
                fontSize: "11px",
                background: "rgba(51, 117, 173, 0.15)",
                border: "1px solid #3376ad",
                color: "#9bd0ff",
                padding: "2px 8px",
                borderRadius: "12px",
                fontWeight: 600,
                textTransform: "capitalize",
                letterSpacing: "0.02em"
              }}
            >
              {vibe}
            </span>
          ))}
        </Box>
      )}

      <ul className="queue-list">
        {queue.map((track, index) => {
          const isActive = index === 0;
          return (
            <li key={index} className={`queue-item ${isActive ? 'active' : ''}`}>
              <Box className="queue-item-left">
                {track.item_id ? (
                  <img
                    src={`${apiBase}/api/music/track-art/${track.item_id}${track.server_id ? '?server_id=' + track.server_id : ''}`}
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
                  <Typography className="queue-item-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    {track.title}
                    {track.server_name && (
                      <span
                        style={{
                          fontSize: "9px",
                          background: "rgba(245, 166, 35, 0.2)",
                          border: "1px solid rgba(245, 166, 35, 0.4)",
                          color: "#f5a623",
                          padding: "1px 5px",
                          borderRadius: "8px",
                          fontWeight: 600,
                          lineHeight: 1.2,
                        }}
                      >
                        {track.server_name}
                      </span>
                    )}
                  </Typography>
                  <Typography className="queue-item-artist">
                    {track.artist}
                  </Typography>
                </Box>
              </Box>
              <Box style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {isActive ? (
                  <span className="material-symbols-outlined queue-equalizer animate-pulse">equalizer</span>
                ) : (
                  <Typography className="queue-item-time">{formatDuration(track.duration)}</Typography>
                )}
                {adminToken && !isActive && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteTrack(track.item_id);
                    }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "rgba(255, 255, 255, 0.4)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      padding: "4px",
                      borderRadius: "4px",
                      transition: "color 0.2s, background-color 0.2s",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = "#f44336";
                      e.currentTarget.style.backgroundColor = "rgba(244, 67, 54, 0.1)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)";
                      e.currentTarget.style.backgroundColor = "transparent";
                    }}
                    title="Remove from queue"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>delete</span>
                  </button>
                )}
              </Box>
            </li>
          );
        })}
      </ul>
    </Box>
  );
};

export default QueueComponent;
