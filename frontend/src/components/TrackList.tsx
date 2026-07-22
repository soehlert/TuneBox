import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios, { AxiosError } from "axios";
import { Button, Card, Typography, Snackbar, Alert } from "@mui/material";
import { FallbackImage } from "./FallbackImage";
import "./TrackList.css";

interface Track {
  track_id: number;
  title: string;
  duration: string;
}

interface AlbumData {
  album_title: string;
  thumb: string | null;
  tracks: Track[];
}

function TrackList() {
  const { albumId } = useParams();
  const navigate = useNavigate();
  const [albumData, setAlbumData] = useState<AlbumData | null>(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [severity, setSeverity] = useState<"success" | "warning" | "error">("success");
  const isDev = window.location.port === "5173";
  const apiBase = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;

  useEffect(() => {
    const fetchTracks = async () => {
      try {
        const albumUrl = `${apiBase}/api/music/albums/${albumId}/tracks`;
        const response = await axios.get(albumUrl);
        setAlbumData(response.data);
      } catch (error) {
        console.error("Error fetching album tracks:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchTracks();
    }, [albumId]);

    // Utility function to convert seconds to mm:ss format
    const formatDuration = (secondsStr: string) => {
      const seconds = parseInt(secondsStr, 10);
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
    };

    const showSnackbar = (message: string, severity: "success" | "warning" | "error") => {
      setSnackbarMessage(message);
      setSeverity(severity);
      setSnackbarOpen(true);
    };

   const addToQueue = async (trackId: number) => {
    try {
      const queueUrl = `${apiBase}/api/music/queue/${trackId}`;
      await axios.post(queueUrl);
      showSnackbar("Track added to queue!", "success");
    } catch (error) {
      // Type assertion to tell TypeScript that this error is an AxiosError
      const axiosError = error as AxiosError;

      // Now we can safely access error.response
      if (axiosError.response) {
        // Handle the error based on status code
        if (axiosError.response.status === 400) {
          showSnackbar("This song is already in the queue!", "warning"); // Show alert for song already in queue
        }
      } else {
        // If error.response doesn't exist, it's likely a network or other issue
        showSnackbar("An unexpected error occurred.", "error"); // Show generic error alert
      }
      console.error("Error adding track to queue:", error);
    }
  };

  return (
    <div className="track-list-page">
      <div className="track-list-container">
        <button className="back-button" onClick={() => navigate(-1)}>
          <span className="material-symbols-outlined">arrow_back</span>
          Back to Albums
        </button>
        {loading ? (
          <Typography variant="h6">Loading...</Typography>
        ) : albumData ? (
          <>
            <header className="page-header">
              <Typography variant="h1" className="gradient-text">{albumData.album_title}</Typography>
              <Typography className="page-subtitle">Queue songs to the Jukebox</Typography>
            </header>
              {(
                <FallbackImage
                  src={`${apiBase}/api/music/album-art/${albumId}`}
                  alt={albumData.album_title}
                  type="album"
                  className="album-banner"
                />
              )}

              <div className="track-list">
                {albumData.tracks.map((track) => (
                  <Card className="track-card" key={track.track_id}>
                    <div className="track-card-left">
                      <Typography className="album-track-title">{track.title}</Typography>
                    </div>
                    <div className="track-card-right">
                      <Typography className="track-duration">
                        {formatDuration(track.duration)}
                      </Typography>
                      <Button
                        variant="contained"
                        onClick={() => addToQueue(track.track_id)}
                      >
                        Add to Queue
                      </Button>
                    </div>
                  </Card>
                ))}
              </div>
            </>
          ) : (
            <Typography variant="h6">No tracks found.</Typography>
          )}
      </div>
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000} // Automatically hide after 3 seconds
        onClose={() => setSnackbarOpen(false)}
      >
        <Alert onClose={() => setSnackbarOpen(false)} severity={severity}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </div>
  );
}

export default TrackList;
