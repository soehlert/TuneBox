import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Typography } from '@mui/material';
import "./Queue.css";

const QueueComponent = () => {
  const navigate = useNavigate();
  const [queue, setQueue] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'queue' | 'history'>('queue');
  const [vibes, setVibes] = useState<string[]>([]);
  const adminToken = localStorage.getItem("tunebox_admin_token") || "";

  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const touchDragRef = useRef<{ index: number; targetIndex: number | null } | null>(null);

  const fetchHistory = async () => {
    try {
      const response = await fetch(`${apiBase}/api/music/queue/history`);
      if (response.ok) {
        const data = await response.json();
        setHistory(data);
      }
    } catch (error) {
      console.error("Error fetching playback history:", error);
    }
  };

  const handleTrackClick = (track: any) => {
    if (track && track.album_id) {
      const sParam = track.server_id ? `?server_id=${track.server_id}` : "";
      navigate(`/albums/${track.album_id}/tracks${sParam}`);
    }
  };

  const handleRequeue = async (track: any) => {
    try {
      const sParam = track.server_id ? `?server_id=${track.server_id}` : "";
      const response = await fetch(`${apiBase}/api/music/queue/${track.item_id}${sParam}`, {
        method: "POST",
      });
      if (response.ok) {
        setActiveTab("queue");
      }
    } catch (error) {
      console.error("Error re-queueing track:", error);
    }
  };

  const handleDeleteTrack = async (itemId: number | string) => {
    try {
      const headers: Record<string, string> = {};
      if (adminToken) headers["X-Admin-Token"] = adminToken;
      const response = await fetch(`${apiBase}/api/music/queue/${itemId}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        throw new Error(`Failed to delete track: ${response.statusText}`);
      }
    } catch (error) {
      console.error("Error deleting track from queue:", error);
    }
  };

  const handleReorder = async (fromIndex: number, toIndex: number) => {
    if (fromIndex < 1 || toIndex < 1 || fromIndex === toIndex) return;
    try {
      const response = await fetch(`${apiBase}/api/music/queue/reorder`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Token": adminToken,
        },
        body: JSON.stringify({ from_index: fromIndex, to_index: toIndex }),
      });
      if (!response.ok) {
        throw new Error(`Failed to reorder queue: ${response.statusText}`);
      }
    } catch (error) {
      console.error("Error reordering queue:", error);
    }
  };

  const handleMoveTop = async (fromIndex: number) => {
    if (fromIndex <= 1) return;
    try {
      const response = await fetch(`${apiBase}/api/music/queue/move-top`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Token": adminToken,
        },
        body: JSON.stringify({ from_index: fromIndex }),
      });
      if (!response.ok) {
        throw new Error(`Failed to move track to top: ${response.statusText}`);
      }
    } catch (error) {
      console.error("Error moving track to top:", error);
    }
  };

  // Mouse Drag and Drop Handlers
  const handleDragStart = (e: React.DragEvent, index: number) => {
    if (index === 0 || !adminToken) return;
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", index.toString());
    const rowEl = (e.currentTarget as HTMLElement).closest(".queue-item");
    if (rowEl && e.dataTransfer.setDragImage) {
      e.dataTransfer.setDragImage(rowEl as HTMLElement, 20, 20);
    }
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    if (index === 0 || draggedIndex === null || !adminToken) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverIndex !== index) {
      setDragOverIndex(index);
    }
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    if (draggedIndex !== null && targetIndex > 0 && draggedIndex !== targetIndex) {
      handleReorder(draggedIndex, targetIndex);
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // Mobile Touch Drag Handlers
  const handleTouchStart = (_e: React.TouchEvent, index: number) => {
    if (index === 0 || !adminToken) return;
    touchDragRef.current = { index, targetIndex: null };
    setDraggedIndex(index);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchDragRef.current || !adminToken) return;
    const touch = e.touches[0];
    const targetElement = document.elementFromPoint(touch.clientX, touch.clientY);
    const itemElement = targetElement?.closest(".queue-item");
    if (itemElement) {
      const idxAttr = itemElement.getAttribute("data-index");
      if (idxAttr) {
        const targetIdx = parseInt(idxAttr, 10);
        if (targetIdx > 0) {
          touchDragRef.current.targetIndex = targetIdx;
          setDragOverIndex(targetIdx);
        }
      }
    }
  };

  const handleTouchEnd = () => {
    if (touchDragRef.current) {
      const { index, targetIndex } = touchDragRef.current;
      if (targetIndex !== null && targetIndex > 0 && index !== targetIndex) {
        handleReorder(index, targetIndex);
      }
    }
    touchDragRef.current = null;
    setDraggedIndex(null);
    setDragOverIndex(null);
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
              fetchHistory();
            } else if (
              data.message === "Track state update" ||
              data.message === "Now playing update" ||
              data.message === "Song finished" ||
              data.type === "queue_update"
            ) {
              fetchHistory();
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

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
          console.log("Tab became visible, reconnecting Queue WS...");
          connectWebSocket();
        } else {
          socketRef.current.send(JSON.stringify({ type: "queue_update", message: "get_current_queue" }));
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (pongTimeoutRef.current) clearTimeout(pongTimeoutRef.current);
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
      }
    };
  }, [wsHost]);

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(fetchHistory, 15000);
    return () => clearInterval(interval);
  }, [activeTab]);

  return (
    <Box className="queue-wrapper">
      <Box className="queue-tabs-container">
        <button
          className={`queue-tab-btn ${activeTab === 'queue' ? 'active' : ''}`}
          onClick={() => setActiveTab('queue')}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>queue_music</span>
          <span>Up Next ({queue.length})</span>
        </button>
        <button
          className={`queue-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('history');
            fetchHistory();
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>history</span>
          <span>History ({history.length})</span>
        </button>
      </Box>

      {activeTab === 'queue' && vibes && vibes.length > 0 && (
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

      {activeTab === 'queue' ? (
        <ul className="queue-list">
          {queue.map((track, index) => {
            const isActive = index === 0;
            const isDragging = draggedIndex === index;
            const isDragOver = dragOverIndex === index;

            return (
              <li
                key={index}
                data-index={index}
                draggable={!isActive && Boolean(adminToken)}
                onClick={() => handleTrackClick(track)}
                onDragStart={(e) => handleDragStart(e, index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDrop={(e) => handleDrop(e, index)}
                onDragEnd={handleDragEnd}
                className={`queue-item ${isActive ? 'active' : ''} ${isDragging ? 'dragging' : ''} ${isDragOver ? 'drag-over' : ''}`}
              >
                <Box className="queue-item-left">
                  {adminToken && !isActive && (
                    <span
                      className="material-symbols-outlined queue-drag-handle"
                      onMouseDown={(e) => e.stopPropagation()}
                      onTouchStart={(e) => {
                        e.stopPropagation();
                        handleTouchStart(e, index);
                      }}
                      onTouchMove={handleTouchMove}
                      onTouchEnd={handleTouchEnd}
                      title="Drag to reorder"
                    >
                      drag_indicator
                    </span>
                  )}
                  {track.item_id ? (
                    <img
                      src={`${apiBase}/api/music/album-art/${track.album_id || track.item_id}${track.server_id ? '?server_id=' + track.server_id : ''}`}
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
                  <Box className="queue-item-meta" style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, width: "100%" }}>
                    <Typography
                      className="queue-item-title"
                      title={track.title}
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}
                    >
                      {track.title}
                    </Typography>
                    <Typography
                      className="queue-item-artist"
                      title={track.artist}
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}
                    >
                      {track.artist}
                    </Typography>
                    {(() => {
                      const sName = track.server_name;
                      if (!sName) return null;
                      const sLower = sName.toLowerCase();
                      if (sLower === "plex-so" || sLower === "home server" || sLower === "primary server") return null;

                      return (
                        <Box style={{ display: "flex", marginTop: "2px" }}>
                          <span
                            style={{
                              fontSize: "9px",
                              background: isActive ? "rgba(0, 0, 0, 0.25)" : "rgba(245, 166, 35, 0.2)",
                              border: isActive ? "1px solid rgba(0, 0, 0, 0.4)" : "1px solid rgba(245, 166, 35, 0.4)",
                              color: isActive ? "#0e0e0f" : "#f5a623",
                              padding: "1px 6px",
                              borderRadius: "8px",
                              fontWeight: 700,
                              lineHeight: 1.2,
                              display: "inline-block",
                            }}
                            title={`Source Library: ${sName}`}
                          >
                            {sName}
                          </span>
                        </Box>
                      );
                    })()}
                  </Box>
                </Box>
                <Box style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  {isActive ? (
                    <span className="material-symbols-outlined queue-equalizer animate-pulse">equalizer</span>
                  ) : (
                    <Typography className="queue-item-time">{formatDuration(track.duration)}</Typography>
                  )}
                  {!isActive && (
                    <>
                      {index > 1 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleMoveTop(index);
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
                            e.currentTarget.style.color = "#f5a623";
                            e.currentTarget.style.backgroundColor = "rgba(245, 166, 35, 0.1)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)";
                            e.currentTarget.style.backgroundColor = "transparent";
                          }}
                          title="Move to Next (Up Next)"
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>vertical_align_top</span>
                        </button>
                      )}
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
                    </>
                  )}
                </Box>
              </li>
            );
          })}
        </ul>
      ) : (
        <ul className="queue-list">
          {history.length === 0 ? (
            <Box style={{ textAlign: "center", color: "rgba(255, 255, 255, 0.4)", padding: "24px 12px", fontSize: "0.9rem" }}>
              No playback history yet.
            </Box>
          ) : (
            history.map((track, index) => (
              <li key={index} className="queue-item" onClick={() => handleTrackClick(track)}>
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
                  <Box className="queue-item-meta" style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, width: "100%" }}>
                    <Typography
                      className="queue-item-title"
                      title={track.title}
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}
                    >
                      {track.title}
                    </Typography>
                    <Typography
                      className="queue-item-artist"
                      title={track.artist}
                      style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}
                    >
                      {track.artist}
                    </Typography>
                  </Box>
                </Box>
                <Box className="queue-item-right">
                  <button
                    className="requeue-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRequeue(track);
                    }}
                    title="Add back to queue"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>add</span>
                    <span>Re-queue</span>
                  </button>
                </Box>
              </li>
            ))
          )}
        </ul>
      )}
    </Box>
  );
};

export default QueueComponent;
