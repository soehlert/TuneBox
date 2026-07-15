import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { AxiosError } from 'axios';
import { Button, Grid, Card, CardContent, Typography, Snackbar, Alert } from "@mui/material";
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
  const [albumData, setAlbumData] = useState<AlbumData | null>(null);
  const [loading, setLoading] = useState(true);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState("");
  const [severity, setSeverity] = useState<"success" | "warning" | "error">("success");
  const backendUrl = import.meta.env.VITE_TUNEBOX_URL;

  useEffect(() => {
    const fetchTracks = async () => {
      try {
        const albumUrl = `http://${backendUrl}:8000/api/music/albums/${albumId}/tracks`;
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
    const formatDuration = (seconds: string) => {
      const minutes = Math.floor(Number(seconds) / 60);
      const remainingSeconds = Number(seconds) % 60;
      return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    };

    const showSnackbar = (message: string, severity: "success" | "warning" | "error") => {
      setSnackbarMessage(message);
      setSeverity(severity);
      setSnackbarOpen(true);
    };

   const addToQueue = async (trackId: number) => {
    try {
      const queueUrl = `http://${backendUrl}:8000/api/music/queue/${trackId}`;
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
        <div className="track-list">
          {loading ? (
            <p>Loading...</p>
          ) : albumData ? (
            <>
              <h1>{albumData.album_title}</h1>
              {(
                <img
                  src={`http://${backendUrl}:8000/api/music/album-art/${albumId}`}
                  alt={albumData.album_title}
                  className="album-banner"
                />
              )}

              <Grid container spacing={2}>
                {albumData.tracks.map((track) => (
                  <Grid item xs={12} sm={6} md={4} key={track.track_id}>
                    <Card className="track-card">
                      <CardContent>
                        <Typography variant="h6" className="album-track-title">{track.title}</Typography>
                        <Typography variant="body2" className="track-duration">
                          {formatDuration(track.duration)}
                        </Typography>
                        <Button
                          variant="contained"
                          color="primary"
                          onClick={() => addToQueue(track.track_id)}
                        >
                          Add to Queue
                        </Button>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </>
          ) : (
            <p>No tracks found.</p>
          )}
        </div>
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
