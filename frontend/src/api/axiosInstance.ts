import axios from "axios";

const axiosInstance = axios.create({
  baseURL: "http://0.0.0.0:8000/api/music", // Update with your backend URL
  timeout: 5000, // Optional: request timeout in ms
  headers: {
    "Content-Type": "application/json",
  },
});

export default axiosInstance;
