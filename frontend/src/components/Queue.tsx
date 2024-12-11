import { useEffect, useState, useRef } from 'react';

const QueueComponent = () => {
  const [queue, setQueue] = useState<any[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const pongTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      if (!socketRef.current) {
        socketRef.current = new WebSocket("ws://localhost:8000/ws");

        socketRef.current.onopen = () => {
          console.log("WebSocket connected to QueueComponent");
          socketRef.current?.send(JSON.stringify({ message: "get_current_queue" }));
          console.log("Asked for queue")
        };

        socketRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.message === "Queue update") {
              console.log("Queue update received:", data.queue);
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

    // Initial connection
    connectWebSocket();

    // Cleanup on unmount
    return () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.close();
        clearInterval(pingIntervalRef.current!);
        clearTimeout(pongTimeoutRef.current!);
        console.log("WebSocket connection closed on component unmount.");
      }
    };
  }, []); // Empty dependency array ensures this runs only once

  return (
    <div className="queue-container">
      <h3>Queue</h3>
      <ul className="queue-list">
        {queue.map((track, index) => (
            <li key={index} className="queue-item">
              <strong>{track.title}</strong> by {track.artist}
            </li>
        ))}
      </ul>
    </div>
  );
};

export default QueueComponent;
