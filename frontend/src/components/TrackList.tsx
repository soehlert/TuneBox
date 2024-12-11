import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { AxiosError } from 'axios';
import { Button, Grid, Card, CardContent, Typography } from "@mui/material"; // MUI components for styling

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

  useEffect(() => {
    const fetchTracks = async () => {
      try {
        const response = await axios.get(`http://localhost:8000/api/music/albums/${albumId}/tracks`);
        setAlbumData(response.data);
      } catch (error) {
        console.error("Error fetching album tracks:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchTracks();
  }, [albumId]);

   const addToQueue = async (trackId: number) => {
    try {
      await axios.post(`http://localhost:8000/api/music/queue/${trackId}`);
      alert("Track added to queue!"); // Show success alert
    } catch (error) {
      // Type assertion to tell TypeScript that this error is an AxiosError
      const axiosError = error as AxiosError;

      // Now we can safely access error.response
      if (axiosError.response) {
        // Handle the error based on status code
        if (axiosError.response.status === 400) {
          alert("This song is already in the queue!"); // Show alert for song already in queue
        }
      } else {
        // If error.response doesn't exist, it's likely a network or other issue
        alert("An unexpected error occurred."); // Show generic error alert
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
              {albumData.thumb && (
                <img
                  src={albumData.thumb}
                  alt={albumData.album_title}
                  className="album-cover"
                />
              )}

              <Grid container spacing={3}>
                {albumData.tracks.map((track) => (
                  <Grid item xs={12} sm={6} md={4} key={track.track_id}>
                    <Card className="track-card">
                      <CardContent>
                        <Typography variant="h6">{track.title}</Typography>
                        <Typography variant="body2" color="textSecondary">
                          {track.duration}
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
    </div>
  );
}

export default TrackList;
