import { useEffect, useState, useRef } from 'react';

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
              console.log("Received message from server in MusicControlsComponent:", data); // Added log here
              setCurrentTrack(data.current_track); // Update the current track state with the new data
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
          // Try to reconnect
          setTimeout(connectWebSocket, 5000); // Attempt reconnection after 5 seconds
        };

        // Heartbeat: Ping the server every 10 seconds
        pingIntervalRef.current = setInterval(() => {
          if (socketRef.current?.readyState === WebSocket.OPEN) {
            socketRef.current?.send(JSON.stringify({ message: "ping" }));

            // Set timeout to wait for pong
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
    <div>
      <h1>Current Track</h1>
      {currentTrack && (
        <div>
          <p>{currentTrack.title} by {currentTrack.artist}</p>
        </div>
      )}
    </div>
  );
};

export default MusicControlsComponent;
